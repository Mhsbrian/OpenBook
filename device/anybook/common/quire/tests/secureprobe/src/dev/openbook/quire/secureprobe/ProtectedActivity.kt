// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.secureprobe

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.widget.TextView

/**
 * A window that asks the system to hide other apps' overlays (Window.setHideOverlayWindows), as a banking or password
 * app would. Quire's note and tray must hide while it is on screen (scripts/quire/q5-safety-check.py, ANAL-219). Every
 * touch it receives is logged with its obscured flags, so a check can tell whether a tap reached it or an overlay took
 * it. Started with `--ez hide false` it is an ordinary window that hides nothing: the target for checking that clicks
 * beside Quire's note reach the app below.
 */
class ProtectedActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val hide = intent.getBooleanExtra("hide", true)
        window.setHideOverlayWindows(hide)
        setContentView(object : TextView(this) {
            override fun onTouchEvent(event: MotionEvent): Boolean {
                if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                    Log.i(TAG, "touch ${event.rawX.toInt()},${event.rawY.toInt()} flags=0x${Integer.toHexString(event.flags)}")
                }
                return true
            }
        }.apply {
            text = if (hide) "PROTECTED PROBE\nsetHideOverlayWindows(true)" else "TOUCH PROBE\nhides nothing"
            textSize = 32f
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
            setBackgroundColor(if (hide) Color.rgb(0, 128, 96) else Color.rgb(48, 64, 160))
        })
        Log.i(TAG, "shown, hide=$hide")
    }

    companion object {
        private const val TAG = "QuireProtectedProbe"
    }
}
