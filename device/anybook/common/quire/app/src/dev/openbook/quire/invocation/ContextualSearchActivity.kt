// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.invocation

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.util.TypedValue
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.R

/**
 * Quire as the contextual search app (config_defaultContextualSearchPackageName). Every invocation ends here, whatever
 * started it: the pointer shake, Meta+A or Meta+G through Launcher3, or Meta+Space and the assist key through Quire's
 * assistant session. Q2 records what arrived and shows it in a plain note; Q5 builds the real one (ANAL-219).
 */
class ContextualSearchActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Recreated after a configuration change: the screenshot is still in the intent, but it is not a new call.
        show(intent, record = savedInstanceState == null)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        show(intent, record = true)
    }

    private fun show(intent: Intent, record: Boolean) {
        val invocation = Invocation.from(intent)
        if (record) Invocations.record(this, invocation, (application as QuireApplication).io)
        setContentView(note(invocation))
    }

    private fun note(invocation: Invocation): LinearLayout {
        val pad = dp(24)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            addView(text(getString(R.string.note_title), 22f))
            addView(text(getString(R.string.note_trigger, "${invocation.trigger} (${invocation.entrypointName})")))
            val visible = invocation.visiblePackages
                ?.takeIf { it.isNotEmpty() }
                ?.joinToString(", ")
                ?: getString(R.string.note_nothing_visible)
            addView(text(getString(R.string.note_visible, visible)))
            if (invocation.flagSecureFound == true) addView(text(getString(R.string.note_secure)))
            val shot = invocation.screenshot
            if (shot != null) {
                addView(ImageView(context).apply {
                    setImageBitmap(shot)
                    adjustViewBounds = true
                    maxHeight = dp(280)
                    contentDescription = getString(R.string.note_title)
                }, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(12) })
            } else {
                addView(text(getString(R.string.note_no_screenshot)))
            }
            addView(Button(context).apply {
                text = getString(R.string.note_close)
                setOnClickListener { finish() }
            }, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { topMargin = dp(12) })
        }
    }

    private fun text(value: String, sizeSp: Float = 15f) =
        TextView(this).apply {
            text = value
            setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
            setPadding(0, dp(4), 0, dp(4))
        }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
