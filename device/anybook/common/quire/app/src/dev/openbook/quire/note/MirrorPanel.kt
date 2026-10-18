// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import dev.openbook.quire.R
import dev.openbook.quire.control.MirrorView
import dev.openbook.quire.ui.Motion
import dev.openbook.quire.ui.PointerDrawable
import dev.openbook.quire.ui.QButton
import dev.openbook.quire.ui.TextRole
import dev.openbook.quire.ui.dp
import dev.openbook.quire.ui.dpi
import dev.openbook.quire.ui.rounded
import dev.openbook.quire.ui.withIcon

/**
 * The live mirror inside the note (docs/quire-design.md §3.4): the automation chip, the session display in a 16:10
 * view that zooms 2× on the control the agent acts on, the agent's pointer and tap ring and the target's focus ring,
 * the steps, and Stop · Pause · Take over, always visible.
 */
class MirrorPanel(private val env: NoteEnv, private val onAction: (Action) -> Unit) : LinearLayout(env.context) {
    enum class Action { STOP, PAUSE, RESUME, TAKE_OVER }

    private val p = env.palette
    private val dot = View(context)
    private val chip = env.text(TextRole(12f, 16f, 600), p.onTertiaryContainer)
    private val chipWrap = LinearLayout(context).apply {
        orientation = HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dpi(8f), 0, dpi(10f), 0)
        addView(dot, LayoutParams(dpi(8f), dpi(8f)))
        addView(chip, LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(6f) })
    }
    private val title = env.text(TextRole(13f, 20f, 500), p.onSurface).apply {
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
    }
    val mirror = MirrorView(context).apply {
        setCornerRadius(context.dp(16f))
        backdrop = p.surfaceDim
    }
    private val marks = Overlay(context)
    private val scrimText = env.text(TextRole(13f, 18f, 500), p.inverseOnSurface).apply {
        background = rounded(context, p.inverseSurface, 18f)
        gravity = Gravity.CENTER
        setPadding(dpi(14f), 0, dpi(14f), 0)
    }
    private val scrim = FrameLayout(context).apply {
        setBackgroundColor(p.scrim)
        addView(scrimText, FrameLayout.LayoutParams(WRAP_CONTENT, dpi(36f), Gravity.CENTER))
        visibility = GONE
        // Clicks go through to the mirror, which is interactive while paused.
        isClickable = false
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
    }
    private val frame = object : FrameLayout(context) {
        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            val w = MeasureSpec.getSize(widthMeasureSpec)
            val h = w * 10 / 16
            super.onMeasure(MeasureSpec.makeMeasureSpec(w, MeasureSpec.EXACTLY),
                MeasureSpec.makeMeasureSpec(h, MeasureSpec.EXACTLY))
        }
    }.apply {
        background = rounded(context, p.surfaceDim, 16f, p.outlineVariant, 1f)
        clipToOutline = true
        addView(mirror, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        addView(marks, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        addView(scrim, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        accessibilityLiveRegion = ACCESSIBILITY_LIVE_REGION_POLITE
    }
    private val steps = StepsView(env)
    private val status = env.text(TextRole(13f, 18f, 400), p.onSurfaceVariant).apply {
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
    }
    private val stop = QButton(context, p, context.getString(R.string.q_stop), QButton.Style.DANGER).apply {
        setOnClickListener { onAction(Action.STOP) }
    }
    private val pause = QButton(context, p, context.getString(R.string.q_pause), QButton.Style.TONAL, Icons.PAUSE)
    private val takeOver = QButton(context, p, context.getString(R.string.q_take_over), QButton.Style.FILLED,
        Icons.OPEN_IN_FULL).apply { setOnClickListener { onAction(Action.TAKE_OVER) } }
    private var task: Task? = null
    private var state: Mirror? = null
    private var describedStep = ""

    init {
        orientation = VERTICAL
        addView(LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dpi(16f), dpi(10f), dpi(12f), dpi(8f))
            addView(chipWrap, LayoutParams(WRAP_CONTENT, dpi(26f)))
            addView(title, LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = dpi(10f) })
        })
        addView(frame, LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
            marginStart = dpi(12f)
            marginEnd = dpi(12f)
        })
        addView(steps.view, LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
            setMargins(dpi(16f), dpi(8f), dpi(16f), 0)
        })
        addView(LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dpi(16f), dpi(10f), dpi(12f), dpi(12f))
            addView(status, LayoutParams(0, WRAP_CONTENT, 1f))
            addView(stop, LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(8f) })
            addView(pause, LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(8f) })
            addView(takeOver, LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(8f) })
        })
        mirror.onTransform = { marks.invalidate() }
    }

    fun bind(t: Task, m: Mirror) {
        task = t
        state = m
        mirror.setSession(t.control?.session)
        val blocked = m.blockedReason != null
        val grey = m.paused || blocked
        chipWrap.background = rounded(context, if (grey) p.surfaceHighest else p.tertiaryContainer, 13f)
        dot.background = rounded(context, if (grey) p.outline else p.tertiary, 4f)
        chip.setTextColor(if (grey) p.onSurfaceVariant else p.onTertiaryContainer)
        chip.text = when {
            blocked -> context.getString(R.string.q_mirror_blocked)
            m.paused -> context.getString(R.string.q_mirror_paused)
            else -> context.getString(R.string.q_mirror_using, m.app)
        }
        title.text = m.title
        // Paused: the view returns to the whole display and the mirror is interactive (§3.4). Blocked: the platform
        // shows its placeholder and drops the agent's input; the person can take over or stop.
        mirror.interactive = m.paused
        mirror.viewport = if (grey) null else zoomed(m)
        scrim.visibility = if (m.paused) VISIBLE else GONE
        scrimText.text = withIcon(context, Icons.PAUSE, context.getString(R.string.q_mirror_paused_hint), 16f)
        pause.visibility = if (blocked) GONE else VISIBLE
        pause.set(context.getString(if (m.paused) R.string.q_resume else R.string.q_pause),
            if (m.paused) Icons.PLAY_ARROW else Icons.PAUSE)
        pause.setOnClickListener { onAction(if (m.paused) Action.RESUME else Action.PAUSE) }
        steps.bindAny(m.steps)
        tick(t)
        marks.invalidate()
        describe(t, m)
    }

    fun unbind() {
        mirror.setSession(null)
        task = null
        state = null
    }

    fun tick(t: Task) {
        val m = state ?: return
        val now = android.os.SystemClock.elapsedRealtime()
        val secs = ((now - t.startedAt) / 1000).toInt()
        val done = m.steps.items.count { it.status == StepStatus.DONE }
        status.text = when {
            m.blockedReason != null -> m.status
            m.paused -> context.getString(R.string.q_cc_paused_status, ((now - m.pausedAt) / 1000).toInt())
            m.total > 0 -> context.getString(R.string.q_cc_status, (done + 1).coerceAtMost(m.total), m.total, secs)
            else -> t.footer()
        }
    }

    /** The mirror view's bounds in [ancestor]'s coordinates, for the note's surface to leave unblurred. */
    fun holeIn(ancestor: android.view.ViewGroup, out: RectF): Boolean {
        if (frame.width == 0) return false
        val r = android.graphics.Rect(0, 0, frame.width, frame.height)
        ancestor.offsetDescendantRectToMyCoords(frame, r)
        out.set(r)
        return true
    }

    fun focusResume() {
        pause.requestFocus()
    }

    /**
     * The 2× region (§3.4): half the session display's width, at the view's own aspect so the zoom fills the view,
     * centred on the target and clamped to the display.
     */
    private fun zoomed(m: Mirror): RectF? {
        val target = m.target ?: return null
        val size = mirror.sessionSize ?: return null
        val w = size.width / ZOOM
        val h = minOf(size.height.toFloat(), w * 10f / 16f)
        val l = (target.exactCenterX() - w / 2f).coerceIn(0f, size.width - w)
        val top = (target.exactCenterY() - h / 2f).coerceIn(0f, size.height - h)
        return RectF(l, top, l + w, top + h)
    }

    /** TalkBack: one description per step, never per frame (§6.3 Mirror). */
    private fun describe(t: Task, m: Mirror) {
        val current = m.steps.items.lastOrNull { it.status == StepStatus.RUNNING } ?: m.steps.items.lastOrNull()
        val key = "${m.paused}|${m.blockedReason}|${current?.title}|${m.steps.items.size}"
        if (key == describedStep) return
        describedStep = key
        val agent = t.agent?.name ?: ""
        frame.contentDescription = when {
            m.paused -> context.getString(R.string.q_a11y_mirror_paused)
            m.blockedReason != null -> context.getString(R.string.q_a11y_mirror_blocked, m.app)
            else -> context.getString(R.string.q_a11y_mirror, m.app, agent,
                m.steps.items.indexOf(current) + 1, m.steps.items.size, current?.title ?: "")
        }
    }

    /** Draws the agent's pointer, the tap ring and the target's focus ring over the mirror (§3.4). */
    private inner class Overlay(context: Context) : View(context) {
        private val pointer = PointerDrawable()
        private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
        private var fade: ValueAnimator? = null
        private var tapAlpha = 0f
        private var lastTap = 0L

        init {
            importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        }

        override fun onDraw(canvas: Canvas) {
            val m = state ?: return
            if (m.paused || m.blockedReason != null) return
            m.target?.let { t ->
                val a = mirror.sessionToView(t.left.toFloat(), t.top.toFloat())
                val b = mirror.sessionToView(t.right.toFloat(), t.bottom.toFloat())
                ring.color = p.primary
                ring.alpha = 255
                ring.strokeWidth = dp(2f)
                val o = dp(2f) + dp(1f)
                canvas.drawRoundRect(a.x - o, a.y - o, b.x + o, b.y + o, dp(12f), dp(12f), ring)
            }
            val at = m.pointer ?: return
            val v = mirror.sessionToView(at.x, at.y)
            if (m.tapAt != lastTap) {
                lastTap = m.tapAt
                startTapFade()
            }
            if (tapAlpha > 0f) {
                ring.color = p.primary
                ring.alpha = (tapAlpha * 0.8f * 255).toInt()
                ring.strokeWidth = dp(2f)
                canvas.drawCircle(v.x, v.y, dp(18f) - dp(1f), ring)
            }
            val size = dpi(24f)
            val hx = (PointerDrawable.HOTSPOT_X * size).toInt()
            val hy = (PointerDrawable.HOTSPOT_Y * size).toInt()
            pointer.setBounds(v.x.toInt() - hx, v.y.toInt() - hy, v.x.toInt() - hx + size, v.y.toInt() - hy + size)
            pointer.draw(canvas)
        }

        /** A tap draws a 36 dp ring that fades in 200 ms (§3.4); with animations off it shows until the next frame. */
        private fun startTapFade() {
            fade?.cancel()
            if (!Motion.enabled) {
                tapAlpha = 1f
                postDelayed({ tapAlpha = 0f; invalidate() }, Motion.FADE_SLOW)
                return
            }
            fade = ValueAnimator.ofFloat(1f, 0f).apply {
                duration = Motion.FADE_SLOW
                addUpdateListener {
                    tapAlpha = it.animatedValue as Float
                    invalidate()
                }
                start()
            }
        }
    }

    companion object {
        private const val ZOOM = 2f
    }
}
