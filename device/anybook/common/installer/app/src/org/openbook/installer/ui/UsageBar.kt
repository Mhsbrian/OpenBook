// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** A part of a usage bar: [kind] is windows, linux, efi, openbook, other or free. */
data class BarPart(val kind: String, val bytes: Long)

@Composable
fun kindColor(kind: String): Color {
    val ext = Ob.colors
    return when (kind) {
        "windows" -> ext.barWindows
        "linux" -> ext.barLinux
        "efi" -> ext.barEfi
        "openbook" -> ext.barOpenBookStart
        "free" -> MaterialTheme.colorScheme.surfaceContainerHighest
        else -> ext.barOther
    }
}

/**
 * The partition bar from the design: segments with 3 dp gaps, rounded, OpenBook as a gradient and free space
 * hatched. Decorative for accessibility; the legend next to it carries the same information as text.
 */
@Composable
fun UsageBar(parts: List<BarPart>, modifier: Modifier = Modifier, height: Dp = 30.dp) {
    val ext = Ob.colors
    val colors = parts.map { kindColor(it.kind) }
    val freeBase = MaterialTheme.colorScheme.surfaceContainerHighest
    val stripe = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.55f)
    Canvas(modifier.fillMaxWidth().height(height)) {
        val visible = parts.withIndex().filter { it.value.bytes > 0 }
        if (visible.isEmpty()) {
            drawRoundRect(freeBase, cornerRadius = CornerRadius(6.dp.toPx()))
            return@Canvas
        }
        val gap = 3.dp.toPx()
        val minW = 6.dp.toPx()
        val avail = size.width - gap * (visible.size - 1)
        val total = visible.sumOf { it.value.bytes }.toDouble()
        val raw = visible.map { maxOf(minW, (it.value.bytes / total * avail).toFloat()) }
        val scale = avail / raw.sum()
        val r = CornerRadius(minOf(6.dp.toPx(), size.height / 2f))
        var x = 0f
        visible.forEachIndexed { i, (idx, part) ->
            val w = raw[i] * scale
            val topLeft = Offset(x, 0f)
            val sz = Size(w, size.height)
            when (part.kind) {
                "openbook" -> drawRoundRect(
                    Brush.horizontalGradient(listOf(ext.barOpenBookStart, ext.barOpenBookEnd), startX = x, endX = x + w),
                    topLeft, sz, r,
                )
                "free" -> {
                    val clip = Path().apply { addRoundRect(RoundRect(x, 0f, x + w, size.height, r)) }
                    clipPath(clip) {
                        drawRect(freeBase, topLeft, sz)
                        val step = 14.dp.toPx()
                        var sx = x - size.height
                        while (sx < x + w) {
                            drawLine(
                                stripe,
                                Offset(sx, size.height),
                                Offset(sx + size.height, 0f),
                                strokeWidth = 5.dp.toPx(),
                            )
                            sx += step
                        }
                    }
                }
                else -> drawRoundRect(colors[idx], topLeft, sz, r)
            }
            x += w + gap
        }
    }
}

/** Legend under a usage bar: one entry per kind, with the summed size. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun UsageLegend(parts: List<BarPart>, modifier: Modifier = Modifier) {
    val sums = LinkedHashMap<String, Long>()
    parts.filter { it.bytes > 0 }.forEach { sums[it.kind] = (sums[it.kind] ?: 0L) + it.bytes }
    FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(18.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        sums.forEach { (kind, bytes) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                LegendSwatch(kind)
                Spacer(Modifier.width(7.dp))
                Text(
                    kindLabel(kind),
                    fontSize = 13.sp,
                    fontWeight = if (kind == "free" || kind == "efi") FontWeight.Normal else FontWeight.SemiBold,
                    color = if (kind == "free" || kind == "efi") {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    } else {
                        MaterialTheme.colorScheme.onSurface
                    },
                )
                Spacer(Modifier.width(5.dp))
                Text(bytesText(bytes), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** The coloured square of a legend entry. */
@Composable
fun LegendSwatch(kind: String, size: Dp = 10.dp) {
    val ext = Ob.colors
    val color = kindColor(kind)
    Canvas(Modifier.size(size)) {
        val r = CornerRadius(3.dp.toPx())
        if (kind == "openbook") {
            drawRoundRect(Brush.linearGradient(listOf(ext.barOpenBookStart, ext.barOpenBookEnd)), cornerRadius = r)
        } else {
            drawRoundRect(color, cornerRadius = r)
        }
    }
}
