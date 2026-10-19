// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.TextUtils
import android.text.style.ForegroundColorSpan
import android.text.style.StrikethroughSpan
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.TextView
import dev.openbook.quire.R
import dev.openbook.quire.ui.Avatar
import dev.openbook.quire.ui.RingTarget
import dev.openbook.quire.ui.Icon
import dev.openbook.quire.ui.IconButton
import dev.openbook.quire.ui.Leaf
import dev.openbook.quire.ui.Motion
import dev.openbook.quire.ui.Palette
import dev.openbook.quire.ui.QButton
import dev.openbook.quire.ui.Ring
import dev.openbook.quire.ui.SpringValue
import dev.openbook.quire.ui.StatusRing
import dev.openbook.quire.ui.TextRole
import dev.openbook.quire.ui.Type
import dev.openbook.quire.ui.dp
import dev.openbook.quire.ui.dpi
import dev.openbook.quire.ui.hoverable
import dev.openbook.quire.ui.role
import dev.openbook.quire.ui.rounded

/** What block views need from the note: colours, type and the task they act on. */
class NoteEnv(val context: Context, val palette: Palette, val task: () -> Task?) {
    val type = Type.of(context)

    /** Speaks [text] through the note's live region (set by NoteCard). */
    var announce: (CharSequence) -> Unit = {}

    /** Saves [text] as a file the person picks (the Storage Access Framework), set by the note's window. */
    var save: (name: String, mime: String, text: String) -> Unit = { _, _, _ -> }
    fun dp(v: Float) = context.dp(v)
    fun dpi(v: Float) = context.dpi(v)

    fun text(role: TextRole, color: Int, value: CharSequence? = null) = TextView(context).apply {
        role(role, color, type)
        if (value != null) text = value
    }

    fun lp(w: Int = MATCH_PARENT, h: Int = WRAP_CONTENT, top: Float = 0f) =
        LinearLayout.LayoutParams(w, h).apply { topMargin = dpi(top) }
}

/** A view for one block; [bind] runs when the block's version changes. */
abstract class BlockView<B : Block>(val env: NoteEnv) {
    abstract val view: View
    var shown = -1
    abstract fun bind(b: B)

    @Suppress("UNCHECKED_CAST")
    fun bindAny(b: Block) {
        if (b.version == shown) return
        shown = b.version
        bind(b as B)
    }

    companion object {
        fun create(env: NoteEnv, b: Block): BlockView<*> = when (b) {
            is Block.Prompt -> PromptView(env)
            is Block.Thinking -> ThinkingView(env)
            is Block.Answer -> AnswerView(env)
            is Block.Steps -> StepsView(env)
            is Block.Plan -> PlanView(env)
            is Block.Consent -> ConsentView(env)
            is Block.Changes -> ChangesView(env)
            is Block.Result -> ResultView(env)
            is Block.Error -> ErrorView(env)
            is Block.Auth -> RowsCardView(env, Icons.KEY)
            is Block.Agents -> RowsCardView(env, Icons.HUB)
            is Block.Image -> ImageBlockView(env)
            is Block.Buttons -> ButtonsView(env)
        }
    }
}

/** A card inside the note (§4.2): 16 dp corners, `card` fill, an outline at 55 % `outlineVariant`. */
open class CardLayout(context: Context, palette: Palette, stroke: Int = palette.cardOutline, strokeDp: Float = 1f) :
    LinearLayout(context), RingTarget {
    override val ring = Ring.EDGE
    override val ringRadius = context.dp(16f)

    private val line = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = context.dp(1f)
        color = palette.paperLine
    }
    private val lit = palette.glass

    init {
        orientation = VERTICAL
        background = rounded(context, palette.card, 16f, stroke, strokeDp)
        setPadding(context.dpi(14f), context.dpi(12f), context.dpi(14f), context.dpi(12f))
        clipToOutline = false
        setWillNotDraw(false)
    }

    /** Paper's lit top edge (§4.2 paper.line), between the corners. */
    override fun onDraw(canvas: android.graphics.Canvas) {
        super.onDraw(canvas)
        if (!lit || width == 0) return
        val r = context.dp(16f)
        val y = context.dp(1.5f)
        canvas.drawLine(r, y, width - r, y, line)
    }
}

/** A card's title row: icon, title (13 sp semibold), and meta at the right. */
fun titleRow(env: NoteEnv, glyph: String, iconColor: Int, title: CharSequence, meta: CharSequence?,
    filled: Boolean = false): LinearLayout = LinearLayout(env.context).apply {
    orientation = LinearLayout.HORIZONTAL
    gravity = Gravity.CENTER_VERTICAL
    addView(Icon(env.context, glyph, 18f, iconColor, filled), LinearLayout.LayoutParams(env.dpi(18f), env.dpi(18f)))
    addView(env.text(TextRole.TITLE, env.palette.onSurface, title).apply {
        maxLines = 2
        ellipsize = TextUtils.TruncateAt.END
    }, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = env.dpi(8f) })
    if (meta != null) {
        addView(env.text(TextRole.META_MEDIUM, env.palette.onSurfaceVariant, meta).apply {
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.MIDDLE
            maxWidth = env.dpi(180f)
        }, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = env.dpi(8f) })
    }
}

/** A row of buttons; [end] right-aligns them. Wraps to a second line when they don't fit (§6.4). */
class ButtonRow(context: Context, private val gapDp: Float, private val end: Boolean) : ViewGroup(context) {
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val w = MeasureSpec.getSize(widthMeasureSpec)
        val gap = context.dpi(gapDp)
        var x = 0
        var y = 0
        var line = 0
        for (i in 0 until childCount) {
            val c = getChildAt(i)
            if (c.visibility == GONE) continue
            c.measure(MeasureSpec.makeMeasureSpec(w, MeasureSpec.AT_MOST), MeasureSpec.UNSPECIFIED)
            if (x > 0 && x + gap + c.measuredWidth > w) {
                y += line + gap
                x = 0
                line = 0
            }
            x += (if (x > 0) gap else 0) + c.measuredWidth
            line = maxOf(line, c.measuredHeight)
        }
        setMeasuredDimension(w, y + line)
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val w = r - l
        val gap = context.dpi(gapDp)
        val rows = ArrayList<MutableList<View>>()
        var x = 0
        var current = ArrayList<View>()
        for (i in 0 until childCount) {
            val c = getChildAt(i)
            if (c.visibility == GONE) continue
            if (x > 0 && x + gap + c.measuredWidth > w) {
                rows += current
                current = ArrayList()
                x = 0
            }
            x += (if (x > 0) gap else 0) + c.measuredWidth
            current += c
        }
        if (current.isNotEmpty()) rows += current
        var y = 0
        val rtl = layoutDirection == LAYOUT_DIRECTION_RTL
        for (row in rows) {
            val total = row.sumOf { it.measuredWidth } + gap * (row.size - 1)
            var cx = if (end != rtl) w - total else 0
            val h = row.maxOf { it.measuredHeight }
            val ordered = if (rtl) row.reversed() else row
            for (c in ordered) {
                c.layout(cx, y + (h - c.measuredHeight) / 2, cx + c.measuredWidth, y + (h + c.measuredHeight) / 2)
                cx += c.measuredWidth + gap
            }
            y += h + gap
        }
    }
}

private class PromptView(env: NoteEnv) : BlockView<Block.Prompt>(env) {
    override val view = env.text(TextRole.PROMPT, env.palette.onSurface)
    override fun bind(b: Block.Prompt) {
        view.text = b.text
    }
}

private class ThinkingView(env: NoteEnv) : BlockView<Block.Thinking>(env) {
    private val leaf = Leaf(env.context, 14f)
    override val view = LinearLayout(env.context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        addView(leaf, LinearLayout.LayoutParams(env.dpi(14f), env.dpi(14f)))
        addView(env.text(TextRole.CHIP, env.palette.onSurfaceVariant, env.context.getString(R.string.q_thinking)),
            LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = env.dpi(8f) })
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
    }

    override fun bind(b: Block.Thinking) {
        leaf.breathing = true
    }
}

/**
 * Streaming text (§3.2): message chunks append; no per-character animation; a 2 dp caret in `primary` blinks at 1 Hz
 * while text arrives (still with animations off). Fenced code becomes code blocks (§3.2 Code).
 */
class AnswerView(env: NoteEnv) : BlockView<Block.Answer>(env) {
    override val view = LinearLayout(env.context).apply { orientation = LinearLayout.VERTICAL }

    /** How much of the last text segment had arrived, for the ink of what arrives next (§5.2 The words). */
    private var inked = 0
    private var inkedIndex = -1

    private var caretOn = true
    private var streaming = false
    private val blink = object : Runnable {
        override fun run() {
            caretOn = !caretOn
            view.findViewWithTag<CaretText>(CARET)?.invalidate()
            if (streaming && Motion.enabled) view.postDelayed(this, Motion.CARET / 2)
        }
    }

    override fun bind(b: Block.Answer) {
        val segments = Markdown.parse(env.context, env.palette, b.text.toString())
        streaming = b.streaming
        // Reuse views in place so focus and scroll stay put while text streams.
        while (view.childCount > segments.size) view.removeViewAt(view.childCount - 1)
        segments.forEachIndexed { i, s ->
            val existing = view.getChildAt(i)
            when (s) {
                is Markdown.Segment.Text -> {
                    val tv = existing as? CaretText ?: CaretText(env).also { replace(i, it) }
                    tv.text = ink(i, s.text, b.streaming && i == segments.size - 1)
                    tv.tag = null
                }
                is Markdown.Segment.Code -> {
                    val cv = existing?.getTag(R.id.q_code) as? CodeBlock ?: CodeBlock(env).also { replace(i, it.view) }
                    cv.set(s.language, s.source)
                }
            }
        }
        for (i in 0 until view.childCount) (view.getChildAt(i) as? CaretText)?.showCaret = { false }
        val last = view.getChildAt(view.childCount - 1) as? CaretText
        last?.tag = CARET
        last?.showCaret = { streaming && caretOn }
        view.removeCallbacks(blink)
        caretOn = true
        if (streaming && Motion.enabled) view.postDelayed(blink, Motion.CARET / 2)
        view.contentDescription = null
    }

    /**
     * The words that arrived since the last chunk rise into place as ink (§5.1 duration.ink): an [InkSpan] over the new
     * range, its alpha 0 → 1 over 160 ms. Text that is already there never moves. At most six fades in flight; past
     * that, new text appears at once so it never lags the agent.
     */
    private fun ink(index: Int, text: CharSequence, live: Boolean): CharSequence {
        if (!Motion.enabled || !live) {
            inked = text.length
            inkedIndex = index
            return text
        }
        val from = if (index == inkedIndex) inked.coerceAtMost(text.length) else 0
        inkedIndex = index
        inked = text.length
        val out = android.text.SpannableStringBuilder(text)
        // Fades still running keep their spans on their ranges.
        for ((span, range) in spanRange) {
            if (range.second <= out.length) out.setSpan(span, range.first, range.second,
                android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        if (from < out.length && spanRange.size < MAX_INK) {
            val span = InkSpan()
            spanRange[span] = from to out.length
            out.setSpan(span, from, out.length, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
                duration = INK_MS
                interpolator = Motion.STANDARD
                addUpdateListener {
                    span.alpha = it.animatedValue as Float
                    view.findViewWithTag<CaretText>(CARET)?.invalidate()
                    if (span.alpha >= 1f) spanRange.remove(span)
                }
                start()
            }
        }
        return out
    }

    private val spanRange = HashMap<InkSpan, Pair<Int, Int>>()

    private fun replace(i: Int, v: View) {
        if (i < view.childCount) view.removeViewAt(i)
        view.addView(v, i, env.lp(top = if (i == 0) 0f else 8f))
    }

    companion object {
        private const val CARET = "caret"
        private const val INK_MS = 160L
        private const val MAX_INK = 6
    }
}

/** Answer text that can draw the streaming caret after its last character. */
class CaretText(private val env: NoteEnv) : TextView(env.context) {
    var showCaret: () -> Boolean = { false }
    private val paint = Paint().apply { color = env.palette.primary }

    init {
        role(TextRole.BODY, env.palette.onSurface, env.type)
        breakStrategy = android.text.Layout.BREAK_STRATEGY_HIGH_QUALITY
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (!showCaret()) return
        val l = layout ?: return
        val line = l.lineCount - 1
        if (line < 0) return
        val x = totalPaddingLeft + l.getLineRight(line) + env.dp(2f)
        val base = totalPaddingTop + l.getLineBaseline(line)
        canvas.drawRoundRect(x, base - env.dp(13f), x + env.dp(2f), base + env.dp(3f), env.dp(1f), env.dp(1f), paint)
    }
}

/** A code block (§3.2 Code): Google Sans Code 12.5/18 on `inverseSurface` (light) or `surfaceContainerLowest` (dark). */
class CodeBlock(private val env: NoteEnv) {
    private val p = env.palette
    private val bg = if (p.dark) p.surfaceLowest else p.inverseSurface
    private val fg = if (p.dark) p.onSurface else p.inverseOnSurface
    private val lang = env.text(TextRole.HEADING, Palette.withAlpha(fg, 0.75f)).apply { isAllCaps = true }
    private var source = ""
    private val code = TextView(env.context).apply {
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
        setLineHeight(TypedValue.COMPLEX_UNIT_SP, 18f)
        typeface = env.type.code
        setTextColor(fg)
        setHorizontallyScrolling(true)
        setPadding(env.dpi(14f), env.dpi(4f), env.dpi(14f), env.dpi(12f))
    }
    private val copy = IconButton(env.context, env.palette, Icons.CONTENT_COPY,
        env.context.getString(R.string.q_copy_code)).apply {
        icon.setTextColor(fg)
        icon.setTextSize(TypedValue.COMPLEX_UNIT_PX, env.dp(16f))
        setOnClickListener {
            val cm = env.context.getSystemService(ClipboardManager::class.java)
            cm.setPrimaryClip(ClipData.newPlainText("code", source))
            env.announce(env.context.getString(R.string.q_copied))
        }
    }
    // Focusable so a keyboard can scroll long lines sideways; labelled with the language for TalkBack.
    private val scroller = HorizontalScrollView(env.context).apply {
        isHorizontalScrollBarEnabled = false
        addView(code)
    }
    private val save = QButton(env.context, env.palette, env.context.getString(R.string.q_save_code), QButton.Style.TEXT,
        Icons.SAVE).apply {
        setOnClickListener {
            // The type follows the name, or the document provider appends its own extension (script.sh.txt).
            val name = fileName()
            val mime = android.webkit.MimeTypeMap.getSingleton()
                .getMimeTypeFromExtension(name.substringAfterLast('.')) ?: "application/octet-stream"
            env.save(name, mime, source)
        }
    }
    private val block: LinearLayout = LinearLayout(env.context).apply {
        orientation = LinearLayout.VERTICAL
        background = rounded(env.context, bg, 12f)
        clipToOutline = true
        addView(LinearLayout(env.context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(env.dpi(12f), 0, env.dpi(6f), 0)
            minimumHeight = env.dpi(32f)
            addView(lang, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
            addView(copy, LinearLayout.LayoutParams(env.dpi(32f), env.dpi(32f)))
        })
        addView(scroller)
    }

    /** The block, and under it Save as file (§3.2 Code). Run it is a consent step and comes with Q6's tools. */
    val view: View = LinearLayout(env.context).apply {
        orientation = LinearLayout.VERTICAL
        addView(block, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        addView(ButtonRow(env.context, 8f, false).apply { addView(save) },
            LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = env.dpi(8f) })
        setTag(R.id.q_code, this@CodeBlock)
    }
    private var language = ""

    private fun fileName(): String = "script." + when (language.lowercase()) {
        "bash", "sh", "shell", "zsh" -> "sh"
        "python", "py" -> "py"
        "kotlin", "kt" -> "kt"
        "java" -> "java"
        "javascript", "js" -> "js"
        "typescript", "ts" -> "ts"
        "json" -> "json"
        "html" -> "html"
        "css" -> "css"
        "markdown", "md" -> "md"
        else -> "txt"
    }

    fun set(language: String, src: String) {
        this.language = language
        source = src
        lang.text = language.ifEmpty { env.context.getString(R.string.q_code) }
        code.text = src
        scroller.contentDescription = env.context.getString(R.string.q_a11y_code, language.ifEmpty {
            env.context.getString(R.string.q_code) })
    }
}

/** One line per tool call (§3.2 Steps), or the folded chip "4 steps ✓" once the run is over. */
/**
 * One line per step (§3.2 Tool steps). A long run keeps only its latest [window] lines in view, under one line that
 * counts the earlier ones and opens them on click, so the note never outgrows the screen however long the agent works
 * (ANAL-220: a 102-step run in the mirror ran off the display).
 */
class StepsView(env: NoteEnv, private val window: Int = 5) : BlockView<Block.Steps>(env) {
    override val view = LinearLayout(env.context).apply {
        orientation = LinearLayout.VERTICAL
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
    }
    private val rows = LinkedHashMap<String, StepRow>()
    private var chip: TextView? = null
    private var earlier: TextView? = null

    override fun bind(b: Block.Steps) {
        val folded = b.folded && !b.expanded
        if (folded) {
            view.removeAllViews()
            rows.clear()
            earlier = null
            val failed = b.items.any { it.status == StepStatus.FAILED || it.status == StepStatus.INTERRUPTED }
            view.addView(foldedChip(b, failed), LinearLayout.LayoutParams(WRAP_CONTENT, env.dpi(28f)))
            return
        }
        chip?.let { view.removeView(it) }
        chip = null
        val rolling = !b.folded && !b.expanded && b.items.size > window + 1
        val shownItems = if (rolling) b.items.takeLast(window) else b.items
        // The earlier steps, counted on one line that opens them (§5.2 Settle: nothing slides, the count changes).
        val hidden = b.items.size - shownItems.size
        if (rolling) {
            val line = earlier ?: foldedChip(b, false).also {
                chip = null
                earlier = it
                view.addView(it, 0, LinearLayout.LayoutParams(WRAP_CONTENT, env.dpi(28f)).apply {
                    bottomMargin = env.dpi(2f)
                })
            }
            val ok = b.items.take(hidden).count { it.status == StepStatus.DONE }
            line.text = env.context.resources.getQuantityString(R.plurals.q_steps_earlier, hidden, hidden, ok)
        } else {
            earlier?.let { view.removeView(it) }
            earlier = null
        }
        val base = if (earlier != null) 1 else 0
        val ids = shownItems.map { it.id }.toSet()
        rows.keys.filter { it !in ids }.forEach { view.removeView(rows.remove(it)!!.view) }
        shownItems.forEachIndexed { i, s ->
            val row = rows[s.id] ?: StepRow(env).also {
                rows[s.id] = it
                view.addView(it.view, (base + i).coerceAtMost(view.childCount), LinearLayout.LayoutParams(MATCH_PARENT,
                    WRAP_CONTENT).apply {
                    topMargin = if (i == 0) 0 else env.dpi(2f)
                })
                if (Motion.enabled) {
                    it.view.alpha = 0f
                    Motion.fade(it.view, 1f)
                }
            }
            row.bind(s)
        }
        if (b.folded && b.expanded) {
            view.addView(foldedChip(b, false).also { c -> c.text = withChevron(Icons.EXPAND_LESS, b) },
                LinearLayout.LayoutParams(WRAP_CONTENT, env.dpi(28f)).apply { topMargin = env.dpi(4f) })
        }
        val done = b.items.count { it.status == StepStatus.DONE }
        view.contentDescription = env.context.getString(R.string.q_a11y_steps, done, b.items.size)
    }

    private fun withChevron(chev: String, b: Block.Steps): CharSequence {
        val ok = b.items.count { it.status == StepStatus.DONE }
        val s = SpannableStringBuilder()
        val check = Icons.CHECK_CIRCLE
        s.append(check)
        s.setSpan(android.text.style.TypefaceSpan(env.type.symbols), 0, check.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        s.setSpan(ForegroundColorSpan(env.palette.success), 0, check.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        s.setSpan(android.text.style.AbsoluteSizeSpan(env.dpi(16f)), 0, check.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        s.append("  ").append(env.context.resources.getQuantityString(R.plurals.q_steps, b.items.size, b.items.size))
        if (ok != b.items.size) s.append(" · ").append(env.context.getString(R.string.q_steps_done, ok))
        val st = s.length
        s.append(" ").append(chev)
        s.setSpan(android.text.style.TypefaceSpan(env.type.symbols), st + 1, s.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        s.setSpan(android.text.style.AbsoluteSizeSpan(env.dpi(16f)), st + 1, s.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        return s
    }

    private fun foldedChip(b: Block.Steps, failed: Boolean): TextView {
        val c = object : TextView(env.context), RingTarget {
            override val ring = Ring.GAP
            override val ringRadius = env.dp(14f)
        }
        c.role(TextRole.INTAKE, env.palette.onSurfaceVariant, env.type)
        c.text = withChevron(Icons.EXPAND_MORE, b)
        c.gravity = Gravity.CENTER_VERTICAL
        c.setPadding(env.dpi(8f), 0, env.dpi(10f), 0)
        c.background = rounded(env.context, env.palette.surfaceHigh, 14f)
        c.isFocusable = true
        c.isClickable = true
        c.contentDescription = env.context.getString(R.string.q_a11y_steps_folded, b.items.size)
        c.setOnClickListener {
            b.expanded = !b.expanded
            b.changed()
            env.task()?.let { t -> t.refresh() }
        }
        chip = c
        return c
    }
}

private class StepRow(val env: NoteEnv) {
    private val p = env.palette
    private val mark = StepMark(env.context, p)
    private val kind = Icon(env.context, Icons.MORE_HORIZ, 16f, p.onSurfaceVariant)
    private val title = env.text(TextRole.LABEL, p.onSurface).apply {
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
    }
    private var status: StepStatus? = null
    val view = LinearLayout(env.context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        minimumHeight = env.dpi(28f)
        addView(mark, LinearLayout.LayoutParams(env.dpi(20f), env.dpi(20f)))
        addView(kind, LinearLayout.LayoutParams(env.dpi(16f), env.dpi(16f)).apply { marginStart = env.dpi(10f) })
        addView(title, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = env.dpi(10f) })
    }

    fun bind(s: Step) {
        title.text = s.title
        kind.text = kindIcon(s.kind)
        val was = status
        status = s.status
        // The pen's marks (§5.2): the ink dot while it runs, then a tick or a cross drawn in the same frame.
        val changed = was != null && was != s.status
        when (s.status) {
            StepStatus.PENDING -> {
                mark.set(StepMark.Kind.PENDING, false)
                title.setTextColor(p.onSurfaceVariant)
            }
            StepStatus.RUNNING -> {
                mark.set(StepMark.Kind.RUNNING, false)
                title.setTextColor(p.onSurface)
            }
            StepStatus.DONE -> {
                mark.set(StepMark.Kind.DONE, changed)
                title.setTextColor(p.onSurface)
            }
            StepStatus.FAILED, StepStatus.INTERRUPTED -> {
                mark.set(StepMark.Kind.FAILED, changed)
                title.setTextColor(p.error)
            }
        }
        val state = env.context.getString(when (s.status) {
            StepStatus.PENDING -> R.string.q_step_pending
            StepStatus.RUNNING -> R.string.q_step_running
            StepStatus.DONE -> R.string.q_step_done
            StepStatus.FAILED -> R.string.q_step_failed
            StepStatus.INTERRUPTED -> R.string.q_step_interrupted
        })
        view.contentDescription = "${s.title}, $state"
    }

    companion object {
        fun kindIcon(kind: String) = when (kind) {
            "read" -> Icons.VISIBILITY
            "edit" -> Icons.EDIT
            "delete" -> Icons.DELETE
            "move" -> Icons.DRIVE_FILE_MOVE
            "search" -> Icons.SEARCH
            "execute" -> Icons.TERMINAL
            "think" -> Icons.PSYCHOLOGY
            "fetch" -> Icons.LANGUAGE
            "setting" -> Icons.TUNE
            "app" -> Icons.APPS
            "window" -> Icons.SELECT_WINDOW
            else -> Icons.MORE_HORIZ
        }
    }
}

/** A plan (§3.2 Plan): "Plan · 1 of 4", numbered entries; done entries checked and struck; the active one filled. */
private class PlanView(env: NoteEnv) : BlockView<Block.Plan>(env) {
    private val p = env.palette
    private val list = LinearLayout(env.context).apply { orientation = LinearLayout.VERTICAL }
    private val title = titleRow(env, Icons.CHECKLIST, p.onSurfaceVariant, env.context.getString(R.string.q_plan), "")
    override val view = CardLayout(env.context, p).apply {
        addView(title)
        addView(list, env.lp(top = 8f))
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
    }

    override fun bind(b: Block.Plan) {
        val done = b.entries.count { it.status == "completed" }
        (title.getChildAt(2) as? TextView)?.text = env.context.getString(R.string.q_plan_meta, done, b.entries.size)
        list.removeAllViews()
        b.entries.forEachIndexed { i, e ->
            val state = when (e.status) { "completed" -> "done"; "in_progress" -> "active"; else -> "pending" }
            val n = TextView(env.context).apply {
                role(TextRole.META_BOLD, when (state) {
                    "done" -> p.onSuccessContainer
                    "active" -> p.onPrimary
                    else -> p.onSurfaceVariant
                }, env.type)
                text = if (state == "done") "✓" else "${i + 1}"
                gravity = Gravity.CENTER
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    setColor(when (state) {
                        "done" -> p.successContainer
                        "active" -> p.primary
                        else -> p.surfaceHighest
                    })
                }
            }
            val t = env.text(TextRole.LABEL, if (state == "done") p.onSurfaceVariant else p.onSurface).apply {
                text = if (state == "done") SpannableStringBuilder(e.content).apply {
                    setSpan(StrikethroughSpan(), 0, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                } else e.content
            }
            val row = LinearLayout(env.context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                minimumHeight = env.dpi(26f)
                addView(n, LinearLayout.LayoutParams(env.dpi(20f), env.dpi(20f)))
                addView(t, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = env.dpi(10f) })
                if (e.priority == "high") {
                    addView(env.text(TextRole.META_BOLD, p.tertiary,
                        env.context.getString(R.string.q_priority_high)).apply { isAllCaps = true })
                }
            }
            val stateText = env.context.getString(when (state) {
                "done" -> R.string.q_step_done
                "active" -> R.string.q_plan_active
                else -> R.string.q_step_pending
            })
            row.contentDescription = listOfNotNull("${i + 1}", e.content,
                if (e.priority == "high") env.context.getString(R.string.q_a11y_high) else null, stateText)
                .joinToString(", ")
            list.addView(row, env.lp(top = if (i == 0) 0f else 4f))
        }
        view.contentDescription = env.context.getString(R.string.q_a11y_plan, done, b.entries.size)
    }
}

/** A change row: name, where it lives, old → new as a pill, and an undo button after Allow (§3.2, §3.6). */
fun changeRow(env: NoteEnv, c: Change, undo: (() -> Unit)?): View {
    val p = env.palette
    if (c.old.isEmpty() && c.new.isEmpty()) {
        // The thing itself, on its own row (§3.2 The destructive question): name, then where · size · when.
        return LinearLayout(env.context).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(env.context, p.field, 10f)
            setPadding(env.dpi(10f), env.dpi(8f), env.dpi(10f), env.dpi(8f))
            addView(env.text(TextRole.LABEL_MEDIUM, p.onSurface, c.name))
            addView(env.text(TextRole.META, p.onSurfaceVariant, c.where), env.lp(top = 4f))
            contentDescription = "${c.name}, ${c.where}"
        }
    }
    val old = env.text(TextRole.CHIP_REGULAR, p.onSurfaceVariant).apply {
        text = SpannableStringBuilder(c.old).apply {
            setSpan(StrikethroughSpan(), 0, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
    }
    val nu = env.text(TextRole.TITLE, p.onPrimaryContainer, c.new).apply {
        background = rounded(env.context, p.primaryContainer, 8f)
        setPadding(env.dpi(8f), env.dpi(2f), env.dpi(8f), env.dpi(2f))
    }
    val values = LinearLayout(env.context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        addView(old)
        addView(Icon(env.context, Icons.ARROW_FORWARD, 16f, p.onSurfaceVariant),
            LinearLayout.LayoutParams(env.dpi(16f), env.dpi(16f)).apply { marginStart = env.dpi(6f); marginEnd = env.dpi(6f) })
        addView(nu)
        if (undo != null) addView(IconButton(env.context, p, Icons.UNDO, env.context.getString(R.string.q_undo_one, c.name))
            .apply { setOnClickListener { undo() } },
            LinearLayout.LayoutParams(env.dpi(28f), env.dpi(28f)).apply { marginStart = env.dpi(4f) })
    }
    return LinearLayout(env.context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        background = rounded(env.context, p.field, 10f)
        setPadding(env.dpi(10f), env.dpi(8f), env.dpi(10f), env.dpi(8f))
        addView(LinearLayout(env.context).apply {
            orientation = LinearLayout.VERTICAL
            addView(env.text(TextRole.LABEL_MEDIUM, p.onSurface, c.name))
            addView(env.text(TextRole.META, p.onSurfaceVariant, c.where), env.lp(top = 6f))
        }, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        addView(values, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginStart = env.dpi(12f) })
        contentDescription = env.context.getString(R.string.q_a11y_change, c.name, c.old, c.new)
    }
}

/**
 * Inline consent (§3.3): outlined 1.5 dp in `primary`; names exactly what changes (rows, the command, or the diff);
 * one button per option the agent sent, with the agent's own names, reject first and `allow_once` last. A
 * `reject_always` option sits behind the card's overflow so a mistaken click can't reach it. Nothing is preselected.
 */
class ConsentView(env: NoteEnv) : BlockView<Block.Consent>(env) {
    override val view = CardLayout(env.context, env.palette, env.palette.primary, 1.5f).apply {
        isFocusable = true
        isFocusableInTouchMode = true
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_ASSERTIVE
    }

    override fun bind(b: Block.Consent) {
        val p = env.palette
        val v = view
        v.removeAllViews()
        // The destructive question (§3.2, §3.3 rule 2): paper rimmed in `error`, the verb on `errorContainer`, the safe
        // choice filled and focused first.
        v.background = rounded(env.context, p.card, 16f, if (b.destructive) Palette.withAlpha(p.error, 0.7f) else
            p.primary, 1.5f)
        val head = if (b.destructive) titleRow(env, Icons.DELETE, p.error, b.title, b.meta, filled = true)
            else titleRow(env, Icons.SHIELD, p.primary, b.title, b.meta, filled = true)
        val hidden = b.options.filter { it.kind == "reject_always" }
        if (hidden.isNotEmpty()) {
            head.addView(IconButton(env.context, p, Icons.MORE_VERT, env.context.getString(R.string.q_more_options))
                .apply {
                    setOnClickListener { anchor ->
                        PopupMenu(env.context, anchor).apply {
                            hidden.forEachIndexed { i, o -> menu.add(0, i, i, o.name) }
                            setOnMenuItemClickListener { item ->
                                env.task()?.answer(b, hidden[item.itemId].id)
                                true
                            }
                            show()
                        }
                    }
                }, LinearLayout.LayoutParams(env.dpi(28f), env.dpi(28f)).apply { marginStart = env.dpi(4f) })
        }
        v.addView(head)
        b.rows.forEach { v.addView(changeRow(env, it, null), env.lp(top = 8f)) }
        b.command?.let { cmd ->
            v.addView(TextView(env.context).apply {
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
                setLineHeight(TypedValue.COMPLEX_UNIT_SP, 18f)
                typeface = env.type.code
                setTextColor(p.onSurface)
                text = cmd
                background = rounded(env.context, p.field, 8f)
                setPadding(env.dpi(10f), env.dpi(6f), env.dpi(10f), env.dpi(6f))
            }, env.lp(top = 8f))
        }
        b.diff?.let { lines -> v.addView(diffView(lines), env.lp(top = 8f)) }
        b.why?.let { v.addView(env.text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, it), env.lp(top = 8f)) }
        val row = ButtonRow(env.context, 6f, end = true)
        b.options.filter { it.kind != "reject_always" }.forEach { o ->
            val style = if (!b.destructive) o.style else if (o.kind.startsWith("reject")) QButton.Style.FILLED
                else QButton.Style.DESTRUCTIVE
            row.addView(QButton(env.context, p, o.name, style).apply {
                if (b.destructive && o.kind.startsWith("reject")) tag = KEEP
                setOnClickListener { env.task()?.answer(b, o.id) }
            })
        }
        v.addView(row, env.lp(top = 8f))
        val name = env.task()?.agent?.name ?: ""
        v.contentDescription = env.context.getString(R.string.q_a11y_consent, name, b.title,
            b.options.joinToString(", ") { it.name })
    }

    companion object {
        /** The safe choice on a destructive card, which takes focus first. */
        const val KEEP = "keep"
    }

    private fun diffView(lines: List<DiffLine>): View {
        val p = env.palette
        val col = LinearLayout(env.context).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(env.context, p.field, 8f)
            clipToOutline = true
        }
        for (l in lines) {
            fun codeText(color: Int) = TextView(env.context).apply {
                role(TextRole.CODE, color, env.type)
                typeface = env.type.code
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            }
            // The tint says added or removed; the sign is a quiet gutter, so a line isn't marked twice.
            val sign = codeText(p.onSurfaceVariant).apply {
                text = when (l.kind) {
                    DiffLine.Kind.ADD -> "+"
                    DiffLine.Kind.DEL -> "−"
                    DiffLine.Kind.SKIP -> "⋯"
                    DiffLine.Kind.SAME -> ""
                }
                gravity = Gravity.CENTER
            }
            val line = codeText(if (l.kind == DiffLine.Kind.SKIP) p.onSurfaceVariant else p.onSurface).apply {
                text = l.text
            }
            col.addView(LinearLayout(env.context).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(env.dpi(4f), 0, env.dpi(10f), 0)
                addView(sign, LinearLayout.LayoutParams(env.dpi(16f), WRAP_CONTENT))
                addView(line, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = env.dpi(2f) })
                when (l.kind) {
                    DiffLine.Kind.ADD -> setBackgroundColor(Palette.withAlpha(p.successContainer, 0.55f))
                    DiffLine.Kind.DEL -> setBackgroundColor(Palette.withAlpha(p.errorContainer, 0.35f))
                    else -> {}
                }
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
                contentDescription = when (l.kind) {
                    DiffLine.Kind.ADD -> env.context.getString(R.string.q_a11y_diff_add, l.text)
                    DiffLine.Kind.DEL -> env.context.getString(R.string.q_a11y_diff_del, l.text)
                    else -> l.text
                }
            }, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        }
        return col
    }
}

private class ChangesView(env: NoteEnv) : BlockView<Block.Changes>(env) {
    override val view = CardLayout(env.context, env.palette)
    override fun bind(b: Block.Changes) {
        view.removeAllViews()
        view.addView(titleRow(env, Icons.TUNE, env.palette.onSurfaceVariant, b.title, b.meta))
        b.rows.forEachIndexed { i, row ->
            val undo = if (b.undo && i !in b.undone && b.onUndo != null) ({ b.onUndo.invoke(i) }) else null
            view.addView(changeRow(env, row, undo), env.lp(top = 8f))
        }
    }
}

/** A result line (§3.2 Done, Stopped, waiting for permission, offline): icon, one sentence, a sub-line. */
private class ResultView(env: NoteEnv) : BlockView<Block.Result>(env) {
    private val icon = Icon(env.context, Icons.CHECK_CIRCLE, 20f, env.palette.success, filled = true)
    private val msg = env.text(TextRole.BODY, env.palette.onSurface)
    private val sub = env.text(TextRole.SUB, env.palette.onSurfaceVariant)
    override val view = LinearLayout(env.context).apply {
        orientation = LinearLayout.HORIZONTAL
        addView(icon, LinearLayout.LayoutParams(env.dpi(20f), env.dpi(22f)))
        addView(LinearLayout(env.context).apply {
            orientation = LinearLayout.VERTICAL
            addView(msg)
            addView(sub, env.lp(top = 2f))
        }, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = env.dpi(10f) })
        accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
    }

    override fun bind(b: Block.Result) {
        icon.setGlyph(b.icon, true)
        icon.setTextColor(when (b.tone) {
            Tone.SUCCESS -> env.palette.success
            Tone.WARN -> env.palette.tertiary
            Tone.ERROR -> env.palette.error
        })
        msg.text = b.message
        sub.text = b.sub
        sub.visibility = if (b.sub.isNullOrEmpty()) View.GONE else View.VISIBLE
        view.contentDescription = listOfNotNull(b.message, b.sub).joinToString(". ")
    }
}

/** The error card (§3.2 Error): what stopped, one sentence; details behind a disclosure; Show log · Try again. */
private class ErrorView(env: NoteEnv) : BlockView<Block.Error>(env) {
    override val view = CardLayout(env.context, env.palette, Palette.withAlpha(env.palette.error, 0.5f)).apply {
        accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_ASSERTIVE
    }

    override fun bind(b: Block.Error) {
        val p = env.palette
        view.removeAllViews()
        view.addView(titleRow(env, Icons.ERROR, p.error, b.title, b.meta, filled = true))
        view.addView(env.text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, b.message), env.lp(top = 8f))
        if (b.showDetails && b.details != null) {
            view.addView(TextView(env.context).apply {
                role(TextRole.META, p.onSurfaceVariant, env.type)
                text = b.details
                background = rounded(env.context, p.field, 8f)
                setPadding(env.dpi(10f), env.dpi(8f), env.dpi(10f), env.dpi(8f))
            }, env.lp(top = 8f))
        }
        val row = ButtonRow(env.context, 8f, end = true)
        if (b.details != null) {
            row.addView(QButton(env.context, p, env.context.getString(if (b.showDetails) R.string.q_hide_log else
                R.string.q_show_log), QButton.Style.TEXT).apply {
                setOnClickListener {
                    b.showDetails = !b.showDetails
                    b.changed()
                    env.task()?.refresh()
                }
            })
        }
        row.addView(QButton(env.context, p, env.context.getString(R.string.q_try_again), QButton.Style.TONAL,
            Icons.REFRESH).apply { setOnClickListener { env.task()?.tryAgain() } })
        view.addView(row, env.lp(top = 8f))
        view.contentDescription = "${b.title}. ${b.message}"
    }
}

/** Sign-in methods (§3.2 Agent not signed in) and the agents found (§3.2 No agent connected). */
private class RowsCardView(env: NoteEnv, private val glyph: String) : BlockView<Block>(env) {
    override val view = CardLayout(env.context, env.palette)

    override fun bind(b: Block) {
        val p = env.palette
        val (title, msg, rows) = when (b) {
            is Block.Auth -> Triple(b.title, b.message, b.methods)
            is Block.Agents -> Triple(b.title, b.message, b.agents)
            else -> return
        }
        view.removeAllViews()
        view.addView(titleRow(env, glyph, if (b is Block.Auth) p.onSurfaceVariant else p.onSurfaceVariant, title, null,
            filled = b is Block.Auth))
        view.addView(env.text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, msg), env.lp(top = 8f))
        rows.forEachIndexed { i, r ->
            val row = object : LinearLayout(env.context), RingTarget {
                override val ring = Ring.GAP
                override val ringRadius = env.dp(10f)
            }
            row.orientation = LinearLayout.HORIZONTAL
            row.gravity = Gravity.CENTER_VERTICAL
            row.setPadding(env.dpi(10f), env.dpi(8f), env.dpi(10f), env.dpi(8f))
            row.background = hoverable(env.context, p.surfaceContainer, 10f)
            if (r.initials != null) {
                row.addView(Avatar(env.context, 22f, 10f).apply { set(r.initials, r.color) },
                    LinearLayout.LayoutParams(env.dpi(22f), env.dpi(22f)))
            } else if (r.glyph != null) {
                row.addView(Icon(env.context, r.glyph, 18f, p.onSurfaceVariant),
                    LinearLayout.LayoutParams(env.dpi(18f), env.dpi(18f)))
            }
            row.addView(env.text(TextRole.LABEL, p.onSurface, r.title),
                LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = env.dpi(10f) })
            r.sub?.let { row.addView(env.text(TextRole.META, p.onSurfaceVariant, it)) }
            if (r.onClick != null) {
                row.isFocusable = true
                row.isClickable = true
                row.setOnClickListener { r.onClick.invoke() }
                row.accessibilityDelegate = object : View.AccessibilityDelegate() {
                    override fun onInitializeAccessibilityNodeInfo(host: View, info: AccessibilityNodeInfo) {
                        super.onInitializeAccessibilityNodeInfo(host, info)
                        info.className = android.widget.Button::class.java.name
                    }
                }
            }
            row.contentDescription = listOfNotNull(r.title, r.sub).joinToString(", ")
            row.tag = if (i == 0) FIRST_ROW else null
            view.addView(row, env.lp(top = if (i == 0) 6f else 4f))
        }
    }

    companion object {
        const val FIRST_ROW = "first-row"
    }
}

private class ImageBlockView(env: NoteEnv) : BlockView<Block.Image>(env) {
    private val image = ImageView(env.context).apply {
        scaleType = ImageView.ScaleType.CENTER_CROP
        adjustViewBounds = true
    }
    private val cap = env.text(TextRole.META_MEDIUM, env.palette.inverseOnSurface).apply {
        background = rounded(env.context, env.palette.inverseSurface, 12f)
        setPadding(env.dpi(10f), env.dpi(4f), env.dpi(10f), env.dpi(4f))
    }
    override val view = FrameLayout(env.context).apply {
        background = rounded(env.context, env.palette.surfaceContainer, 12f, env.palette.outlineVariant, 1f)
        clipToOutline = true
        addView(image, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        addView(cap, FrameLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.BOTTOM or Gravity.START).apply {
            setMargins(env.dpi(8f), 0, 0, env.dpi(8f))
        })
        isFocusable = true
        isClickable = true
    }

    override fun bind(b: Block.Image) {
        image.setImageBitmap(b.bitmap)
        image.maxHeight = if (b.expanded) Int.MAX_VALUE else env.dpi(150f)
        cap.text = b.caption
        view.contentDescription = b.caption
        view.setOnClickListener {
            b.expanded = !b.expanded
            b.changed()
            env.task()?.refresh()
        }
    }
}

private class ButtonsView(env: NoteEnv) : BlockView<Block.Buttons>(env) {
    private var row = ButtonRow(env.context, 8f, false)
    override val view = FrameLayout(env.context).apply { addView(row) }

    override fun bind(b: Block.Buttons) {
        view.removeAllViews()
        row = ButtonRow(env.context, 8f, b.end)
        b.actions.forEach { a ->
            row.addView(QButton(env.context, env.palette, a.label, a.style, a.glyph).apply {
                setOnClickListener { a.run() }
            })
        }
        view.addView(row, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
    }
}

/** Typeface for the symbol glyphs, for spans. */
fun symbols(context: Context): Typeface = Type.of(context).symbols
