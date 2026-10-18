// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication

/**
 * Quire's surface (docs/quire-design.md): the note and the tasks behind it. Every way of calling Quire ends in
 * [invoke]. A running task can be hidden behind the taskbar button and keeps running; Esc stops it; closing folds the
 * note back into where it came from (§3.3 rule 4, §5.2, §6.1).
 */
class QuireSurface(private val app: QuireApplication) : Task.Host, NoteWindow.Callbacks,
    android.content.ComponentCallbacks {
    override val context: Context
        get() = app
    override val handler = Handler(Looper.getMainLooper())
    override val agents = AgentDirectory(app, app.mainExecutor)
    val window = NoteWindow(app, this)

    /** Tasks that exist: the one on screen, hidden ones still running, and finished ones until closed. */
    val tasks = mutableListOf<Task>()

    private var night = app.resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK

    init {
        app.registerComponentCallbacks(this)
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        val n = newConfig.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK
        if (n == night) return
        night = n
        Log.i(TAG, "note: theme changed (night=${n == android.content.res.Configuration.UI_MODE_NIGHT_YES})")
        window.retheme()
    }

    @Deprecated("ComponentCallbacks API") override fun onLowMemory() {}

    private val ticker = object : Runnable {
        override fun run() {
            window.tick()
            if (window.task?.running == true) handler.postDelayed(this, 1000)
        }
    }

    /**
     * A call from the person. A key or the taskbar while the note is up hides a running task or closes an idle one
     * (§6.1: "Meta+Space again from anywhere"); with a hidden task running, the same key brings it back.
     */
    fun invoke(trigger: String, anchor: Anchor, intake: Intake?) {
        val shown = window.task
        if (shown != null) {
            Log.i(TAG, "note: invoked ($trigger) while task ${shown.id} is shown")
            if (shown.running) hide() else close()
            return
        }
        val hiddenTask = tasks.lastOrNull { it.hidden && (it.running || it.needsAnswer) }
        if (hiddenTask != null && trigger != TRIGGER_SHAKE) {
            reopen(hiddenTask)
            return
        }
        val t = Task(this, agents.default(), intake, anchor)
        tasks += t
        Log.i(TAG, "note: task ${t.id} for $trigger, agent=${t.agent?.endpoint?.id ?: "none"} " +
            "intake=${intake?.javaClass?.simpleName ?: "none"}")
        window.show(t, Task.Focus.FIELD)
    }

    /** Opens a task's note again at the taskbar anchor, where it was hidden (§3.2 Hidden). */
    fun reopen(t: Task) {
        t.hidden = false
        t.anchor = Anchor.Taskbar(null)
        Log.i(TAG, "note: reopened task ${t.id} running=${t.running} needsAnswer=${t.needsAnswer}")
        window.show(t, if (t.needsAnswer) Task.Focus.CONSENT else Task.Focus.FIELD)
        startTicker()
    }

    /** Starts a computer-control run in a new note (debuggable builds; see ControlRun). */
    fun startControl(prompt: String, appName: String, launch: String, plan: List<ControlRun.Tap>, anchor: Anchor) {
        window.task?.let { close() }
        val t = Task(this, agents.default(), Intake.Window(appName, null), anchor)
        tasks += t
        window.show(t, Task.Focus.KEEP)
        val run = ControlRun(app, handler, app.computerControl, t, appName, launch, plan, window)
        handler.post { run.start(prompt) }
    }

    // ---------------------------------------------------------------------------------------- NoteCard.Actions

    override fun send(text: String) {
        window.task?.send(text)
    }

    override fun escape() {
        val t = window.task ?: return
        if (window.closePicker()) return
        if (!t.escape()) close()
    }

    /** Hide (the header button, Meta+Space, a click elsewhere): a running task folds into the taskbar and runs on. */
    override fun hide() {
        val t = window.task ?: return
        if (!t.running && !t.needsAnswer) {
            close()
            return
        }
        t.hidden = true
        Log.i(TAG, "note: hid task ${t.id} running=${t.running} needsAnswer=${t.needsAnswer}")
        window.fold(intoTaskbar = true)
    }

    /** The header's ✕: hides a running task (it never stops one), closes the rest. */
    override fun close() {
        val t = window.task ?: return
        if (t.running || t.needsAnswer) {
            hide()
            return
        }
        tasks.remove(t)
        t.close()
        Log.i(TAG, "note: closed task ${t.id} phase=${t.phase}")
        window.fold(intoTaskbar = t.anchor is Anchor.Taskbar)
    }

    override fun outside() {
        hide()
    }

    override fun openPicker(anchor: View) {
        window.openPicker(anchor)
    }

    override fun pickAgent(entry: AgentEntry) {
        window.closePicker()
        window.task?.chooseAgent(entry)
    }

    override fun mirrorAction(action: MirrorPanel.Action) {
        window.task?.control?.action(action)
    }

    override fun addScreen() {}

    // ---------------------------------------------------------------------------------------- Task.Host

    override fun changed(task: Task, focus: Task.Focus) {
        if (window.task === task) {
            window.update(task, focus)
            startTicker()
        }
        if (task.hidden && !task.running && !task.needsAnswer) {
            Log.i(TAG, "note: hidden task ${task.id} finished phase=${task.phase}")
        }
    }

    override fun announce(task: Task, text: CharSequence, assertive: Boolean) {
        if (window.task !== task) return
        window.card?.announce(text, assertive)
    }

    private fun startTicker() {
        handler.removeCallbacks(ticker)
        if (window.task?.running == true) handler.postDelayed(ticker, 1000)
    }

    companion object {
        const val TRIGGER_SHAKE = "system_action"
    }
}
