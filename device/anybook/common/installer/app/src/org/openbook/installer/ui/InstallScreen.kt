// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.Article
import androidx.compose.material.icons.automirrored.rounded.ReceiptLong
import androidx.compose.material.icons.rounded.Battery5Bar
import androidx.compose.material.icons.rounded.BatteryChargingFull
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.HourglassTop
import androidx.compose.material.icons.rounded.Power
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.LinearWavyProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.WavyProgressIndicatorDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.Load
import org.openbook.installer.R
import org.openbook.installer.WizardStep
import org.openbook.installer.daemon.INSTALL_STEPS
import org.openbook.installer.valueOrNull

/** Step 6: `apply` / `attach` progress, the engine's steps, a tip card, power and log chips, and "Show details". */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun InstallScreen(vm: InstallerViewModel, rail: RailModel) {
    val st = vm.install
    val failure = st.failure
    val cs = MaterialTheme.colorScheme
    val hello = vm.hello.valueOrNull
    WizardScaffold(
        step = WizardStep.INSTALL,
        rail = rail,
        overline = if (failure == null) {
            stringResource(R.string.overline_step, 6, WizardStep.entries.size)
        } else {
            stringResource(R.string.overline_step_named, 6, WizardStep.entries.size, stringResource(R.string.overline_stopped))
        },
        overlineColor = if (failure == null) cs.primary else cs.error,
        title = when {
            failure == null -> stringResource(R.string.install_title)
            failure.notStarted -> stringResource(R.string.install_title_not_started)
            else -> stringResource(R.string.install_title_failed)
        },
        actionsLeading = {
            hello?.power?.let { p ->
                when {
                    p.ac -> StatusPill(stringResource(R.string.chip_charger), Tone.OK, icon = Icons.Rounded.BatteryChargingFull)
                    p.batteryPct != null -> StatusPill(
                        stringResource(R.string.chip_battery, p.batteryPct),
                        if (p.ok) Tone.WARN else Tone.ERROR,
                        icon = Icons.Rounded.Battery5Bar,
                    )
                    else -> StatusPill(stringResource(R.string.chip_no_battery), Tone.INFO, icon = Icons.Rounded.Power)
                }
            }
            if (hello?.logsOnStick != false) {
                StatusPill(
                    stringResource(R.string.chip_log_path, st.result?.log ?: stringResource(R.string.log_dir)),
                    Tone.INFO,
                    icon = Icons.AutoMirrored.Rounded.ReceiptLong,
                )
            } else {
                StatusPill(stringResource(R.string.chip_log_memory), Tone.WARN, icon = Icons.AutoMirrored.Rounded.ReceiptLong)
            }
        },
        actionsTrailing = {
            TextActionButton(
                stringResource(if (st.showDetails) R.string.action_hide_details else R.string.action_show_details),
                onClick = vm::toggleDetails,
                icon = Icons.AutoMirrored.Rounded.Article,
            )
            if (failure != null && !st.running) {
                if (failure.notStarted) {
                    TonalButton(stringResource(R.string.action_back), vm::back, icon = Icons.AutoMirrored.Rounded.ArrowBack)
                } else {
                    TonalButton(stringResource(R.string.action_start_again), vm::back, icon = Icons.Rounded.Refresh)
                }
            }
        },
    ) {
        if (failure != null) {
            val stepName = failure.step?.let { stepLabel(it, done = false) }
            val text = when {
                failure.notStarted -> stringResource(R.string.install_not_started, errorSentence(failure.code, failure.message))
                failure.code == Load.UNREACHABLE -> stringResource(R.string.install_lost_contact)
                stepName != null -> stringResource(R.string.install_failed_at, stepName)
                else -> stringResource(R.string.install_failed)
            }
            ErrorNotice(text)
            if (!failure.notStarted && !failure.message.isNullOrBlank() && failure.code != Load.UNREACHABLE) {
                Text(
                    stringResource(R.string.install_error_detail, failure.message),
                    style = Ob.type.mono,
                    color = cs.onSurfaceVariant,
                    modifier = Modifier.padding(top = 10.dp),
                )
            }
            Spacer(Modifier.height(18.dp))
        }
        if (failure?.notStarted != true) {
            ProgressHead(vm)
            val density = LocalDensity.current
            val stroke = with(density) { Stroke(width = 6.dp.toPx(), cap = StrokeCap.Round) }
            LinearWavyProgressIndicator(
                progress = { (st.pct / 100.0).toFloat().coerceIn(0f, 1f) },
                color = if (failure != null) cs.error else cs.primary,
                trackColor = (if (failure != null) cs.error else cs.primary).copy(alpha = 0.24f),
                stroke = stroke,
                trackStroke = stroke,
                amplitude = { p ->
                    if (vm.a11y.reduceMotion || failure != null || !st.running) 0f else WavyProgressIndicatorDefaults.indicatorAmplitude(p)
                },
                modifier = Modifier.fillMaxWidth().height(26.dp).padding(bottom = 4.dp),
            )
            Spacer(Modifier.height(20.dp))
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                if (maxWidth >= 720.dp) {
                    Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                        StepList(vm, Modifier.weight(1f))
                        TipCard(vm, Modifier.width(300.dp))
                    }
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
                        StepList(vm, Modifier.fillMaxWidth())
                        TipCard(vm, Modifier.fillMaxWidth())
                    }
                }
            }
        }
        if (st.showDetails) {
            Spacer(Modifier.height(18.dp))
            LogPanel(vm)
        }
    }
}

@Composable
private fun ProgressHead(vm: InstallerViewModel) {
    val st = vm.install
    val cs = MaterialTheme.colorScheme
    val pct = st.pct.toInt().coerceIn(0, 100)
    val eta = when {
        st.reconnecting -> stringResource(R.string.install_reconnecting)
        st.failure != null -> ""
        st.etaSeconds == null -> stringResource(R.string.install_starting)
        st.etaSeconds!! < 60 -> stringResource(R.string.eta_less_than_minute)
        else -> {
            val m = (st.etaSeconds!! + 59) / 60
            pluralStringResource(R.plurals.eta_minutes_left, m, m)
        }
    }
    Row(Modifier.padding(top = 6.dp, bottom = 14.dp), verticalAlignment = Alignment.Bottom) {
        Text(
            stringResource(R.string.install_percent, pct),
            style = Ob.type.percent,
            color = if (st.failure != null) cs.error else cs.primary,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
        )
        Spacer(Modifier.width(18.dp))
        Text(
            eta,
            fontSize = 16.sp,
            color = cs.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 10.dp),
        )
    }
}

@Composable
private fun StepList(vm: InstallerViewModel, modifier: Modifier) {
    val st = vm.install
    val cs = MaterialTheme.colorScheme
    Column(
        modifier
            .clip(RoundedCornerShape(22.dp))
            .background(cs.surfaceContainerLow)
            .padding(horizontal = 4.dp, vertical = 8.dp),
    ) {
        INSTALL_STEPS.forEach { step ->
            StepRow(vm, step, st.steps[step] ?: "pending")
        }
    }
}

@Composable
private fun StepRow(vm: InstallerViewModel, step: String, state: String) {
    val st = vm.install
    val cs = MaterialTheme.colorScheme
    val ext = Ob.colors
    val running = state == "running"
    val failed = state == "failed"
    val label = stepLabel(step, done = state == "done")
    val stateText = stringResource(
        when (state) {
            "done" -> R.string.step_state_done
            "running" -> R.string.step_state_running
            "failed" -> R.string.step_state_failed
            "skipped" -> R.string.step_state_skipped
            else -> R.string.step_state_pending
        },
    )
    val right = when {
        running && st.totalBytes > 0 -> stringResource(
            R.string.progress_bytes,
            bytesText(st.doneBytes),
            bytesText(st.totalBytes),
        )
        failed || state == "skipped" -> stateText
        else -> ""
    }
    val bg = when {
        failed -> cs.errorContainer
        running -> cs.primaryContainer
        else -> Color.Transparent
    }
    val fg = when {
        failed -> cs.onErrorContainer
        running -> cs.onPrimaryContainer
        state == "done" -> cs.onSurface
        else -> cs.onSurfaceVariant
    }
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(bg)
            .padding(horizontal = 14.dp, vertical = 10.dp)
            .clearAndSetSemantics { contentDescription = "$label: $stateText" },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(24.dp), contentAlignment = Alignment.Center) {
            when (state) {
                "done" -> Icon(Icons.Rounded.CheckCircle, null, tint = ext.success, modifier = Modifier.size(22.dp))
                "failed" -> Icon(Icons.Rounded.Error, null, tint = cs.error, modifier = Modifier.size(22.dp))
                "running" -> if (vm.a11y.reduceMotion) {
                    Icon(Icons.Rounded.HourglassTop, null, tint = cs.primary, modifier = Modifier.size(22.dp))
                } else {
                    CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.5.dp, color = cs.primary)
                }
                else -> Icon(Icons.Rounded.RadioButtonUnchecked, null, tint = cs.outline, modifier = Modifier.size(22.dp))
            }
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(label, fontSize = 15.sp, fontWeight = if (running || failed) FontWeight.SemiBold else FontWeight.Normal, color = fg)
            if (running && st.totalBytes > 0) {
                LinearProgressIndicator(
                    progress = { (st.doneBytes.toDouble() / st.totalBytes).toFloat().coerceIn(0f, 1f) },
                    color = cs.primary,
                    trackColor = cs.primary.copy(alpha = 0.22f),
                    drawStopIndicator = {},
                    modifier = Modifier.padding(top = 7.dp).fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                )
            }
        }
        if (right.isNotEmpty()) {
            Spacer(Modifier.width(12.dp))
            Text(right, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = fg)
        }
    }
}

@Composable
private fun TipCard(vm: InstallerViewModel, modifier: Modifier) {
    val cs = MaterialTheme.colorScheme
    var tip by rememberSaveable { mutableIntStateOf(0) }
    val running = vm.install.running
    LaunchedEffect(running) {
        while (running) {
            delay(9_000)
            tip = (tip + 1) % 3
        }
    }
    val (title, body) = when (tip) {
        0 -> stringResource(R.string.tip_windows_title) to stringResource(R.string.tip_windows_body)
        1 -> stringResource(R.string.tip_setup_title) to stringResource(R.string.tip_setup_body)
        else -> stringResource(R.string.tip_log_title) to stringResource(R.string.tip_log_body)
    }
    Column(modifier.clip(RoundedCornerShape(24.dp)).background(cs.surfaceContainer)) {
        TipArt(tip, Modifier.fillMaxWidth().height(150.dp))
        Column(Modifier.padding(start = 18.dp, end = 18.dp, top = 16.dp, bottom = 18.dp).semantics(mergeDescendants = true) {}) {
            Text(stringResource(R.string.tip_label), fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = cs.primary)
            Text(title, fontSize = 15.5.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(vertical = 4.dp))
            Text(body, fontSize = 13.5.sp, lineHeight = 19.sp, color = cs.onSurfaceVariant)
            Row(Modifier.padding(top = 12.dp).clearAndSetSemantics {}, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                repeat(3) { i ->
                    Box(
                        Modifier
                            .height(6.dp)
                            .width(if (i == tip) 18.dp else 6.dp)
                            .clip(RoundedCornerShape(3.dp))
                            .background(if (i == tip) cs.primary else cs.outlineVariant),
                    )
                }
            }
        }
    }
}

@Composable
private fun LogPanel(vm: InstallerViewModel) {
    val cs = MaterialTheme.colorScheme
    val lines = vm.install.log
    val state = rememberLazyListState()
    LaunchedEffect(lines.size) {
        if (lines.isNotEmpty()) state.scrollToItem(lines.size - 1)
    }
    Column(Modifier.fillMaxWidth()) {
        SectionLabel(stringResource(R.string.log_title))
        SelectionContainer {
            LazyColumn(
                state = state,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(240.dp)
                    .clip(RoundedCornerShape(18.dp))
                    .background(cs.surfaceContainerHigh)
                    .padding(horizontal = 14.dp, vertical = 10.dp),
            ) {
                if (lines.isEmpty()) {
                    item { Text(stringResource(R.string.log_empty), style = Ob.type.mono, color = cs.onSurfaceVariant) }
                }
                items(lines) { line -> Text(line, style = Ob.type.mono, color = cs.onSurface) }
            }
        }
    }
}
