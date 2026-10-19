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
import dev.openbook.quire.R
import dev.openbook.quire.acp.Endpoint
import dev.openbook.quire.agents.Connectors

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
    val tray = TrayWindow(app, this)

    /** Tasks that exist: the one on screen, hidden ones still running, and finished ones until closed. */
    val tasks = mutableListOf<Task>()

    private var night = app.resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK

    private var discovering = false
    private var settingUp = false

    override var linuxState: Connectors.State? = null
        private set

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
     * (§6.1: "Meta+Space again from anywhere"); with a hidden task running, the same key brings it back. A shake or
     * a selection while the note is up is a new question: the shown task is hidden (or closed when idle) first.
     */
    fun invoke(trigger: String, anchor: Anchor, intake: Intake?) {
        discover()
        val shown = window.task
        if (shown != null) {
            Log.i(TAG, "note: invoked ($trigger) while task ${shown.id} is shown")
            val toggle = trigger in REOPEN_TRIGGERS
            if (shown.running || shown.needsAnswer) {
                shown.hidden = true
                window.remove()
                Log.i(TAG, "note: hid task ${shown.id} running=${shown.running} needsAnswer=${shown.needsAnswer}")
            } else {
                tasks.remove(shown)
                shown.close()
                window.remove()
                Log.i(TAG, "note: closed task ${shown.id} phase=${shown.phase}")
            }
            if (toggle) return
        }
        // Meta+Space, the assist key and the taskbar button bring a hidden task back (§6.1); a shake or a selection
        // is a new question.
        val hiddenTask = tasks.lastOrNull { it.hidden && (it.running || it.needsAnswer) }
        if (hiddenTask != null && trigger in REOPEN_TRIGGERS) {
            reopen(hiddenTask)
            return
        }
        val t = Task(this, agents.default(), intake, anchor)
        tasks += t
        Log.i(TAG, "note: task ${t.id} for $trigger, agent=${t.agent?.endpoint?.id ?: "none"} " +
            "intake=${intake?.javaClass?.simpleName ?: "none"}")
        window.show(t, Task.Focus.FIELD)
    }

    /**
     * Asks quired in the Linux environment which agents it has (Q4, agents/Agents.kt) and lists the new ones. Off the
     * main thread; a note still asking for an agent shows them when the answer comes. A stopped Linux environment
     * (after every reboot) is started first, so the person never opens Terminal for it (ANAL-225); one that is off or
     * not installed is left for the note's Set up. The agents already listed stay either way.
     */
    private fun discover() {
        if (discovering || settingUp) return
        discovering = true
        app.agentWork.execute {
            var env = Connectors.LinuxEnvironment.status(app)
            if (env.state == Connectors.State.STOPPED || env.state == Connectors.State.ERROR ||
                env.state == Connectors.State.STARTING) {
                handler.post { linuxChanged(Connectors.State.STARTING) }
                env = Connectors.LinuxEnvironment.ensureRunning(app, Endpoint.START_TIMEOUT_MS)
            }
            val found = if (env.state == Connectors.State.READY) linuxAgents() else null
            handler.post {
                discovering = false
                linuxChanged(env.state)
                if (found != null && agents.foundInLinux(found)) window.task?.agentsChanged()
            }
        }
    }

    /** The note's Set up: turns the Linux environment on, installs and starts it, then lists its agents. */
    override fun setUpLinux() {
        if (settingUp) return
        settingUp = true
        linuxChanged(Connectors.State.INSTALLING)
        app.agentWork.execute {
            var env = Connectors.LinuxEnvironment.setUp(app)
            if (env.state != Connectors.State.READY) {
                env = Connectors.LinuxEnvironment.ensureRunning(app, SET_UP_TIMEOUT_MS)
            }
            val found = if (env.state == Connectors.State.READY) linuxAgents() else null
            Log.i(TAG, "note: Linux environment set up: ${env.state}, ${found?.size ?: 0} agent(s)")
            handler.post {
                settingUp = false
                linuxChanged(env.state)
                if (found != null) agents.foundInLinux(found)
                window.task?.agentsChanged()
            }
        }
    }

    private fun linuxAgents(): List<Endpoint>? = try {
        app.agents.agents().filter { it.supported }.map {
            Endpoint(id = Endpoint.LINUX + it.id, name = it.name, where = app.getString(R.string.q_where_linux),
                address = Endpoint.LINUX + it.id, cwd = "", local = true)
        }
    } catch (e: Exception) {
        Log.i(TAG, "note: no agents from the Linux environment: ${e.javaClass.simpleName}")
        null
    }

    private fun linuxChanged(state: Connectors.State) {
        if (state == linuxState) return
        linuxState = state
        window.task?.agentsChanged()
    }

    /** The tray of tasks above the taskbar (§3.5). */
    fun showTray() {
        if (window.task != null) hide()
        tray.show()
    }

    /** Opens a task's note again at the taskbar anchor, where it was hidden (§3.2 Hidden). */
    fun reopen(t: Task) {
        tray.hide()
        t.hidden = false
        t.anchor = Anchor.Taskbar(null)
        Log.i(TAG, "note: reopened task ${t.id} running=${t.running} needsAnswer=${t.needsAnswer}")
        window.show(t, if (t.needsAnswer) Task.Focus.CONSENT else Task.Focus.FIELD)
        startTicker()
    }

    /** Starts a computer-control run in a new note (debuggable builds; see ControlRun). */
    fun startControl(prompt: String, appName: String, launch: String, plan: List<ControlRun.Tap>, anchor: Anchor,
        aimMs: Long = 700L) {
        window.task?.let { close() }
        val t = Task(this, agents.default(), Intake.Window(appName, null), anchor)
        tasks += t
        window.show(t, Task.Focus.KEEP)
        val run = ControlRun(app, handler, app.computerControl, t, appName, launch, plan, window, aimMs)
        window.whenVisible { run.start(prompt) }
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

    /** Save as a file (§3.2): the note steps aside for the picker and says where the file went. */
    override fun saveFile(name: String, mime: String, text: String) {
        val t = window.task ?: return
        window.suspended = true
        Saver.save(app, Saver.Job(name, mime, text) { r ->
            window.suspended = false
            r.onSuccess { t.notify(app.getString(dev.openbook.quire.R.string.q_saved, it)) }
            r.onFailure {
                if (it !is SaveActivity.CancelledException) {
                    t.notify(app.getString(dev.openbook.quire.R.string.q_save_failed))
                } else {
                    t.refresh()
                }
            }
            window.card?.focus(Task.Focus.FIELD)
        })
    }

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
        private val REOPEN_TRIGGERS = setOf("assistant_shortcut", "assist_key", "taskbar")

        /** A first install from the download can take minutes; from the debuggable build's local image, about 30 s. */
        private const val SET_UP_TIMEOUT_MS = 15 * 60_000L
    }
}
