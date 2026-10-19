// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.assist

import android.content.Intent
import android.speech.RecognitionService
import android.speech.SpeechRecognizer
import android.util.Log
import dev.openbook.quire.Quire.TAG

/** The assistant role requires a recognition service. On-device speech arrives with Q7 (ANAL-221); until then, none. */
class QuireRecognitionService : RecognitionService() {
    override fun onStartListening(recognizerIntent: Intent?, listener: Callback?) {
        Log.i(TAG, "speech: not available yet")
        listener?.error(SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE)
    }

    override fun onStopListening(listener: Callback?) {}

    override fun onCancel(listener: Callback?) {}
}
