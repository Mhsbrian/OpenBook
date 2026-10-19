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
        // Quire reads the screen only through contextual search, which leaves secure windows out of its screenshot.
        // The assistant session itself asks for neither the assist structure nor a second screenshot.
        setDisabledShowContext(
            VoiceInteractionSession.SHOW_WITH_ASSIST or VoiceInteractionSession.SHOW_WITH_SCREENSHOT
        )
        Log.i(TAG, "assistant: ready")
    }

    override fun onShutdown() {
        Log.i(TAG, "assistant: shut down")
        super.onShutdown()
    }
}
