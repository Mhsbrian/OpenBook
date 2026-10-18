// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.control

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.util.TypedValue
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.R
import dev.openbook.quire.invocation.Invocations

/**
 * Quire's window for Q2: the computer-control session's status and live mirror, with buttons for the person, and the
 * last invocation. Scripted checks drive the same actions through the non-exported LabActivity alias.
 */
class ControlActivity : Activity(), ComputerControl.Listener {
    private val control: ComputerControl
        get() = (application as QuireApplication).computerControl

    private lateinit var status: TextView
    private lateinit var lastCall: TextView
    private lateinit var mirror: MirrorView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(layout())
        control.addListener(this)
        onChanged()
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
        super.onDestroy()
    }

    override fun onChanged() {
        status.text = control.status
        mirror.setSession(control.session)
    }

    /** Commands from scripts/quire/q2-cf-check.sh. Only root and the system can start the alias. */
    private fun handleLab(intent: Intent) {
        if (intent.component?.className != LAB_ALIAS) return
        val action = intent.action ?: return
        Log.i(TAG, "lab: $action")
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

        private const val SETTINGS = "com.android.settings"
        private const val DARK_THEME = "com.android.settings/.Settings\$DarkThemeSettingsActivity"
        private const val DARK_THEME_LABEL = "Use Dark theme"
    }
}
