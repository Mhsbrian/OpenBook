// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.tools.AgentControl
import dev.openbook.quire.tools.Apps
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

/**
 * A task's computer control as an agent drives it (Q6, tools/ControlTools.kt): a [ControlRun] in agent mode, in the
 * task's own note. Each call blocks the tool's worker thread; the run acts on the main thread, in the mirror.
 */
class TaskControl(private val task: Task, private val surface: QuireSurface) : AgentControl {
    private val quire get() = surface.context as QuireApplication
    private val cc get() = quire.computerControl
    private val main = Handler(Looper.getMainLooper())

    /** Runs [block] on the main thread and waits for the value it completes, up to [timeoutMs]. */
    private fun <T> onMain(timeoutMs: Long = 10_000, fallback: T, block: (CompletableFuture<T>) -> Unit): T {
        val f = CompletableFuture<T>()
        main.post {
            try {
                block(f)
            } catch (e: Exception) {
                f.completeExceptionally(e)
            }
        }
        return try {
            f.get(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (e: java.util.concurrent.TimeoutException) {
            fallback
        } catch (e: java.util.concurrent.ExecutionException) {
            throw e.cause ?: e
        }
    }

    private fun run(): ControlRun? = task.control?.takeIf { it.agentMode && it.live }

    override val app: String?
        get() = onMain(2000, null) { it.complete(run()?.appName) }

    override fun open(app: Apps.App): String? = onMain(OPEN_MS, "The person didn't answer the request to operate " +
        "${app.label}.") { f ->
        val existing = task.control
        if (existing != null && !existing.agentMode) {
            f.complete("A demonstration is using computer control.")
            return@onMain
        }
        val start = {
            val r = ControlRun(surface.context, surface.handler, cc, task, app.label, app.pkg, emptyList(), surface.window,
                agentMode = true)
            r.ready = { why -> f.complete(why) }
            r.start("")
        }
        // The platform requires a visible Quire window, and the person must see the mirror: the task's note shows.
        if (surface.window.task !== task) surface.reopen(task)
        surface.window.whenVisible(start)
    }

    override fun read(): String {
        val deadline = SystemClock.elapsedRealtime() + READ_WAIT_MS
        while (true) {
            val text = onMain(5000, null as String?) { f ->
                val r = run()
                val answered = r?.answeredPrompt?.let {
                    r.answeredPrompt = null
                    "The person answered Android's prompt in $it.\n"
                } ?: ""
                f.complete(when {
                    r == null -> "${task.control?.endedBecause ?: "Computer control has ended."}"
                    r.prompt != null -> "Android is asking the person to confirm on their own screen (${r.prompt}): " +
                        "installing an app or granting a permission. Wait for them; your next step waits by itself. " +
                        "Don't repeat the action that asked.\n" + (cc.read() ?: "")
                    r.blocked -> "${r.appName} is showing a protected screen, which Quire can't read or use. The " +
                        "person can take over."
                    else -> cc.read()?.let { answered + it }
                })
            }
            if (text != null) return text
            if (SystemClock.elapsedRealtime() > deadline) {
                return "The app's controls can't be read right now (the system stopped showing them to Quire). " +
                    "Try control_screenshot, or hand the app over (control_end with hand_over)."
            }
            SystemClock.sleep(300)
        }
    }

    override fun locate(text: String?, node: Int?, x: Int?, y: Int?): AgentControl.Target? {
        val deadline = SystemClock.elapsedRealtime() + FIND_WAIT_MS
        while (true) {
            val t = onMain(5000, null as AgentControl.Target?) { f ->
                if (run() == null) {
                    f.complete(null)
                    return@onMain
                }
                f.complete(when {
                    node != null -> cc.nodes.firstOrNull { it.n == node }?.let {
                        AgentControl.Target(it.bounds.centerX(), it.bounds.centerY(), it.label, Rect(it.bounds))
                    }
                    text != null -> cc.find(text)?.let { AgentControl.Target(it.centerX(), it.centerY(), cc.foundLabel, it) }
                    x != null && y != null -> {
                        if (cc.nodes.isEmpty()) cc.read()
                        val hit = cc.nodes.filter { it.bounds.contains(x, y) }.minByOrNull { it.bounds.width() * it.bounds.height() }
                        AgentControl.Target(x, y, hit?.label ?: "the point $x,$y", hit?.bounds?.let { Rect(it) })
                    }
                    else -> null
                })
            }
            if (t != null || node != null || SystemClock.elapsedRealtime() > deadline) return t
            SystemClock.sleep(300)
        }
    }

    override val pageTitles: List<String>
        get() = onMain(2000, emptyList()) { it.complete(cc.titles) }

    /** Waits for a step, which may be held while the person has paused (up to [STEP_MS]). */
    private fun step(block: (ControlRun, (String?) -> Unit) -> Unit): String? =
        onMain(STEP_MS, "The person kept the run paused, so the step wasn't done.") { f ->
            val r = run()
            if (r == null) f.complete(task.control?.endedBecause ?: "Computer control has ended.")
            else block(r) { f.complete(it) }
        }

    override fun tap(t: AgentControl.Target, title: String): String? = step { r, done -> r.agentTap(t.x, t.y, t.bounds, title, done) }

    override fun type(text: String, replace: Boolean, submit: Boolean, title: String): String? =
        step { r, done -> r.agentAction(title, { cc.type(text, replace, submit) }, done) }

    override fun scroll(down: Boolean, title: String): String? = step { r, done ->
        r.agentAction(title, {
            val size = cc.session?.displaySize
            if (size == null) "No session." else {
                val x = size.width / 2
                val from = size.height * (if (down) 7 else 3) / 10
                val to = size.height * (if (down) 3 else 7) / 10
                cc.swipe(x, from, x, to)
                null
            }
        }, done)
    }

    override fun back(title: String): String? = step { r, done -> r.agentAction(title, { cc.back(); null }, done) }

    override fun screenshot(): Bitmap? = onMain(10_000, null as Bitmap?) { f ->
        if (run()?.blocked != false) f.complete(null) else cc.capture { f.complete(it) }
    }

    override fun end(handOver: Boolean): String {
        val name = onMain(2000, null as String?) { f ->
            val r = run()
            f.complete(r?.appName)
            r?.agentEnd(handOver)
        } ?: return "No app was being operated."
        val deadline = SystemClock.elapsedRealtime() + 5000
        while (SystemClock.elapsedRealtime() < deadline && onMain(2000, false) { it.complete(run() != null) }) {
            SystemClock.sleep(200)
        }
        return if (handOver) "$name is on the person's own screen now." else "Closed $name."
    }

    companion object {
        /** The platform's consent dialog waits for the person. */
        private const val OPEN_MS = 10 * 60_000L
        private const val STEP_MS = 30 * 60_000L
        private const val FIND_WAIT_MS = 4000L
        private const val READ_WAIT_MS = 4000L
    }
}
