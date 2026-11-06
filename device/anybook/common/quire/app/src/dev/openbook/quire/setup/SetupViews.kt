// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.setup

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.SweepGradient
import android.graphics.drawable.Drawable
import android.view.View
import dev.openbook.quire.ui.LeafDrawable
import dev.openbook.quire.ui.Motion
import dev.openbook.quire.ui.Palette
import dev.openbook.quire.ui.dp

/**
 * The window's material (docs/quire-setup.md §3, quire-design.md §4.1): the note's colour, a bloom from the top-left,
 * a specular top edge, and the holographic rim in the halo's hues. With the platform's blur on, the window itself
 * blurs what is behind it and this draws the colour at 80 %; with blur off, at 96 %.
 */
class GlassBackground(private val context: Context, private val p: Palette, private val radiusDp: Float,
    opaque: Boolean = true) : Drawable() {
    // An opaque window can't show what is behind it, so its colour is drawn solid (the 96 % paper of quire-design §4.5).
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = if (opaque) Palette.withAlpha(p.noteBackground, 1f) else p.noteBackground
    }
    private val bloom = Paint(Paint.ANTI_ALIAS_FLAG)
    private val specular = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = context.dp(1f)
        color = p.specular
    }
    private val rim = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = context.dp(1.5f)
    }
    private val rect = RectF()

    override fun onBoundsChange(bounds: android.graphics.Rect) {
        val w = bounds.width().toFloat()
        val h = bounds.height().toFloat()
        bloom.shader = RadialGradient(bounds.left.toFloat(), bounds.top.toFloat(), maxOf(w, h) * 0.7f,
            p.bloom, 0, Shader.TileMode.CLAMP)
        val colors = p.rim + p.rim[0]
        rim.shader = SweepGradient(bounds.exactCenterX(), bounds.exactCenterY(), colors, null).apply {
            setLocalMatrix(android.graphics.Matrix().apply { setRotate(200f, bounds.exactCenterX(), bounds.exactCenterY()) })
        }
    }

    override fun draw(canvas: Canvas) {
        val r = context.dp(radiusDp)
        rect.set(bounds)
        canvas.drawRoundRect(rect, r, r, fill)
        canvas.drawRoundRect(rect, r, r, bloom)
        val half = rim.strokeWidth / 2
        rect.inset(half, half)
        canvas.drawRoundRect(rect, r - half, r - half, rim)
        run {
            rect.inset(half, half)
            canvas.save()
            canvas.clipRect(rect.left, rect.top, rect.right, rect.top + r)
            canvas.drawRoundRect(rect, r - 2 * half, r - 2 * half, specular)
            canvas.restore()
        }
    }

    override fun setAlpha(alpha: Int) {}
    override fun setColorFilter(colorFilter: ColorFilter?) {}
    @Deprecated("Drawable API") override fun getOpacity() = PixelFormat.TRANSLUCENT
}

/** The Linux page's ring (§3): the halo drawn as a progress arc around the leaf. */
class ProgressRing(context: Context, private val p: Palette, private val sizeDp: Float, private val strokeDp: Float,
    private val leafDp: Float) : View(context) {
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = context.dp(strokeDp)
        color = Palette.withAlpha(p.outlineVariant, 0.45f)
    }
    private val arc = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = context.dp(strokeDp)
        strokeCap = Paint.Cap.ROUND
    }
    private val leaf = LeafDrawable()
    private val rect = RectF()
    private var shown = 0f
    private var animator: ValueAnimator? = null

    var fraction = 0f
        set(value) {
            val to = value.coerceIn(0f, 1f)
            if (to == field) return
            field = to
            animator?.cancel()
            if (!Motion.enabled || !isAttachedToWindow) {
                shown = to
                invalidate()
                return
            }
            animator = ValueAnimator.ofFloat(shown, to).apply {
                duration = 400
                interpolator = Motion.STANDARD
                addUpdateListener { shown = it.animatedValue as Float; invalidate() }
                start()
            }
        }

    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val s = context.dp(sizeDp).toInt()
        setMeasuredDimension(s, s)
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        arc.shader = SweepGradient(w / 2f, h / 2f, intArrayOf(Palette.BRAND_A, 0xFFC58BFF.toInt(), 0xFFFF7A9C.toInt(),
            Palette.BRAND_A), floatArrayOf(0f, 0.5f, 0.9f, 1f)).apply {
            setLocalMatrix(android.graphics.Matrix().apply { setRotate(-90f, w / 2f, h / 2f) })
        }
        val l = context.dp(leafDp).toInt()
        leaf.setBounds((w - l) / 2, (h - l) / 2, (w + l) / 2, (h + l) / 2)
    }

    override fun onDraw(canvas: Canvas) {
        val half = track.strokeWidth / 2
        rect.set(half, half, width - half, height - half)
        canvas.drawOval(rect, track)
        if (shown > 0f) canvas.drawArc(rect, -90f, 360f * shown, false, arc)
        leaf.draw(canvas)
    }

    override fun onDetachedFromWindow() {
        animator?.cancel()
        super.onDetachedFromWindow()
    }
}

/** A row's mark (§2): the ink dot while running, a tick drawn as a stroke when done, a cross when it failed. */
class Mark(context: Context, private val p: Palette) : View(context) {
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = context.dp(2.2f)
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG)
    private val path = Path()

    var state = SetupModel.Row.WAIT
        set(value) {
            if (field == value) return
            field = value
            invalidate()
        }

    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    /** The ink dot breathes on the clock's phase, so the page's redraws never restart it; still with Remove animations. */
    private fun dotScale(): Float {
        if (!Motion.enabled) return 1f
        val t = (android.os.SystemClock.uptimeMillis() % 1200L) / 1200f
        return 1f - 0.4f * Motion.STANDARD.getInterpolation(if (t < 0.5f) t * 2f else (1f - t) * 2f)
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val s = context.dp(22f).toInt()
        setMeasuredDimension(s, s)
    }

    override fun onDraw(canvas: Canvas) {
        val u = width / 22f
        when (state) {
            SetupModel.Row.DONE -> {
                stroke.color = p.success
                path.reset()
                path.moveTo(5.5f * u, 11.5f * u)
                path.lineTo(9.1f * u, 15.1f * u)
                path.lineTo(16.8f * u, 7.4f * u)
                canvas.drawPath(path, stroke)
            }
            SetupModel.Row.FAILED -> {
                stroke.color = p.error
                canvas.drawLine(7f * u, 7f * u, 15f * u, 15f * u, stroke)
                canvas.drawLine(15f * u, 7f * u, 7f * u, 15f * u, stroke)
            }
            SetupModel.Row.NOW -> {
                dot.style = Paint.Style.FILL
                dot.color = p.primary
                canvas.drawCircle(width / 2f, height / 2f, 4f * u * dotScale(), dot)
                if (Motion.enabled) postInvalidateOnAnimation()
            }
            SetupModel.Row.WAIT -> {
                dot.style = Paint.Style.STROKE
                dot.strokeWidth = 1.5f * u
                dot.color = p.outlineVariant
                canvas.drawCircle(width / 2f, height / 2f, 3.5f * u, dot)
            }
        }
    }
}

/** A thin progress bar in the brand's hues, under an installing card's line. */
class InkBar(context: Context, private val p: Palette) : View(context) {
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Palette.withAlpha(p.outline, 0.18f) }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val rect = RectF()

    var fraction = 0f
        set(value) {
            field = value.coerceIn(0f, 1f)
            invalidate()
        }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), context.dp(3f).toInt())
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        fill.shader = LinearGradient(0f, 0f, w.toFloat(), 0f, intArrayOf(Palette.BRAND_A, 0xFFC58BFF.toInt(),
            0xFFFF7A9C.toInt()), floatArrayOf(0f, 0.6f, 1f), Shader.TileMode.CLAMP)
    }

    override fun onDraw(canvas: Canvas) {
        val r = height / 2f
        rect.set(0f, 0f, width.toFloat(), height.toFloat())
        canvas.drawRoundRect(rect, r, r, track)
        rect.right = width * fraction
        if (rect.right > 0f) canvas.drawRoundRect(rect, r, r, fill)
    }
}
