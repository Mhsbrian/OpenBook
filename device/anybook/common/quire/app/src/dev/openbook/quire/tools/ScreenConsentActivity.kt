// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.app.Activity
import android.app.voiceinteraction.VoiceInteractionManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.util.Log
import dev.openbook.quire.Quire.TAG
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

/**
 * Asks the person, with the platform's own dialog, whether Quire may read the screen (AOSP 17: the assistant's "Use
 * text from screen" is off until the person allows it, `READ_SCREEN_CONTEXT`). Inert and transparent; it only starts
 * the permission controller's request and reports the answer to [ask]. Not exported.
 */
class ScreenConsentActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState != null) return
        val vim = getSystemService(VoiceInteractionManager::class.java)
        try {
            startActivityForResult(vim.createRequestReadScreenContextIntent(), REQUEST)
        } catch (e: Exception) {
            Log.w(TAG, "tools: no screen context request dialog: ${e.message}")
            done(false)
        }
    }

    @Deprecated("Activity API")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQUEST) done(resultCode == RESULT_OK)
    }

    private fun done(ok: Boolean) {
        Log.i(TAG, "tools: screen context request answered ${if (ok) "allowed" else "not allowed"}")
        pending?.complete(ok)
        pending = null
        finish()
    }

    companion object {
        private const val REQUEST = 1
        @Volatile private var pending: CompletableFuture<Boolean>? = null

        /**
         * Whether Quire may read the screen, asking the person when the platform lets it ask. Worker thread. Throws a
         * [ToolError] saying why not.
         */
        fun ensure(c: Context, note: CallNote) {
            val vim = c.getSystemService(VoiceInteractionManager::class.java)
                ?: throw ToolError("This laptop gives no screen reading to its assistant.")
            when (vim.readScreenContextRequestState) {
                VoiceInteractionManager.READ_SCREEN_CONTEXT_REQUEST_STATE_GRANTED -> return
                VoiceInteractionManager.READ_SCREEN_CONTEXT_REQUEST_STATE_UNREQUESTABLE -> throw ToolError(
                    "The person turned off screen reading for Quire (Settings › Apps › Default apps › Digital " +
                        "assistant › Use text from screen), so Quire can't read the screen. Ask them instead.")
            }
            note.retitle("Asking to read your screen")
            val f = CompletableFuture<Boolean>()
            pending = f
            note.platformDialog(true)
            val ok = try {
                c.startActivity(Intent(c, ScreenConsentActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                f.get(5, TimeUnit.MINUTES)
            } catch (e: Exception) {
                false
            } finally {
                note.platformDialog(false)
            }
            // The platform lets its assistant read the screen only while the assistant shows: give the note a moment
            // to be back on screen.
            Thread.sleep(400)
            if (!ok) throw ToolError("The person didn't allow Quire to read the screen. Don't try another way.")
        }
    }
}
