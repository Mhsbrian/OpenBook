// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import dev.openbook.quire.Quire
import dev.openbook.quire.Quire.TAG
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.json.JSONArray
import org.json.JSONObject

/**
 * Quire core's OS tools broker (Q6, docs/quire.md §4.2, §5.3). Agents in the Linux environment reach it through
 * `quired`'s MCP server (`_quire/tools/list`, `_quire/tools/call`); every call is decided here, whatever the agent
 * asks or claims: OBSERVE and ACT run at once as steps in the note, CONFIRM asks the person first and runs only on
 * Allow, and the never tier has no tool. A call belongs to the task whose session it came from, and only while that
 * task's turn runs.
 *
 * Every call is logged as "tools: ..." under [Quire.TAG] with its name, tier and outcome (and on debuggable builds its
 * step line), never its arguments or result: they can hold the person's data.
 */
class Broker(private val context: Context) {
    /** The task a call belongs to, as the broker sees it. Main thread. */
    interface Owner {
        /** The step for a call: the agent's own line for it if it sent one, retitled, else a new line. */
        fun toolStep(tool: Tool, title: String): Any

        fun toolRetitle(step: Any, title: String)

        /** Shows [ask] as a consent card for [step]; [answer] runs once on the main thread, true for Allow only. */
        fun toolAsk(step: Any, tool: Tool, ask: Ask, answer: (Boolean) -> Unit)

        fun toolChanged(step: Any, entries: List<ChangeLog.Entry>)

        fun toolDone(step: Any, ok: Boolean)

        fun toolPlatformDialog(up: Boolean)

        fun toolOnScreen(on: Boolean)

        /** False once the task stopped or its turn ended: a call still running then is cancelled. */
        val toolsLive: Boolean

        val agentControl: AgentControl
    }

    val tools: List<Tool> = TOOLS
    private val byName = tools.associateBy { it.name }
    private val main = Handler(Looper.getMainLooper())
    private val worker: ExecutorService = Executors.newCachedThreadPool { r -> Thread(r, "quire-tool") }


    /** `_quire/tools/call` for [owner]. Main thread; [answer] takes an MCP CallToolResult, once, from any thread. */
    fun call(owner: Owner, name: String, args: JSONObject, answer: (JSONObject) -> Unit) {
        val tool = byName[name]
        if (tool == null) {
            Log.i(TAG, "tools: $name unknown")
            answer(ToolResult.error("OpenBook has no tool \"$name\". Its tools are: ${byName.keys.joinToString(", ")}.")
                .json())
            return
        }
        if (!owner.toolsLive) {
            Log.i(TAG, "tools: $name refused, the task is not running")
            answer(ToolResult.error("The person's request has ended.").json())
            return
        }
        val title = try {
            tool.title(context, args)
        } catch (e: Exception) {
            tool.name
        }
        val step = owner.toolStep(tool, title)
        val t0 = SystemClock.elapsedRealtime()
        val note = CallNoteImpl(owner, step, tool)
        worker.execute {
            val (result, outcome) = run(tool, args, note)
            val ms = SystemClock.elapsedRealtime() - t0
            Log.i(TAG, "tools: ${tool.name} tier=${tool.tier} -> $outcome in $ms ms" +
                if (Quire.keepsEvidence) " \"${note.title}\"" else "")
            main.post { owner.toolDone(step, !result.error) }
            answer(result.json())
        }
    }

    private fun run(tool: Tool, args: JSONObject, note: CallNoteImpl): Pair<ToolResult, String> = try {
        val ask = tool.ask(context, args)
        if (tool.tier == Tier.CONFIRM && ask == null) throw IllegalStateException("${tool.name} has no question")
        if (ask != null && !note.ask(ask)) {
            if (note.cancelled) ToolResult.error(CANCELLED) to "cancelled"
            else ToolResult.error(DENIED) to "denied"
        } else if (note.cancelled) {
            ToolResult.error(CANCELLED) to "cancelled"
        } else {
            val r = tool.run(context, args, note)
            r to if (r.error) "error" else "ok"
        }
    } catch (e: ToolError) {
        ToolResult.error(e.message ?: "Failed.") to "refused"
    } catch (e: SecurityException) {
        Log.w(TAG, "tools: ${tool.name}: ${e.message}")
        ToolResult.error("OpenBook didn't allow this: ${e.message}") to "error"
    } catch (e: Exception) {
        Log.w(TAG, "tools: ${tool.name} failed", e)
        ToolResult.error("It failed: ${e.javaClass.simpleName}: ${e.message}") to "error"
    }

    /** One call's [CallNote]: hands each request to the note on the main thread. */
    private inner class CallNoteImpl(val owner: Owner, val step: Any, val tool: Tool) : CallNote {
        @Volatile var title: String = ""

        override fun retitle(title: String) {
            this.title = title
            main.post { owner.toolRetitle(step, title) }
        }

        fun ask(ask: Ask): Boolean = confirm(ask)

        override fun confirm(ask: Ask): Boolean {
            val f = CompletableFuture<Boolean>()
            main.post {
                if (!owner.toolsLive) f.complete(false) else owner.toolAsk(step, tool, ask) { f.complete(it) }
            }
            return try {
                f.get(ASK_TIMEOUT_MIN, TimeUnit.MINUTES)
            } catch (e: Exception) {
                false
            }
        }

        override fun platformDialog(up: Boolean) {
            main.post { owner.toolPlatformDialog(up) }
        }

        override fun onScreen(on: Boolean) {
            val f = CompletableFuture<Unit>()
            main.post {
                owner.toolOnScreen(on)
                f.complete(Unit)
            }
            runCatching { f.get(2, TimeUnit.SECONDS) }
        }

        override fun changed(entries: List<ChangeLog.Entry>) {
            main.post { owner.toolChanged(step, entries) }
        }

        override val cancelled: Boolean
            get() = !owner.toolsLive

        override val control: AgentControl
            get() = owner.agentControl
    }

    companion object {
        const val DENIED = "The person did not allow this, so nothing was done. Don't try it another way; tell the " +
            "person, and ask what they want instead."
        const val CANCELLED = "The person stopped the request, so nothing more was done."

        /** A question nobody answers is a no, after this long. */
        private const val ASK_TIMEOUT_MIN = 30L

        /** Every OS tool, in the order agents see them. */
        val TOOLS: List<Tool> by lazy {
            AppTools.all + ScreenTools.all + SettingsTools.all + FileTools.all + WindowTools.all + SystemTools.all +
                ControlTools.all
        }

        /** `_quire/tools/list`: the tools, and the instructions quired's MCP server gives the agent. */
        fun list(): JSONObject = JSONObject().put("tools", JSONArray(TOOLS.map { it.spec() }))
            .put("instructions", Skill.instructions())

        private val NAMES: List<String> by lazy { TOOLS.map { it.name }.sortedByDescending { it.length } }

        private fun norm(s: String) = s.lowercase().replace(Regex("[^a-z0-9]+"), "_").trim('_')

        /**
         * The name of Quire's tool that an agent's tool line or permission question names, or null. Agents title MCP
         * tools in their own ways: `openbook_open_url` (opencode), `mcp__openbook__open_url` (Claude Code),
         * `open_url (openbook MCP Server)` (Gemini CLI). [strict] requires the server's name too, unless the title is
         * exactly the tool's name.
         */
        fun toolNamed(title: String, strict: Boolean = false): String? {
            val n = norm(title)
            if (n.isEmpty()) return null
            for (name in NAMES) {
                if (n == name) return name
                val named = n.endsWith("_$name") || n.startsWith("${name}_")
                if (named && (!strict || "openbook" in n)) return name
            }
            return null
        }
    }
}
