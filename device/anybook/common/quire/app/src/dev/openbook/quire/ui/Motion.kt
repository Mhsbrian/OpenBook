// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.ui

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.view.Choreographer
import android.view.View
import android.view.animation.LinearInterpolator
import android.view.animation.PathInterpolator
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Motion tokens (docs/quire-design.md §5.1). Springs are stiffness and damping ratio with mass 1, as in Compose and
 * SpringForce; durations are for opacity only. "Remove animations" (animator duration scale 0) turns every spring into
 * a cut and every loop into a still (§5.3): springs check [enabled] themselves, because nothing in the platform does
 * it for them.
 */
object Motion {
    data class Spring(val stiffness: Float, val damping: Float)

    val UNFOLD = Spring(380f, 0.80f)
    val SETTLE = Spring(700f, 0.90f)
    val EXPAND = Spring(300f, 0.85f)
    val FOLD = Spring(900f, 1.00f)
    val TICK = Spring(1400f, 0.70f)

    const val FADE = 120L
    const val FADE_SLOW = 200L
    const val BREATHE = 1600L
    const val SPINNER = 1000L
    const val CARET = 1000L

    /** Material 3 standard easing, for fades. */
    val STANDARD = PathInterpolator(0.2f, 0f, 0f, 1f)

    /** False when the person turned on Remove animations. */
    val enabled: Boolean
        get() = ValueAnimator.areAnimatorsEnabled()

    /** Fades [view] to [alpha] over [duration] ms with the standard easing, or cuts when animations are off. */
    fun fade(view: View, alpha: Float, duration: Long = FADE, delay: Long = 0, end: (() -> Unit)? = null) {
        view.animate().cancel()
        if (!enabled) {
            view.alpha = alpha
            end?.invoke()
            return
        }
        view.animate().alpha(alpha).setDuration(duration).setStartDelay(delay).setInterpolator(STANDARD)
            .withEndAction { end?.invoke() }.start()
    }

    /** The breathe loop (§5.1, 1 → 1.08 → 1 over 1600 ms); still when animations are off. */
    fun breathe(view: View): Animator? {
        if (!enabled) return null
        return ValueAnimator.ofFloat(0f, 1f).apply {
            duration = BREATHE
            repeatCount = ValueAnimator.INFINITE
            interpolator = LinearInterpolator()
            addUpdateListener {
                // Up for half the period, down for the other half, each half with the standard easing (as CSS
                // applies a keyframe animation's easing per segment).
                val t = it.animatedFraction
                val s = 1f + 0.08f * STANDARD.getInterpolation(if (t < 0.5f) t * 2f else (1f - t) * 2f)
                view.scaleX = s
                view.scaleY = s
            }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationCancel(animation: Animator) {
                    view.scaleX = 1f
                    view.scaleY = 1f
                }
            })
            start()
        }
    }

    /** One rotation per second, linear (§5.1); null when animations are off (the spinner draws a still arc). */
    fun spin(view: View): Animator? {
        if (!enabled) return null
        return ObjectAnimator.ofFloat(view, View.ROTATION, 0f, 360f).apply {
            duration = SPINNER
            repeatCount = ValueAnimator.INFINITE
            interpolator = LinearInterpolator()
            start()
        }
    }
}

/**
 * A value moved by a spring, frame by frame on the Choreographer, keeping its velocity when retargeted mid-flight.
 * Integrated with semi-implicit Euler in 4 ms substeps, like the prototype's solver, so the build and the prototype
 * move the same way. With animations off, [animateTo] cuts to the target.
 */
class SpringValue(
    var spec: Motion.Spring,
    initial: Float,
    /** Below this distance and speed the spring is at rest. */
    private val threshold: Float,
    private val onUpdate: (Float) -> Unit,
) : Choreographer.FrameCallback {
    var value = initial
        private set
    var target = initial
        private set
    private var velocity = 0f
    private var lastFrame = 0L
    private var running = false
    private var onEnd: (() -> Unit)? = null

    val isRunning: Boolean
        get() = running

    fun animateTo(to: Float, spring: Motion.Spring = spec, end: (() -> Unit)? = null) {
        spec = spring
        target = to
        onEnd = end
        if (!Motion.enabled) {
            snapTo(to)
            return
        }
        if (!running) {
            running = true
            lastFrame = 0L
            Choreographer.getInstance().postFrameCallback(this)
        }
    }

    fun snapTo(to: Float) {
        if (running) Choreographer.getInstance().removeFrameCallback(this)
        running = false
        value = to
        target = to
        velocity = 0f
        onUpdate(to)
        finish()
    }

    fun cancel() {
        if (running) Choreographer.getInstance().removeFrameCallback(this)
        running = false
        onEnd = null
    }

    override fun doFrame(frameTimeNanos: Long) {
        if (!running) return
        if (lastFrame == 0L) {
            lastFrame = frameTimeNanos
            Choreographer.getInstance().postFrameCallback(this)
            return
        }
        val dt = min(0.064f, (frameTimeNanos - lastFrame) / 1e9f)
        lastFrame = frameTimeNanos
        val k = spec.stiffness
        val c = 2f * spec.damping * sqrt(k)
        val steps = ceil(dt / 0.004f).toInt().coerceAtLeast(1)
        val h = dt / steps
        repeat(steps) {
            val a = -k * (value - target) - c * velocity
            velocity += a * h
            value += velocity * h
        }
        if (abs(value - target) < threshold && abs(velocity) < threshold * 10f) {
            value = target
            velocity = 0f
            running = false
            onUpdate(value)
            finish()
            return
        }
        onUpdate(value)
        Choreographer.getInstance().postFrameCallback(this)
    }

    private fun finish() {
        val end = onEnd
        onEnd = null
        end?.invoke()
    }
}
