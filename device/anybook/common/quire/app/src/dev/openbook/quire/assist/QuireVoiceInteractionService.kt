// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.assist

import android.service.voice.VoiceInteractionService
import android.service.voice.VoiceInteractionSession
import android.util.Log
import dev.openbook.quire.Quire.TAG

/**
 * Quire's assistant (ROLE_ASSISTANT, config_defaultAssistant). Holding the role routes Meta+Space, the assist key and
 * the Copilot key to Quire, and is one of computer control's conditions for an agent.
 */
class QuireVoiceInteractionService : VoiceInteractionService() {
    override fun onReady() {
        super.onReady()
        // A call (Meta+Space, the assist key) reads the screen through contextual search, which leaves secure windows out
        // of its screenshot, so the session it shows asks for neither the assist structure nor a second screenshot. Only
        // an agent's read_screen or take_screenshot (tools/ScreenTools.kt) allows them, for its own session.
        allowScreenContext(false)
        instance = this
        Log.i(TAG, "assistant: ready")
    }

    /** Main thread. While allowed, a session Quire shows may get the assist structure and screenshot. */
    fun allowScreenContext(allow: Boolean) {
        setDisabledShowContext(if (allow) 0 else
            VoiceInteractionSession.SHOW_WITH_ASSIST or VoiceInteractionSession.SHOW_WITH_SCREENSHOT)
    }

    override fun onShutdown() {
        Log.i(TAG, "assistant: shut down")
        if (instance === this) instance = null
        super.onShutdown()
    }

    companion object {
        /** The running service, while Quire holds the assistant role. Main thread. */
        @Volatile var instance: QuireVoiceInteractionService? = null
            private set
    }
}
