// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.control

import android.companion.virtual.computercontrol.ComputerControlSession
import android.companion.virtual.computercontrol.InteractiveMirror
import android.content.Context
import android.graphics.PointF
import android.graphics.RectF
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
import dev.openbook.quire.ui.Motion
import dev.openbook.quire.ui.SpringValue
import kotlin.math.min

/**
 * A live view of the session display: the platform's [InteractiveMirror] surface, scaled to fit and reparented under
 * this SurfaceView. Modelled on AOSP's computercontrol extension MirrorView, without its accessibility embedding.
 *
 * The note's mirror (docs/quire-design.md §3.4) adds a [viewport]: the region of the session display the view shows,
 * moved with spring.expand. Null shows the whole display; the note zooms 2× on the control the agent acts on. The
 * mirror accepts the person's input only while [interactive] (Pause; the platform also requires the session to be
 * blocked). Q2's ControlActivity uses neither, and sees the whole display, non-interactive.
 */
class MirrorView(context: Context) : SurfaceView(context), SurfaceHolder.Callback {
    // The worker lives while the view is attached; the note re-attaches its mirror when it reopens.
    private var worker = HandlerThread("QuireMirror").apply { start() }
    private var workerHandler = Handler(worker.looper)
    private var session: ComputerControlSession? = null
    private var surfaceReady = false

    /** Owned by the worker thread. */
    @Volatile private var mirror: InteractiveMirror? = null

    /** Owned by the main thread. */
    private var mirrorSurface: SurfaceControl? = null
    private var displaySize: Size? = null

    /** Called on the main thread whenever the transform changes, so overlays can follow. */
    var onTransform: (() -> Unit)? = null

    /** The region of the session display shown, in its pixels; null for all of it. */
    var viewport: RectF? = null
        set(value) {
            if (value == field) return
            from.set(current)
            field = value
            progress.snapTo(0f)
            progress.animateTo(1f, Motion.EXPAND)
        }
    private val from = RectF()
    private val current = RectF()
    private val progress = SpringValue(Motion.EXPAND, 1f, 0.001f) { apply() }

    /** Fills the view where the session display doesn't (a 16:9 session in a 16:10 view letterboxes, §3.4). */
    var backdrop: Int = 0xFF000000.toInt()

    var interactive = false
        set(value) {
            field = value
            workerHandler.post { runCatching { mirror?.setInteractive(value) } }
        }

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
        val wantInteractive = interactive
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
            if (created != null && wantInteractive) runCatching { created.setInteractive(true) }
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
        if (size != null) current.set(target(size))
        if (surface != null && surfaceReady) {
            t.reparent(surface, surfaceControl).show(surface)
            place(t)
        }
        t.apply()
        onTransform?.invoke()
    }

    private fun target(size: Size): RectF = viewport ?: RectF(0f, 0f, size.width.toFloat(), size.height.toFloat())

    private fun apply() {
        val size = displaySize ?: return
        val to = target(size)
        val f = progress.value
        if (from.isEmpty) from.set(to)
        current.set(from.left + (to.left - from.left) * f, from.top + (to.top - from.top) * f,
            from.right + (to.right - from.right) * f, from.bottom + (to.bottom - from.bottom) * f)
        val t = SurfaceControl.Transaction()
        place(t)
        t.apply()
        onTransform?.invoke()
    }

    /** The scale from session pixels to view pixels, and the offset, for the current viewport. */
    private fun scale(): Float {
        if (current.isEmpty || width == 0) return 1f
        return min(width / current.width(), height / current.height())
    }

    /** Maps a point on the session display to this view's coordinates. */
    fun sessionToView(x: Float, y: Float): PointF {
        val s = scale()
        val ox = (width - current.width() * s) / 2f
        val oy = (height - current.height() * s) / 2f
        return PointF(ox + (x - current.left) * s, oy + (y - current.top) * s)
    }

    fun sessionScale(): Float = scale()

    val sessionSize: Size?
        get() = displaySize

    private fun place(t: SurfaceControl.Transaction) {
        val surface = mirrorSurface ?: return
        val size = displaySize ?: return
        if (width == 0 || height == 0) return
        if (current.isEmpty) current.set(target(size))
        val s = scale()
        val origin = sessionToView(0f, 0f)
        // Crop in the mirror's own pixels, so a zoomed view doesn't spill past the view's bounds.
        val crop = android.graphics.Rect(current.left.toInt(), current.top.toInt(), current.right.toInt(),
            current.bottom.toInt())
        t.setScale(surface, s, s).setPosition(surface, origin.x, origin.y).setCrop(surface, crop)
    }

    override fun surfaceCreated(holder: SurfaceHolder) {
        surfaceReady = true
        rebuild()
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        // The view's own buffer sits under the mirror: paint it once, so letterbox bars are the note's colour.
        runCatching {
            holder.lockCanvas()?.let { c ->
                c.drawColor(backdrop)
                holder.unlockCanvasAndPost(c)
            }
        }
        val t = SurfaceControl.Transaction()
        place(t)
        t.apply()
        onTransform?.invoke()
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

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (!worker.isAlive) {
            worker = HandlerThread("QuireMirror").apply { start() }
            workerHandler = Handler(worker.looper)
        }
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        progress.cancel()
        worker.quitSafely()
    }
}
