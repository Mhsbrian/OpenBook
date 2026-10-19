// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.control

import android.companion.virtual.computercontrol.ComputerControlSession
import android.companion.virtual.computercontrol.InteractiveMirror
import android.content.Context
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.util.Size
import android.view.SurfaceControl
import android.view.SurfaceHolder
import android.view.SurfaceView
import com.android.internal.os.IResultReceiver
import dev.openbook.quire.Quire.TAG
import kotlin.math.min

/**
 * A live view of the session display: the platform's [InteractiveMirror] surface, scaled to fit and reparented under
 * this SurfaceView. View-only (the mirror stays non-interactive); the person takes over with "Take over", which hands
 * the apps to their own display. Modelled on AOSP's computercontrol extension MirrorView, without its accessibility
 * embedding, which Q5 adds (ANAL-219).
 */
class MirrorView(context: Context) : SurfaceView(context), SurfaceHolder.Callback {
    private val worker = HandlerThread("QuireMirror").apply { start() }
    private val workerHandler = Handler(worker.looper)
    private var session: ComputerControlSession? = null
    private var surfaceReady = false

    /** Owned by the worker thread. */
    @Volatile private var mirror: InteractiveMirror? = null

    /** Owned by the main thread. */
    private var mirrorSurface: SurfaceControl? = null
    private var displaySize: Size? = null

    // The mirror's accessibility tree is not embedded yet; the platform only needs a receiver.
    private val a11yReceiver =
        object : IResultReceiver.Stub() {
            override fun send(resultCode: Int, resultData: Bundle?) {}
        }

    init {
        holder.addCallback(this)
    }

    fun setSession(newSession: ComputerControlSession?) {
        if (newSession === session) return
        session = newSession
        if (surfaceReady) rebuild()
    }

    private fun rebuild() {
        val s = session
        workerHandler.post {
            mirror?.close()
            mirror = null
            val created = s?.let {
                try {
                    it.createInteractiveMirror(a11yReceiver)
                } catch (e: RuntimeException) {
                    Log.e(TAG, "cc: mirror failed", e)
                    null
                }
            }
            mirror = created
            if (s != null) Log.i(TAG, "cc: mirror ${if (created != null) "created" else "refused"}")
            val surface = created?.mirrorSurfaceControl
            val size = s?.displaySize
            post { attach(surface, size) }
        }
    }

    private fun attach(surface: SurfaceControl?, size: Size?) {
        val t = SurfaceControl.Transaction()
        mirrorSurface?.let { t.remove(it) }
        mirrorSurface = surface
        displaySize = size
        if (surface != null && surfaceReady) {
            t.reparent(surface, surfaceControl).show(surface)
            place(t)
        }
        t.apply()
    }

    private fun place(t: SurfaceControl.Transaction) {
        val surface = mirrorSurface ?: return
        val size = displaySize ?: return
        if (width == 0 || height == 0) return
        val scale = min(width.toFloat() / size.width, height.toFloat() / size.height)
        t.setScale(surface, scale, scale)
            .setPosition(surface, (width - size.width * scale) / 2f, (height - size.height * scale) / 2f)
    }

    override fun surfaceCreated(holder: SurfaceHolder) {
        surfaceReady = true
        rebuild()
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        val t = SurfaceControl.Transaction()
        place(t)
        t.apply()
        workerHandler.post { mirror?.resize(width, height) }
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        surfaceReady = false
        val t = SurfaceControl.Transaction()
        mirrorSurface?.let { t.remove(it) }
        t.apply()
        mirrorSurface = null
        workerHandler.post {
            mirror?.close()
            mirror = null
        }
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        worker.quitSafely()
    }
}
