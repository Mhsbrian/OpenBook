// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.Context
import android.graphics.Bitmap
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
 * The note (docs/quire-design.md §3.1): prompt, body, composer and the quiet line in one pane of glass, or the
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
        fun saveFile(name: String, mime: String, text: String)
    }

    private val p = env.palette
    var widthDp = WIDTH
        private set
    var maxHeight = Int.MAX_VALUE

    // There is no header (glass and ink, §1): the agent, what was taken in and how to leave are the quiet line, the last
    // line of the note in every state. The leaf sits in the field.
    private val leaf = Leaf(context, 18f)
    private val avatar = Avatar(context, 16f, 9f)
    private val agentName = env.text(TextRole.META_MEDIUM, p.onSurface).apply {
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
    }
    val agentChip: LinearLayout = object : LinearLayout(context), RingTarget {
        override val ring = Ring.GAP
        override val ringRadius = context.dp(12f)
    }.apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dpi(2f), 0, dpi(6f), 0)
        background = hoverable(context, p.card, 12f)
        isFocusable = true
        isClickable = true
        addView(avatar, LinearLayout.LayoutParams(dpi(16f), dpi(16f)))
        addView(agentName, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(6f) })
        setOnClickListener { actions.openPicker(this) }
    }
    private val closeButton = IconButton(context, p, Icons.CLOSE, context.getString(R.string.q_close)).apply {
        setOnClickListener { actions.close() }
    }

    // What Quire took in, on the quiet line (§3.1).
    private val intakeChip = IntakeChip(env) { task?.removeIntake() }

    // The prompt in ink, with the pen's rule under it (§3.1, §5.2 The words).
    private val promptText = env.text(TextRole.PROMPT, p.onSurface)
    private val rule = InkRule(context, p.primary)
    private val prompt = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dpi(16f), dpi(14f), dpi(16f), dpi(2f))
        addView(promptText, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        addView(rule, LinearLayout.LayoutParams(MATCH_PARENT, dpi(1.5f)).apply { topMargin = dpi(8f) })
    }
    private var ruledPrompt: String? = null

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

    // Composer and the quiet line.
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
        setPadding(dpi(8f), dpi(10f), dpi(6f), dpi(10f))
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
    // The field (§3.1): one pill of paper, 44 dp, radius 22, with the leaf, the words, the mic and send in it.
    private val fieldFrame = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        minimumHeight = dpi(44f)
        setPadding(dpi(12f), 0, dpi(4f), 0)
    }
    private val mic = object : FrameLayout(context), RingTarget {
        override val ring = Ring.OFFSET
        override val ringRadius = context.dp(20f)
    }.apply {
        addView(Icon(context, Icons.MIC, 20f, p.onSurfaceVariant), FrameLayout.LayoutParams(dpi(36f), dpi(36f)))
        contentDescription = context.getString(R.string.q_a11y_mic)
        isFocusable = true
        isClickable = true
        background = hoverable(context, p.card, 18f)
        // Hold to talk arrives with Q7 (ANAL-221); the button is in its place so focus order is final (§6.2).
        isEnabled = false
        alpha = 0.6f
    }
    private val sendIcon = Icon(context, Icons.ARROW_UPWARD, 20f, p.onPrimary)
    private val send = object : FrameLayout(context), RingTarget {
        override val ring = Ring.OFFSET
        override val ringRadius = context.dp(20f)
    }.apply {
        addView(sendIcon, FrameLayout.LayoutParams(dpi(36f), dpi(36f)))
        contentDescription = context.getString(R.string.q_a11y_send)
        isFocusable = true
        isClickable = true
        setOnClickListener { submit() }
    }
    private val composer = FrameLayout(context).apply {
        setPadding(dpi(10f), dpi(8f), dpi(10f), dpi(2f))
        fieldFrame.addView(leaf, LinearLayout.LayoutParams(dpi(18f), dpi(18f)))
        fieldFrame.addView(field, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        fieldFrame.addView(mic, LinearLayout.LayoutParams(dpi(36f), dpi(36f)).apply { marginStart = dpi(2f) })
        fieldFrame.addView(send, LinearLayout.LayoutParams(dpi(36f), dpi(36f)).apply { marginStart = dpi(4f) })
        addView(fieldFrame, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
    }
    private val footText = env.text(TextRole.META, p.onSurfaceVariant).apply {
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
    }
    /** "Save as a file" for a long answer (§3.2 Long output): a quiet text button in the footer. */
    private val footSave = object : TextView(context), RingTarget {
        override val ring = Ring.GAP
        override val ringRadius = context.dp(12f)
    }.apply {
        role(TextRole.META_MEDIUM, p.primary, env.type)
        text = dev.openbook.quire.ui.withIcon(context, Icons.SAVE, context.getString(R.string.q_save_answer), 16f)
        contentDescription = context.getString(R.string.q_save_answer)
        gravity = Gravity.CENTER_VERTICAL
        minHeight = dpi(24f)
        setPadding(dpi(8f), 0, dpi(8f), 0)
        background = hoverable(context, p.surfaceHigh, 12f)
        isFocusable = true
        isClickable = true
        visibility = GONE
        setOnClickListener {
            task?.let { t ->
                actions.saveFile(context.getString(R.string.q_save_answer_name), "text/markdown", t.answersMarkdown())
            }
        }
    }
    private val footKey = kbd(context, p, "Esc")
    private val footAction = env.text(TextRole.META, p.onSurfaceVariant)
    private val dot = env.text(TextRole.META, p.onSurfaceVariant, "·")

    /**
     * The quiet line (§1, §3.1): the agent, what Quire took in, the state, how to leave, and ×. The last line of the
     * note in every state; 12/16 in soft ink.
     */
    private val footer = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dpi(12f), dpi(4f), dpi(8f), dpi(8f))
        minimumHeight = dpi(36f)
        addView(agentChip, LinearLayout.LayoutParams(WRAP_CONTENT, dpi(24f)))
        addView(dot, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(4f) })
        addView(intakeChip, LinearLayout.LayoutParams(WRAP_CONTENT, dpi(24f)).apply { marginStart = dpi(4f) })
        addView(footText, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = dpi(8f) })
        addView(footSave, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginEnd = dpi(4f) })
        addView(footKey)
        addView(footAction, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = dpi(4f) })
        addView(closeButton, LinearLayout.LayoutParams(dpi(28f), dpi(28f)).apply { marginStart = dpi(4f) })
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

    // Glass and ink (§3.1): no header and no suggestions; the quiet line closes every state.
    private val sections = listOf<View>(prompt, listenRow, mirrorPanel, body, composer, footer)
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

    // Glass (§4.1): bloom, the specular line on the top edge, and the holographic rim, whose light turns while the
    // agent works (§5.1 loop.rim) and stands at 200° otherwise.
    private val bloomPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val specularPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(1f)
    }
    private val rimPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(1.5f)
    }
    private val rimMatrix = android.graphics.Matrix()
    private var rimShader: android.graphics.SweepGradient? = null
    private var rimCx = Float.NaN
    private var rimCy = Float.NaN
    private var rimAngle = RIM_REST
    private var rimLoop: android.animation.ValueAnimator? = null

    /** Turns the rim's light while the agent works; still under Remove animations and with blur off (§5.3). */
    private fun rimTurning(on: Boolean) {
        val run = on && Motion.enabled && p.glass && isAttachedToWindow
        if (run == (rimLoop != null)) return
        if (!run) {
            rimLoop?.cancel()
            rimLoop = null
            rimAngle = RIM_REST
            invalidate()
            return
        }
        rimLoop = android.animation.ValueAnimator.ofFloat(0f, 360f).apply {
            duration = RIM_TURN_MS
            repeatCount = android.animation.ValueAnimator.INFINITE
            interpolator = android.view.animation.LinearInterpolator()
            val start = rimAngle
            addUpdateListener {
                rimAngle = (start + it.animatedValue as Float) % 360f
                invalidate()
            }
            start()
        }
    }

    private fun drawGlass(canvas: Canvas) {
        val w = shown.width()
        if (w <= 0f || shown.height() <= 0f) return
        if (p.glass) {
            bloomPaint.shader = android.graphics.RadialGradient(shown.left, shown.top, w * 0.62f, p.bloom,
                android.graphics.Color.TRANSPARENT, android.graphics.Shader.TileMode.CLAMP)
            canvas.drawRoundRect(shown, radius, radius, bloomPaint)
        }
    }

    private fun drawEdges(canvas: Canvas) {
        val inset = dp(0.75f)
        // The pane's edge where it meets the desktop, 1 dp inside the rim.
        canvas.drawRoundRect(shown.left + dp(2f), shown.top + dp(2f), shown.right - dp(2f), shown.bottom - dp(2f),
            radius - dp(2f), radius - dp(2f), outlinePaint)
        if (p.glass) {
            // Light on the top edge, fading towards the corners.
            val y = shown.top + dp(1.5f)
            specularPaint.shader = android.graphics.LinearGradient(shown.left + radius, y, shown.right - radius, y,
                intArrayOf(android.graphics.Color.TRANSPARENT, p.specular, p.specular, android.graphics.Color.TRANSPARENT),
                floatArrayOf(0f, 0.2f, 0.8f, 1f), android.graphics.Shader.TileMode.CLAMP)
            canvas.drawLine(shown.left + radius * 0.6f, y, shown.right - radius * 0.6f, y, specularPaint)
        }
        val cx = shown.centerX()
        val cy = shown.centerY()
        if (rimShader == null || cx != rimCx || cy != rimCy) {
            rimCx = cx
            rimCy = cy
            rimShader = android.graphics.SweepGradient(cx, cy, p.rim + p.rim[0], null)
        }
        rimMatrix.setRotate(rimAngle, cx, cy)
        rimShader!!.setLocalMatrix(rimMatrix)
        rimPaint.shader = rimShader
        canvas.drawRoundRect(shown.left + inset, shown.top + inset, shown.right - inset, shown.bottom - inset,
            radius - inset, radius - inset, rimPaint)
    }

    override fun onDetachedFromWindow() {
        rimLoop?.cancel()
        rimLoop = null
        super.onDetachedFromWindow()
    }

    init {
        sections.forEach { addView(it) }
        addView(announcer)
        env.announce = { announce(it, false) }
        env.save = { name, mime, text -> actions.saveFile(name, mime, text) }
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
        // The system's background blur at the shade's radius, under the note's colour at 80 % (§4.1); with blur off,
        // the colour at 96 % alone (§4.5).
        surfaces.clear()
        repeat(4) {
            val b = if (p.glass) viewRootImpl?.createBackgroundBlurDrawable() else null
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
            drawGlass(canvas)
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
        if (mirrorPanel.visibility != GONE && fixed > cap) {
            // The mirror's pane gives up height until the note fits the display: Stop, Pause and Take over stay in
            // view however many steps there are.
            val over = fixed - cap
            val before = mirrorPanel.measuredHeight
            mirrorPanel.maxFrameHeight = (mirrorPanel.frameHeight() - over).coerceAtLeast(dpi(120f))
            mirrorPanel.measure(exact, MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED))
            fixed += mirrorPanel.measuredHeight - before
        } else if (mirrorPanel.visibility == GONE) {
            mirrorPanel.maxFrameHeight = Int.MAX_VALUE
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
        val task = this.task
        if (task != null && !task.wide && task.mirror == null && body.visibility == VISIBLE &&
            blocksColumn.height > scroll.height + 1 && task.blocks.any { it is Block.Answer }) {
            task.wide = true
            post { this.task?.let { bind(it) } }
        }
    }

    /**
     * A still of the card for Quire's waiting activity beneath the platform's consent dialog (§3.3 rule 5): every
     * section above the composer, as laid out now: header, intake, prompt, steps and the waiting row. No composer,
     * no footer, no focus ring, and no surface (the activity draws the same surface under it).
     */
    fun still(): Bitmap? {
        val bottom = if (composer.visibility != GONE) composer.top else footer.top
        if (width <= 0 || bottom <= 0) return null
        // A block that just arrived is still fading in (§5.2 Settle); the still shows it as it will be.
        for (i in 0 until blocksColumn.childCount) {
            val v = blocksColumn.getChildAt(i)
            if (v.alpha < 1f) {
                v.animate().cancel()
                v.alpha = 1f
            }
        }
        val bmp = Bitmap.createBitmap(width, bottom, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        for (v in sections) {
            if (v === composer || v === footer) break
            if (v.visibility != VISIBLE) continue
            c.save()
            c.translate(v.left.toFloat(), v.top.toFloat())
            v.draw(c)
            c.restore()
        }
        return bmp
    }

    override fun dispatchDraw(canvas: Canvas) {
        super.dispatchDraw(canvas)
        drawEdges(canvas)
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
        send.background = rounded(context, if (enabled) p.primary else 0, 18f)
        sendIcon.setTextColor(if (enabled) p.onPrimary else p.onSurfaceVariant)
        send.isEnabled = enabled
    }

    private fun updateFieldFrame() {
        val focused = field.hasFocus()
        fieldFrame.background = rounded(context, p.field, 22f, if (focused) p.primary else p.cardOutline,
            if (focused) 2f else 1f)
    }

    private fun updateJump() {
        val t = task
        val streaming = t?.blocks?.lastOrNull() is Block.Answer && t.running
        val v = if (!atBottom && streaming) View.VISIBLE else View.GONE
        if (jump.visibility != v) android.util.Log.i(dev.openbook.quire.Quire.TAG,
            "note: jump to latest ${if (v == View.VISIBLE) "shown" else "hidden"}")
        jump.visibility = v
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
        // Wide (480 dp) once a long answer or code arrives (§3.1); the task keeps the width, so the note doesn't
        // flip back and forth while text streams. A body that overflows at 400 dp counts as long (onLayout).
        if (t.blocks.any { b -> b is Block.Answer && (b.text.contains("```") || b.text.length > LONG) } ||
            t.blocks.any { b -> b is Block.Consent && (b.diff != null || (b.command?.length ?: 0) > 80) }) {
            t.wide = true
        }
        widthDp = when {
            mirror != null -> MIRROR_WIDTH
            t.wide -> WIDE_WIDTH
            else -> WIDTH
        }

        // Header.
        val agent = t.agent
        leaf.breathing = t.thinking || (mirror != null && t.running && !mirror.paused)
        if (agent != null) {
            avatar.set(agent.initials, agent.color)
            agentName.text = agent.name
        } else {
            avatar.set("?", p.outline)
            agentName.text = context.getString(R.string.q_no_agent)
        }
        agentChip.contentDescription = context.getString(R.string.q_a11y_agent, agentName.text, agent?.where ?: "")
        agentChip.isEnabled = !t.running
        closeButton.contentDescription = context.getString(if (t.running) R.string.q_a11y_hide else R.string.q_close)
        closeButton.tooltipText = context.getString(if (t.running) R.string.q_tip_hide else R.string.q_tip_close)

        // The quiet line's intake.
        intakeChip.bind(t.intake, removable = t.prompt == null)
        intakeChip.visibility = if (t.intake != null) VISIBLE else GONE
        dot.visibility = intakeChip.visibility

        // The prompt in ink, then the rule drawn under it (§5.2 The words).
        promptText.text = t.prompt
        prompt.visibility = if (t.prompt != null) VISIBLE else GONE
        if (t.prompt != null && t.prompt != ruledPrompt) {
            val fresh = !newTask
            ruledPrompt = t.prompt
            if (fresh && Motion.enabled) {
                promptText.alpha = 0f
                promptText.translationY = dp(2f)
                promptText.animate().alpha(1f).translationY(0f).setDuration(INK_MS).setInterpolator(Motion.STANDARD)
                    .start()
                rule.draw(animated = true)
            } else {
                rule.draw(animated = false)
            }
        }

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

        // The quiet line: in every state but the mirror, which has its own controls.
        footer.visibility = if (mirror != null) GONE else VISIBLE
        rimTurning(t.running && t.phase != Task.Phase.WAITING || t.needsAnswer)
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
        val save = if (t.wide && t.mirror == null && t.blocks.any { b -> b is Block.Answer &&
            b.text.length > LONG }) VISIBLE else GONE
        if (footSave.visibility != save && save == VISIBLE) {
            android.util.Log.i(dev.openbook.quire.Quire.TAG, "note: save as a file offered (width ${widthDp} dp)")
        }
        footSave.visibility = save
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
                    // A destructive question focuses the safe choice (§3.3 rule 2); Enter does nothing until then.
                    card.findViewWithTag<View>(ConsentView.KEEP)?.requestFocus() ?: card.requestFocus()
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
        private const val RIM_REST = 200f
        private const val RIM_TURN_MS = 12_000L
        private const val INK_MS = 160L
        const val WIDTH = 400
        const val WIDE_WIDTH = 480
        const val MIRROR_WIDTH = 760
        const val RADIUS_DP = 28f
        const val BLUR_DP = 34f
        /** Characters past which an answer is long (§3.2 Long output): about eight lines at 480 dp. */
        private const val LONG = 480
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

/**
 * The pen's rule under the sent prompt (§3.1, §4.3 ink.rule): 1.5 dp of `primary` at 55 %, fading to transparent at
 * the right, drawn left to right over 240 ms after a 120 ms delay (§5.1 duration.rule).
 */
class InkRule(context: Context, private val color: Int) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var progress = 0f
    private var anim: android.animation.ValueAnimator? = null

    fun draw(animated: Boolean) {
        anim?.cancel()
        if (!animated || !Motion.enabled) {
            progress = 1f
            invalidate()
            return
        }
        progress = 0f
        anim = android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
            startDelay = 120L
            duration = 240L
            interpolator = android.view.animation.PathInterpolator(0.05f, 0.7f, 0.1f, 1f)
            addUpdateListener {
                progress = it.animatedValue as Float
                invalidate()
            }
            start()
        }
    }

    override fun onDraw(canvas: Canvas) {
        if (width == 0 || progress <= 0f) return
        val w = width * progress
        paint.shader = android.graphics.LinearGradient(0f, 0f, width.toFloat(), 0f,
            Palette.withAlpha(color, 0.55f), android.graphics.Color.TRANSPARENT, android.graphics.Shader.TileMode.CLAMP)
        canvas.drawRect(0f, 0f, w, height.toFloat(), paint)
    }
}

/**
 * The pen's mark on a step (§3.2 Tool steps, §5.2 The marks): the ink dot while it runs, pulsing; a tick drawn as a
 * stroke in `success` when it is done; a cross in `error` when it failed or was interrupted; a small hollow dot while
 * it waits.
 */
class StepMark(context: Context, private val palette: Palette) : View(context) {
    enum class Kind { PENDING, RUNNING, DONE, FAILED }

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val path = android.graphics.Path()
    private val part = android.graphics.Path()
    private val measure = android.graphics.PathMeasure()
    private var kind = Kind.PENDING
    private var drawn = 1f
    private var pulse = 0f
    private var anim: android.animation.ValueAnimator? = null

    fun set(k: Kind, animate: Boolean) {
        if (k == kind && anim != null) return
        val was = kind
        kind = k
        anim?.cancel()
        anim = null
        drawn = 1f
        pulse = 0f
        when {
            k == Kind.RUNNING && Motion.enabled && palette.glass -> anim = android.animation.ValueAnimator.ofFloat(0f, 1f)
                .apply {
                    duration = 900L
                    repeatCount = android.animation.ValueAnimator.INFINITE
                    repeatMode = android.animation.ValueAnimator.REVERSE
                    interpolator = android.view.animation.AccelerateDecelerateInterpolator()
                    addUpdateListener {
                        pulse = it.animatedValue as Float
                        invalidate()
                    }
                    start()
                }
            (k == Kind.DONE || k == Kind.FAILED) && animate && was != k && Motion.enabled -> {
                drawn = 0f
                anim = android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
                    duration = 180L
                    interpolator = android.view.animation.PathInterpolator(0.05f, 0.7f, 0.1f, 1f)
                    addUpdateListener {
                        drawn = it.animatedValue as Float
                        invalidate()
                    }
                    start()
                }
            }
        }
        invalidate()
    }

    override fun onDetachedFromWindow() {
        anim?.cancel()
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        val s = minOf(width, height).toFloat()
        val cx = width / 2f
        val cy = height / 2f
        val d = resources.displayMetrics.density
        when (kind) {
            Kind.PENDING -> {
                stroke.color = palette.onSurfaceVariant
                stroke.strokeWidth = 1.5f * d
                canvas.drawCircle(cx, cy, 3.5f * d, stroke)
            }
            Kind.RUNNING -> {
                // A still dot with a 3 dp halo when loops are off (§5.1 loop.inkdot).
                val still = anim == null
                fill.color = Palette.withAlpha(palette.primary, if (still) 0.3f else 0.18f * (1f - pulse))
                canvas.drawCircle(cx, cy, (if (still) 7f else 4f + 3.5f * pulse) * d, fill)
                fill.color = Palette.withAlpha(palette.primary, 0.9f - 0.35f * pulse)
                canvas.drawCircle(cx, cy, 4f * d * (1f + 0.35f * pulse), fill)
            }
            Kind.DONE, Kind.FAILED -> {
                stroke.color = if (kind == Kind.DONE) palette.success else palette.error
                stroke.strokeWidth = 2f * d
                path.reset()
                if (kind == Kind.DONE) {
                    path.moveTo(cx - s * 0.28f, cy + s * 0.02f)
                    path.lineTo(cx - s * 0.08f, cy + s * 0.22f)
                    path.lineTo(cx + s * 0.30f, cy - s * 0.20f)
                } else {
                    path.moveTo(cx - s * 0.22f, cy - s * 0.22f)
                    path.lineTo(cx + s * 0.22f, cy + s * 0.22f)
                    path.moveTo(cx + s * 0.22f, cy - s * 0.22f)
                    path.lineTo(cx - s * 0.22f, cy + s * 0.22f)
                }
                if (drawn >= 1f) {
                    canvas.drawPath(path, stroke)
                } else {
                    // Drawn as a stroke from its start to its end (§5.2).
                    measure.setPath(path, false)
                    var left = drawn * run { var t = 0f; do { t += measure.length } while (measure.nextContour()); t }
                    measure.setPath(path, false)
                    do {
                        val len = measure.length
                        part.reset()
                        measure.getSegment(0f, minOf(len, left), part, true)
                        canvas.drawPath(part, stroke)
                        left -= len
                    } while (left > 0f && measure.nextContour())
                }
            }
        }
    }
}

/** Ink arriving (§5.1 duration.ink): a span whose alpha rises from 0 to 1 while the new words settle. */
class InkSpan : android.text.style.CharacterStyle(), android.text.style.UpdateAppearance {
    var alpha = 0f

    override fun updateDrawState(tp: android.text.TextPaint) {
        tp.color = Palette.withAlpha(tp.color, android.graphics.Color.alpha(tp.color) / 255f * alpha)
    }
}
