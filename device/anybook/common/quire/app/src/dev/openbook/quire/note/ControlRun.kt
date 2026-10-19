// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.companion.virtual.computercontrol.ComputerControlSession
import android.content.Context
import android.graphics.PointF
import android.os.Handler
import android.os.SystemClock
import android.util.Log
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.R
import dev.openbook.quire.control.ComputerControl

/**
 * A computer-control run in the note (docs/quire-design.md §3.3 rule 5, §3.4): the platform's consent, the live
 * mirror with the agent's pointer and the 2× zoom, Pause, Take over and Stop, and honest copy for every way it ends.
 *
 * Until Q6 (ANAL-220) gives agents Quire's computer-control tools over MCP, the steps come from [plan]: a fixed list of
 * controls to tap, found through the session's accessibility tree, given by a debuggable build's lab command. Every
 * action is real (the platform session, its consent dialog, the taps, the mirror); only the choice of steps is scripted.
 * Like the broker will, the run holds its input while paused, so a dropped tap never shows as a completed step.
 */
class ControlRun(
    private val context: Context,
    private val handler: Handler,
    private val control: ComputerControl,
    private val task: Task,
    private val app: String,
    private val launch: String,
    private val plan: List<Tap>,
    private val window: NoteWindow,
    /** How long the pointer rests on a control before the tap; the checks slow it down to take their screenshots. */
    private val aimMs: Long = AIM_MS,
) : ComputerControl.Events {
    /** One step: tap the control labelled [text]; [title] is the step's line while it runs, [done] after. */
    data class Tap(val text: String, val title: String, val done: String)

    val session: ComputerControlSession?
        get() = control.session

    /**
     * True from the session's creation until the run ends: while its task is the one shown, the note is a system
     * overlay (NoteWindow.systemFor), so the mirror and Stop stay in view.
     */
    var sessionLive = false
        private set

    private var index = 0
    private var mirror: Mirror? = null
    private var waitingStep: Step? = null
    private var waitingResult: Block.Result? = null
    private var finished = false
    private var handedOver = false
    private var stopped = false
    private var stepStart = 0L
    private var resumedAt = 0L

    fun start(prompt: String) {
        task.beginControl(prompt, this)
        control.events = this
        val asking = Step("cc-ask", context.getString(R.string.q_cc_asking, app), "app", StepStatus.RUNNING)
        waitingStep = asking
        task.blocks += Block.Steps().apply { items += asking }
        task.controlPhase(Task.Phase.WORKING)
        // Quire asks from its waiting activity, so the platform finds a visible Quire window even when overlays are
        // hidden; if the platform asks the person, its dialog opens above that activity, which then shows this card
        // where the note was, and the note steps aside (onPending).
        ConsentWait.begin(context, ConsentWait.Card(context.getString(R.string.q_cc_waiting),
            context.getString(R.string.q_cc_waiting_sub, task.agent?.name ?: context.getString(R.string.app_name), app),
            window.cardOnScreen())) { ok ->
            if (finished || stopped) return@begin
            if (ok) {
                control.request(context, listOf(PACKAGE_OF[app] ?: launch.substringBefore('/')), null, ConsentWait)
            } else {
                onRefused(context.getString(R.string.q_cc_no_window))
            }
        }
    }

    override fun beforeDialog(proceed: () -> Unit) {
        // The note waits and says so; Quire's waiting activity shows a still of it, at its place, beneath the
        // platform's dialog (§3.3 rule 5). The dialog opens once the still is ready.
        waitingResult = Block.Result(Icons.SHIELD, Tone.WARN, context.getString(R.string.q_cc_waiting),
            context.getString(R.string.q_cc_waiting_sub, task.agent?.name ?: context.getString(R.string.app_name), app))
            .also { task.blocks += it }
        task.controlPhase(Task.Phase.WAITING)
        window.stillOfCard { still, at ->
            if (finished || stopped) return@stillOfCard
            ConsentWait.still(still, at)
            proceed()
        }
    }

    override fun onPending(dialogShown: Boolean) {
        if (!dialogShown) {
            waitingResult?.let { task.blocks.remove(it) }
            waitingResult = null
            task.controlPhase(Task.Phase.WORKING)
            return
        }
        // The platform's dialog is starting: the note steps aside, and the still beneath the dialog takes its place.
        window.platformDialog = true
    }

    override fun onCreated(session: ComputerControlSession) {
        window.platformDialog = false
        // While the session runs, the person must always see it and be able to stop it, even when the app it drives
        // hides overlays (Settings always does, on the session display too): while this task is shown, the note is a
        // system overlay until the run ends (NoteWindow.systemFor). Other tasks stay ordinary.
        sessionLive = true
        Log.i(TAG, "note: task ${task.id} owns a live session")
        window.sessionChanged()
        waitingResult?.let { task.blocks.remove(it) }
        waitingStep?.let {
            it.status = StepStatus.DONE
            it.title = context.getString(R.string.q_cc_allowed, app)
        }
        val m = Mirror(app)
        m.total = plan.size + 1
        mirror = m
        task.mirror = m
        m.steps.items += Step("cc-open", context.getString(R.string.q_cc_opening, app), "app", StepStatus.RUNNING)
        m.steps.changed()
        task.controlPhase(Task.Phase.MIRROR)
        control.launch(launch)
        handler.postDelayed({
            if (finished) return@postDelayed
            m.steps.items.last().apply {
                status = StepStatus.DONE
                title = context.getString(R.string.q_cc_opened, app)
            }
            m.steps.changed()
            task.controlPhase(Task.Phase.MIRROR)
            next()
        }, OPEN_SETTLE_MS)
    }

    override fun onCreationFailed(errorCode: Int, dialogShown: Boolean) {
        window.platformDialog = false
        waitingResult?.let { task.blocks.remove(it) }
        waitingStep?.status = StepStatus.FAILED
        val agent = task.agent?.name ?: context.getString(R.string.app_name)
        // §3.3 rule 5: PERMISSION_DENIED means "you didn't allow" only when the dialog was shown and refused.
        val (msg, sub) = when (errorCode) {
            ComputerControlSession.ERROR_PERMISSION_DENIED -> if (dialogShown) {
                context.getString(R.string.q_cc_denied, app) to null
            } else {
                context.getString(R.string.q_cc_refused, app, agent) to
                    context.getString(R.string.q_cc_refused_sub, ComputerControl.errorName(errorCode))
            }
            ComputerControlSession.ERROR_DEVICE_LOCKED -> context.getString(R.string.q_cc_locked) to null
            ComputerControlSession.ERROR_SESSION_LIMIT_REACHED -> context.getString(R.string.q_cc_limit) to null
            else -> context.getString(R.string.q_cc_refused, app, agent) to ComputerControl.errorName(errorCode)
        }
        end(stopped = false, msg, sub ?: context.getString(R.string.q_fx_none), Tone.WARN, Icons.SHIELD)
    }

    override fun onRefused(reason: String) {
        waitingStep?.status = StepStatus.FAILED
        end(stopped = false, context.getString(R.string.q_cc_refused, app, task.agent?.name ?: ""), reason, Tone.ERROR,
            Icons.ERROR)
    }

    override fun onBlocked(reason: Int, blockingPackage: String?) {
        val m = mirror ?: return
        if (reason == ComputerControlSession.BLOCK_REASON_CALLER_INITIATED) return
        // Secure content and authentication prompts block the session; they don't close it (§3.4).
        m.blockedReason = ComputerControl.blockReasonName(reason)
        m.status = context.getString(R.string.q_cc_protected, app)
        task.controlPhase(Task.Phase.MIRROR)
    }

    override fun onActive() {
        val m = mirror ?: return
        if (m.blockedReason != null) {
            m.blockedReason = null
            m.status = ""
            task.controlPhase(Task.Phase.MIRROR)
            if (!m.paused) handler.post { next() }
        }
    }

    override fun onClosed(reason: Int) {
        if (finished) return
        val m = mirror
        when {
            handedOver -> end(false, context.getString(R.string.q_cc_handed_over, app), null, Tone.SUCCESS,
                Icons.CHECK_CIRCLE)
            stopped -> end(true, stopMessage(), stopSub(), Tone.WARN, Icons.STOP_CIRCLE)
            else -> {
                val why = context.getString(when (reason) {
                    ComputerControlSession.CLOSE_REASON_SESSION_TIMED_OUT -> R.string.q_cc_closed_timeout
                    ComputerControlSession.CLOSE_REASON_USER_INITIATED -> R.string.q_cc_closed_user
                    ComputerControlSession.CLOSE_REASON_SESSION_EMPTY -> R.string.q_cc_closed_empty
                    else -> R.string.q_cc_closed_other
                }, app)
                if (m != null && index >= plan.size) {
                    end(false, context.getString(R.string.q_cc_done, app), why, Tone.SUCCESS, Icons.CHECK_CIRCLE)
                } else {
                    end(true, why, stopSub(), Tone.WARN, Icons.INFO)
                }
            }
        }
    }

    /** The next tap: find the control, zoom to it, move the pointer there, wait for the zoom to settle, tap. */
    private fun next() {
        val m = mirror ?: return
        if (finished || stopped || m.paused || m.blockedReason != null) return
        if (index >= plan.size) {
            complete()
            return
        }
        val tap = plan[index]
        val step = m.steps.items.firstOrNull { it.id == "cc-$index" } ?: Step("cc-$index", tap.title, "execute",
            StepStatus.RUNNING).also { m.steps.items += it }
        m.steps.changed()
        stepStart = SystemClock.elapsedRealtime()
        locate(tap, step, attempt = 0)
    }

    private fun locate(tap: Tap, step: Step, attempt: Int) {
        val m = mirror ?: return
        if (finished || stopped || m.paused) return
        val bounds = control.find(tap.text)
        if (bounds == null) {
            if (attempt < FIND_ATTEMPTS) {
                handler.postDelayed({ locate(tap, step, attempt + 1) }, FIND_INTERVAL_MS)
            } else {
                step.status = StepStatus.FAILED
                m.steps.changed()
                Log.w(TAG, "note: control step \"${tap.text}\" not found")
                // After a pause the platform can stop showing Quire the app's controls (docs/quire.md §8): say so,
                // rather than call the control missing.
                val msg = if (resumedAt > 0 && control.windowsUnavailable) {
                    context.getString(R.string.q_cc_blind_after_pause, app)
                } else {
                    context.getString(R.string.q_cc_not_found, tap.text, app)
                }
                end(false, msg, stopSub(), Tone.ERROR, Icons.ERROR)
            }
            return
        }
        m.target = bounds
        m.pointer = PointF(bounds.exactCenterX(), bounds.exactCenterY())
        task.controlPhase(Task.Phase.MIRROR)
        Log.i(TAG, "note: control aiming at \"${tap.text}\" bounds=$bounds")
        handler.postDelayed({ tapNow(tap, step) }, aimMs)
    }

    private fun tapNow(tap: Tap, step: Step) {
        val m = mirror ?: return
        if (finished || stopped) return
        // The broker holds the agent's input while paused or blocked; it resumes from this step (§3.4).
        if (m.paused || m.blockedReason != null) return
        val p = m.pointer ?: return
        control.tap(p.x.toInt(), p.y.toInt())
        m.tapAt = SystemClock.uptimeMillis()
        step.status = StepStatus.DONE
        step.title = tap.done
        m.steps.changed()
        index++
        task.controlPhase(Task.Phase.MIRROR)
        handler.postDelayed({
            // Between steps the view returns to the whole display (§3.4).
            m.target = null
            task.controlPhase(Task.Phase.MIRROR)
            handler.postDelayed({ next() }, BETWEEN_MS)
        }, AFTER_TAP_MS)
    }

    private fun complete() {
        val m = mirror ?: return
        m.target = null
        m.pointer = null
        Log.i(TAG, "note: control run complete")
        val secs = (SystemClock.elapsedRealtime() - task.startedAt) / 1000
        end(false, plan.lastOrNull()?.done?.let { "$it." } ?: context.getString(R.string.q_cc_done, app),
            context.getString(R.string.q_cc_done_sub, app, plan.size, secs), Tone.SUCCESS, Icons.CHECK_CIRCLE)
    }

    fun action(a: MirrorPanel.Action) {
        val m = mirror ?: return
        Log.i(TAG, "note: mirror action $a")
        when (a) {
            MirrorPanel.Action.PAUSE -> {
                control.pause()
                m.paused = true
                m.pausedAt = SystemClock.elapsedRealtime()
                m.target = null
                task.controlPhase(Task.Phase.MIRROR, Task.Focus.RESUME)
            }
            MirrorPanel.Action.RESUME -> {
                resumedAt = SystemClock.elapsedRealtime()
                control.resume()
                m.paused = false
                task.controlPhase(Task.Phase.MIRROR, Task.Focus.RESUME)
                handler.postDelayed({ next() }, BETWEEN_MS)
            }
            MirrorPanel.Action.TAKE_OVER -> {
                handedOver = true
                control.handOver()
            }
            MirrorPanel.Action.STOP -> task.stop()
        }
    }

    /** Stop (§3.4): close the session and the app. */
    fun stop() {
        if (finished) return
        stopped = true
        ConsentWait.close()
        window.platformDialog = false
        if (control.session != null) {
            control.close()
        } else {
            end(true, stopMessage(), stopSub(), Tone.WARN, Icons.STOP_CIRCLE)
        }
    }

    private fun stopMessage(): String {
        val steps = allSteps()
        val done = steps.count { it.status == StepStatus.DONE }
        return context.getString(R.string.q_stopped_after, done, steps.size)
    }

    private fun allSteps(): List<Step> =
        task.blocks.filterIsInstance<Block.Steps>().flatMap { it.items } + (mirror?.steps?.items ?: emptyList())

    /** §3.3 rule 6: an injected tap can have effects the broker can't see; say what to check. */
    private fun stopSub(): String {
        val running = allSteps().filter { it.status == StepStatus.RUNNING }
        return if (running.isEmpty()) context.getString(R.string.q_cc_stop_clean, app)
        else context.getString(R.string.q_cc_stop_partial, running.joinToString(", ") { it.title }, app)
    }

    private fun end(stopped: Boolean, msg: String, sub: String?, tone: Tone, icon: String) {
        if (finished && mirror == null && task.control == null) return
        finished = true
        control.events = null
        // A run that ends without a hand-over closes its session, so no app is left running out of sight.
        if (!handedOver && control.session != null) control.close()
        // The mirror's steps join the run's first steps block, so Done folds them into one chip.
        val steps = mirror?.steps?.items?.toList().orEmpty()
        task.mirror = null
        mirror = null
        if (steps.isNotEmpty()) {
            val first = task.blocks.filterIsInstance<Block.Steps>().firstOrNull()
            if (first != null) first.items += steps else task.blocks += Block.Steps().apply { items += steps }
            first?.changed()
        }
        window.platformDialog = false
        sessionLive = false
        window.sessionChanged()
        ConsentWait.close()
        Log.i(TAG, "note: control run ended stopped=$stopped: $msg")
        task.controlEnded(stopped, msg, sub, tone, icon)
    }

    companion object {
        private val PACKAGE_OF = mapOf("Settings" to "com.android.settings")
        private const val OPEN_SETTLE_MS = 1500L
        private const val AIM_MS = 700L
        private const val AFTER_TAP_MS = 600L
        private const val BETWEEN_MS = 500L
        private const val FIND_INTERVAL_MS = 300L
        private const val FIND_ATTEMPTS = 20
    }
}
