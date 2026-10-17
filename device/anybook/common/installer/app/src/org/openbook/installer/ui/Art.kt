// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/*
 * Illustrations from docs/installer-design/index.html, drawn from the same SVG path data. All are decorative: the
 * surrounding text carries the meaning, so none has a content description.
 */

private fun path(d: String): Path = PathParser().parsePathString(d).toPath()

// The OpenBook mark (assets/brand/openbook-mark.svg, viewBox 48 x 48): two pages opening from a spine, and a spark.
private val PageLeft = path(
    "M23 40 C17 36 10 35 5 36 C4 36 3.4 35.3 3.5 34.4 L5.6 12.6 C5.7 11.7 6.4 11 7.3 11 C12.6 10.9 18.4 12.7 23 16.6 Z",
)
private val PageRight = path(
    "M25 40 C31 36 38 35 43 36 C44 36 44.6 35.3 44.5 34.4 L42.4 12.6 C42.3 11.7 41.6 11 40.7 11 C35.4 10.9 29.6 12.7 25 16.6 Z",
)
private val Spark = path(
    "M24 2.5 C24.7 6.3 26.2 7.8 30 8.5 C26.2 9.2 24.7 10.7 24 14.5 C23.3 10.7 21.8 9.2 18 8.5 C21.8 7.8 23.3 6.3 24 2.5 Z",
)
private val PageLeftBrush = Brush.linearGradient(
    listOf(Color(0xFF7E8CFF), Color(0xFF4355B9)), start = Offset(3.4f, 10.9f), end = Offset(23f, 40f),
)
private val PageRightBrush = Brush.linearGradient(
    listOf(Color(0xFFD08BFF), Color(0xFF7A4CE0)), start = Offset(44.6f, 10.9f), end = Offset(25f, 40f),
)
private val SparkBrush = Brush.linearGradient(
    listOf(Color(0xFFFFB38A), Color(0xFFFF7A9C)), start = Offset(18f, 2.5f), end = Offset(30f, 14.5f),
)

/** Draws the mark into a [side] x [side] square at [topLeft] (pixels). */
fun DrawScope.drawMark(topLeft: Offset, side: Float) {
    val s = side / 48f
    withTransform({
        translate(topLeft.x, topLeft.y)
        scale(s, s, pivot = Offset.Zero)
    }) {
        drawPath(PageLeft, PageLeftBrush)
        drawPath(PageRight, PageRightBrush)
        drawPath(Spark, SparkBrush)
    }
}

@Composable
fun OpenBookMark(size: Dp, modifier: Modifier = Modifier) {
    Canvas(modifier.size(size)) { drawMark(Offset.Zero, this.size.minDimension) }
}

// Laptop (viewBox 220 x 150)
private val LaptopBase = path("M8 118 H212 L204 136 C203 139 200 141 197 141 H23 C20 141 17 139 16 136 Z")
private val ScreenBrush = Brush.linearGradient(
    0f to Color(0xFF5367E0), 0.6f to Color(0xFF8B5CE6), 1f to Color(0xFFE58BB5),
    start = Offset(37f, 15f), end = Offset(183f, 105f),
)

/** The laptop symbol, scaled uniformly to [width] (pixels) at [topLeft]. */
fun DrawScope.drawLaptop(topLeft: Offset, width: Float) {
    val s = width / 220f
    withTransform({
        translate(topLeft.x, topLeft.y)
        scale(s, s, pivot = Offset.Zero)
    }) {
        drawRoundRect(Color(0xFF1E2033), Offset(30f, 8f), Size(160f, 104f), CornerRadius(12f))
        drawRoundRect(ScreenBrush, Offset(37f, 15f), Size(146f, 90f), CornerRadius(6f))
        drawMark(Offset(94f, 38f), 32f)
        drawPath(LaptopBase, Color(0xFFC9CCDD))
        drawRoundRect(Color(0xFFA9ACC0), Offset(90f, 118f), Size(40f, 5f), CornerRadius(2.5f))
    }
}

/** The USB stick symbol (viewBox 120 x 60), scaled to [width]. */
fun DrawScope.drawUsbStick(topLeft: Offset, width: Float) {
    val s = width / 120f
    withTransform({
        translate(topLeft.x, topLeft.y)
        scale(s, s, pivot = Offset.Zero)
    }) {
        drawRoundRect(Color(0xFF3B3E57), Offset(6f, 14f), Size(78f, 32f), CornerRadius(10f))
        drawRoundRect(Color(0xFFB9BCD0), Offset(84f, 20f), Size(28f, 20f), CornerRadius(3f))
        drawRoundRect(Color(0xFF6E7190), Offset(92f, 25f), Size(6f, 4f), CornerRadius(1f))
        drawRoundRect(Color(0xFF6E7190), Offset(102f, 25f), Size(6f, 4f), CornerRadius(1f))
        drawMark(Offset(30f, 17f), 26f)
    }
}

private val SparkleBig = path("M220 40 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z")
private val SparkleSmall = path("M236 70 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z")
private val DownloadArrow = path("M200 29 v18 m-8 -7 l8 8 8 -8")

/** Art for the two cards on "Try or install" (viewBox 250 x 150), centred in the canvas. */
@Composable
fun ChoiceArt(install: Boolean, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val s = minOf(size.width / 250f, size.height / 150f)
        val ox = (size.width - 250f * s) / 2f
        val oy = (size.height - 150f * s) / 2f
        withTransform({
            translate(ox, oy)
            scale(s, s, pivot = Offset.Zero)
        }) {
            if (!install) {
                drawLaptop(Offset(0f, 1.8f), 200f)
                drawUsbStick(Offset(168f, 96f), 80f)
                drawPath(SparkleBig, Color(0xFF7E8CFF))
                drawPath(SparkleSmall, Color(0xFFE58BB5))
            } else {
                drawLaptop(Offset(25f, 1.8f), 200f)
                drawCircle(Color(0xFF4355B9), radius = 22f, center = Offset(200f, 40f))
                drawPath(
                    DownloadArrow,
                    Color.White,
                    style = Stroke(width = 4f, cap = StrokeCap.Round, join = StrokeJoin.Round),
                )
            }
        }
    }
}

/** The small laptop on the Hardware screen's machine card (112 x 76 in the design). */
@Composable
fun LaptopIllustration(modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val w = minOf(size.width, size.height * 220f / 150f)
        drawLaptop(Offset((size.width - w) / 2f, (size.height - w * 150f / 220f) / 2f), w)
    }
}

// The "cookie" on the Done screen (viewBox 200 x 200).
private val Cookie = path(
    "M100 8 C112 8 118 18 129 21 C140 24 151 19 160 26 C169 33 168 45 174 55 C180 65 191 70 193 82 " +
        "C195 94 186 102 186 114 C186 126 194 135 190 146 C186 157 174 160 166 169 C158 178 156 190 145 194 " +
        "C134 198 124 190 112 191 C100 192 91 200 80 196 C69 192 66 180 56 173 C46 166 33 166 26 156 " +
        "C19 146 23 134 19 123 C15 112 5 104 6 92 C7 80 18 74 22 63 C26 52 22 39 30 30 C38 21 51 23 61 17 " +
        "C71 11 88 8 100 8 Z",
)
private val CookieBrush = Brush.linearGradient(
    listOf(Color(0xFF5B6CF0), Color(0xFF9B5DE5)), start = Offset(6f, 8f), end = Offset(194f, 198f),
)

/** The Done screen's expressive shape with a check and a little confetti. */
@Composable
fun CookieCheck(size: Dp, modifier: Modifier = Modifier) {
    Box(modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size)) {
            val s = this.size.minDimension / 200f
            withTransform({ scale(s, s, pivot = Offset.Zero) }) { drawPath(Cookie, CookieBrush) }
            val u = this.size.minDimension / 260f // confetti positions are in the design's 260 px box
            fun confetti(x: Float, y: Float, w: Float, h: Float, color: Color, deg: Float, round: Boolean = false) {
                translate(x * u, y * u) {
                    rotate(deg, pivot = Offset(w * u / 2f, h * u / 2f)) {
                        drawRoundRect(
                            color,
                            Offset.Zero,
                            Size(w * u, h * u),
                            CornerRadius(if (round) w * u / 2f else 4f * u),
                        )
                    }
                }
            }
            confetti(-6f, 30f, 14f, 14f, Color(0xFFFF9B7A), 20f)
            confetti(234f, -4f, 10f, 22f, Color(0xFF7E8CFF), -25f)
            confetti(260f, 190f, 14f, 14f, Color(0xFF59C3A6), 0f, round = true)
            confetti(20f, 257f, 20f, 9f, Color(0xFFE58BB5), -12f)
            confetti(-18f, 120f, 9f, 9f, Color(0xFFC08BFF), 0f, round = true)
        }
        Icon(
            Icons.Rounded.Check,
            contentDescription = null,
            tint = Color.White,
            modifier = Modifier.size(size * 0.42f),
        )
    }
}

/** The tip card's art: two app windows on a gradient, with a taskbar strip. */
@Composable
fun TipArt(variant: Int, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        drawRect(
            Brush.linearGradient(
                listOf(Color(0xFF5367E0), Color(0xFF9A62E6)),
                start = Offset.Zero,
                end = Offset(size.width, size.height),
            ),
        )
        val u = size.height / 150f
        val window = Color.White.copy(alpha = 0.92f)
        val header = Color(0xFF4355B9).copy(alpha = 0.18f)
        fun win(x: Float, y: Float, w: Float, h: Float) {
            drawRoundRect(window, Offset(x * u, y * u), Size(w * u, h * u), CornerRadius(10f * u))
            drawRoundRect(header, Offset(x * u, y * u), Size(w * u, 14f * u), CornerRadius(10f * u))
        }
        when (variant % 3) {
            0 -> { // windows side by side
                win(26f, 30f, 118f, 88f)
                win(154f, 30f, 118f, 88f)
            }
            1 -> { // one big window
                win(40f, 22f, 220f, 100f)
            }
            else -> { // overlapping windows
                win(30f, 22f, 150f, 86f)
                win(110f, 46f, 150f, 76f)
            }
        }
        drawRect(Color.White.copy(alpha = 0.35f), Offset(0f, size.height - 16f * u), Size(size.width, 16f * u))
    }
}

/** The Welcome screen's brand panel background: gradients and two soft blobs. */
fun DrawScope.drawHeroBackground() {
    drawRect(
        Brush.linearGradient(
            0f to Color(0xFF3446B0), 0.6f to Color(0xFF5B3FC4), 1f to Color(0xFF7B3FB3),
            start = Offset(size.width * 0.3f, 0f),
            end = Offset(size.width * 0.7f, size.height),
        ),
    )
    fun glow(color: Color, cx: Float, cy: Float, r: Float) = drawRect(
        Brush.radialGradient(listOf(color, color.copy(alpha = 0f)), center = Offset(cx, cy), radius = r),
    )
    val d = density
    glow(Color(0xFF7D8BFF), size.width * 0.2f, size.height * 0.1f, 380f * d)
    glow(Color(0xFFC06CF0), size.width, size.height, 400f * d)
    glow(Color(0xFFFF9B7A).copy(alpha = 0.85f), 0f, size.height, 280f * d)
    drawCircle(Color.White.copy(alpha = 0.22f), radius = 130f * d, center = Offset(size.width + 40f * d, 60f * d))
    drawCircle(Color.White.copy(alpha = 0.14f), radius = 70f * d, center = Offset(30f * d, size.height - 190f * d))
}
