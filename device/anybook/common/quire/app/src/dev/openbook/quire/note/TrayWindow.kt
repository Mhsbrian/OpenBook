// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.Context
import android.graphics.PixelFormat
import android.os.SystemClock
import android.text.TextUtils
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import com.android.internal.graphics.drawable.BackgroundBlurDrawable
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.R
import dev.openbook.quire.ui.Icon
import dev.openbook.quire.ui.IconButton
import dev.openbook.quire.ui.Leaf
import dev.openbook.quire.ui.Motion
import dev.openbook.quire.ui.Palette
import dev.openbook.quire.ui.QButton
import dev.openbook.quire.ui.Ring
import dev.openbook.quire.ui.RingTarget
import dev.openbook.quire.ui.SpringValue
import dev.openbook.quire.ui.StatusRing
import dev.openbook.quire.ui.TextRole
import dev.openbook.quire.ui.dp
import dev.openbook.quire.ui.dpi
import dev.openbook.quire.ui.hoverable
import dev.openbook.quire.ui.role
import dev.openbook.quire.ui.rounded

/**
 * The tray (docs/quire-design.md §3.5, §3.2 Hidden): every task that is running, waiting for an answer or recently
 * done, above the taskbar's Quire button. A row opens that task's note; New starts a note. It opens with
 * spring.settle on scale 0.9 → 1 and a 120 ms fade, from the bottom centre (§5.2 The tray).
 *
 * Q5 draws the tray in Quire, so it can show Quire's own task state directly; the button it rises from is Launcher3's
 * (the next increment). Until then it opens centred above the taskbar.
 */
class TrayWindow(private val context: Context, private val surface: QuireSurface) {
    private val wm = context.getSystemService(WindowManager::class.java)
    private var root: FrameLayout? = null

    val isShowing: Boolean
        get() = root != null

    fun show() {
        if (root != null) return
        val p = Palette.of(context)
        val card = TrayCard(context, p)
        val r = object : FrameLayout(context) {
            override fun dispatchKeyEvent(event: KeyEvent): Boolean {
                if ((event.keyCode == KeyEvent.KEYCODE_ESCAPE || event.keyCode == KeyEvent.KEYCODE_BACK)) {
                    if (event.action == KeyEvent.ACTION_UP) hide()
                    return true
                }
                return super.dispatchKeyEvent(event)
            }

            override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
                if (ev.actionMasked == MotionEvent.ACTION_OUTSIDE) {
                    hide()
                    return true
                }
                return super.dispatchTouchEvent(ev)
            }
        }
        // Room for the card's shadow.
        val pad = context.dpi(24f)
        r.setPadding(pad, pad, pad, pad)
        r.clipToPadding = false
        r.addView(card, FrameLayout.LayoutParams(context.dpi(400f), WRAP_CONTENT))
        val bottom = wm.currentWindowMetrics.windowInsets
            .getInsets(WindowInsets.Type.navigationBars() or WindowInsets.Type.tappableElement()).bottom
        val lp = WindowManager.LayoutParams(WRAP_CONTENT, WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT).apply {
            title = "Quire tray"
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = bottom + context.dpi(12f) - pad
            privateFlags = privateFlags or WindowManager.LayoutParams.PRIVATE_FLAG_SYSTEM_APPLICATION_OVERLAY
            fitInsetsTypes = 0
            windowAnimations = 0
        }
        wm.addView(r, lp)
        root = r
        Log.i(TAG, "note: tray shown with ${surface.tasks.size} tasks")
        card.pivotX = context.dp(200f)
        card.post {
            card.pivotY = card.height.toFloat()
            card.alpha = 0f
            Motion.fade(card, 1f)
            val s = SpringValue(Motion.SETTLE, 0.9f, 0.002f) { v -> card.scaleX = v; card.scaleY = v }
            s.snapTo(0.9f)
            s.animateTo(1f)
            card.focusFirst()
        }
    }

    fun hide() {
        val r = root ?: return
        runCatching { wm.removeView(r) }
        root = null
        Log.i(TAG, "note: tray hidden")
    }

    private inner class TrayCard(context: Context, private val p: Palette) : LinearLayout(context) {
        private var firstRow: View? = null

        init {
            orientation = VERTICAL
            setPadding(dpi(8f), dpi(8f), dpi(8f), dpi(8f))
            elevation = dp(12f)
            outlineAmbientShadowColor = p.shadow
            outlineSpotShadowColor = p.shadow
            accessibilityPaneTitle = context.getString(R.string.q_tray)
            addView(LinearLayout(context).apply {
                orientation = HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dpi(10f), dpi(8f), dpi(4f), dpi(6f))
                addView(Leaf(context, 18f), LayoutParams(dpi(18f), dpi(18f)))
                addView(TextView(context).apply {
                    role(TextRole.TITLE, p.onSurface)
                    text = context.getString(R.string.app_name)
                }, LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = dpi(8f) })
                addView(IconButton(context, p, Icons.SETTINGS, context.getString(R.string.q_tray_settings)).apply {
                    isEnabled = false
                }, LayoutParams(dpi(28f), dpi(28f)))
            })
            val tasks = surface.tasks.reversed()
            tasks.forEach { addView(row(it), LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dpi(2f) }) }
            addView(LinearLayout(context).apply {
                orientation = HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dpi(6f), dpi(6f), dpi(6f), dpi(2f))
                addView(QButton(context, p, context.getString(R.string.q_tray_new), QButton.Style.TONAL, Icons.ADD)
                    .apply { setOnClickListener { hide(); surface.invoke("taskbar", Anchor.Taskbar(null), Intake.None) } })
                addView(QButton(context, p, context.getString(R.string.q_tray_history), QButton.Style.TEXT).apply {
                    // History with 24 h of undo lists is the Q6 audit log.
                    isEnabled = false
                }, LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(8f) })
            })
        }

        override fun onAttachedToWindow() {
            super.onAttachedToWindow()
            val b = viewRootImpl?.createBackgroundBlurDrawable()
            background = if (b != null) {
                b.setColor(p.noteBackground)
                b.setCornerRadius(dp(24f))
                b.setBlurRadius(dpi(34f))
                b
            } else {
                rounded(context, p.noteBackground, 24f)
            }
            clipToOutline = true
            outlineProvider = android.view.ViewOutlineProvider.BACKGROUND
        }

        fun focusFirst() {
            firstRow?.requestFocus()
        }

        private fun row(t: Task): View {
            val r = object : LinearLayout(context), RingTarget {
                override val ring = Ring.GAP
                override val ringRadius = context.dp(14f)
            }
            r.orientation = HORIZONTAL
            r.gravity = Gravity.CENTER_VERTICAL
            r.setPadding(dpi(10f), dpi(8f), dpi(10f), dpi(8f))
            r.background = hoverable(context, p.surfaceHigh, 14f)
            r.isFocusable = true
            r.isClickable = true
            val mark = FrameLayout(context)
            when {
                t.needsAnswer -> mark.addView(Icon(context, Icons.SHIELD, 20f, p.primary, filled = true))
                t.running -> mark.addView(StatusRing(context, p).apply { mode = StatusRing.Mode.RUNNING },
                    FrameLayout.LayoutParams(dpi(16f), dpi(16f), Gravity.CENTER))
                t.phase == Task.Phase.DONE -> mark.addView(Icon(context, Icons.CHECK_CIRCLE, 20f, p.success, true))
                t.phase == Task.Phase.ERROR -> mark.addView(Icon(context, Icons.ERROR, 20f, p.error, true))
                else -> mark.addView(Icon(context, Icons.STOP_CIRCLE, 20f, p.tertiary, true))
            }
            r.addView(mark, LayoutParams(dpi(28f), dpi(28f)))
            val status = status(t)
            r.addView(LinearLayout(context).apply {
                orientation = VERTICAL
                addView(TextView(context).apply {
                    role(TextRole(14f, 20f, 600), p.onSurface)
                    text = t.prompt ?: context.getString(R.string.q_tray_new_note)
                    maxLines = 1
                    ellipsize = TextUtils.TruncateAt.END
                })
                addView(TextView(context).apply {
                    role(TextRole.META, p.onSurfaceVariant)
                    text = status
                    maxLines = 1
                    ellipsize = TextUtils.TruncateAt.END
                })
            }, LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = dpi(10f) })
            t.agent?.let { a ->
                r.addView(TextView(context).apply {
                    role(TextRole.META_MEDIUM, p.onSurfaceVariant)
                    text = a.name
                    background = rounded(context, p.surfaceHigh, 10f)
                    setPadding(dpi(8f), dpi(3f), dpi(8f), dpi(3f))
                }, LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(8f) })
            }
            r.addView(Icon(context, Icons.CHEVRON_RIGHT, 18f, p.onSurfaceVariant),
                LayoutParams(dpi(18f), dpi(18f)).apply { marginStart = dpi(4f) })
            r.contentDescription = listOfNotNull(t.prompt, status, t.agent?.name).joinToString(". ")
            r.setOnClickListener {
                hide()
                surface.reopen(t)
            }
            if (firstRow == null) firstRow = r
            return r
        }

        /** The row's status line (§3.5): needs your answer · running · done N min ago. */
        private fun status(t: Task): String {
            val now = SystemClock.elapsedRealtime()
            val consent = t.blocks.filterIsInstance<Block.Consent>().lastOrNull { !it.answered }
            return when {
                t.needsAnswer -> listOfNotNull(context.getString(R.string.q_tray_needs_answer), consent?.title)
                    .joinToString(" · ")
                t.running -> t.footer(now)
                t.phase == Task.Phase.DONE -> {
                    val mins = ((now - t.endedAt) / 60000).toInt()
                    if (mins < 1) context.getString(R.string.q_tray_done_now)
                    else context.resources.getQuantityString(R.plurals.q_tray_done_ago, mins, mins)
                }
                else -> t.footer(now)
            }
        }
    }
}
