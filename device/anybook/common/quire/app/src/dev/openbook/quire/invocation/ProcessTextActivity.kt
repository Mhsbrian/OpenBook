// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.invocation

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.note.Anchor
import dev.openbook.quire.note.Intake

/**
 * "Ask Quire" on a selection (docs/quire-design.md §2): Android lists this `ACTION_PROCESS_TEXT` handler in the text
 * toolbar's overflow as a plain label, and TalkBack offers it as an action. The intent carries only the text, so the
 * window's name comes from the caller, and the note opens at the taskbar until the pointer's position reaches Quire.
 */
class ProcessTextActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) {
            val text = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString().orEmpty()
            val from = callingPackage?.let { label(it) }
            Log.i(TAG, "note: ask on a selection (${text.length} chars) from ${callingPackage ?: "unknown"}")
            if (text.isNotBlank()) {
                (application as QuireApplication).surface.invoke("selection", Anchor.Taskbar(null),
                    Intake.Selection(text, from))
            }
        }
        finish()
    }

    private fun label(pkg: String): String =
        try {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, 0)).toString()
        } catch (e: PackageManager.NameNotFoundException) {
            pkg
        }
}
