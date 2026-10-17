// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Lightbulb
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Storage
import androidx.compose.material.icons.rounded.Usb
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.DialogProperties
import org.openbook.installer.InstallBlocker
import org.openbook.installer.InstallLayout
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.Load
import org.openbook.installer.R
import org.openbook.installer.WizardStep
import org.openbook.installer.daemon.Disk
import org.openbook.installer.daemon.Plan

/** Step 4: pick the target disk (the boot stick is locked, S1) and the layout; "View the plan" is the dry run (S5). */
@Composable
fun DiskScreen(vm: InstallerViewModel, rail: RailModel) {
    val disks = vm.disks
    val selected = vm.selectedDiskInfo
    WizardScaffold(
        step = WizardStep.DISK,
        rail = rail,
        overline = stringResource(R.string.overline_step, 4, WizardStep.entries.size),
        title = stringResource(R.string.disk_title),
        lede = stringResource(R.string.disk_lede),
        actionsLeading = {
            TextActionButton(
                stringResource(R.string.action_view_plan),
                onClick = { vm.requestPlan(toConfirm = false) },
                icon = Icons.Rounded.Description,
                enabled = vm.canPlan && !vm.planLoading,
            )
        },
        actionsTrailing = {
            TonalButton(stringResource(R.string.action_back), vm::back, icon = Icons.AutoMirrored.Rounded.ArrowBack)
            PrimaryButton(
                stringResource(R.string.action_continue),
                onClick = { vm.requestPlan(toConfirm = true) },
                enabled = vm.canPlan,
                busy = vm.planLoading,
                icon = Icons.AutoMirrored.Rounded.ArrowForward,
            )
        },
    ) {
        if (vm.installBlocker != InstallBlocker.NONE) {
            BlockerNotice(vm)
            Spacer(Modifier.height(16.dp))
        }
        when (disks) {
            is Load.Ready -> {
                val ordered = disks.value.sortedBy { if (it.bootDisk) 2 else if (it.selectable) 0 else 1 }
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    ordered.forEach { d -> DiskCard(d, selected = d.byId == vm.selectedDisk, onSelect = { vm.selectDisk(d) }) }
                }
                if (disks.value.none { it.selectable }) {
                    Spacer(Modifier.height(12.dp))
                    ErrorNotice(stringResource(R.string.disk_none))
                }
            }
            is Load.Failed -> ErrorNotice(errorSentence(disks.code, disks.message))
            else -> Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(28.dp))
                Spacer(Modifier.width(16.dp))
                Text(stringResource(R.string.disk_loading), style = Ob.type.body)
            }
        }
        TextActionButton(
            stringResource(R.string.disk_rescan),
            onClick = vm::loadDisks,
            icon = Icons.Rounded.Refresh,
            enabled = disks !is Load.Loading,
            modifier = Modifier.padding(top = 6.dp),
        )
        if (selected != null) {
            Spacer(Modifier.height(14.dp))
            LayoutChooser(vm, selected)
            AfterBar(vm, selected)
            Explainer(selected)
        }
        vm.planError?.let {
            Spacer(Modifier.height(14.dp))
            ErrorNotice(stringResource(R.string.plan_failed, it))
        }
    }
}

@Composable
private fun diskDetail(d: Disk): String {
    val parts = mutableListOf(bytesText(d.sizeBytes))
    busLabel(d.bus).takeIf { it.isNotEmpty() }?.let { parts += it }
    parts += when {
        d.bootDisk -> stringResource(R.string.disk_boot_stick)
        d.external -> stringResource(R.string.disk_external)
        else -> stringResource(R.string.disk_internal)
    }
    return parts.joinToString(stringResource(R.string.separator_dot))
}

/** Partition bar parts in disk order, with the free space at the end. */
fun diskParts(d: Disk): List<BarPart> {
    val parts = d.partitions.sortedBy { it.start }.map { BarPart(partitionKind(it), it.bytes) }.toMutableList()
    if (parts.none { it.kind == "free" } && d.freeBytes > 0) parts += BarPart("free", d.freeBytes)
    return parts
}

@Composable
private fun DiskCard(d: Disk, selected: Boolean, onSelect: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(24.dp)
    val locked = d.bootDisk
    val detail = diskDetail(d)
    val why = if (!d.selectable && !locked) whySentence(d.whole.why ?: d.alongside.why) else ""
    val description = listOf(d.model, detail, why).filter { it.isNotEmpty() }.joinToString(", ")
    val interaction = if (d.selectable) {
        Modifier
            .selectable(selected = selected, role = Role.RadioButton, onClick = onSelect)
            .semantics { contentDescription = description }
    } else {
        Modifier.clearAndSetSemantics {
            contentDescription = description
            disabled()
        }
    }
    Column(
        Modifier
            .fillMaxWidth()
            .then(if (d.selectable) Modifier.focusRing(shape) else Modifier)
            .alpha(if (locked) 0.78f else if (!d.selectable) 0.7f else 1f)
            .clip(shape)
            .background(if (selected) lerp(cs.surfaceContainerLow, cs.primaryContainer, 0.3f) else cs.surfaceContainerLow)
            .then(if (selected) Modifier.border(2.5.dp, cs.primary, shape) else Modifier)
            .then(interaction)
            .padding(horizontal = 20.dp, vertical = 18.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(52.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(if (d.selectable) cs.primaryContainer else cs.surfaceContainerHighest),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (d.bus == "usb" || locked) Icons.Rounded.Usb else Icons.Rounded.Storage,
                    contentDescription = null,
                    tint = if (d.selectable) cs.onPrimaryContainer else cs.onSurfaceVariant,
                    modifier = Modifier.size(28.dp),
                )
            }
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text(d.model, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.2).sp)
                Text(detail, fontSize = 13.5.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 3.dp))
            }
            Spacer(Modifier.width(10.dp))
            when {
                locked -> StatusPill(stringResource(R.string.disk_in_use), Tone.OFF, icon = Icons.Rounded.Lock)
                !d.selectable -> StatusPill(stringResource(R.string.disk_unavailable), Tone.OFF)
                else -> RadioButton(selected = selected, onClick = null)
            }
        }
        if (!locked && d.sizeBytes > 0) {
            val parts = diskParts(d)
            Spacer(Modifier.height(16.dp))
            UsageBar(parts)
            Spacer(Modifier.height(10.dp))
            UsageLegend(parts)
        }
        if (why.isNotEmpty()) {
            Text(why, style = Ob.type.caption, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 10.dp))
        }
        if (!locked) {
            d.warnings.forEach { w ->
                Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.Warning, null, tint = Ob.colors.warning, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(diskWarningSentence(w), style = Ob.type.caption, color = cs.onSurfaceVariant)
                }
            }
            if (d.byId.isNotEmpty()) {
                Text(
                    stringResource(R.string.disk_by_id, d.byId),
                    style = Ob.type.mono,
                    color = cs.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LayoutChooser(vm: InstallerViewModel, d: Disk) {
    val cs = MaterialTheme.colorScheme
    val wholeLabel = stringResource(R.string.layout_whole)
    val alongsideLabel = if (d.alongside.ok) {
        stringResource(R.string.layout_alongside_free, bytesText(d.alongside.freeBytes))
    } else {
        stringResource(R.string.layout_alongside)
    }
    SingleChoiceSegmentedButtonRow(Modifier.widthIn(max = 640.dp).fillMaxWidth()) {
        SegmentedButton(
            selected = vm.layout == InstallLayout.WHOLE,
            onClick = { vm.selectLayout(InstallLayout.WHOLE) },
            enabled = d.whole.ok,
            shape = SegmentedButtonDefaults.itemShape(index = 0, count = 2),
            modifier = Modifier.heightIn(min = 48.dp).focusRing(RoundedCornerShape(50)),
        ) { Text(wholeLabel, maxLines = 1) }
        SegmentedButton(
            selected = vm.layout == InstallLayout.ALONGSIDE,
            onClick = { vm.selectLayout(InstallLayout.ALONGSIDE) },
            enabled = d.alongside.ok,
            shape = SegmentedButtonDefaults.itemShape(index = 1, count = 2),
            modifier = Modifier.heightIn(min = 48.dp).focusRing(RoundedCornerShape(50)),
        ) { Text(alongsideLabel, maxLines = 1) }
    }
    if (!d.whole.ok) {
        Text(
            stringResource(R.string.layout_whole_unavailable, whySentence(d.whole.why)),
            style = Ob.type.caption,
            color = cs.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
    if (!d.alongside.ok) {
        Text(
            stringResource(R.string.layout_alongside_unavailable, whySentence(d.alongside.why)),
            style = Ob.type.caption,
            color = cs.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
    if (vm.layout == InstallLayout.ALONGSIDE) {
        // S7: the boot order changes only with consent.
        Row(
            Modifier
                .padding(top = 12.dp)
                .widthIn(max = 640.dp)
                .fillMaxWidth()
                .focusRing(RoundedCornerShape(16.dp))
                .clip(RoundedCornerShape(16.dp))
                .toggleable(value = vm.alongsideSetDefault, role = Role.Switch, onValueChange = vm::setAlongsideDefault)
                .padding(horizontal = 4.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.layout_set_default), style = Ob.type.body, fontWeight = FontWeight.SemiBold)
                Text(stringResource(R.string.layout_set_default_detail), style = Ob.type.caption, color = cs.onSurfaceVariant)
            }
            Spacer(Modifier.width(12.dp))
            Switch(checked = vm.alongsideSetDefault, onCheckedChange = null)
        }
    }
    // App add-ons the stick carries (ANAL-210), off by default: installed as normal apps on the first start.
    for (a in vm.availableAddons) {
        val on = a.name in vm.selectedAddons
        Row(
            Modifier
                .padding(top = 12.dp)
                .widthIn(max = 640.dp)
                .fillMaxWidth()
                .focusRing(RoundedCornerShape(16.dp))
                .clip(RoundedCornerShape(16.dp))
                .toggleable(value = on, role = Role.Switch, onValueChange = { vm.setAddon(a.name, it) })
                .padding(horizontal = 4.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                val known = a.name == "microg"
                Text(
                    if (known) stringResource(R.string.addon_microg) else a.title,
                    style = Ob.type.body,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    if (known) stringResource(R.string.addon_microg_detail, bytesText(a.bytes))
                    else stringResource(R.string.addon_detail, a.version, bytesText(a.bytes)),
                    style = Ob.type.caption,
                    color = cs.onSurfaceVariant,
                )
            }
            Spacer(Modifier.width(12.dp))
            Switch(checked = on, onCheckedChange = null)
        }
    }
}

@Composable
private fun AfterBar(vm: InstallerViewModel, d: Disk) {
    val cs = MaterialTheme.colorScheme
    val (parts, openbookBytes) = if (vm.layout == InstallLayout.WHOLE) {
        listOf(BarPart("openbook", d.sizeBytes)) to d.sizeBytes
    } else {
        val kept = diskParts(d).filter { it.kind != "free" }
        (kept + BarPart("openbook", d.alongside.freeBytes)) to d.alongside.freeBytes
    }
    Row(Modifier.padding(top = 14.dp).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(R.string.after_installing), fontSize = 14.sp, color = cs.onSurfaceVariant)
        Spacer(Modifier.width(14.dp))
        UsageBar(parts, Modifier.weight(1f), height = 12.dp)
        Spacer(Modifier.width(14.dp))
        Text(
            buildAnnotatedString {
                withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = cs.onSurface)) {
                    append(stringResource(R.string.kind_openbook))
                }
                append(stringResource(R.string.separator_dot))
                append(bytesText(openbookBytes))
            },
            fontSize = 14.sp,
            color = cs.onSurfaceVariant,
        )
    }
}

@Composable
private fun Explainer(d: Disk) {
    if (d.os.isEmpty()) return
    val systems = d.os.distinct().let { os ->
        if (os.size == 1) os[0] else stringResource(R.string.os_and, os.dropLast(1).joinToString(", "), os.last())
    }
    val cs = MaterialTheme.colorScheme
    Notice(icon = Icons.Rounded.Lightbulb, modifier = Modifier.padding(top = 22.dp).fillMaxWidth()) {
        Text(
            buildAnnotatedString {
                withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = cs.onSurface)) {
                    append(stringResource(R.string.explainer_keep_title, systems))
                }
                append(" ")
                append(
                    if (d.alongside.ok) {
                        stringResource(R.string.explainer_keep_body, bytesText(d.alongside.freeBytes))
                    } else {
                        stringResource(R.string.explainer_keep_unavailable, whySentence(d.alongside.why))
                    },
                )
            },
            style = Ob.type.body,
        )
    }
}

/** The dry-run plan: every operation the engine would run, in a monospace list. */
@Composable
fun PlanDialog(plan: Plan, onDismiss: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    AlertDialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
        modifier = Modifier.widthIn(min = 480.dp, max = 860.dp).padding(24.dp),
        title = { Text(stringResource(R.string.plan_title)) },
        text = {
            Column {
                Text(
                    stringResource(
                        R.string.plan_summary,
                        plan.targetModel,
                        bytesText(plan.bytesToWrite),
                        etaText(plan.estimatedSeconds),
                    ),
                    style = Ob.type.body,
                    color = cs.onSurfaceVariant,
                )
                Spacer(Modifier.height(12.dp))
                LazyColumn(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(max = 420.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(cs.surfaceContainerHigh)
                        .padding(12.dp),
                ) {
                    itemsIndexed(plan.operations) { i, op ->
                        Text("${i + 1}. ${op.text}", style = Ob.type.mono, modifier = Modifier.padding(vertical = 2.dp))
                    }
                }
            }
        },
        confirmButton = { TextActionButton(stringResource(R.string.action_close), onDismiss) },
    )
}
