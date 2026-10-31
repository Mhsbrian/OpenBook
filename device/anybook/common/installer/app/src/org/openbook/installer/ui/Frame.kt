// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.FlowRowScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Celebration
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.R
import org.openbook.installer.WizardStep

/** Window size class for this app: the window is 840-1920 dp wide (G14 at density 240: 1920 x 1200 dp). */
data class WindowFit(val compact: Boolean, val wide: Boolean)

val LocalWindowFit = staticCompositionLocalOf { WindowFit(compact = false, wide = false) }

/** What the rail shows under each step label, and its bottom note. */
data class RailModel(
    val hints: Map<WizardStep, String>,
    val noteIcon: ImageVector,
    val note: String,
)

@Composable
fun stepTitle(step: WizardStep): String = stringResource(
    when (step) {
        WizardStep.WELCOME -> R.string.rail_language
        WizardStep.HARDWARE -> R.string.rail_hardware
        WizardStep.CHOOSE -> R.string.rail_choose
        WizardStep.DISK -> R.string.rail_disk
        WizardStep.CONFIRM -> R.string.rail_confirm
        WizardStep.INSTALL -> R.string.rail_install
        WizardStep.DONE -> R.string.rail_done
    },
)

/** Measures the window once for every screen. */
@Composable
fun WindowFitProvider(content: @Composable () -> Unit) {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val fit = WindowFit(compact = maxWidth < 1040.dp || maxHeight < 680.dp, wide = maxWidth >= 1500.dp)
        CompositionLocalProvider(LocalWindowFit provides fit) { content() }
    }
}

/**
 * The frame of steps 2-7: the step rail on the left; on the right the overline, headline and lede, scrollable
 * content, and the action row, which always stays visible.
 */
@Composable
fun WizardScaffold(
    step: WizardStep,
    rail: RailModel,
    overline: String,
    title: String?,
    modifier: Modifier = Modifier,
    lede: String? = null,
    overlineColor: Color = MaterialTheme.colorScheme.primary,
    actionsLeading: @Composable FlowRowScope.() -> Unit = {},
    actionsTrailing: @Composable RowScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    val fit = LocalWindowFit.current
    Row(modifier.fillMaxSize()) {
        StepRail(step, rail, Modifier.width(if (fit.compact) 236.dp else 286.dp).fillMaxHeight())
        ContentColumn(
            overline = overline,
            title = title,
            lede = lede,
            overlineColor = overlineColor,
            actionsLeading = actionsLeading,
            actionsTrailing = actionsTrailing,
            modifier = Modifier.weight(1f).fillMaxHeight(),
            content = content,
        )
    }
}

/** The right-hand column (also used by the Welcome screen next to its brand panel). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ContentColumn(
    overline: String,
    title: String?,
    lede: String?,
    modifier: Modifier = Modifier,
    overlineColor: Color = MaterialTheme.colorScheme.primary,
    actionsLeading: @Composable FlowRowScope.() -> Unit = {},
    actionsTrailing: @Composable RowScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    val fit = LocalWindowFit.current
    val hPad: Dp = if (fit.compact) 32.dp else 56.dp
    Column(modifier.padding(start = hPad, end = hPad, top = if (fit.compact) 28.dp else 40.dp, bottom = 24.dp)) {
        Column(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState()),
        ) {
            Column(Modifier.widthIn(max = if (fit.wide) 1280.dp else Dp.Unspecified)) {
                if (overline.isNotEmpty()) {
                    Text(overline, style = Ob.type.overline, color = overlineColor, modifier = Modifier.padding(bottom = 10.dp))
                }
                if (title != null) {
                    Text(
                        title,
                        style = if (fit.compact) Ob.type.headline.copy(fontSize = 32.sp, lineHeight = 40.sp) else Ob.type.headline,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.padding(bottom = 10.dp).semantics { heading() },
                    )
                }
                if (lede != null) {
                    Text(
                        lede,
                        style = Ob.type.lede,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.widthIn(max = 680.dp).padding(bottom = 22.dp),
                    )
                }
                content()
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 18.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FlowRow(
                Modifier.weight(1f),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                itemVerticalAlignment = Alignment.CenterVertically,
                content = actionsLeading,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                actionsTrailing()
            }
        }
    }
}

@Composable
fun StepRail(current: WizardStep, rail: RailModel, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    val border = cs.outlineVariant.copy(alpha = 0.45f)
    Column(
        modifier
            .background(cs.surfaceContainerLow)
            .drawBehind {
                drawLine(border, Offset(size.width - 0.5f, 0f), Offset(size.width - 0.5f, size.height), 1.dp.toPx())
            }
            .padding(start = 22.dp, end = 22.dp, top = 26.dp, bottom = 22.dp),
    ) {
        Row(Modifier.padding(start = 4.dp, bottom = 30.dp), verticalAlignment = Alignment.CenterVertically) {
            OpenBookMark(38.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.semantics(mergeDescendants = true) {}) {
                Text(
                    stringResource(R.string.brand_name),
                    fontSize = 23.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = (-0.4).sp,
                    color = cs.onSurface,
                )
                Text(
                    stringResource(R.string.brand_installer),
                    fontSize = 12.5.sp,
                    fontWeight = FontWeight.Medium,
                    color = cs.onSurfaceVariant,
                )
            }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            WizardStep.entries.forEach { s ->
                RailStep(s, current, rail.hints[s])
            }
        }
        Spacer(Modifier.height(16.dp))
        Surface(color = cs.surfaceContainerHigh, contentColor = cs.onSurfaceVariant, shape = RoundedCornerShape(18.dp)) {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 14.dp)) {
                Icon(rail.noteIcon, contentDescription = null, tint = cs.primary, modifier = Modifier.size(22.dp))
                Spacer(Modifier.width(12.dp))
                Text(rail.note, fontSize = 13.sp, lineHeight = 18.sp)
            }
        }
    }
}

@Composable
private fun RailStep(step: WizardStep, current: WizardStep, hint: String?) {
    val cs = MaterialTheme.colorScheme
    val done = step.ordinal < current.ordinal || (current == WizardStep.DONE && step != WizardStep.DONE)
    val now = step == current
    val connectorColor = if (step.ordinal <= current.ordinal) cs.primary else cs.outlineVariant
    val label = stepTitle(step)
    val stateText = stringResource(
        when {
            now -> R.string.rail_state_current
            done -> R.string.rail_state_done
            else -> R.string.rail_state_upcoming
        },
    )
    val description = stringResource(R.string.rail_step_description, step.number, WizardStep.entries.size, label, stateText)
    Row(
        Modifier
            .fillMaxWidth()
            .drawWithContent {
                drawContent()
                if (step.ordinal > 0) {
                    val x = 20.dp.toPx()
                    drawLine(connectorColor, Offset(x, -9.dp.toPx()), Offset(x, 9.dp.toPx()), 2.dp.toPx())
                }
            }
            .clip(RoundedCornerShape(16.dp))
            .background(if (now) cs.primaryContainer.copy(alpha = 0.7f) else Color.Transparent)
            .padding(horizontal = 4.dp, vertical = 9.dp)
            .clearAndSetSemantics { contentDescription = description },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(34.dp), contentAlignment = Alignment.Center) {
            val dotModifier = when {
                now -> Modifier
                    .drawBehind { drawCircle(cs.primary.copy(alpha = 0.18f), radius = size.minDimension / 2f + 5.dp.toPx()) }
                    .background(cs.primary, CircleShape)
                done -> Modifier.background(cs.primary, CircleShape)
                else -> Modifier.background(cs.surfaceContainerLow, CircleShape).border(2.dp, cs.outlineVariant, CircleShape)
            }
            Box(Modifier.size(32.dp).then(dotModifier), contentAlignment = Alignment.Center) {
                when {
                    now && step == WizardStep.DONE ->
                        Icon(Icons.Rounded.Celebration, null, tint = cs.onPrimary, modifier = Modifier.size(19.dp))
                    done -> Icon(Icons.Rounded.Check, null, tint = cs.onPrimary, modifier = Modifier.size(19.dp))
                    else -> Text(
                        step.number.toString(),
                        fontSize = 14.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = if (now) cs.onPrimary else cs.onSurfaceVariant,
                    )
                }
            }
        }
        Spacer(Modifier.width(14.dp))
        Column {
            Text(
                label,
                fontSize = 15.sp,
                fontWeight = if (done || now) FontWeight.SemiBold else FontWeight.Medium,
                color = if (done || now) cs.onSurface else cs.onSurfaceVariant,
            )
            if (!hint.isNullOrEmpty() && (now || done)) {
                Text(hint, fontSize = 12.5.sp, color = cs.onSurfaceVariant, maxLines = 1)
            }
        }
    }
}
