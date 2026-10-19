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
            "pointer=${args?.containsKey(Quire.EXTRA_POINTER_X) == true} " +
            "source=${args?.getString(Quire.EXTRA_SOURCE_PACKAGE)} " +
            "invocationType=${args?.getInt(AssistUtils.INVOCATION_TYPE_KEY, -1)} " +
            "keyboardHint=${args?.getBoolean(Intent.EXTRA_ASSIST_INPUT_HINT_KEYBOARD, false)} " +
            "display=$displayId showFlags=0x${Integer.toHexString(showFlags)}")
        val manager = context.getSystemService(ContextualSearchManager::class.java)
        if (manager == null) {
            Log.w(TAG, "assistant: no ContextualSearchManager")
        } else {
            // SystemUI adds the pointer and the window under it (its bounds, package, and when they were read) when
            // the pointer moved in the last 10 s (frameworks/base 0008); they travel on as contextual search's
            // sourceBounds and extras, so the note opens at the pointer and takes in that window (docs/quire-design.md
            // §2). Without them Quire takes in nothing.
            val bounds = args?.getParcelable(Quire.EXTRA_SOURCE_BOUNDS, android.graphics.Rect::class.java)
            val extras = Bundle().apply {
                putString(Quire.EXTRA_TRIGGER, trigger)
                if (args?.containsKey(Quire.EXTRA_POINTER_X) == true) {
                    putFloat(Quire.EXTRA_POINTER_X, args.getFloat(Quire.EXTRA_POINTER_X))
                    putFloat(Quire.EXTRA_POINTER_Y, args.getFloat(Quire.EXTRA_POINTER_Y))
                }
                if (args?.containsKey(Quire.EXTRA_SOURCE_PACKAGE) == true) {
                    putString(Quire.EXTRA_SOURCE_PACKAGE, args.getString(Quire.EXTRA_SOURCE_PACKAGE))
                    putLong(Quire.EXTRA_SOURCE_TIME, args.getLong(Quire.EXTRA_SOURCE_TIME, -1L))
                }
            }
            val config = ContextualSearchConfig.Builder()
                .setDisplayId(displayId)
                .setSourceBounds(bounds)
                .setIntentExtras(extras)
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
