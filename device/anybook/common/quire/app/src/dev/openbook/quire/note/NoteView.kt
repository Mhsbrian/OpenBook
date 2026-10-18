// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.Context
import android.graphics.Canvas
import android.graphics.Outline
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.drawable.Drawable
import android.text.Editable
import android.text.InputType
import android.text.TextUtils
import android.text.TextWatcher
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.ViewOutlineProvider
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.android.internal.graphics.drawable.BackgroundBlurDrawable
import dev.openbook.quire.R
import dev.openbook.quire.ui.Avatar
import dev.openbook.quire.ui.RingTarget
import dev.openbook.quire.ui.Icon
import dev.openbook.quire.ui.IconButton
import dev.openbook.quire.ui.Leaf
import dev.openbook.quire.ui.Motion
import dev.openbook.quire.ui.Palette
import dev.openbook.quire.ui.Ring
import dev.openbook.quire.ui.TextRole
import dev.openbook.quire.ui.dp
import dev.openbook.quire.ui.dpi
import dev.openbook.quire.ui.hoverable
import dev.openbook.quire.ui.kbd
import dev.openbook.quire.ui.role
import dev.openbook.quire.ui.rounded

/**
 * The note (docs/quire-design.md §3.1): header, prompt, body, suggestions, composer and footer in one card, or the
 * mirror (§3.4) in the same card, grown. [bind] reconciles the card with a [Task]. The card is laid out at its final
 * size; [NoteRoot] reveals it with spring.settle from the old size to the new (§5.2 Settle), so content never slides.
 */
class NoteCard(context: Context, val env: NoteEnv, private val actions: Actions) : ViewGroup(context) {
    interface Actions {
        fun send(text: String)
        fun escape()
        fun hide()
        fun close()
        fun openPicker(anchor: View)
        fun mirrorAction(action: MirrorPanel.Action)
        fun addScreen()
    }

    private val p = env.palette
    var widthDp = WIDTH
        private set
    var maxHeight = Int.MAX_VALUE

    // Header (§3.1): leaf · agent chip · Hide · Close.
    private val leaf = Leaf(context, 22f)
    private val avatar = Avatar(context, 18f, 9.5f)
    private val agentName = env.text(TextRole.CHIP, p.onSurface)
    private val agentWhere = env.text(TextRole(13f, 20f, 400), p.onSurfaceVariant)
    val agentChip: LinearLayout = object : LinearLayout(context), RingTarget {
        override val ring = Ring.GAP
        override val ringRadius = context.dp(14f)
    }.apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dpi(6f), 0, dpi(4f), 0)
        background = hoverable(context, p.surfaceHigh, 14f)
        isFocusable = true
        isClickable = true
        addView(avatar, LinearLayout.LayoutParams(dpi(18f), dpi(18f)))
        addView(agentName, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(6f) })
        addView(agentWhere, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(5f) })
        addView(Icon(context, Icons.ARROW_DROP_DOWN, 18f, p.onSurfaceVariant),
            LinearLayout.LayoutParams(dpi(18f), dpi(18f)).apply { marginStart = dpi(2f) })
        setOnClickListener { actions.openPicker(this) }
    }
    private val hideButton = IconButton(context, p, Icons.OPEN_IN_NEW_DOWN, context.getString(R.string.q_a11y_hide))
        .apply { setOnClickListener { actions.hide() } }
    private val closeButton = IconButton(context, p, Icons.CLOSE, context.getString(R.string.q_close)).apply {
        setOnClickListener { actions.close() }
    }
    private val header = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dpi(16f), dpi(12f), dpi(12f), 0)
        minimumHeight = dpi(44f)
        addView(leaf, LinearLayout.LayoutParams(dpi(22f), dpi(22f)))
        addView(agentChip, LinearLayout.LayoutParams(WRAP_CONTENT, dpi(28f)).apply { marginStart = dpi(8f) })
        addView(View(context), LinearLayout.LayoutParams(0, 1, 1f))
        addView(hideButton, LinearLayout.LayoutParams(dpi(32f), dpi(32f)).apply { marginEnd = dpi(4f) })
        addView(closeButton, LinearLayout.LayoutParams(dpi(32f), dpi(32f)))
    }

    // Prompt (§3.1): intake chip and the person's words.
    private val intakeChip = IntakeChip(env) { task?.removeIntake() }
    private val promptText = env.text(TextRole.PROMPT, p.onSurface)
    private val prompt = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dpi(16f), dpi(10f), dpi(16f), dpi(4f))
        addView(intakeChip, LinearLayout.LayoutParams(WRAP_CONTENT, dpi(28f)))
        addView(promptText, env.lp(top = 8f).apply { bottomMargin = dpi(0f) })
    }

    // Body (§3.1): scrolls; header and composer stay.
    private val blocksColumn = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dpi(16f), dpi(8f), dpi(16f), dpi(12f))
    }
    val scroll = object : ScrollView(context) {
        override fun onScrollChanged(l: Int, t: Int, oldl: Int, oldt: Int) {
            super.onScrollChanged(l, t, oldl, oldt)
            atBottom = !canScrollVertically(1)
            updateJump()
            this@NoteCard.invalidate()
        }
    }.apply {
        isVerticalScrollBarEnabled = true
        isFillViewport = false
        overScrollMode = View.OVER_SCROLL_NEVER
        addView(blocksColumn, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        isFocusable = false
        descendantFocusability = ViewGroup.FOCUS_AFTER_DESCENDANTS
    }
    private var atBottom = true
    private val jump = env.text(TextRole.INTAKE, p.inverseOnSurface).apply {
        text = dev.openbook.quire.ui.withIcon(context, Icons.ARROW_DOWNWARD, context.getString(R.string.q_jump), 16f)
        background = rounded(context, p.inverseSurface, 15f)
        gravity = Gravity.CENTER
        setPadding(dpi(10f), 0, dpi(12f), 0)
        elevation = dp(2f)
        visibility = View.GONE
        setOnClickListener { scrollToEnd() }
    }
    private val body = FrameLayout(context).apply {
        addView(scroll, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        addView(jump, FrameLayout.LayoutParams(WRAP_CONTENT, dpi(30f), Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL)
            .apply { bottomMargin = dpi(8f) })
    }
    private val views = LinkedHashMap<Int, BlockView<*>>()

    // Suggestions, composer, footer.
    private val suggest = ButtonRow(context, 6f, false).apply { setPadding(dpi(16f), 0, dpi(16f), dpi(4f)) }
    val field: EditText = object : EditText(context) {
        override fun onKeyPreIme(keyCode: Int, event: KeyEvent): Boolean {
            if (keyCode == KeyEvent.KEYCODE_ESCAPE && event.action == KeyEvent.ACTION_UP) {
                actions.escape()
                return true
            }
            return super.onKeyPreIme(keyCode, event)
        }
    }.apply {
        role(TextRole.FIELD, p.onSurface, env.type)
        setHintTextColor(p.onSurfaceVariant)
        background = null
        setPadding(dpi(14f), dpi(10f), dpi(14f), dpi(10f))
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or
            InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        imeOptions = EditorInfo.IME_ACTION_SEND or EditorInfo.IME_FLAG_NO_FULLSCREEN
        maxLines = 4
        minHeight = dpi(40f)
        isVerticalScrollBarEnabled = true
        contentDescription = null
        textCursorDrawable = rounded(context, p.primary, 1f).apply { setSize(dpi(2f), dpi(16f)) }
        setOnKeyListener { _, keyCode, event ->
            if (keyCode == KeyEvent.KEYCODE_ENTER && event.action == KeyEvent.ACTION_DOWN && !event.isShiftPressed) {
                submit()
                true
            } else {
                false
            }
        }
        setOnEditorActionListener { _, id, _ -> if (id == EditorInfo.IME_ACTION_SEND) { submit(); true } else false }
        addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                task?.draft = s?.toString() ?: ""
                updateSend()
            }
        })
        setOnFocusChangeListener { _, _ -> fieldFrame.refreshDrawableState(); updateFieldFrame() }
    }
    private val fieldFrame = FrameLayout(context).apply { addView(field, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT)) }
    private val mic = object : FrameLayout(context), RingTarget {
        override val ring = Ring.OFFSET
        override val ringRadius = context.dp(20f)
    }.apply {
        addView(Icon(context, Icons.MIC, 20f, p.onSurfaceVariant), FrameLayout.LayoutParams(dpi(40f), dpi(40f)))
        contentDescription = context.getString(R.string.q_a11y_mic)
        isFocusable = true
        isClickable = true
        background = hoverable(context, p.surfaceHigh, 20f)
        // Hold to talk arrives with Q7 (ANAL-221); the button is in its place so focus order is final (§6.2).
        isEnabled = false
        alpha = 0.6f
    }
    private val sendIcon = Icon(context, Icons.ARROW_UPWARD, 20f, p.onPrimary)
    private val send = object : FrameLayout(context), RingTarget {
        override val ring = Ring.OFFSET
        override val ringRadius = context.dp(20f)
    }.apply {
        addView(sendIcon, FrameLayout.LayoutParams(dpi(40f), dpi(40f)))
        contentDescription = context.getString(R.string.q_a11y_send)
        isFocusable = true
        isClickable = true
        setOnClickListener { submit() }
    }
    private val composer = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.BOTTOM
        setPadding(dpi(12f), dpi(8f), dpi(10f), dpi(10f))
        addView(fieldFrame, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        addView(mic, LinearLayout.LayoutParams(dpi(40f), dpi(40f)).apply { marginStart = dpi(6f) })
        addView(send, LinearLayout.LayoutParams(dpi(40f), dpi(40f)).apply { marginStart = dpi(6f) })
    }
    private val footText = env.text(TextRole.META, p.onSurfaceVariant).apply {
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
    }
    private val footKey = kbd(context, p, "Esc")
    private val footAction = env.text(TextRole.META, p.onSurfaceVariant)
    private val footer = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dpi(16f), 0, dpi(16f), dpi(10f))
        minimumHeight = dpi(30f)
        addView(footText, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        addView(footKey)
        addView(footAction, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(6f) })
    }
    val mirrorPanel = MirrorPanel(env) { actions.mirrorAction(it) }

    // Listening (§3.2): seven level bars and the transcript, recognised words in onSurface, the partial ones in
    // onSurfaceVariant.
    private val levels = LevelBars(context, p.primary)
    private val transcript = env.text(TextRole.BODY, p.onSurface).apply {
        accessibilityLiveRegion = ACCESSIBILITY_LIVE_REGION_POLITE
    }
    private val listenRow = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dpi(16f), dpi(4f), dpi(16f), dpi(8f))
        addView(levels, LinearLayout.LayoutParams(dpi(7 * 4f + 6 * 3f), dpi(28f)))
        addView(transcript, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = dpi(12f) })
        visibility = GONE
    }

    /** TalkBack announcements (§6.3): a live region whose text changes, rather than the deprecated announce call. */
    private val announcer = TextView(context).apply {
        setTextColor(0)
        textSize = 1f
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        accessibilityLiveRegion = ACCESSIBILITY_LIVE_REGION_POLITE
    }

    fun announce(text: CharSequence, assertive: Boolean) {
        announcer.accessibilityLiveRegion = if (assertive) ACCESSIBILITY_LIVE_REGION_ASSERTIVE
            else ACCESSIBILITY_LIVE_REGION_POLITE
        announcer.text = text
    }

    private val sections = listOf<View>(header, prompt, listenRow, mirrorPanel, body, suggest, composer, footer)
    var task: Task? = null
        private set
    private var draftShown = 0

    /** The card's visible rect in its own coordinates, set by [NoteRoot] while it reveals a size change. */
    val shown = RectF()
    /**
     * The note's surface: one blurred rounded rect, or, while the mirror shows, four pieces around the mirror. The
     * mirror's surface sits below the window, so a blur over it would blur the live view itself.
     */
    private val surfaces = ArrayList<Drawable>()
    private val hole = RectF()
    private val outlinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(1f)
        color = p.noteOutline
    }
    private val ringPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val radius = dp(RADIUS_DP)

    init {
        sections.forEach { addView(it) }
        addView(announcer)
        env.announce = { announce(it, false) }
        clipChildren = true
        elevation = dp(12f)
        outlineAmbientShadowColor = p.shadow
        outlineSpotShadowColor = p.shadow
        outlineProvider = object : ViewOutlineProvider() {
            override fun getOutline(view: View, outline: Outline) {
                outline.setRoundRect(shown.left.toInt(), shown.top.toInt(), shown.right.toInt(), shown.bottom.toInt(),
                    radius)
            }
        }
        clipToOutline = true
        setWillNotDraw(false)
        isFocusable = false
        descendantFocusability = FOCUS_AFTER_DESCENDANTS
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        accessibilityPaneTitle = context.getString(R.string.app_name)
        viewTreeObserver.addOnGlobalFocusChangeListener { _, _ -> invalidate() }
        updateFieldFrame()
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        // The system's background blur at the shade's radius, under the 92 % note colour (§3.1 Surface).
        surfaces.clear()
        repeat(4) {
            val b = viewRootImpl?.createBackgroundBlurDrawable()
            surfaces += if (b != null) {
                b.setColor(p.noteBackground)
                b.setBlurRadius(dpi(BLUR_DP))
                b
            } else {
                rounded(context, p.noteBackground, 0f)
            }
        }
        background = null
        syncShown()
    }

    /** Called by NoteRoot when the revealed rect moves. */
    fun syncShown() {
        invalidateOutline()
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (surfaces.size < 4) return
        val l = shown.left.toInt()
        val t = shown.top.toInt()
        val r = shown.right.toInt()
        val b = shown.bottom.toInt()
        val mirrorShown = mirrorPanel.visibility == VISIBLE && mirrorPanel.holeIn(this, hole) &&
            hole.top > shown.top && hole.bottom < shown.bottom
        if (!mirrorShown) {
            setPiece(0, l, t, r, b, radius, radius, radius, radius)
            surfaces[0].draw(canvas)
            return
        }
        val ht = hole.top.toInt()
        val hb = hole.bottom.toInt()
        setPiece(0, l, t, r, ht, radius, radius, 0f, 0f)
        setPiece(1, l, hb, r, b, 0f, 0f, radius, radius)
        setPiece(2, l, ht, hole.left.toInt(), hb, 0f, 0f, 0f, 0f)
        setPiece(3, hole.right.toInt(), ht, r, hb, 0f, 0f, 0f, 0f)
        surfaces.forEach { it.draw(canvas) }
    }

    private fun setPiece(i: Int, l: Int, t: Int, r: Int, b: Int, tl: Float, tr: Float, bl: Float, br: Float) {
        val d = surfaces[i]
        d.setBounds(l, t, maxOf(l, r), maxOf(t, b))
        when (d) {
            is BackgroundBlurDrawable -> d.setCornerRadius(tl, tr, bl, br)
            is android.graphics.drawable.GradientDrawable ->
                d.cornerRadii = floatArrayOf(tl, tl, tr, tr, br, br, bl, bl)
        }
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val w = dpi(widthDp.toFloat())
        val cap = minOf(MeasureSpec.getSize(heightMeasureSpec), maxHeight)
        val exact = MeasureSpec.makeMeasureSpec(w, MeasureSpec.EXACTLY)
        var fixed = 0
        for (v in sections) {
            if (v === body || v.visibility == GONE) continue
            v.measure(exact, MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED))
            fixed += v.measuredHeight
        }
        announcer.measure(MeasureSpec.makeMeasureSpec(1, MeasureSpec.EXACTLY),
            MeasureSpec.makeMeasureSpec(1, MeasureSpec.EXACTLY))
        if (body.visibility != GONE) {
            body.measure(exact, MeasureSpec.makeMeasureSpec((cap - fixed).coerceAtLeast(dpi(48f)), MeasureSpec.AT_MOST))
            fixed += body.measuredHeight
        }
        setMeasuredDimension(w, fixed)
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        var y = 0
        for (v in sections) {
            if (v.visibility == GONE) continue
            v.layout(0, y, r - l, y + v.measuredHeight)
            y += v.measuredHeight
        }
        announcer.layout(0, 0, 1, 1)
    }

    override fun dispatchDraw(canvas: Canvas) {
        super.dispatchDraw(canvas)
        val inset = outlinePaint.strokeWidth / 2
        canvas.drawRoundRect(shown.left + inset, shown.top + inset, shown.right - inset, shown.bottom - inset,
            radius, radius, outlinePaint)
        drawFocusRing(canvas)
    }

    /**
     * The keyboard focus ring (§4.2), drawn here around whatever is focused so it can sit outside the view's bounds:
     * 2 dp `primary`, with a 2 dp `surface` gap for buttons. Only in keyboard mode, never on touch or click.
     */
    private fun drawFocusRing(canvas: Canvas) {
        if (isInTouchMode) return
        val f = findFocus() ?: return
        if (f === field || f === this) return
        val ring = (f as? RingTarget) ?: return
        val r = Rect(0, 0, f.width, f.height)
        offsetDescendantRectToMyCoords(f, r)
        val clip = Rect()
        if (!f.getGlobalVisibleRect(clip)) return
        val rf = RectF(r)
        val w = dp(2f)
        canvas.save()
        if (isDescendant(scroll, f)) {
            val s = Rect(0, 0, scroll.width, scroll.height)
            offsetDescendantRectToMyCoords(scroll, s)
            canvas.clipRect(s)
        }
        when (ring.ring) {
            Ring.GAP -> {
                ringPaint.strokeWidth = w
                ringPaint.color = p.surface
                val g = RectF(rf).apply { inset(-w / 2, -w / 2) }
                canvas.drawRoundRect(g, ring.ringRadius + w / 2, ring.ringRadius + w / 2, ringPaint)
                ringPaint.color = p.primary
                val o = RectF(rf).apply { inset(-w * 1.5f, -w * 1.5f) }
                canvas.drawRoundRect(o, ring.ringRadius + w * 1.5f, ring.ringRadius + w * 1.5f, ringPaint)
            }
            Ring.OFFSET -> {
                ringPaint.strokeWidth = w
                ringPaint.color = p.primary
                val o = RectF(rf).apply { inset(-dp(1f) - w / 2, -dp(1f) - w / 2) }
                canvas.drawRoundRect(o, ring.ringRadius + dp(2f), ring.ringRadius + dp(2f), ringPaint)
            }
            Ring.EDGE -> {
                ringPaint.strokeWidth = w
                ringPaint.color = p.primary
                val o = RectF(rf).apply { inset(-w / 2, -w / 2) }
                canvas.drawRoundRect(o, ring.ringRadius + w / 2, ring.ringRadius + w / 2, ringPaint)
            }
        }
        canvas.restore()
    }

    private fun isDescendant(parent: View, v: View): Boolean {
        var c: View? = v
        while (c != null) {
            if (c === parent) return true
            c = c.parent as? View
        }
        return false
    }

    private fun submit() {
        val t = task ?: return
        if (!t.canSend) return
        val text = field.text.toString()
        if (text.isBlank()) return
        field.setText("")
        actions.send(text)
    }

    private fun updateSend() {
        val enabled = task?.canSend == true && field.text.isNotBlank()
        send.background = rounded(context, if (enabled) p.primary else p.surfaceHighest, 20f)
        sendIcon.setTextColor(if (enabled) p.onPrimary else p.onSurfaceVariant)
        send.isEnabled = enabled
    }

    private fun updateFieldFrame() {
        val focused = field.hasFocus()
        fieldFrame.background = rounded(context, p.field, 20f, if (focused) p.primary else 0, if (focused) 2f else 0f)
    }

    private fun updateJump() {
        val t = task
        val streaming = t?.blocks?.lastOrNull() is Block.Answer && t.running
        jump.visibility = if (!atBottom && streaming) View.VISIBLE else View.GONE
    }

    fun scrollToEnd() {
        scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
        atBottom = true
        updateJump()
    }

    fun pageScroll(down: Boolean) {
        scroll.pageScroll(if (down) View.FOCUS_DOWN else View.FOCUS_UP)
    }

    /** Reconciles the card with [t]: the width class, each section's visibility, and the blocks by identity. */
    fun bind(t: Task) {
        val newTask = task !== t
        task = t
        val mirror = t.mirror
        widthDp = when {
            mirror != null -> MIRROR_WIDTH
            t.blocks.any { b -> b is Block.Answer && (b.text.contains("```") || b.text.length > LONG) } ||
                t.blocks.any { b -> b is Block.Consent && (b.diff != null || (b.command?.length ?: 0) > 80) } -> WIDE_WIDTH
            else -> WIDTH
        }

        // Header.
        val agent = t.agent
        leaf.breathing = t.thinking || (mirror != null && t.running && !mirror.paused)
        if (agent != null) {
            avatar.set(agent.initials, agent.color)
            agentName.text = agent.name
            agentWhere.text = "· " + if (t.phase == Task.Phase.NO_AGENT) context.getString(R.string.q_not_connected)
                else agent.where
        } else {
            avatar.set("?", p.outline)
            agentName.text = context.getString(R.string.q_no_agent)
            agentWhere.text = "· " + context.getString(R.string.q_not_connected)
        }
        agentChip.contentDescription = context.getString(R.string.q_a11y_agent, agentName.text, agent?.where ?: "")
        agentChip.isEnabled = !t.running
        hideButton.visibility = if (t.running) VISIBLE else GONE
        closeButton.contentDescription = context.getString(if (t.running) R.string.q_a11y_hide else R.string.q_close)
        closeButton.tooltipText = context.getString(if (t.running) R.string.q_tip_hide else R.string.q_tip_close)
        hideButton.tooltipText = context.getString(R.string.q_tip_hide)

        // Prompt.
        intakeChip.bind(t.intake, removable = t.prompt == null)
        intakeChip.visibility = if (t.intake != null) VISIBLE else GONE
        promptText.text = t.prompt
        promptText.visibility = if (t.prompt != null) VISIBLE else GONE
        prompt.visibility = if (t.intake != null || t.prompt != null) VISIBLE else GONE
        (promptText.layoutParams as LinearLayout.LayoutParams).topMargin = if (t.intake != null) dpi(8f) else 0

        // Listening.
        val l = t.listening
        listenRow.visibility = if (l != null) VISIBLE else GONE
        levels.running = l != null
        if (l != null) {
            transcript.text = android.text.SpannableStringBuilder(l.final).apply {
                val start = length
                append(l.partial)
                setSpan(android.text.style.ForegroundColorSpan(p.onSurfaceVariant), start, length,
                    android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
        }

        // Mirror or body.
        if (mirror != null) {
            mirrorPanel.visibility = VISIBLE
            mirrorPanel.bind(t, mirror)
            body.visibility = GONE
        } else {
            mirrorPanel.visibility = GONE
            mirrorPanel.unbind()
            bindBlocks(t, newTask)
            body.visibility = if (t.blocks.isEmpty() || l != null) GONE else VISIBLE
        }

        // Suggestions.
        val s = t.suggestions
        suggest.removeAllViews()
        s.forEach { (glyph, label) ->
            suggest.addView(SuggestionChip(env, glyph, label) { actions.send(label) })
        }
        suggest.visibility = if (s.isEmpty() || l != null) GONE else VISIBLE

        // Composer.
        composer.visibility = if (t.composerVisible) VISIBLE else GONE
        field.hint = t.placeholder
        if (newTask || t.draftRevision != draftShown || (field.text.toString() != t.draft && !field.hasFocus())) {
            draftShown = t.draftRevision
            field.setText(t.draft)
            field.setSelection(field.text.length)
        }
        field.contentDescription = null
        field.tooltipText = null
        updateSend()

        // Footer.
        footer.visibility = if (mirror != null) GONE else VISIBLE
        tick()
        requestLayout()
        invalidate()
    }

    /** Updates the elapsed time in the footer, once a second while a task runs. */
    fun tick() {
        val t = task ?: return
        footText.text = t.footer()
        footKey.text = "Esc"
        footAction.text = t.escapeHint
        mirrorPanel.tick(t)
    }

    private fun bindBlocks(t: Task, newTask: Boolean) {
        if (newTask) {
            blocksColumn.removeAllViews()
            views.clear()
        }
        val ids = t.blocks.map { it.id }.toSet()
        views.keys.filter { it !in ids }.forEach { blocksColumn.removeView(views.remove(it)!!.view) }
        val wasAtBottom = atBottom
        t.blocks.forEachIndexed { i, b ->
            var v = views[b.id]
            if (v == null) {
                v = BlockView.create(env, b)
                views[b.id] = v
                blocksColumn.addView(v.view, i, env.lp(top = if (i == 0) 0f else 10f))
                // New content fades in at its final position over 120 ms; nothing slides (§5.2 Settle).
                if (!newTask && Motion.enabled) {
                    v.view.alpha = 0f
                    Motion.fade(v.view, 1f)
                }
            } else if (blocksColumn.indexOfChild(v.view) != i) {
                blocksColumn.removeView(v.view)
                blocksColumn.addView(v.view, i, env.lp(top = if (i == 0) 0f else 10f))
            }
            (v.view.layoutParams as LinearLayout.LayoutParams).topMargin = if (i == 0) 0 else dpi(10f)
            v.bindAny(b)
        }
        if (wasAtBottom && t.running) scrollToEnd()
        updateJump()
    }

    /** Moves keyboard focus where §6.2 says, without taking it from someone who is typing. */
    fun focus(where: Task.Focus) {
        val t = task ?: return
        when (where) {
            Task.Focus.KEEP -> {}
            Task.Focus.FIELD -> if (composer.visibility == VISIBLE) field.requestFocus()
            Task.Focus.CONSENT -> {
                if (field.hasFocus() && field.text.isNotEmpty()) return
                val card = views.values.firstOrNull { it is ConsentView }?.view ?: return
                card.post {
                    card.requestFocus()
                    scroll.requestChildRectangleOnScreen(card, android.graphics.Rect(0, 0, card.width, card.height),
                        false)
                }
            }
            Task.Focus.RESULT -> {
                val button = firstButton() ?: return field.requestFocus().let { }
                button.requestFocus()
            }
            Task.Focus.AUTH -> {
                val row = blocksColumn.findViewWithTag<View>("first-row") ?: return
                row.requestFocus()
            }
            Task.Focus.RESUME -> mirrorPanel.focusResume()
        }
        if (t.mirror == null) invalidate()
    }

    private fun firstButton(): View? {
        for (i in blocksColumn.childCount - 1 downTo 0) {
            val v = blocksColumn.getChildAt(i)
            val b = v.getFocusables(View.FOCUS_FORWARD).firstOrNull { it is dev.openbook.quire.ui.QButton }
            if (b != null) return b
        }
        return null
    }

    companion object {
        const val WIDTH = 400
        const val WIDE_WIDTH = 480
        const val MIRROR_WIDTH = 760
        const val RADIUS_DP = 28f
        const val BLUR_DP = 34f
        private const val LONG = 900
    }
}

/** The intake chip (§2 rules): what was taken in, with a button that drops it before sending. */
class IntakeChip(private val env: NoteEnv, private val onRemove: () -> Unit) : LinearLayout(env.context) {
    private val p = env.palette
    private val thumb = ImageView(context).apply {
        scaleType = ImageView.ScaleType.CENTER_CROP
        background = rounded(context, p.surfaceLowest, 6f, p.outlineVariant, 1f)
        clipToOutline = true
    }
    private val glyph = Icon(context, Icons.FORMAT_QUOTE, 16f, p.onSecondaryContainer)
    private val label = env.text(TextRole.INTAKE, p.onSecondaryContainer).apply {
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
    }
    private val remove = object : FrameLayout(context), RingTarget {
        override val ring = Ring.OFFSET
        override val ringRadius = context.dp(10f)
    }.apply {
        addView(Icon(context, Icons.CLOSE, 16f, Palette.withAlpha(p.onSecondaryContainer, 0.7f)),
            FrameLayout.LayoutParams(context.dpi(20f), context.dpi(20f)))
        isFocusable = true
        isClickable = true
        contentDescription = context.getString(R.string.q_a11y_intake_remove)
        setOnClickListener { onRemove() }
    }

    init {
        orientation = HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        addView(thumb, LayoutParams(context.dpi(32f), context.dpi(20f)))
        addView(glyph, LayoutParams(context.dpi(16f), context.dpi(16f)))
        addView(label, LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = context.dpi(8f) })
        addView(remove, LayoutParams(context.dpi(20f), context.dpi(20f)).apply { marginStart = context.dpi(2f) })
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
    }

    fun bind(intake: Intake?, removable: Boolean) {
        val tinted = intake is Intake.Secure || intake is Intake.None
        background = if (tinted) rounded(context, 0, 14f, p.outlineVariant, 1f) else rounded(context, p.secondaryContainer, 14f)
        val fg = if (tinted) p.onSurfaceVariant else p.onSecondaryContainer
        label.setTextColor(fg)
        glyph.setTextColor(fg)
        thumb.visibility = GONE
        glyph.visibility = VISIBLE
        remove.visibility = if (removable && !tinted) VISIBLE else GONE
        setPadding(context.dpi(if (intake is Intake.Window || intake is Intake.Region) 4f else 8f), 0,
            context.dpi(if (remove.visibility == VISIBLE) 4f else 10f), 0)
        when (intake) {
            is Intake.Window -> {
                label.text = intake.name
                showThumb(intake.shot)
                contentDescription = context.getString(R.string.q_a11y_intake_window, intake.name)
            }
            is Intake.Region -> {
                label.text = intake.name
                showThumb(intake.shot)
                contentDescription = context.getString(R.string.q_a11y_intake_window, intake.name)
            }
            is Intake.Selection -> {
                glyph.setGlyph(Icons.FORMAT_QUOTE, false)
                label.text = "“${intake.text.replace('\n', ' ')}”"
                contentDescription = context.getString(R.string.q_a11y_intake_selection, intake.from ?: "",
                    intake.text.take(120))
            }
            Intake.Secure -> {
                glyph.setGlyph(Icons.LOCK, false)
                label.text = context.getString(R.string.q_intake_secure)
                contentDescription = context.getString(R.string.q_a11y_intake_secure)
            }
            Intake.None -> {
                glyph.setGlyph(Icons.ADD_A_PHOTO, false)
                label.text = context.getString(R.string.q_intake_none)
                contentDescription = label.text
            }
            null -> {}
        }
        (label.layoutParams as LayoutParams).marginStart = context.dpi(if (glyph.visibility == VISIBLE &&
            thumb.visibility == GONE) 6f else 8f)
        label.maxWidth = context.dpi(300f)
    }

    private fun showThumb(shot: android.graphics.Bitmap?) {
        glyph.visibility = GONE
        thumb.visibility = VISIBLE
        if (shot != null) thumb.setImageBitmap(shot) else thumb.setImageDrawable(null)
    }
}

/** A suggestion chip (§3.2 Composing): outlined pill, icon and label; Enter sends it. */
class SuggestionChip(env: NoteEnv, glyph: String, label: String, onClick: () -> Unit) :
    TextView(env.context), RingTarget {
    override val ring = Ring.GAP
    override val ringRadius = env.dp(15f)

    init {
        role(TextRole.INTAKE, env.palette.onSurface, env.type)
        text = dev.openbook.quire.ui.withIcon(env.context, glyph, label, 16f)
        gravity = Gravity.CENTER_VERTICAL
        minHeight = env.dpi(30f)
        setPadding(env.dpi(12f), 0, env.dpi(12f), 0)
        val hover = hoverable(env.context, env.palette.surfaceHigh, 15f)
        background = android.graphics.drawable.LayerDrawable(arrayOf(hover,
            rounded(env.context, 0, 15f, env.palette.outlineVariant, 1f)))
        isFocusable = true
        isClickable = true
        contentDescription = label
        setOnClickListener { onClick() }
    }
}

/**
 * The mic level bars (§5.1 loop.levels): 1100 ms ease-in-out per bar, staggered. With animations off they hold the
 * still shape the design shows (§5.3). Q7 will drive them from the microphone's level.
 */
class LevelBars(context: Context, color: Int) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color }
    private val still = floatArrayOf(0.4f, 0.8f, 1f, 0.6f, 0.9f, 0.5f, 0.3f)
    private val delays = floatArrayOf(0f, 0.1f, 0.2f, 0.05f, 0.25f, 0.15f, 0.3f)
    private var anim: android.animation.ValueAnimator? = null
    private var t = 0f

    var running = false
        set(value) {
            if (field == value) return
            field = value
            anim?.cancel()
            anim = null
            if (value && Motion.enabled) {
                anim = android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
                    duration = 1100
                    repeatCount = android.animation.ValueAnimator.INFINITE
                    interpolator = android.view.animation.LinearInterpolator()
                    addUpdateListener { t = it.animatedValue as Float; invalidate() }
                    start()
                }
            }
            invalidate()
        }

    override fun onDetachedFromWindow() {
        running = false
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        val w = dp(4f)
        val gap = dp(3f)
        for (i in 0 until 7) {
            val s = if (anim == null) still[i] else {
                val ph = (t - delays[i] / 1.1f + 1f) % 1f
                val tri = if (ph < 0.5f) ph * 2f else (1f - ph) * 2f
                0.3f + 0.7f * android.view.animation.AccelerateDecelerateInterpolator().getInterpolation(tri)
            }
            val h = height * s
            val x = i * (w + gap)
            canvas.drawRoundRect(x, (height - h) / 2f, x + w, (height + h) / 2f, w / 2f, w / 2f, paint)
        }
    }
}
