// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.drawOutline
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.inset
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** A visible keyboard-focus ring drawn just outside the component (the design has no hover states to lean on). */
fun Modifier.focusRing(shape: Shape = CircleShape, gap: Dp = 3.dp, width: Dp = 3.dp): Modifier = composed {
    var focused by remember { mutableStateOf(false) }
    val color = MaterialTheme.colorScheme.primary
    this
        .onFocusChanged { focused = it.isFocused || it.hasFocus }
        .drawWithContent {
            drawContent()
            if (focused) {
                val g = gap.toPx() + width.toPx() / 2f
                inset(-g, -g) {
                    drawOutline(shape.createOutline(size, layoutDirection, this), color, style = Stroke(width.toPx()))
                }
            }
        }
}

private val PillShape = RoundedCornerShape(50)
private val ButtonPadding = PaddingValues(horizontal = 26.dp, vertical = 0.dp)

@Composable
private fun ButtonContent(text: String, icon: ImageVector?, iconAfter: Boolean, busy: Boolean = false) {
    if (busy) {
        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.5.dp, color = LocalContentColor.current)
        Spacer(Modifier.width(10.dp))
    } else if (icon != null && !iconAfter) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(8.dp))
    }
    Text(text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    if (icon != null && iconAfter && !busy) {
        Spacer(Modifier.width(8.dp))
        Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp))
    }
}

/** Filled pill (Continue, Restart now). [big] is the design's 54 dp variant. */
@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    iconAfter: Boolean = true,
    enabled: Boolean = true,
    busy: Boolean = false,
    big: Boolean = false,
) {
    Button(
        onClick = onClick,
        enabled = enabled && !busy,
        shape = PillShape,
        contentPadding = if (big) PaddingValues(horizontal = 30.dp) else ButtonPadding,
        modifier = modifier.focusRing(PillShape).heightIn(min = if (big) 54.dp else 48.dp),
    ) { ButtonContent(text, icon, iconAfter, busy) }
}

/** Tonal pill (Back). */
@Composable
fun TonalButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    enabled: Boolean = true,
) {
    FilledTonalButton(
        onClick = onClick,
        enabled = enabled,
        shape = PillShape,
        contentPadding = ButtonPadding,
        modifier = modifier.focusRing(PillShape).heightIn(min = 48.dp),
    ) { ButtonContent(text, icon, iconAfter = false) }
}

/** Outlined pill (Keep trying). */
@Composable
fun OutlinedPillButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        shape = PillShape,
        contentPadding = ButtonPadding,
        modifier = modifier.focusRing(PillShape).heightIn(min = 48.dp),
    ) { ButtonContent(text, null, iconAfter = false) }
}

/** Text button with a leading icon (Help, Save report to USB, View the plan, Show details). */
@Composable
fun TextActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    enabled: Boolean = true,
    busy: Boolean = false,
) {
    TextButton(
        onClick = onClick,
        enabled = enabled && !busy,
        shape = PillShape,
        contentPadding = PaddingValues(horizontal = 14.dp),
        modifier = modifier.focusRing(PillShape).heightIn(min = 48.dp),
    ) { ButtonContent(text, icon, iconAfter = false, busy = busy) }
}

/** The red confirmation button. Never given default focus (S2-S4). */
@Composable
fun DangerButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = PillShape,
        contentPadding = ButtonPadding,
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.error,
            contentColor = MaterialTheme.colorScheme.onError,
        ),
        modifier = modifier.focusRing(PillShape).heightIn(min = 48.dp),
    ) { ButtonContent(text, icon, iconAfter = false) }
}

/** The tones of [StatusPill] (here, not in Texts.kt, so this file builds into OpenBookSetup on its own). */
enum class Tone { OK, WARN, OFF, INFO, ERROR }

/** Status pill: Ready / Quieter / New / Off / Not found, and the progress screen's chips. */
@Composable
fun StatusPill(text: String, tone: Tone, modifier: Modifier = Modifier, icon: ImageVector? = null) {
    val ext = Ob.colors
    val cs = MaterialTheme.colorScheme
    val (bg, fg) = when (tone) {
        Tone.OK -> ext.successContainer to ext.onSuccessContainer
        Tone.WARN -> ext.warningContainer to ext.onWarningContainer
        Tone.OFF -> cs.surfaceContainerHighest to cs.onSurfaceVariant
        Tone.INFO -> cs.primaryContainer to cs.onPrimaryContainer
        Tone.ERROR -> cs.errorContainer to cs.onErrorContainer
    }
    Surface(color = bg, contentColor = fg, shape = RoundedCornerShape(13.dp), modifier = modifier) {
        Row(
            Modifier.heightIn(min = 26.dp).padding(horizontal = 11.dp, vertical = 3.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (icon != null) {
                Icon(icon, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(5.dp))
            }
            Text(text, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        }
    }
}

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = Ob.type.sectionLabel,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier.padding(top = 6.dp, bottom = 10.dp).semantics { heading() },
    )
}

/** Tonal note with an icon: explainer on Disk, rail assurance, Done notice. */
@Composable
fun Notice(
    icon: ImageVector,
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.surfaceContainerLow,
    contentColor: Color = MaterialTheme.colorScheme.onSurfaceVariant,
    iconTint: Color = MaterialTheme.colorScheme.primary,
    content: @Composable () -> Unit,
) {
    Surface(color = color, contentColor = contentColor, shape = RoundedCornerShape(18.dp), modifier = modifier) {
        Row(Modifier.padding(horizontal = 18.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = iconTint, modifier = Modifier.size(22.dp))
            Spacer(Modifier.width(12.dp))
            Box(Modifier.weight(1f)) { content() }
        }
    }
}

/** An error the user should notice at once: announced by screen readers (live region). */
@Composable
fun ErrorNotice(text: String, modifier: Modifier = Modifier) {
    Notice(
        icon = Icons.Rounded.ErrorOutline,
        color = MaterialTheme.colorScheme.errorContainer,
        contentColor = MaterialTheme.colorScheme.onErrorContainer,
        iconTint = MaterialTheme.colorScheme.error,
        modifier = modifier.semantics { liveRegion = LiveRegionMode.Assertive },
    ) { Text(text, style = Ob.type.body) }
}
