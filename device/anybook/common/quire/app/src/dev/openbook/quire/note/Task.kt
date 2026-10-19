// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.Context
import android.graphics.Bitmap
import android.os.SystemClock
import android.util.Base64
import android.util.Log
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.R
import dev.openbook.quire.agents.Connectors
import dev.openbook.quire.acp.AcpAgent
import dev.openbook.quire.acp.AcpConnection
import dev.openbook.quire.tools.AgentControl
import dev.openbook.quire.tools.Ask
import dev.openbook.quire.tools.Broker
import dev.openbook.quire.tools.ChangeLog
import dev.openbook.quire.tools.LiveContext
import dev.openbook.quire.tools.SettingsTools
import dev.openbook.quire.tools.Tool
import dev.openbook.quire.tools.ToolResult
import dev.openbook.quire.ui.QButton
import java.io.ByteArrayOutputStream
import org.json.JSONArray
import org.json.JSONObject

/**
 * One piece of work in the note: what the person asked, what Quire took in, and everything the agent did, as blocks
 * (docs/quire-design.md §3.2). ACP session updates and permission requests arrive here and become blocks (§7);
 * Esc, Stop and Hide follow §3.3 rule 4 and §6.1. The note draws whatever task is visible; a hidden task keeps running.
 */
class Task(private val host: Host, var agent: AgentEntry?, var intake: Intake?, var anchor: Anchor) :
    AgentDirectory.SessionOwner, Broker.Owner {
    interface Host {
        val context: Context
        val agents: AgentDirectory
        val handler: android.os.Handler
        fun changed(task: Task, focus: Focus = Focus.KEEP)
        fun announce(task: Task, text: CharSequence, assertive: Boolean)

        /** The Linux environment's state as Quire last saw it, null before the first look (ANAL-225). */
        val linuxState: Connectors.State?
            get() = null

        /** The note's Set up: turns the Linux environment on, installs and starts it. */
        fun setUpLinux() {}

        /** Q6: Quire's OS tools broker, for this task's agent calls. */
        val broker: Broker?
            get() = null

        /** Q6: this task's computer control, as the tools drive it. */
        fun controlFor(task: Task): AgentControl? = null

        /** Q6: a platform consent dialog is up for this task's tool; the note steps aside meanwhile. */
        fun platformDialog(task: Task, up: Boolean) {}
    }

    enum class Phase { COMPOSE, WORKING, WAITING, MIRROR, DONE, STOPPED, ERROR, SIGNIN, NO_AGENT, OFFLINE }

    /** Where keyboard focus goes after a change (§6.2). */
    enum class Focus { KEEP, FIELD, CONSENT, RESULT, AUTH, RESUME }

    val id = nextId++
    private val context get() = host.context
    var phase = if (agent == null) Phase.NO_AGENT else Phase.COMPOSE
        private set
    val blocks = mutableListOf<Block>()

    /** The first prompt, shown under the intake chip; follow-ups appear in the body. */
    var prompt: String? = null
        private set
    var draft: String = ""

    /** Goes up when Quire itself sets [draft] (an offline prompt kept), so the field shows it even with focus. */
    var draftRevision = 0
        private set
    var running = false
        private set
    var hidden = false
    var stopping = false
        private set
    var mirror: Mirror? = null

    /** Set once an answer is long or holds code (§3.1 Wide); the note keeps the width for the task's life. */
    var wide = false

    /** A short line the footer shows for a few seconds instead of the status ("Saved as Quire answer.md"). */
    var notice: String? = null
    var noticeUntil = 0L
    var startedAt = 0L
        private set
    var endedAt = 0L
        private set
    var sessionId: String? = null
        private set

    /** The connection [sessionId] was opened on: the session's ID means something only there (SessionRoutes). */
    private var sessionAgent: AcpAgent? = null
    private var pending: Block.Consent? = null
    private var intakeSent = false
    private var stopTimeout: Runnable? = null

    /**
     * Set by a computer-control run: one that drives this task instead of an agent turn (a lab run), or one the task's
     * agent drives through Quire's tools within its turn ([ControlRun.agentMode], Q6).
     */
    var control: ControlRun? = null

    /** Q6: broker cards waiting behind the one shown, when an agent asks two things at once. */
    private val queuedCards = ArrayDeque<Block.Consent>()

    /** Q6: the settings the broker changed in this task, one Changes block for all of them. */
    private var changes: Block.Changes? = null
    private val changeEntries = ArrayList<ChangeLog.Entry>()

    /** Q6: the first turn opens with the skill's preface; every turn with the time and the windows on screen. */
    private var contextSent = false
    private var nextToolStep = 1

    init {
        if (agent == null) showAgents()
    }

    // ---------------------------------------------------------------------------------------- what the note shows

    val thinking: Boolean
        get() = running && phase == Phase.WORKING && !stopping

    val needsAnswer: Boolean
        get() = pending != null

    val composerVisible: Boolean
        get() = phase != Phase.NO_AGENT && phase != Phase.MIRROR && listening == null

    /** Hold to talk (§3.2 Listening): what is recognised so far, and the partial words still changing. */
    class Listening(var final: String, var partial: String)

    var listening: Listening? = null
        private set

    fun listen(final: String, partial: String) {
        if (running) return
        val l = listening ?: Listening("", "").also { listening = it }
        l.final = final
        l.partial = partial
        host.changed(this)
    }

    /** Release sends what was heard (§6.1 Hold to talk). */
    fun releaseListening() {
        val l = listening ?: return
        listening = null
        val text = (l.final + l.partial).trim()
        if (text.isEmpty()) host.changed(this, Focus.FIELD) else send(text)
    }

    /** Esc while holding cancels: nothing is sent, the field is as it was (§6.1). */
    fun cancelListening() {
        listening = null
        host.changed(this, Focus.FIELD)
    }

    val canSend: Boolean
        get() = !running && agent != null && phase != Phase.NO_AGENT

    val placeholder: String
        get() = when {
            prompt != null -> context.getString(R.string.q_field_followup)
            intake is Intake.Selection -> context.getString(R.string.q_field_selection)
            else -> context.getString(R.string.q_field)
        }

    /** Suggestions for the window Quire took in (§3.2 Composing); none once the person has asked something. */
    val suggestions: List<Pair<String, String>>
        get() {
            if (prompt != null || phase != Phase.COMPOSE) return emptyList()
            val s = { id: Int -> context.getString(id) }
            return when (val i = intake) {
                is Intake.Selection -> listOf(Icons.SUMMARIZE to s(R.string.q_suggest_summarise),
                    Icons.TRANSLATE to s(R.string.q_suggest_translate), Icons.HELP to s(R.string.q_suggest_explain))
                is Intake.Window -> if (i.name == SETTINGS_LABEL) {
                    listOf(Icons.DARK_MODE to s(R.string.q_suggest_dark), Icons.FORMAT_SIZE to s(R.string.q_suggest_text),
                        Icons.HELP to s(R.string.q_suggest_page))
                } else {
                    listOf(Icons.HELP to s(R.string.q_suggest_page), Icons.TUNE to s(R.string.q_suggest_setting))
                }
                else -> listOf(Icons.TUNE to s(R.string.q_suggest_setting), Icons.HELP to s(R.string.q_suggest_what))
            }
        }

    /** The footer's left side: what is happening, and for how long (§3.1). */
    fun footer(now: Long = SystemClock.elapsedRealtime()): String {
        val secs = ((if (running) now else endedAt) - startedAt).coerceAtLeast(0) / 1000
        if (notice != null && now < noticeUntil) return notice!!
        return when {
            listening != null -> context.getString(R.string.q_foot_listening)
            stopping -> context.getString(R.string.q_foot_stopping)
            phase == Phase.COMPOSE -> when (intake) {
                Intake.Secure -> context.getString(R.string.q_foot_secure)
                is Intake.Selection -> context.getString(R.string.q_foot_selection,
                    (intake as Intake.Selection).from ?: context.getString(R.string.q_an_app))
                else -> context.getString(R.string.q_foot_send)
            }
            phase == Phase.WAITING -> context.getString(R.string.q_foot_waiting)
            phase == Phase.WORKING && blocks.lastOrNull() is Block.Answer ->
                context.getString(R.string.q_foot_answering, secs)
            phase == Phase.WORKING -> context.getString(R.string.q_foot_working, secs)
            phase == Phase.DONE -> context.getString(R.string.q_foot_done_time, secs)
            phase == Phase.STOPPED || phase == Phase.ERROR -> context.getString(R.string.q_foot_stopped)
            phase == Phase.SIGNIN -> context.getString(R.string.q_foot_signin)
            phase == Phase.NO_AGENT -> context.getString(R.string.q_foot_noagent)
            phase == Phase.OFFLINE -> context.getString(R.string.q_foot_offline)
            else -> ""
        }
    }

    /** The footer's right side names what Esc does (§1: "how to stop" is always visible). */
    val escapeHint: String
        get() = context.getString(when {
            listening != null -> R.string.q_esc_cancel
            running -> R.string.q_esc_stop
            else -> R.string.q_esc_close
        })

    // ---------------------------------------------------------------------------------------- the person's actions

    /** The agent's answers in this task, as the markdown they arrived in, for Save as a file (§3.2 Long output). */
    fun answersMarkdown(): String =
        blocks.filterIsInstance<Block.Answer>().joinToString("\n\n") { it.text.toString().trim() }

    /** Shows [text] in the footer for a few seconds. */
    fun notify(text: String) {
        notice = text
        noticeUntil = SystemClock.elapsedRealtime() + NOTICE_MS
        host.changed(this)
        host.handler.postDelayed({ host.changed(this) }, NOTICE_MS + 50)
    }

    /** Redraws after a view-only change (a disclosure, an expanded chip). */
    fun refresh() = host.changed(this)

    /** The error card's Try again: the same prompt, again. */
    fun tryAgain() = retry()

    fun removeIntake() {
        if (intakeSent) return
        intake = null
        host.changed(this)
    }

    fun chooseAgent(entry: AgentEntry) {
        if (running) return
        if (entry !== agent && sessionId != null) releaseSession()
        agent = entry
        host.agents.use(entry)
        if (phase == Phase.NO_AGENT || phase == Phase.SIGNIN || phase == Phase.OFFLINE) {
            blocks.clear()
            phase = Phase.COMPOSE
        }
        host.changed(this, Focus.FIELD)
    }

    /** Sends [text] as the next turn (Enter, §6.1). */
    fun send(text: String) {
        val a = agent ?: return
        if (running || text.isBlank()) return
        if (prompt == null) prompt = text.trim() else blocks += Block.Prompt(text.trim())
        draft = ""
        if (phase in setOf(Phase.SIGNIN, Phase.OFFLINE, Phase.ERROR, Phase.STOPPED)) {
            blocks.removeAll { it is Block.Auth || it is Block.Error || it is Block.Result || it is Block.Buttons }
        }
        foldSteps(false)
        phase = Phase.WORKING
        running = true
        stopping = false
        startedAt = SystemClock.elapsedRealtime()
        blocks += Block.Thinking()
        host.changed(this, Focus.FIELD)
        host.announce(this, context.getString(R.string.q_a11y_thinking, a.name), false)
        host.agents.ensure(a) { r ->
            r.onFailure { unreachable(a, it) }
            r.onSuccess { agentReady(a, it, text.trim()) }
        }
    }

    private fun agentReady(entry: AgentEntry, agent: AcpAgent, text: String) {
        if (!running || stopping) return
        val sid = sessionId
        if (sid != null && sessionAgent === agent) {
            turn(agent, sid, text)
            return
        }
        if (sid != null) {
            // The session was opened on a connection that has since closed; this one has never heard of it.
            Log.i(TAG, "note: task $id session $sid was on a closed connection; opening a new one")
            releaseSession()
        }
        agent.newSession { r ->
            if (!running || stopping) return@newSession
            r.onSuccess {
                sessionId = it
                sessionAgent = agent
                host.agents.own(agent, it, this)
                Log.i(TAG, "note: task $id session $it with ${entry.endpoint.id}")
                turn(agent, it, text)
            }
            r.onFailure { failed(it) }
        }
    }

    private fun releaseSession() {
        val sid = sessionId
        val a = sessionAgent
        if (sid != null && a != null) host.agents.release(a, sid, this)
        sessionId = null
        sessionAgent = null
    }

    private fun turn(agent: AcpAgent, sid: String, text: String) {
        val content = JSONArray()
        // The live context (ANAL-220): who the agent is, the time, the language and the windows on screen. From Quire,
        // and labelled so; app names only, no window titles.
        try {
            content.put(text(LiveContext.block(context, first = !contextSent)))
        } catch (e: Exception) {
            Log.w(TAG, "note: task $id: no live context: ${e.message}")
        }
        contextSent = true
        if (!intakeSent) {
            intakeContent(agent).forEach { content.put(it) }
            intakeSent = true
        }
        content.put(JSONObject().put("type", "text").put("text", text))
        Log.i(TAG, "note: task $id prompt (${content.length()} blocks)")
        agent.prompt(sid, content) { r ->
            r.onSuccess { ended(it) }
            r.onFailure { failed(it) }
        }
    }

    /** What Quire took in, as ACP content (§2): its scope is the chip the person saw, its destination this agent. */
    private fun intakeContent(agent: AcpAgent): List<JSONObject> {
        val out = ArrayList<JSONObject>()
        when (val i = intake) {
            is Intake.Window -> {
                out += text(context.getString(R.string.q_ctx_window, i.name))
                if (i.shot != null && agent.info?.images == true) out += image(i.shot)
            }
            is Intake.Region -> {
                out += text(context.getString(R.string.q_ctx_region, i.name))
                if (agent.info?.images == true) out += image(i.shot)
            }
            is Intake.Selection -> out += text(context.getString(R.string.q_ctx_selection,
                i.from ?: context.getString(R.string.q_an_app), i.text))
            else -> {}
        }
        return out
    }

    private fun text(s: String) = JSONObject().put("type", "text").put("text", s)

    private fun image(b: Bitmap): JSONObject {
        val scale = minOf(1f, MAX_IMAGE / maxOf(b.width, b.height).toFloat())
        val sw = Bitmap.createScaledBitmap(b.copy(Bitmap.Config.ARGB_8888, false),
            (b.width * scale).toInt().coerceAtLeast(1), (b.height * scale).toInt().coerceAtLeast(1), true)
        val bytes = ByteArrayOutputStream().also { sw.compress(Bitmap.CompressFormat.JPEG, 85, it) }.toByteArray()
        return JSONObject().put("type", "image").put("mimeType", "image/jpeg")
            .put("data", Base64.encodeToString(bytes, Base64.NO_WRAP))
    }

    /** Esc (§3.3 rule 4): stops a running task, closes the rest. Returns false when the note should close. */
    fun escape(): Boolean {
        if (listening != null) {
            cancelListening()
            return true
        }
        if (!running) return false
        stop()
        return true
    }

    /** Stops the run: a pending request is answered cancelled, then `session/cancel` (§3.3 rule 4, §7 Stop). */
    fun stop() {
        if (!running || stopping) return
        stopping = true
        drainCards()
        pending?.let { answer(it, null) }
        val ctl = control
        if (ctl != null) {
            ctl.stop()
            // A lab run is the whole task; an agent's run is a step of its turn, which is cancelled too.
            if (!ctl.agentMode) return
        }
        val sid = sessionId
        // The cancel goes to the connection the session lives on, never to whichever agent the note shows.
        val a = sessionAgent
        markInterrupted()
        if (sid == null || a == null) {
            ended("cancelled")
            return
        }
        a.cancel(sid)
        Log.i(TAG, "note: task $id cancel sent to ${a.endpoint.id} for $sid")
        // If the agent never confirms, the note still ends the task, and says the stop wasn't confirmed.
        val timeout = Runnable { if (running) ended("cancelled", confirmed = false) }
        stopTimeout = timeout
        host.handler.postDelayed(timeout, STOP_TIMEOUT_MS)
        host.changed(this)
    }

    // ---------------------------------------------------------------------------------------- ACP → blocks (§7)

    override fun onUpdate(update: JSONObject) {
        if (!running) return
        when (update.optString("sessionUpdate")) {
            "agent_thought_chunk" -> {
                if (blocks.lastOrNull() !is Block.Thinking && blocks.lastOrNull() !is Block.Answer) {
                    blocks += Block.Thinking()
                    host.changed(this)
                }
            }
            "agent_message_chunk" -> {
                removeThinking()
                val content = update.optJSONObject("content") ?: return
                when (content.optString("type")) {
                    "text" -> currentAnswer().apply {
                        text.append(content.optString("text"))
                        changed()
                    }
                    "image" -> decodeImage(content)?.let { blocks += Block.Image(it, context.getString(R.string.q_image)) }
                }
                host.changed(this)
            }
            "tool_call" -> {
                removeThinking()
                endAnswer()
                upsertStep(update)
                host.changed(this)
            }
            "tool_call_update" -> {
                upsertStep(update)
                host.changed(this)
            }
            "plan" -> {
                val entries = update.optJSONArray("entries") ?: JSONArray()
                val plan = blocks.filterIsInstance<Block.Plan>().firstOrNull() ?: Block.Plan().also {
                    removeThinking()
                    blocks += it
                }
                plan.entries = (0 until entries.length()).mapNotNull { i ->
                    entries.optJSONObject(i)?.let {
                        PlanEntry(it.optString("content"), it.optString("priority").ifEmpty { null },
                            it.optString("status", "pending"))
                    }
                }
                plan.changed()
                host.changed(this)
            }
        }
    }

    private fun decodeImage(content: JSONObject): Bitmap? = runCatching {
        val bytes = Base64.decode(content.optString("data"), Base64.DEFAULT)
        android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }.getOrNull()

    private fun removeThinking() {
        blocks.removeAll { it is Block.Thinking }
    }

    private fun currentAnswer(): Block.Answer {
        val last = blocks.lastOrNull()
        if (last is Block.Answer && last.streaming) return last
        return Block.Answer().also { blocks += it }
    }

    private fun endAnswer() {
        (blocks.lastOrNull() as? Block.Answer)?.let {
            if (it.streaming) {
                it.streaming = false
                it.changed()
            }
        }
    }

    private fun currentSteps(): Block.Steps {
        val last = blocks.lastOrNull { it !is Block.Thinking }
        if (last is Block.Steps) return last
        return Block.Steps().also { blocks += it }
    }

    private fun findStep(id: String): Pair<Block.Steps, Step>? {
        for (b in blocks) if (b is Block.Steps) b.items.firstOrNull { it.id == id || it.agentId == id }
            ?.let { return b to it }
        return null
    }

    private fun upsertStep(u: JSONObject): Step? {
        val id = u.optString("toolCallId").ifEmpty { return null }
        var found = findStep(id)
        if (found == null) {
            // An agent may announce its call of Quire's tool after the broker has drawn the line for it: one line.
            val named = Broker.toolNamed(u.optString("title"))
            if (named != null) {
                found = blocks.filterIsInstance<Block.Steps>().flatMap { b -> b.items.map { b to it } }.lastOrNull { (_, s) ->
                    s.broker && s.agentId == null && s.toolName == named &&
                        SystemClock.elapsedRealtime() - s.startedAt < LATE_ANNOUNCE_MS
                }?.also { it.second.agentId = id }
            }
        }
        val block = found?.first ?: currentSteps()
        val step = found?.second ?: Step(id, "", "other", StepStatus.PENDING).also { block.items += it }
        if (!step.broker) {
            u.optString("title").takeIf { it.isNotEmpty() }?.let { step.title = it }
            u.optString("kind").takeIf { it.isNotEmpty() }?.let { step.kind = it }
            when (u.optString("status")) {
                "pending" -> step.status = StepStatus.PENDING
                "in_progress" -> step.status = StepStatus.RUNNING
                "completed" -> step.status = StepStatus.DONE
                "failed" -> step.status = StepStatus.FAILED
            }
        }
        u.optJSONObject("rawInput")?.let { step.rawInput = it }
        val content = u.optJSONArray("content")
        if (content != null) {
            for (i in 0 until content.length()) {
                val c = content.optJSONObject(i) ?: continue
                if (c.optString("type") == "diff") {
                    val old = if (c.isNull("oldText") || !c.has("oldText")) null else c.optString("oldText")
                    step.diff = Diff.lines(old, c.optString("newText"))
                    step.diffPath = c.optString("path")
                    step.newFile = old == null
                }
            }
        }
        if (step.title.isEmpty()) step.title = context.getString(R.string.q_step_untitled)
        block.changed()
        return step
    }

    override fun onPermission(request: JSONObject, answer: (JSONObject) -> Unit) {
        if (!running || stopping) {
            answer(AcpAgent.cancelled())
            return
        }
        val tool = request.optJSONObject("toolCall") ?: JSONObject()
        val opts = request.optJSONArray("options") ?: JSONArray()
        val options = (0 until opts.length()).mapNotNull { i ->
            opts.optJSONObject(i)?.let { Option(it.optString("optionId"), it.optString("name"), it.optString("kind")) }
        }.sortedBy { it.order }
        // Quire's own tools (Q6): the broker decides every call to them itself, and asks the person before anything
        // destructive, so the agent's own question about calling one is answered here instead of asking twice.
        val own = Broker.toolNamed(tool.optString("title"), strict = true)
        if (own != null) {
            val allow = options.firstOrNull { it.kind == "allow_always" } ?: options.firstOrNull { it.kind == "allow_once" }
            if (allow != null) {
                Log.i(TAG, "note: task $id permission for Quire's $own: ${allow.kind}, the broker decides the call")
                answer(AcpAgent.selected(allow.id))
                return
            }
        }
        val step = upsertStep(tool)
        if (options.isEmpty()) {
            answer(AcpAgent.cancelled())
            return
        }
        removeThinking()
        endAnswer()
        val kind = step?.kind ?: tool.optString("kind", "other")
        val raw = step?.rawInput ?: tool.optJSONObject("rawInput")
        val command = if (kind == "execute") {
            raw?.optString("command")?.ifEmpty { null } ?: raw?.optString("cmd")?.ifEmpty { null } ?: step?.title
        } else {
            null
        }
        val name = agent?.name ?: ""
        val why = when {
            step?.diff != null && step.newFile -> context.getString(R.string.q_why_new_file, fileName(step.diffPath))
            step?.diff != null -> {
                val (add, del) = Diff.counts(step.diff!!)
                context.getString(R.string.q_why_edit, fileName(step.diffPath), add, del)
            }
            command != null -> context.getString(R.string.q_why_command, name, agent?.where ?: "")
            else -> null
        }
        val card = Block.Consent(
            source = Block.Consent.Source.AGENT,
            title = step?.title ?: context.getString(R.string.q_consent_title),
            meta = kindLabel(kind),
            rows = emptyList(),
            command = command,
            diff = step?.diff,
            why = why,
            options = options,
            toolCallId = step?.id,
        ) { optionId -> answer(if (optionId == null) AcpAgent.cancelled() else AcpAgent.selected(optionId)) }
        pending = card
        blocks += card
        phase = Phase.WAITING
        Log.i(TAG, "note: task $id permission for ${step?.id} options=${options.map { it.id }} " +
            "from ${sessionAgent?.endpoint?.id} session $sessionId")
        host.changed(this, Focus.CONSENT)
        host.announce(this, context.getString(R.string.q_a11y_consent, name, card.title,
            options.joinToString(", ") { it.name }), true)
    }

    /** The person chose [optionId] on [card], or null when the request was cancelled (Esc, Stop). */
    fun answer(card: Block.Consent, optionId: String?) {
        if (card.answered) return
        card.answered = true
        card.answer(optionId)
        if (pending === card) pending = null
        blocks.remove(card)
        val chosen = card.options.firstOrNull { it.id == optionId }
        Log.i(TAG, "note: task $id answered ${optionId ?: "cancelled"}")
        card.toolCallId?.let { findStep(it) }?.let { (b, s) ->
            if (chosen != null && chosen.kind.startsWith("reject")) s.status = StepStatus.FAILED
            b.changed()
        }
        if (running && !stopping && phase == Phase.WAITING) {
            phase = if (mirror != null) Phase.MIRROR else Phase.WORKING
            if (mirror == null) blocks += Block.Thinking()
        }
        val next = queuedCards.removeFirstOrNull()
        if (next != null && running && !stopping) {
            removeThinking()
            raiseBrokerCard(next)
            return
        }
        host.changed(this, Focus.FIELD)
    }

    /** Answers every waiting broker card no. */
    private fun drainCards() {
        while (true) {
            val c = queuedCards.removeFirstOrNull() ?: break
            c.answered = true
            c.answer(null)
        }
    }

    /**
     * The broker's card for a settings change (§3.3 rule 2, §3.2 Consent, settings), with Quire's own options. Q6's
     * broker raises it while it holds the agent's MCP call; debuggable builds can raise it from the lab, so the card
     * and the change list after it can be checked before Q6. After Allow the rows become the change list (§3.2
     * Settings help); applying and undoing the changes is Q6's.
     */
    fun labBroker(title: String, meta: String, rows: List<Change>, why: String, prompt: String? = null,
        steps: List<Pair<String, String>> = emptyList()) {
        if (this.prompt == null && prompt != null) this.prompt = prompt
        if (steps.isNotEmpty()) {
            blocks += Block.Steps().apply {
                steps.forEachIndexed { i, (title, kind) -> items += Step("lab-$i", title, kind, StepStatus.DONE) }
            }
        }
        val options = listOf(
            Option("deny", context.getString(R.string.q_broker_deny), "reject_once"),
            Option("task", context.getString(R.string.q_broker_task), "allow_always"),
            Option("allow", context.getString(R.string.q_broker_allow), "allow_once"),
        )
        val wasRunning = running
        if (!running) {
            running = true
            startedAt = SystemClock.elapsedRealtime()
        }
        val card = Block.Consent(Block.Consent.Source.BROKER, title, meta, rows, null, null, why, options, null) { id ->
            if (id == "allow" || id == "task") {
                blocks += Block.Changes(context.getString(R.string.q_changed_title, rows.size),
                    context.getString(R.string.q_changed_meta), rows, undo = true)
            }
            if (!wasRunning) {
                running = false
                endedAt = SystemClock.elapsedRealtime()
                phase = if (id == null) Phase.STOPPED else Phase.DONE
                foldSteps(true)
            }
        }
        removeThinking()
        raiseBrokerCard(card)
    }

    /** A broker card for an OS tool (§3.3 rule 2): Quire's own options, enforced by Quire. Used by ControlRun and Q6. */
    fun raiseBrokerCard(card: Block.Consent) {
        pending = card
        blocks += card
        phase = Phase.WAITING
        host.changed(this, Focus.CONSENT)
    }

    // ---------------------------------------------------------------------------------------- how runs end

    private fun ended(stopReason: String, confirmed: Boolean = true) {
        if (!running) return
        stopTimeout?.let { host.handler.removeCallbacks(it) }
        stopTimeout = null
        running = false
        endedAt = SystemClock.elapsedRealtime()
        removeThinking()
        endAnswer()
        drainCards()
        // The agent's computer-control run ends with its turn, so no app is left running out of sight.
        control?.takeIf { it.agentMode }?.agentEnd(handOver = false)
        // A card still open when the turn ends: the agent moved on (§9). Release it.
        pending?.let { p ->
            p.answered = true
            p.answer(null)
            blocks.remove(p)
            pending = null
            blocks += Block.Result(Icons.INFO, Tone.WARN, context.getString(R.string.q_moved_on), null)
        }
        Log.i(TAG, "note: task $id ended stopReason=$stopReason confirmed=$confirmed")
        val name = agent?.name ?: ""
        when (stopReason) {
            "end_turn" -> {
                phase = Phase.DONE
                foldSteps(true)
                host.changed(this, Focus.RESULT)
                host.announce(this, context.getString(R.string.q_a11y_done), false)
            }
            "cancelled" -> {
                phase = Phase.STOPPED
                stopping = false
                val (msg, sub) = stopCopy(confirmed)
                blocks += Block.Result(Icons.STOP_CIRCLE, Tone.WARN, msg, sub)
                host.changed(this, Focus.RESULT)
                host.announce(this, "$msg $sub", true)
            }
            else -> {
                phase = Phase.ERROR
                val msg = context.getString(when (stopReason) {
                    "refusal" -> R.string.q_err_refusal
                    "max_tokens" -> R.string.q_err_max_tokens
                    "max_turn_requests" -> R.string.q_err_max_turns
                    else -> R.string.q_err_unknown
                }) + " " + effects()
                showError(context.getString(if (stopReason == "refusal") R.string.q_err_declined else
                    R.string.q_err_stopped, name), msg, "stopReason: $stopReason")
            }
        }
    }

    private fun failed(error: Throwable) {
        if (!running) return
        if (error is AcpConnection.RpcError && error.code == AcpConnection.AUTH_REQUIRED) {
            agent?.needsSignIn = true
            running = false
            endedAt = SystemClock.elapsedRealtime()
            removeThinking()
            showSignIn()
            return
        }
        if (stopping) {
            ended("cancelled")
            return
        }
        running = false
        endedAt = SystemClock.elapsedRealtime()
        removeThinking()
        endAnswer()
        drainCards()
        pending?.let { p ->
            p.answered = true
            p.answer(null)
            blocks.remove(p)
            pending = null
        }
        control?.takeIf { it.agentMode }?.agentEnd(handOver = false)
        markInterrupted()
        phase = Phase.ERROR
        val name = agent?.name ?: ""
        val (msg, details) = when (error) {
            is AcpConnection.RpcError -> context.getString(R.string.q_err_agent, error.message) to
                "ACP error ${error.code}: ${error.message}" + (error.data?.let { "\n$it" } ?: "")
            else -> context.getString(R.string.q_err_closed) to (error.cause?.message ?: error.message ?: "")
        }
        showError(context.getString(R.string.q_err_stopped, name), "$msg ${effects()}", details)
    }

    override fun onAgentClosed(error: Throwable?) {
        if (running) failed(java.io.IOException("connection closed", error))
    }

    private fun unreachable(entry: AgentEntry, error: Throwable) {
        if (!running) return
        running = false
        endedAt = SystemClock.elapsedRealtime()
        removeThinking()
        if (!entry.endpoint.local) {
            // A paired computer that can't be reached: offline, prompt kept (§3.2 Offline).
            phase = Phase.OFFLINE
            draft = prompt ?: draft
            draftRevision++
            if (blocks.isEmpty()) prompt = null
            blocks += Block.Result(Icons.CLOUD_OFF, Tone.WARN,
                context.getString(R.string.q_offline, entry.where.removePrefix("on ")),
                context.getString(R.string.q_offline_sub))
            val local = host.agents.entries.firstOrNull { it.connected && it.endpoint.local }
            blocks += Block.Buttons(listOfNotNull(
                Action(context.getString(R.string.q_retry), Icons.REFRESH, QButton.Style.TEXT) { retry() },
                local?.let {
                    Action(context.getString(R.string.q_use_local, it.name), null, QButton.Style.TONAL) {
                        chooseAgent(it)
                    }
                },
            ), end = true)
            host.changed(this, Focus.RESULT)
            return
        }
        phase = Phase.ERROR
        showError(context.getString(R.string.q_err_unreachable, entry.name),
            context.getString(R.string.q_err_unreachable_msg), "${entry.endpoint.address}: ${error.message}")
    }

    private fun retry() {
        val text = draft.ifBlank { prompt ?: return }
        blocks.clear()
        prompt = null
        phase = Phase.COMPOSE
        send(text)
    }

    private fun showError(title: String, message: String, details: String?) {
        val elapsed = ((endedAt - startedAt) / 1000).coerceAtLeast(0)
        blocks += Block.Error(title, context.getString(R.string.q_seconds, elapsed), message, details)
        host.changed(this, Focus.RESULT)
        host.announce(this, "$title. $message", true)
    }

    private fun showSignIn() {
        phase = Phase.SIGNIN
        val entry = agent ?: return
        val methods = entry.info?.authMethods.orEmpty()
        blocks += Block.Auth(context.getString(R.string.q_signin_title, entry.name),
            context.getString(R.string.q_signin_msg),
            methods.map { m ->
                Row(Icons.KEY, m.name, m.description) { authenticate(m.id) }
            })
        val other = host.agents.entries.firstOrNull { it.connected && it !== entry }
        blocks += Block.Buttons(listOfNotNull(
            other?.let { Action(context.getString(R.string.q_use_instead, it.name), null, QButton.Style.TEXT) {
                chooseAgent(it)
            } },
            methods.firstOrNull()?.let { m ->
                Action(context.getString(R.string.q_signin), null, QButton.Style.FILLED) { authenticate(m.id) }
            },
        ), end = true)
        host.changed(this, Focus.AUTH)
        host.announce(this, context.getString(R.string.q_signin_title, entry.name), true)
    }

    /** ACP `authenticate`: sign-in happens in the agent's own flow; Quire never sees the secret (§3.2). */
    private fun authenticate(methodId: String) {
        val a = agent?.agent ?: return
        a.authenticate(methodId) { r ->
            r.onSuccess {
                agent?.needsSignIn = false
                Log.i(TAG, "note: task $id authenticated with $methodId")
                retry()
            }
            r.onFailure { Log.w(TAG, "note: task $id authenticate failed: ${it.message}") }
        }
    }

    /** Quire found more agents: a note still asking for one lists them again. */
    fun agentsChanged() {
        if (phase != Phase.NO_AGENT || running) return
        blocks.clear()
        showAgents()
        host.changed(this)
    }

    /**
     * No agent is connected: list what Quire found (§3.2 No agent connected). Nothing is sent before a choice. With
     * none found because the Linux environment is off or not installed, the person's one step is offered: Set up.
     */
    private fun showAgents() {
        phase = Phase.NO_AGENT
        val found = host.agents.entries
        val linux = host.linuxState
        val setUp = found.isEmpty() &&
            (linux == Connectors.State.TERMINAL_OFF || linux == Connectors.State.NOT_INSTALLED)
        val message = when {
            found.isNotEmpty() -> R.string.q_noagent_msg
            linux == Connectors.State.INSTALLING -> R.string.q_noagent_installing
            linux == Connectors.State.STARTING -> R.string.q_noagent_starting
            setUp -> R.string.q_noagent_setup
            else -> R.string.q_noagent_none
        }
        blocks += Block.Agents(context.getString(R.string.q_noagent_title), context.getString(message),
            found.map { e ->
                Row(null, e.name, context.getString(if (e.state == AgentEntry.State.UNREACHABLE)
                    R.string.q_agent_unreachable else R.string.q_agent_found, e.where), e.initials, e.color)
            })
        val first = found.firstOrNull()
        blocks += Block.Buttons(listOfNotNull(
            first?.let {
                Action(context.getString(R.string.q_connect, it.name), null, QButton.Style.FILLED) {
                    host.agents.setConnected(it, true)
                    chooseAgent(it)
                }
            },
            if (setUp) Action(context.getString(R.string.q_setup_linux), null, QButton.Style.FILLED) {
                host.setUpLinux()
            } else null,
        ), end = true)
    }

    // ---------------------------------------------------------------------------------------- honest effects

    private fun markInterrupted() {
        for (b in blocks) if (b is Block.Steps) {
            var touched = false
            b.items.forEach {
                if (it.status == StepStatus.RUNNING) {
                    it.status = StepStatus.INTERRUPTED
                    touched = true
                }
            }
            if (touched) b.changed()
        }
    }

    private fun allSteps() = blocks.filterIsInstance<Block.Steps>().flatMap { it.items }

    /**
     * §3.3 rule 6: what is confirmed done, what was interrupted and may be partly applied. The agent's own file and
     * command actions are not undoable by Quire, and the copy says so; nothing claims a rollback.
     */
    private fun stopCopy(confirmed: Boolean): Pair<String, String> {
        val steps = allSteps()
        val done = steps.count { it.status == StepStatus.DONE }
        val msg = if (steps.isEmpty()) context.getString(R.string.q_stopped) else
            context.getString(R.string.q_stopped_after, done, steps.size)
        val sub = effects() + if (confirmed) "" else " " + context.getString(R.string.q_stop_unconfirmed)
        return msg to sub
    }

    /**
     * §3.3 rule 6: what is confirmed changed, what is confirmed unchanged, and what is unknown. Only an interrupted
     * step that changes something "may be partly applied"; an interrupted read was only interrupted. With no changing
     * step done or interrupted, nothing was changed.
     */
    private fun effects(): String {
        val steps = allSteps()
        val changedDone = steps.filter { it.changes && it.status == StepStatus.DONE }
        val interrupted = steps.filter { it.status == StepStatus.INTERRUPTED }
        val parts = ArrayList<String>()
        if (changedDone.isNotEmpty()) {
            parts += context.getString(R.string.q_fx_done, changedDone.joinToString(", ") { it.title })
        }
        interrupted.forEach {
            parts += context.getString(if (it.changes) R.string.q_fx_interrupted else R.string.q_fx_interrupted_read,
                it.title)
        }
        if (changedDone.isEmpty() && interrupted.none { it.changes }) {
            parts += context.getString(R.string.q_fx_none)
        } else {
            parts += context.getString(R.string.q_fx_own)
        }
        return parts.joinToString(" ")
    }

    private fun foldSteps(fold: Boolean) {
        for (b in blocks) if (b is Block.Steps && b.folded != fold) {
            b.folded = fold && b.items.isNotEmpty()
            b.changed()
        }
    }

    private fun kindLabel(kind: String): String = context.getString(when (kind) {
        "edit" -> R.string.q_kind_edit
        "delete" -> R.string.q_kind_delete
        "move" -> R.string.q_kind_move
        "execute" -> R.string.q_kind_execute
        "fetch" -> R.string.q_kind_fetch
        "read" -> R.string.q_kind_read
        "search" -> R.string.q_kind_search
        else -> R.string.q_kind_other
    })

    private fun fileName(path: String?) = path?.substringAfterLast('/')?.ifEmpty { null } ?: path ?: ""

    // ---------------------------------------------------------------------------------------- for ControlRun

    fun beginControl(text: String, run: ControlRun) {
        prompt = text
        control = run
        phase = Phase.WORKING
        running = true
        stopping = false
        startedAt = SystemClock.elapsedRealtime()
        host.changed(this, Focus.FIELD)
    }

    /** Q6: an agent's computer-control run joins this task's turn. */
    fun attachControl(run: ControlRun) {
        control = run
        removeThinking()
        endAnswer()
        host.changed(this, Focus.KEEP)
    }

    /**
     * Q6: the agent's run ended (the agent finished with the app, the person took over or stopped it, the session
     * closed). Its steps are already in the task; the turn goes on, so the note goes back to working.
     */
    fun controlDetached(stopped: Boolean, message: String, sub: String?, tone: Tone, icon: String) {
        mirror = null
        control = null
        if (tone != Tone.SUCCESS && !stopped) blocks += Block.Result(icon, tone, message, sub)
        if (running && !stopping && phase in setOf(Phase.MIRROR, Phase.WAITING, Phase.WORKING)) {
            phase = if (pending != null) Phase.WAITING else Phase.WORKING
            if (pending == null && blocks.lastOrNull() !is Block.Thinking) blocks += Block.Thinking()
        }
        host.changed(this, Focus.KEEP)
    }

    fun controlPhase(p: Phase, focus: Focus = Focus.KEEP) {
        phase = p
        host.changed(this, focus)
    }

    fun controlEnded(stopped: Boolean, message: String, sub: String?, tone: Tone, icon: String) {
        running = false
        stopping = false
        endedAt = SystemClock.elapsedRealtime()
        mirror = null
        control = null
        pending?.let { answer(it, null) }
        phase = if (stopped) Phase.STOPPED else if (tone == Tone.ERROR) Phase.ERROR else Phase.DONE
        markInterrupted()
        foldSteps(!stopped)
        blocks += Block.Result(icon, tone, message, sub)
        host.changed(this, Focus.RESULT)
        host.announce(this, listOfNotNull(message, sub).joinToString(" "), stopped || tone == Tone.ERROR)
    }

    // ---------------------------------------------------------------------------------------- Q6: the broker

    /** `_quire/tools/call` from this task's session (AgentDirectory). */
    override fun onToolCall(name: String, args: JSONObject, answer: (JSONObject) -> Unit) {
        val b = host.broker
        if (b == null) {
            answer(ToolResult.error("Quire's tools aren't available here.").json())
            return
        }
        b.call(this, name, args, answer)
    }

    override val toolsLive: Boolean
        get() = running && !stopping

    override val agentControl: AgentControl
        get() = host.controlFor(this) ?: throw IllegalStateException("no computer control")

    override fun toolStep(tool: Tool, title: String): Any {
        removeThinking()
        endAnswer()
        // The agent's own line for this call, if it already sent one: the newest open line that names the tool.
        val mine = blocks.filterIsInstance<Block.Steps>().flatMap { b -> b.items.map { b to it } }.lastOrNull { (_, s) ->
            !s.broker && (s.status == StepStatus.PENDING || s.status == StepStatus.RUNNING) &&
                Broker.toolNamed(s.title) == tool.name
        }
        val (block, step) = mine ?: currentSteps().let { b ->
            b to Step("q6-${nextToolStep++}", title, tool.kind, StepStatus.RUNNING).also { b.items += it }
        }
        if (mine != null) step.agentId = step.id
        step.broker = true
        step.toolName = tool.name
        step.startedAt = SystemClock.elapsedRealtime()
        step.title = title
        step.kind = tool.kind
        step.status = StepStatus.RUNNING
        block.changed()
        if (phase == Phase.WORKING && blocks.lastOrNull() !is Block.Thinking) blocks += Block.Thinking()
        host.changed(this)
        return step
    }

    override fun toolPlatformDialog(up: Boolean) = host.platformDialog(this, up)

    /** Q6: true while a screen read needs the note on screen (NoteWindow.systemFor). */
    var heldOnScreen = false
        private set

    override fun toolOnScreen(on: Boolean) {
        heldOnScreen = on
        host.changed(this)
    }

    override fun toolRetitle(step: Any, title: String) {
        val s = step as Step
        s.title = title
        findStep(s.id)?.first?.changed()
        host.changed(this)
    }

    override fun toolDone(step: Any, ok: Boolean) {
        val s = step as Step
        if (s.status == StepStatus.RUNNING || s.status == StepStatus.PENDING) {
            s.status = if (ok) StepStatus.DONE else StepStatus.FAILED
        }
        findStep(s.id)?.first?.changed()
        host.changed(this)
    }

    override fun toolAsk(step: Any, tool: Tool, ask: Ask, answer: (Boolean) -> Unit) {
        if (!running || stopping) {
            answer(false)
            return
        }
        val s = step as Step
        val options = listOf(
            Option("deny", ask.keep, "reject_once"),
            Option("allow", ask.verb, "allow_once"),
        )
        val card = Block.Consent(Block.Consent.Source.BROKER, ask.title, kindLabel(tool.kind), ask.rows, ask.detail,
            null, ask.why, options, s.id, destructive = true) { id -> answer(id == "allow") }
        Log.i(TAG, "note: task $id asks the person before ${tool.name}")
        if (pending != null) {
            queuedCards.addLast(card)
            return
        }
        removeThinking()
        endAnswer()
        raiseBrokerCard(card)
        host.announce(this, context.getString(R.string.q_a11y_consent, context.getString(R.string.app_name), card.title,
            options.joinToString(", ") { it.name }), true)
    }

    override fun toolChanged(step: Any, entries: List<ChangeLog.Entry>) {
        val block = changes ?: Block.Changes("", context.getString(R.string.q_changed_meta), emptyList(), undo = true) { i ->
            undoChange(i)
        }.also {
            changes = it
            blocks += it
        }
        for (e in entries) {
            changeEntries += e
            block.rows += Change(e.name, e.where, e.oldLabel, e.newLabel)
        }
        block.title = context.resources.getQuantityString(R.plurals.q_changed, block.rows.size, block.rows.size)
        block.changed()
        host.changed(this)
    }

    /** The Changes block's undo for row [i]: the setting goes back, and the row says so. */
    private fun undoChange(i: Int) {
        val block = changes ?: return
        val e = changeEntries.getOrNull(i) ?: return
        if (i in block.undone) return
        block.undone += i
        block.changed()
        host.changed(this)
        Thread({
            val r = runCatching { SettingsTools.undo(context, e) }
            host.handler.post {
                r.onSuccess {
                    block.rows[i] = Change(e.name, context.getString(R.string.q_undone_where, e.where), e.newLabel,
                        e.oldLabel)
                    Log.i(TAG, "note: task $id undid ${e.key}")
                }
                r.onFailure {
                    block.undone -= i
                    notify(context.getString(R.string.q_undo_failed, e.name))
                    Log.w(TAG, "note: task $id undo ${e.key} failed: ${it.message}")
                }
                block.changed()
                host.changed(this)
            }
        }, "quire-undo").start()
    }

    /** Debuggable builds: one tool call as an agent's would arrive, its result logged (LabReceiver TOOL). */
    fun labTool(name: String, args: JSONObject) {
        val b = host.broker ?: return
        val wasRunning = running
        if (!running) {
            running = true
            phase = Phase.WORKING
            startedAt = SystemClock.elapsedRealtime()
        }
        b.call(this, name, args) { result ->
            host.handler.post {
                val text = (0 until (result.optJSONArray("content")?.length() ?: 0)).joinToString(" ") { i ->
                    result.getJSONArray("content").getJSONObject(i).let { c ->
                        if (c.optString("type") == "image") "[image ${c.optString("data").length} b64]" else c.optString("text")
                    }
                }
                Log.i(TAG, "lab: tool $name -> error=${result.optBoolean("isError")} " + JSONObject.quote(text.take(3000)))
                if (!wasRunning && running && control == null) {
                    running = false
                    endedAt = SystemClock.elapsedRealtime()
                    removeThinking()
                    phase = Phase.DONE
                    foldSteps(true)
                    host.changed(this, Focus.RESULT)
                }
            }
        }
    }

    /** Debuggable builds: answers the consent card shown (LabReceiver CONSENT). */
    fun labConsent(option: String) {
        val card = pending ?: return
        answer(card, card.options.firstOrNull { it.id == option || it.kind.startsWith(option) }?.id)
    }

    fun close() {
        if (running) stop()
        releaseSession()
    }

    companion object {
        private var nextId = 1
        private const val MAX_IMAGE = 1280
        private const val STOP_TIMEOUT_MS = 8000L
        private const val SETTINGS_LABEL = "Settings"
        private const val NOTICE_MS = 4000L

        /** How long after the broker drew a tool's line the agent's own announcement of it is matched to it. */
        private const val LATE_ANNOUNCE_MS = 5000L
    }
}
