// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.assist

import android.app.contextualsearch.ContextualSearchConfig
import android.app.contextualsearch.ContextualSearchManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.util.Log
import android.view.Display
import com.android.internal.app.AssistUtils
import dev.openbook.quire.Quire
import dev.openbook.quire.Quire.TAG

/**
 * The assistant session, started by Meta+Space, the assist key or the Copilot key. It shows nothing itself: it hands the
 * call to contextual search, so that every way of calling Quire arrives the same way, with a screenshot that leaves
 * secure windows out and the visible packages, at Quire's ContextualSearchActivity.
 */
class QuireSession(context: Context) : VoiceInteractionSession(context) {
    override fun onCreate() {
        super.onCreate()
        setUiEnabled(false)
    }

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        val trigger = triggerOf(args)
        val requestedDisplay = args?.getInt(Intent.EXTRA_ASSIST_DISPLAY_ID, Display.INVALID_DISPLAY)
            ?: Display.INVALID_DISPLAY
        val displayId = if (requestedDisplay >= 0) requestedDisplay else Display.DEFAULT_DISPLAY
        Log.i(TAG, "assistant: session shown trigger=$trigger " +
            "invocationType=${args?.getInt(AssistUtils.INVOCATION_TYPE_KEY, -1)} " +
            "keyboardHint=${args?.getBoolean(Intent.EXTRA_ASSIST_INPUT_HINT_KEYBOARD, false)} " +
            "display=$displayId showFlags=0x${Integer.toHexString(showFlags)}")
        val manager = context.getSystemService(ContextualSearchManager::class.java)
        if (manager == null) {
            Log.w(TAG, "assistant: no ContextualSearchManager")
        } else {
            val config = ContextualSearchConfig.Builder()
                .setDisplayId(displayId)
                .setIntentExtras(Bundle().apply { putString(Quire.EXTRA_TRIGGER, trigger) })
                .build()
            try {
                // Contextual search has no entry point for the assist key; both keys are keyboard keys.
                manager.startContextualSearch(ContextualSearchManager.ENTRYPOINT_KEYBOARD_SHORTCUT, config)
                Log.i(TAG, "assistant: started contextual search trigger=$trigger")
            } catch (e: RuntimeException) {
                Log.e(TAG, "assistant: contextual search failed", e)
            }
        }
        finish()
    }

    private fun triggerOf(args: Bundle?): String {
        val type = args?.getInt(AssistUtils.INVOCATION_TYPE_KEY, AssistUtils.INVOCATION_TYPE_UNKNOWN)
            ?: AssistUtils.INVOCATION_TYPE_UNKNOWN
        return when {
            type == AssistUtils.INVOCATION_TYPE_ASSIST_BUTTON -> "assist_key"
            // PhoneWindowManager's KEY_GESTURE_TYPE_LAUNCH_ASSISTANT: Meta+Space, or the Copilot key's sequence.
            args?.getBoolean(Intent.EXTRA_ASSIST_INPUT_HINT_KEYBOARD, false) == true -> "assistant_shortcut"
            type == AssistUtils.INVOCATION_TYPE_POWER_BUTTON_LONG_PRESS -> "power_long_press"
            type == AssistUtils.INVOCATION_TYPE_HOME_BUTTON_LONG_PRESS -> "home_long_press"
            type == AssistUtils.INVOCATION_TYPE_NAV_HANDLE_LONG_PRESS -> "nav_handle_long_press"
            else -> "assistant_$type"
        }
    }
}
