// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.Context
import android.graphics.PixelFormat
import android.graphics.PointF
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Region
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.ViewTreeObserver
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.R
import dev.openbook.quire.ui.Avatar
import dev.openbook.quire.ui.RingTarget
import dev.openbook.quire.ui.Icon
import dev.openbook.quire.ui.Motion
import dev.openbook.quire.ui.Palette
import dev.openbook.quire.ui.Ring
import dev.openbook.quire.ui.SpringValue
import dev.openbook.quire.ui.TextRole
import dev.openbook.quire.ui.dp
import dev.openbook.quire.ui.dpi
import dev.openbook.quire.ui.hoverable
import dev.openbook.quire.ui.role
import dev.openbook.quire.ui.rounded

/**
 * The note's window (docs/quire-design.md §3.1 Layer, §8 Layers). A window of Quire's own uid, because the platform
 * creates a computer-control session only for an owner with a visible non-toast window (§8). It is an application
 * overlay above app windows and below the status bar and system dialogs, as wide as the display and transparent
 * outside the card; only the card (and the agent picker) take touches.
 *
 * It is a *system* application overlay (SYSTEM_APPLICATION_OVERLAY, a signature permission Quire holds as a
 * platform-signed app): the platform's computer-control consent dialog hides ordinary overlays, and the note has to stay
 * visible through that dialog, or the session the person just allowed is refused for want of a visible window. In
 * return the note never covers or competes with that dialog: while it is up the window gives up focus and touch and
 * the card keeps clear of the screen's centre, where the dialog sits ([platformDialog]).
 */
class NoteWindow(private val context: Context, private val surface: Callbacks) {
    interface Callbacks : NoteCard.Actions {
        fun outside()
        fun pickAgent(entry: AgentEntry)
        val agents: AgentDirectory
    }

    private val wm = context.getSystemService(WindowManager::class.java)
    private var root: NoteRoot? = null
    var card: NoteCard? = null
        private set
    var task: Task? = null
        private set
    private var palette: Palette? = null

    val isShowing: Boolean
        get() = root != null

    /**
     * True while a picker the note opened (Save as a file) is up: the note steps aside, invisible, with no focus or
     * touch, and comes back where it was when the picker closes.
     */
    var suspended = false
        set(value) {
            if (field == value) return
            field = value
            root?.let {
                it.visibility = if (value) View.INVISIBLE else View.VISIBLE
                updateParams(it)
            }
        }

    /** True while the platform's computer-control dialog is up: no focus, no touch, clear of the centre. */
    var platformDialog = false
        set(value) {
            if (field == value) return
            field = value
            root?.let { updateParams(it) }
            root?.requestLayout()
        }

    fun show(t: Task, focus: Task.Focus, animate: Boolean = true) {
        val existing = root
        if (existing != null && task === t) {
            update(t, focus)
            return
        }
        if (existing != null) remove()
        val p = Palette.of(context)
        palette = p
        task = t
        val env = NoteEnv(context, p) { task }
        val c = NoteCard(context, env, surface)
        val r = NoteRoot(context, c, t.anchor)
        card = c
        root = r
        c.bind(t)
        val lp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
            PixelFormat.TRANSLUCENT,
        ).apply {
            title = "Quire"
            gravity = Gravity.TOP or Gravity.START
            privateFlags = privateFlags or WindowManager.LayoutParams.PRIVATE_FLAG_SYSTEM_APPLICATION_OVERLAY
            softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING
            layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
            fitInsetsTypes = 0
            windowAnimations = 0
        }
        r.params = lp
        updateParams(r)
        wm.addView(r, lp)
        Log.i(TAG, "note: shown task ${t.id} phase=${t.phase} anchor=${t.anchor.javaClass.simpleName}")
        if (animate) {
            r.unfold { c.focus(focus) }
        } else {
            c.post { c.focus(focus) }
        }
    }

    /** Draws the note again in the current theme, in place (light and dark follow the system, §4.3). */
    fun retheme() {
        val t = task ?: return
        closePicker()
        remove()
        show(t, Task.Focus.KEEP, animate = false)
    }

    /**
     * Runs [action] once the note's first frame is on the display, which is when the platform counts Quire as having
     * a visible window (a computer-control session asked for before that is refused, §8).
     */
    fun whenVisible(action: () -> Unit) {
        val r = root ?: return action()
        r.post {
            r.viewTreeObserver.registerFrameCommitCallback {
                // The frame is submitted; give WM a frame to show the surface.
                r.postDelayed(action, VISIBLE_SETTLE_MS)
            }
            r.invalidate()
        }
    }

    fun update(t: Task, focus: Task.Focus) {
        val c = card ?: return
        if (task !== t) return
        c.bind(t)
        root?.requestLayout()
        c.post { c.focus(focus) }
    }

    fun tick() {
        card?.tick()
    }

    /** Folds the note into its anchor (§5.2 Fold back), then removes the window. */
    fun fold(intoTaskbar: Boolean, done: () -> Unit = {}) {
        val r = root ?: return done()
        closePicker()
        r.fold(intoTaskbar) {
            remove()
            done()
        }
    }

    fun remove() {
        val r = root ?: return
        r.card.mirrorPanel.unbind()
        runCatching { wm.removeView(r) }
        root = null
        card = null
        task = null
        Log.i(TAG, "note: removed")
    }

    private fun updateParams(r: NoteRoot) {
        val lp = r.params ?: return
        val away = platformDialog || suspended
        val focusable = !away
        lp.flags = if (focusable) lp.flags and WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE.inv()
            else lp.flags or WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        // While the platform dialog (or a picker) is up, the person's clicks are for it: no touch, and no
        // outside-touch events (a non-touchable window still gets ACTION_OUTSIDE, which would hide the note).
        lp.flags = if (away) {
            (lp.flags or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE) and
                WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH.inv()
        } else {
            (lp.flags and WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE.inv()) or
                WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH
        }
        r.keepClearOfCentre = platformDialog
        if (r.isAttachedToWindow) wm.updateViewLayout(r, lp)
    }

    // ---------------------------------------------------------------------------------------- the agent picker

    private var picker: View? = null

    fun openPicker(anchor: View) {
        val r = root ?: return
        val t = task ?: return
        if (picker != null) {
            closePicker()
            return
        }
        val p = palette ?: return
        val v = AgentPicker(context, p, surface.agents, t.agent) { entry ->
            closePicker()
            surface.pickAgent(entry)
        }
        picker = v
        r.addPicker(v, anchor)
        v.post { v.focusSelected() }
    }

    fun closePicker(): Boolean {
        val v = picker ?: return false
        root?.removePicker(v)
        picker = null
        card?.agentChip?.requestFocus()
        return true
    }

    val pickerOpen: Boolean
        get() = picker != null

    /** The window's content: a transparent full-display frame that places, reveals, unfolds and folds the card. */
    private inner class NoteRoot(context: Context, val card: NoteCard, var anchor: Anchor) : FrameLayout(context) {
        var params: WindowManager.LayoutParams? = null
        var keepClearOfCentre = false
        private val target = RectF()
        private val from = RectF()
        private val shown = RectF()
        private var origin = PointF()
        private var placed = false
        private var lastWidthDp = 0
        private val reveal = SpringValue(Motion.SETTLE, 1f, 0.001f) { f -> applyReveal(f) }
        private val scale = SpringValue(Motion.UNFOLD, 1f, 0.002f) { s -> applyScale(s) }
        private var pickerView: View? = null
        private var pickerAnchor: View? = null
        private var folding = false
        private var foldTranslate = PointF()

        private val insets = ViewTreeObserver.OnComputeInternalInsetsListener { info ->
            info.setTouchableInsets(ViewTreeObserver.InternalInsetsInfo.TOUCHABLE_INSETS_REGION)
            val region = Region()
            if (!folding) {
                region.op(Rect(shown.left.toInt(), shown.top.toInt(), shown.right.toInt(), shown.bottom.toInt()),
                    Region.Op.UNION)
                pickerView?.let { pv ->
                    region.op(Rect(pv.left, pv.top, pv.right, pv.bottom), Region.Op.UNION)
                }
            }
            info.touchableRegion.set(region)
        }

        init {
            clipChildren = false
            clipToPadding = false
            addView(card, LayoutParams(WRAP_CONTENT, WRAP_CONTENT))
            isFocusable = false
            descendantFocusability = FOCUS_AFTER_DESCENDANTS
        }

        override fun onAttachedToWindow() {
            super.onAttachedToWindow()
            viewTreeObserver.addOnComputeInternalInsetsListener(insets)
        }

        override fun onDetachedFromWindow() {
            viewTreeObserver.removeOnComputeInternalInsetsListener(insets)
            reveal.cancel()
            scale.cancel()
            super.onDetachedFromWindow()
        }

        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            val h = MeasureSpec.getSize(heightMeasureSpec)
            card.maxHeight = if (card.widthDp == NoteCard.MIRROR_WIDTH) Int.MAX_VALUE else (h * MAX_HEIGHT).toInt()
            super.onMeasure(widthMeasureSpec, heightMeasureSpec)
        }

        override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
            val (x, y) = place(card.measuredWidth, card.measuredHeight, r - l, b - t)
            card.layout(x, y, x + card.measuredWidth, y + card.measuredHeight)
            pickerView?.let { pv ->
                val a = pickerAnchor ?: return@let
                val loc = Rect(0, 0, a.width, a.height)
                offsetDescendantRectToMyCoords(a, loc)
                val px = (loc.left - dpi(6f)).coerceIn(0, (r - l) - pv.measuredWidth)
                val py = loc.bottom + dpi(4f)
                pv.layout(px, py, px + pv.measuredWidth, py + pv.measuredHeight)
            }
            val next = RectF(x.toFloat(), y.toFloat(), (x + card.measuredWidth).toFloat(),
                (y + card.measuredHeight).toFloat())
            if (!placed) {
                placed = true
                target.set(next)
                shown.set(next)
                from.set(next)
                lastWidthDp = card.widthDp
                syncCard()
                return
            }
            if (next != target) {
                // Content changed size: reveal from what is shown to the new size (§5.2 Settle), or expand into or
                // out of the mirror with spring.expand (§5.2 Expand into the mirror).
                val expand = (card.widthDp == NoteCard.MIRROR_WIDTH) != (lastWidthDp == NoteCard.MIRROR_WIDTH)
                lastWidthDp = card.widthDp
                from.set(shown)
                target.set(next)
                reveal.snapTo(0f)
                reveal.animateTo(1f, if (expand) Motion.EXPAND else Motion.SETTLE)
            } else {
                syncCard()
            }
        }

        /** §3.1 Placement: beside the pointer (flipping at the right edge, kept above the taskbar), or above the button. */
        private fun place(w: Int, h: Int, W: Int, H: Int): Pair<Int, Int> {
            val ins = rootWindowInsets
            val bottomInset = ins?.getInsets(WindowInsets.Type.navigationBars() or WindowInsets.Type.tappableElement())
                ?.bottom ?: dpi(64f)
            val topInset = ins?.getInsets(WindowInsets.Type.statusBars())?.top ?: dpi(32f)
            val floor = H - bottomInset
            var x: Int
            var y: Int
            when (val a = anchor) {
                is Anchor.Pointer -> {
                    val hx = a.at.x.toInt()
                    val hy = a.at.y.toInt()
                    x = hx + dpi(18f)
                    y = hy + dpi(18f)
                    // Flips left near the right edge, and keeps that side for the task: a mirror that flipped the
                    // note does not send it back across the hotspot when it shrinks again.
                    if (a.flipped || x + w > W - dpi(24f)) {
                        x = hx - dpi(18f) - w
                        a.flipped = true
                    }
                    if (y + h > floor - dpi(16f)) y = maxOf(topInset + dpi(8f), floor - dpi(16f) - h)
                    origin.set(a.at.x, a.at.y)
                }
                is Anchor.Taskbar -> {
                    val cx = a.button?.exactCenterX() ?: (W / 2f)
                    x = (cx - w / 2f).toInt()
                    y = floor - dpi(12f) - h
                    origin.set(cx, floor.toFloat())
                }
            }
            if (keepClearOfCentre) {
                // The platform dialog sits in the middle of the screen; keep the card beside it, never over it.
                val dw = dpi(DIALOG_W)
                val dh = dpi(DIALOG_H)
                val dialog = Rect((W - dw) / 2, (H - dh) / 2, (W + dw) / 2, (H + dh) / 2)
                val me = Rect(x, y, x + w, y + h)
                if (Rect.intersects(me, dialog)) {
                    x = if (me.centerX() < W / 2) dialog.left - dpi(24f) - w else dialog.right + dpi(24f)
                }
            }
            x = x.coerceIn(dpi(8f), maxOf(dpi(8f), W - w - dpi(8f)))
            y = y.coerceIn(topInset, maxOf(topInset, floor - h))
            return x to y
        }

        private fun applyReveal(f: Float) {
            shown.set(from.left + (target.left - from.left) * f, from.top + (target.top - from.top) * f,
                from.right + (target.right - from.right) * f, from.bottom + (target.bottom - from.bottom) * f)
            syncCard()
        }

        private fun syncCard() {
            card.shown.set(shown.left - card.left, shown.top - card.top, shown.right - card.left,
                shown.bottom - card.top)
            card.syncShown()
            card.pivotX = origin.x - card.left
            card.pivotY = origin.y - card.top
        }

        private fun applyScale(s: Float) {
            card.scaleX = s
            card.scaleY = s
            if (folding) {
                // Opacity 1 → 0 over the last 60 % of the travel (§5.2 Fold back).
                val travel = ((1f - s) / (1f - FOLDED)).coerceIn(0f, 1f)
                card.alpha = (1f - ((travel - 0.4f) / 0.6f).coerceIn(0f, 1f))
                card.translationX = foldTranslate.x * travel
                card.translationY = foldTranslate.y * travel
            }
        }

        /** §5.2 Out from the pointer: scale 0.2 → 1 with spring.unfold around the hotspot, opacity over 120 ms. */
        fun unfold(end: () -> Unit) {
            Log.i(TAG, "note: unfold animated=${Motion.enabled}")
            card.alpha = 0f
            card.scaleX = FOLDED
            card.scaleY = FOLDED
            post {
                syncCard()
                if (!Motion.enabled) {
                    card.alpha = 1f
                    scale.snapTo(1f)
                    end()
                    return@post
                }
                Motion.fade(card, 1f)
                scale.snapTo(FOLDED)
                scale.animateTo(1f, Motion.UNFOLD)
                end()
            }
        }

        /** §5.2 Fold back: scale 1 → 0.2 toward the origin with spring.fold; into the taskbar it also travels there. */
        fun fold(intoTaskbar: Boolean, end: () -> Unit) {
            Log.i(TAG, "note: fold into=${if (intoTaskbar) "taskbar" else "anchor"} animated=${Motion.enabled}")
            folding = true
            requestLayout()
            if (intoTaskbar) {
                val ins = rootWindowInsets
                val bottom = ins?.getInsets(WindowInsets.Type.navigationBars() or WindowInsets.Type.tappableElement())
                    ?.bottom ?: dpi(64f)
                val button = PointF(width / 2f, height - bottom / 2f)
                foldTranslate.set(button.x - origin.x, button.y - origin.y)
            } else {
                foldTranslate.set(0f, 0f)
            }
            if (!Motion.enabled) {
                end()
                return
            }
            scale.animateTo(FOLDED, Motion.FOLD) { end() }
        }

        fun addPicker(v: View, anchor: View) {
            pickerView = v
            pickerAnchor = anchor
            addView(v, LayoutParams(dpi(300f), WRAP_CONTENT))
            v.alpha = 0f
            Motion.fade(v, 1f)
        }

        fun removePicker(v: View) {
            removeView(v)
            pickerView = null
            pickerAnchor = null
        }

        override fun dispatchKeyEvent(event: KeyEvent): Boolean {
            if (event.action == KeyEvent.ACTION_DOWN) {
                when (event.keyCode) {
                    KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_BACK -> {
                        if (event.repeatCount == 0) {
                            if (!closePicker()) surface.escape()
                        }
                        return true
                    }
                    KeyEvent.KEYCODE_PAGE_DOWN, KeyEvent.KEYCODE_PAGE_UP -> {
                        card.pageScroll(event.keyCode == KeyEvent.KEYCODE_PAGE_DOWN)
                        return true
                    }
                    KeyEvent.KEYCODE_MOVE_END -> if (event.isCtrlPressed) {
                        card.scrollToEnd()
                        return true
                    }
                }
            }
            if (event.keyCode == KeyEvent.KEYCODE_ESCAPE || event.keyCode == KeyEvent.KEYCODE_BACK) return true
            return super.dispatchKeyEvent(event)
        }

        override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
            if (ev.actionMasked == MotionEvent.ACTION_OUTSIDE) {
                if (!closePicker() && !platformDialog && !suspended) surface.outside()
                return true
            }
            if (ev.actionMasked == MotionEvent.ACTION_DOWN && pickerView != null) {
                val pv = pickerView!!
                if (ev.x < pv.left || ev.x > pv.right || ev.y < pv.top || ev.y > pv.bottom) {
                    closePicker()
                    return true
                }
            }
            return super.dispatchTouchEvent(ev)
        }
    }

    companion object {
        /** The note is never taller than 60 % of the display (§3.1); the mirror is the one exception. */
        private const val MAX_HEIGHT = 0.6f

        /** The scale the note unfolds from and folds to (§5.2). */
        private const val FOLDED = 0.2f

        /** After the first frame is committed, how long until WM has shown the surface. */
        private const val VISIBLE_SETTLE_MS = 150L

        /** The platform consent dialog's footprint the note keeps clear of, generously (dp). */
        private const val DIALOG_W = 600f
        private const val DIALOG_H = 440f
    }
}

/** The agent picker (§3.2 Choosing the agent): grouped by where agents run; sign-in state per agent. */
class AgentPicker(
    context: Context,
    private val p: Palette,
    agents: AgentDirectory,
    selected: AgentEntry?,
    private val onPick: (AgentEntry) -> Unit,
) : LinearLayout(context) {
    private var selectedRow: View? = null

    init {
        orientation = VERTICAL
        background = rounded(context, if (p.dark) p.surfaceHigh else p.surfaceLowest, 16f)
        elevation = context.dp(12f)
        outlineAmbientShadowColor = p.shadow
        outlineSpotShadowColor = p.shadow
        setPadding(dpi(6f), dpi(6f), dpi(6f), dpi(6f))
        accessibilityPaneTitle = context.getString(R.string.q_picker)
        val groups = agents.entries.groupBy { it.endpoint.local }
        for (local in listOf(true, false)) {
            val list = groups[local] ?: continue
            addView(heading(context.getString(if (local) R.string.q_picker_local else R.string.q_picker_paired)))
            list.forEach { addView(item(it, it === selected)) }
        }
        addView(View(context).apply { setBackgroundColor(p.outlineVariant) },
            LayoutParams(LayoutParams.MATCH_PARENT, dpi(1f)).apply { setMargins(0, dpi(4f), 0, dpi(4f)) })
        addView(row(Icon(context, Icons.ADD_CIRCLE, 20f, p.onSurfaceVariant), context.getString(R.string.q_picker_connect),
            context.getString(R.string.q_picker_connect_sub), null, false).apply { isEnabled = false })
    }

    private fun heading(text: String) = TextView(context).apply {
        role(TextRole.HEADING, p.onSurfaceVariant)
        isAllCaps = true
        letterSpacing = 0.05f
        this.text = text
        setPadding(dpi(10f), dpi(8f), dpi(10f), dpi(4f))
        isFocusable = false
        isAccessibilityHeading = true
    }

    private fun item(e: AgentEntry, selected: Boolean): View {
        val status = when {
            e.state == AgentEntry.State.UNREACHABLE -> context.getString(R.string.q_agent_unreachable_short)
            !e.connected -> context.getString(R.string.q_agent_not_connected)
            e.needsSignIn -> context.getString(R.string.q_agent_needs_signin)
            else -> context.getString(R.string.q_agent_ready)
        }
        val sub = if (e.endpoint.local) status else "${e.where.removePrefix("on ")} · $status"
        val (glyph, tint) = when {
            e.state == AgentEntry.State.UNREACHABLE -> Icons.CLOUD_OFF to p.tertiary
            e.needsSignIn -> Icons.KEY to p.tertiary
            else -> Icons.CHECK to p.success
        }
        val v = row(Avatar(context, 24f, 11f).apply { set(e.initials, e.color) }, e.name, sub,
            Icon(context, glyph, 18f, tint), selected)
        if (e.needsSignIn || e.state == AgentEntry.State.UNREACHABLE) v.alpha = 0.6f
        v.setOnClickListener { onPick(e) }
        v.contentDescription = context.getString(R.string.q_a11y_picker_item, e.name, sub)
        if (selected) selectedRow = v
        return v
    }

    private fun row(lead: View, title: String, sub: String?, trailing: View?, selected: Boolean): View {
        val r = object : LinearLayout(context), RingTarget {
            override val ring = Ring.GAP
            override val ringRadius = context.dp(10f)
        }
        r.orientation = HORIZONTAL
        r.gravity = Gravity.CENTER_VERTICAL
        r.setPadding(dpi(10f), dpi(8f), dpi(10f), dpi(8f))
        r.background = if (selected) rounded(context, p.secondaryContainer, 10f) else
            hoverable(context, p.surfaceContainer, 10f)
        r.addView(lead, LayoutParams(dpi(24f), dpi(24f)))
        r.addView(LinearLayout(context).apply {
            orientation = VERTICAL
            addView(TextView(context).apply {
                role(TextRole.LABEL, if (selected) p.onSecondaryContainer else p.onSurface)
                text = title
            })
            if (sub != null) addView(TextView(context).apply {
                role(TextRole.META, p.onSurfaceVariant)
                text = sub
            })
        }, LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = dpi(10f) })
        if (trailing != null) r.addView(trailing, LayoutParams(dpi(18f), dpi(18f)))
        r.isFocusable = true
        r.isClickable = true
        return r
    }

    fun focusSelected() {
        (selectedRow ?: getChildAt(1))?.requestFocus()
    }
}
