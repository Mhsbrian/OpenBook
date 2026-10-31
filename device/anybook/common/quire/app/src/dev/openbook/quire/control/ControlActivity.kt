// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.control

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.util.TypedValue
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.R
import dev.openbook.quire.agents.Agents
import dev.openbook.quire.invocation.Invocations
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import org.json.JSONArray

/**
 * Quire's window for Q2 and Q4: the computer-control session's status and live mirror, the agents Quire reaches (with
 * a prompt box), and the last invocation. Scripted checks drive the same actions through the non-exported LabActivity
 * alias.
 */
class ControlActivity : Activity(), ComputerControl.Listener, Agents.Listener, Agents.Asker {
    private val control: ComputerControl
        get() = (application as QuireApplication).computerControl
    private val agents: Agents
        get() = (application as QuireApplication).agents
    private val agentWork
        get() = (application as QuireApplication).agentWork

    private lateinit var agentStatus: TextView
    private lateinit var agentName: EditText
    private lateinit var agentPrompt: EditText

    private lateinit var status: TextView
    private lateinit var lastCall: TextView
    private lateinit var mirror: MirrorView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(layout())
        control.addListener(this)
        agents.addListener(this)
        agents.asker = this
        onChanged()
        agentStatus.text = agents.summary
        if (savedInstanceState == null) handleLab(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleLab(intent)
    }

    override fun onResume() {
        super.onResume()
        lastCall.text = Invocations.last(this)?.let { getString(R.string.control_last_invocation, it) }
            ?: getString(R.string.control_no_invocation)
    }

    override fun onDestroy() {
        control.removeListener(this)
        agents.removeListener(this)
        if (agents.asker === this) agents.asker = null
        super.onDestroy()
    }

    override fun onAgentsChanged(summary: String) {
        runOnUiThread { agentStatus.text = summary }
    }

    /** The agent's own question and options, as the person's dialog; a dismissed or unanswered one means no. */
    override fun ask(title: String, kind: String, options: JSONArray): String? {
        val chosen = AtomicReference<String?>(null)
        val done = CountDownLatch(1)
        runOnUiThread {
            val names = Array(options.length()) { options.getJSONObject(it).optString("name") }
            AlertDialog.Builder(this)
                .setTitle(getString(R.string.agents_permission_title, title))
                .setItems(names) { _, i -> chosen.set(options.getJSONObject(i).optString("optionId")) }
                .setOnDismissListener { done.countDown() }
                .show()
        }
        if (!done.await(5, TimeUnit.MINUTES)) return null
        return chosen.get()
    }

    /** Runs agent work off the main thread; failures are logged and shown, never swallowed. */
    private fun agentTask(what: String, block: () -> Unit) {
        agentWork.execute {
            try {
                block()
            } catch (e: Agents.Unavailable) {
                // Already logged and shown by Agents.
            } catch (e: Exception) {
                Log.w(TAG, "agents: error $what: $e")
                onAgentsChanged("$what: ${e.message}")
            }
        }
    }

    override fun onChanged() {
        status.text = control.status
        mirror.setSession(control.session)
    }

    /** Commands from scripts/quire/q2-cf-check.sh. Only root and the system can start the alias. */
    private fun handleLab(intent: Intent) {
        if (intent.component?.className != LAB_ALIAS) return
        val action = intent.action ?: return
        // "delayMs" runs the command later, e.g. after the check has locked the screen.
        val delay = intent.getLongExtra("delayMs", 0)
        Log.i(TAG, "lab: $action" + if (delay > 0) " in $delay ms" else "")
        if (delay > 0) {
            mainThreadHandler.postDelayed({ runLab(action, intent) }, delay)
        } else {
            runLab(action, intent)
        }
    }

    private fun runLab(action: String, intent: Intent) {
        when (action) {
            LAB_REQUEST -> control.request(
                this,
                intent.getStringExtra("targets")?.split(",")?.map { it.trim() }?.filter { it.isNotEmpty() }
                    ?: listOf(SETTINGS),
                intent.getStringExtra("launch"),
            )
            LAB_LAUNCH -> intent.getStringExtra("target")?.let { control.launch(it) }
            LAB_SCREENSHOT -> control.screenshot()
            LAB_TAP -> {
                val text = intent.getStringExtra("text")
                if (text != null) control.tapText(text) else control.tap(intent.getIntExtra("x", 0),
                    intent.getIntExtra("y", 0))
            }
            LAB_WINDOWS -> control.dumpWindows()
            LAB_HAND_OVER -> control.handOver()
            LAB_CLOSE -> control.close()
            LAB_AGENTS_STATUS -> agentTask("status") { agents.statuses() }
            LAB_AGENTS_LIST -> agentTask("list") { agents.agents() }
            LAB_AGENTS_DESCRIBE -> intent.getStringExtra("agent")?.let { a -> agentTask("describe") { agents.describe(a) } }
            LAB_AGENTS_AUTH -> {
                val a = intent.getStringExtra("agent")
                val m = intent.getStringExtra("method")
                if (a != null && m != null) agentTask("authenticate") { agents.authenticate(a, m) }
            }
            LAB_AGENTS_PROMPT -> {
                val a = intent.getStringExtra("agent")
                val text = intent.getStringExtra("text")
                // The checks name a policy; without one nobody is asked, so every request is refused.
                val approve = runCatching { Agents.Approve.valueOf(intent.getStringExtra("approve")?.uppercase() ?: "NONE") }
                    .getOrDefault(Agents.Approve.NONE)
                if (a != null && text != null) agentTask("prompt") { agents.prompt(a, text, approve) }
            }
            LAB_AGENTS_DISCONNECT -> agentTask("disconnect") { agents.disconnect() }
            else -> Log.w(TAG, "lab: unknown action $action")
        }
    }

    private fun layout(): LinearLayout {
        val pad = dp(16)
        status = TextView(this).apply { setPadding(0, dp(4), 0, dp(8)) }
        lastCall = TextView(this).apply { setPadding(0, dp(8), 0, 0) }
        mirror = MirrorView(this)
        val buttons = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(button(R.string.control_open_settings) {
                control.request(this@ControlActivity, listOf(SETTINGS), DARK_THEME)
            })
            addView(button(R.string.control_tap_toggle) { control.tapText(DARK_THEME_LABEL) })
            addView(button(R.string.control_hand_over) { control.handOver() })
            addView(button(R.string.control_stop) { control.close() })
        }
        agentStatus = TextView(this).apply { setPadding(0, dp(4), 0, dp(4)) }
        agentName = EditText(this).apply {
            setText("opencode")
            setSingleLine()
            layoutParams = LinearLayout.LayoutParams(dp(160), WRAP_CONTENT).apply { marginEnd = dp(8) }
        }
        agentPrompt = EditText(this).apply {
            hint = getString(R.string.agents_prompt_hint)
            setSingleLine()
            layoutParams = LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginEnd = dp(8) }
        }
        val agentRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(button(R.string.agents_list_button) { agentTask("list") { agents.agents() } })
            addView(agentName)
            addView(agentPrompt)
            addView(button(R.string.agents_send) {
                val a = agentName.text.toString().trim()
                val text = agentPrompt.text.toString()
                if (a.isNotEmpty() && text.isNotBlank()) agentTask("prompt") { agents.prompt(a, text, Agents.Approve.ASK) }
            })
        }
        val frame = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            addView(mirror, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            addView(TextView(context).apply {
                text = getString(R.string.control_heading)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            })
            addView(status)
            addView(buttons)
            addView(TextView(context).apply {
                text = getString(R.string.agents_heading)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                setPadding(0, dp(12), 0, 0)
            })
            addView(agentRow)
            addView(agentStatus)
            addView(frame, LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f).apply { topMargin = dp(8) })
            addView(lastCall)
        }
    }

    private fun button(label: Int, onClick: () -> Unit) =
        Button(this).apply {
            text = getString(label)
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginEnd = dp(8) }
        }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val LAB_ALIAS = "dev.openbook.quire.control.LabActivity"
        private const val LAB = "dev.openbook.quire.lab."
        const val LAB_REQUEST = LAB + "REQUEST"
        const val LAB_LAUNCH = LAB + "LAUNCH"
        const val LAB_SCREENSHOT = LAB + "SCREENSHOT"
        const val LAB_TAP = LAB + "TAP"
        const val LAB_WINDOWS = LAB + "WINDOWS"
        const val LAB_HAND_OVER = LAB + "HAND_OVER"
        const val LAB_CLOSE = LAB + "CLOSE"
        const val LAB_AGENTS_STATUS = LAB + "AGENTS_STATUS"
        const val LAB_AGENTS_LIST = LAB + "AGENTS_LIST"
        const val LAB_AGENTS_DESCRIBE = LAB + "AGENTS_DESCRIBE"
        const val LAB_AGENTS_AUTH = LAB + "AGENTS_AUTH"
        const val LAB_AGENTS_PROMPT = LAB + "AGENTS_PROMPT"
        const val LAB_AGENTS_DISCONNECT = LAB + "AGENTS_DISCONNECT"

        private const val SETTINGS = "com.android.settings"
        private const val DARK_THEME = "com.android.settings/.Settings\$DarkThemeSettingsActivity"
        private const val DARK_THEME_LABEL = "Use Dark theme"
    }
}
