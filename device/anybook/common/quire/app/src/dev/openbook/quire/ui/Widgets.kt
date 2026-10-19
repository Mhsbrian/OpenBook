// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.ui

import android.animation.Animator
import android.content.Context
import android.graphics.Canvas
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.TextUtils
import android.text.style.AbsoluteSizeSpan
import android.text.style.TypefaceSpan
import android.util.PathParser
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.TextView

fun Context.dp(v: Float): Float = v * resources.displayMetrics.density
fun Context.dpi(v: Float): Int = Math.round(dp(v))
fun View.dp(v: Float): Float = context.dp(v)
fun View.dpi(v: Float): Int = context.dpi(v)

/** A rounded rectangle background: fill, corner radius in dp (a large value makes a pill) and an optional stroke. */
fun rounded(context: Context, color: Int, radiusDp: Float, strokeColor: Int = 0, strokeDp: Float = 0f) =
    GradientDrawable().apply {
        setColor(color)
        cornerRadius = context.dp(radiusDp)
        if (strokeDp > 0f) setStroke(context.dpi(strokeDp).coerceAtLeast(1), strokeColor)
    }

/** How the note draws the keyboard focus ring around a view (docs/quire-design.md §4.2). */
enum class Ring {
    /** A 2 dp `surface` gap, then 2 dp of `primary`: buttons and chips. */
    GAP,

    /** 2 dp of `primary` at a 1 dp offset: icon buttons. */
    OFFSET,

    /** 2 dp of `primary` on the edge: cards. */
    EDGE,
}

/** Views the note's focus layer draws a ring around. [ringRadius] is the view's own corner radius in px. */
interface RingTarget {
    val ring: Ring
    val ringRadius: Float
}

/** A Material Symbols icon, as text in the bundled subset. */
class Icon(context: Context, glyph: String, sizeDp: Float, color: Int, filled: Boolean = false) :
    TextView(context) {
    init {
        typeface = Type.of(context).symbols
        text = glyph
        setTextSize(TypedValue.COMPLEX_UNIT_PX, context.dp(sizeDp))
        setTextColor(color)
        gravity = Gravity.CENTER
        includeFontPadding = false
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        if (filled) fontVariationSettings = "'FILL' 1"
    }

    fun setGlyph(glyph: String, filled: Boolean) {
        text = glyph
        fontVariationSettings = if (filled) "'FILL' 1" else "'FILL' 0"
    }
}

/** Label text with leading icon glyphs from the symbols font, e.g. "↶ Undo". */
fun withIcon(context: Context, glyph: String?, label: CharSequence, iconDp: Float): CharSequence {
    if (glyph == null) return label
    val b = SpannableStringBuilder()
    b.append(glyph)
    b.setSpan(TypefaceSpan(Type.of(context).symbols), 0, glyph.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
    b.setSpan(AbsoluteSizeSpan(context.dpi(iconDp)), 0, glyph.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
    b.append("  ")
    b.append(label)
    return b
}

/** The note's buttons (§4.2): 36 dp pills, filled, tonal or text, labelled in 13.5 sp medium. */
class QButton(
    context: Context,
    private val palette: Palette,
    label: CharSequence,
    style: Style,
    glyph: String? = null,
) : TextView(context), RingTarget {
    enum class Style { FILLED, TONAL, TEXT, DANGER }

    override val ring = Ring.GAP
    override val ringRadius: Float = context.dp(18f)
    var style: Style = style
        set(value) {
            field = value
            apply()
        }
    private var glyph: String? = glyph
    private var label: CharSequence = label

    init {
        role(TextRole.BUTTON, palette.primary)
        gravity = Gravity.CENTER
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
        minHeight = context.dpi(36f)
        isFocusable = true
        isClickable = true
        apply()
    }

    fun set(label: CharSequence, glyph: String?) {
        this.label = label
        this.glyph = glyph
        apply()
    }

    private fun apply() {
        val (bg, fg) = when (style) {
            Style.FILLED -> palette.primary to palette.onPrimary
            Style.TONAL -> palette.secondaryContainer to palette.onSecondaryContainer
            Style.TEXT -> 0 to palette.primary
            Style.DANGER -> 0 to palette.error
        }
        val side = if (style == Style.TEXT || style == Style.DANGER) 10f else 16f
        setPadding(dpi(if (glyph != null) side - 4f else side), 0, dpi(side), 0)
        background = rounded(context, bg, 18f)
        setTextColor(fg)
        text = withIcon(context, glyph, label, 18f)
        contentDescription = label
    }
}

/** A 32 dp round icon button (§4.2), e.g. the header's Hide and Close. */
class IconButton(context: Context, palette: Palette, glyph: String, description: CharSequence) :
    FrameLayout(context), RingTarget {
    override val ring = Ring.OFFSET
    override val ringRadius: Float = context.dp(16f)
    val icon = Icon(context, glyph, 20f, palette.onSurfaceVariant)

    init {
        addView(icon, LayoutParams(context.dpi(32f), context.dpi(32f), Gravity.CENTER))
        contentDescription = description
        isFocusable = true
        isClickable = true
        background = hoverable(context, palette.surfaceHigh, 16f)
    }
}

/** Transparent at rest, [hover] while the pointer is over it or it is pressed (the prototype's :hover). */
fun hoverable(context: Context, hover: Int, radiusDp: Float, rest: Int = 0) = StateListDrawable().apply {
    addState(intArrayOf(android.R.attr.state_pressed), rounded(context, hover, radiusDp))
    addState(intArrayOf(android.R.attr.state_hovered), rounded(context, hover, radiusDp))
    addState(intArrayOf(), rounded(context, rest, radiusDp))
}

/** A keyboard hint, e.g. "Esc" in the footer (§3.1): 11 sp medium on `surfaceContainerHigh`. */
fun kbd(context: Context, palette: Palette, key: String) = TextView(context).apply {
    role(TextRole.KBD, palette.onSurfaceVariant)
    text = key
    setPadding(context.dpi(5f), context.dpi(3f), context.dpi(5f), context.dpi(3f))
    background = rounded(context, palette.surfaceHigh, 5f)
    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
}

/** An agent's round avatar with its initials (§3.1 header, the picker). */
class Avatar(context: Context, sizeDp: Float, textSp: Float) : TextView(context) {
    init {
        setTextSize(TypedValue.COMPLEX_UNIT_SP, textSp)
        typeface = Type.of(context).bold
        setTextColor(0xFFFFFFFF.toInt())
        gravity = Gravity.CENTER
        includeFontPadding = false
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        layoutParams = FrameLayout.LayoutParams(context.dpi(sizeDp), context.dpi(sizeDp))
    }

    fun set(initials: String, color: Int) {
        text = initials
        background = GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(color)
        }
    }
}

/** Parses an SVG path in a 24×24 viewport. */
private fun svg(d: String): Path = PathParser.createPathFromPathData(d)

/**
 * Quire's leaf (§4.4): a page with its top-right corner folded, the body in the brand gradient and the fold in the
 * spark gradient. OpenBook's own glyph; not a star, a sparkle or a ring of light.
 */
class LeafDrawable : Drawable() {
    private val body = svg("M7.5 3H14l6 6v8.5A3.5 3.5 0 0 1 16.5 21h-9A3.5 3.5 0 0 1 4 17.5v-11A3.5 3.5 0 0 1 7.5 3Z")
    private val fold = svg("M14 3v4.5A1.5 1.5 0 0 0 15.5 9H20Z")
    private val bodyPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        shader = LinearGradient(4f, 3f, 20f, 21f, Palette.BRAND_A, Palette.BRAND_B, Shader.TileMode.CLAMP)
    }
    private val foldPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        shader = LinearGradient(14f, 3f, 20f, 9f, Palette.FOLD_A, Palette.FOLD_B, Shader.TileMode.CLAMP)
    }

    override fun draw(canvas: Canvas) {
        val b = bounds
        canvas.save()
        canvas.translate(b.left.toFloat(), b.top.toFloat())
        canvas.scale(b.width() / 24f, b.height() / 24f)
        canvas.drawPath(body, bodyPaint)
        canvas.drawPath(fold, foldPaint)
        canvas.restore()
    }

    override fun setAlpha(alpha: Int) {
        bodyPaint.alpha = alpha
        foldPaint.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {}

    @Deprecated("Drawable API") override fun getOpacity() = PixelFormat.TRANSLUCENT
}

/** The leaf as a view: [breathing] runs the breathe loop while the agent thinks (§5.1); still with animations off. */
class Leaf(context: Context, sizeDp: Float) : View(context) {
    private var loop: Animator? = null

    init {
        background = LeafDrawable()
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        layoutParams = FrameLayout.LayoutParams(context.dpi(sizeDp), context.dpi(sizeDp))
    }

    var breathing = false
        set(value) {
            if (field == value) return
            field = value
            loop?.cancel()
            loop = if (value) Motion.breathe(this) else null
        }

    override fun onDetachedFromWindow() {
        breathing = false
        super.onDetachedFromWindow()
    }
}

/**
 * The agent's pointer in the mirror (§3.4): OpenBook's arrow with the body in brand blue, so it is never mistaken for
 * the person's own. The hotspot is at (4.33, 3.07) in the 24×24 viewport.
 */
class PointerDrawable : Drawable() {
    private val arrow = svg("M4.33 4.07 Q4.33 3.07 5.02 3.79 L14.27 13.47 Q15.03 14.27 13.93 14.3 L12.77 14.32 " +
        "Q10.93 14.37 9.62 14.64 L8.91 14.79 Q8.03 14.97 7.36 15.57 L5.15 17.54 Q4.33 18.27 4.33 17.17 L4.33 4.07 Z")
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2.2f
        strokeJoin = Paint.Join.ROUND
        strokeCap = Paint.Cap.ROUND
        color = 0xFFFFFFFF.toInt()
        setShadowLayer(1f, 0f, 0.5f, 0x40000000)
    }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Palette.BRAND_B }

    override fun draw(canvas: Canvas) {
        val b = bounds
        canvas.save()
        canvas.translate(b.left.toFloat(), b.top.toFloat())
        canvas.scale(b.width() / 24f, b.height() / 24f)
        canvas.drawPath(arrow, stroke)
        canvas.drawPath(arrow, fill)
        canvas.restore()
    }

    override fun setAlpha(alpha: Int) {
        stroke.alpha = alpha
        fill.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {}

    @Deprecated("Drawable API") override fun getOpacity() = PixelFormat.TRANSLUCENT

    companion object {
        const val HOTSPOT_X = 4.33f / 24f
        const val HOTSPOT_Y = 3.07f / 24f
    }
}

/**
 * A step's status mark (§3.2 Steps): a hollow ring while pending, a spinner while running. Done and failed use the
 * filled check and cross glyphs instead. With animations off the spinner is a still 270° arc (§5.3).
 */
class StatusRing(context: Context, private val palette: Palette) : View(context) {
    enum class Mode { PENDING, RUNNING }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val oval = RectF()
    private var spin: Animator? = null
    var mode = Mode.PENDING
        set(value) {
            field = value
            restart()
            invalidate()
        }

    private fun restart() {
        spin?.cancel()
        rotation = 0f
        spin = if (mode == Mode.RUNNING && isAttachedToWindow) Motion.spin(this) else null
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        restart()
    }

    override fun onDetachedFromWindow() {
        spin?.cancel()
        spin = null
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        if (mode == Mode.PENDING) {
            val r = dp(4f) - dp(0.75f)
            paint.strokeWidth = dp(1.5f)
            paint.color = palette.onSurfaceVariant
            canvas.drawCircle(cx, cy, r, paint)
            return
        }
        val r = dp(6f) - dp(1f)
        oval.set(cx - r, cy - r, cx + r, cy + r)
        paint.strokeWidth = dp(2f)
        paint.color = palette.outlineVariant
        canvas.drawCircle(cx, cy, r, paint)
        paint.color = palette.primary
        canvas.drawArc(oval, -135f, if (spin == null) 270f else 90f, false, paint)
    }
}

/** Typeface span for runs of code inside answers. */
fun codeSpan(context: Context): TypefaceSpan = TypefaceSpan(Type.of(context).code)
