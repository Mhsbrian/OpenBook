// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import android.content.ClipData
import android.content.ClipboardManager
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Badge
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.DeleteForever
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.InstallBlocker
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.R
import org.openbook.installer.WizardStep
import org.openbook.installer.daemon.Plan
import org.openbook.installer.daemon.PlanPart

/**
 * Step 5: what gets erased (or kept), before and after, the full by-id, the plan's warnings, and the typed
 * confirmation (S2-S4). The red button enables only on a match, is never focused by default, and Enter in the field
 * does not press it.
 */
@Composable
fun ConfirmScreen(vm: InstallerViewModel, rail: RailModel) {
    val plan = vm.plan
    if (plan == null) {
        // The plan was dropped (the disk list changed): pick the disk again.
        LaunchedEffect(Unit) { vm.goTo(WizardStep.DISK) }
        return
    }
    val whole = plan.layout != "alongside"
    val model = plan.targetModel.ifEmpty { vm.selectedDiskInfo?.model.orEmpty() }
    WizardScaffold(
        step = WizardStep.CONFIRM,
        rail = rail,
        overline = stringResource(
            R.string.overline_step_named,
            5,
            WizardStep.entries.size,
            stringResource(R.string.overline_please_read),
        ),
        overlineColor = MaterialTheme.colorScheme.error,
        title = if (whole) stringResource(R.string.confirm_title_whole, model) else stringResource(R.string.confirm_title_alongside, model),
        actionsLeading = {
            TextActionButton(
                stringResource(R.string.action_view_plan),
                onClick = { vm.planDialog = true },
                icon = Icons.Rounded.Description,
            )
        },
        actionsTrailing = {
            TonalButton(stringResource(R.string.action_back), vm::back, icon = Icons.AutoMirrored.Rounded.ArrowBack)
            DangerButton(
                if (whole) stringResource(R.string.action_erase_install) else stringResource(R.string.action_install),
                onClick = vm::startInstall,
                enabled = vm.typedMatches && vm.installBlocker == InstallBlocker.NONE,
                icon = if (whole) Icons.Rounded.DeleteForever else Icons.Rounded.Download,
            )
        },
    ) {
        if (whole) EraseBox(plan) else KeepBox(plan)
        BeforeAfter(plan)
        IdRow(plan.targetById)
        plan.warnings.forEach { w ->
            Notice(
                icon = Icons.Rounded.Warning,
                color = Ob.colors.warningContainer,
                contentColor = Ob.colors.onWarningContainer,
                iconTint = Ob.colors.onWarningContainer,
                modifier = Modifier.padding(bottom = 10.dp).fillMaxWidth(),
            ) { Text(planWarningSentence(w, alongside = !whole), style = Ob.type.body) }
        }
        Spacer(Modifier.height(6.dp))
        ConfirmField(vm, plan)
    }
}

private fun partKind(p: PlanPart): String = when {
    p.os.equals("windows", ignoreCase = true) -> "windows"
    p.os.equals("linux", ignoreCase = true) -> "linux"
    p.name.contains("EFI", ignoreCase = true) || p.label.equals("EFI", ignoreCase = true) -> "efi"
    p.name.contains("android", ignoreCase = true) || p.label.contains("openbook", ignoreCase = true) -> "openbook"
    else -> "other"
}

private fun partTitle(p: PlanPart, separator: String): String {
    val fs = fsLabel(p.fs)
    val base = p.os.ifEmpty { p.name.ifEmpty { p.label } }
    return when {
        p.os.isNotEmpty() && fs.isNotEmpty() -> base + separator + fs
        base.isEmpty() -> fs
        else -> base
    }
}

@Composable
private fun PartRows(parts: List<PlanPart>) {
    val sep = stringResource(R.string.separator_dot)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        parts.forEach { p ->
            Row(Modifier.semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically) {
                LegendSwatch(partKind(p))
                Spacer(Modifier.width(10.dp))
                Text(partTitle(p, sep), fontSize = 14.5.sp, modifier = Modifier.weight(1f))
                Text(bytesText(p.bytes), fontSize = 14.5.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun EraseBox(plan: Plan) {
    val cs = MaterialTheme.colorScheme
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(cs.errorContainer)
            .padding(horizontal = 22.dp, vertical = 20.dp),
    ) {
        Box(
            Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(cs.error.copy(alpha = 0.18f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Rounded.Warning, contentDescription = null, tint = cs.error, modifier = Modifier.size(26.dp))
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(
                stringResource(R.string.confirm_erase_heading),
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
                color = cs.onErrorContainer,
                modifier = Modifier.padding(top = 2.dp, bottom = 8.dp).semantics { heading() },
            )
            if (plan.erases.isEmpty()) {
                Text(stringResource(R.string.confirm_erase_empty), fontSize = 14.5.sp, color = cs.onErrorContainer)
            } else {
                PartRows(plan.erases)
            }
            Text(
                stringResource(R.string.confirm_erase_undo),
                fontSize = 13.5.sp,
                color = cs.onErrorContainer.copy(alpha = 0.85f),
                modifier = Modifier.padding(top = 10.dp),
            )
        }
    }
}

@Composable
private fun KeepBox(plan: Plan) {
    val cs = MaterialTheme.colorScheme
    val newBytes = plan.after.filter { it.kind == "openbook" }.sumOf { it.bytes }
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(cs.primaryContainer)
            .padding(horizontal = 22.dp, vertical = 20.dp),
    ) {
        Box(
            Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(cs.primary.copy(alpha = 0.16f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Rounded.Info, contentDescription = null, tint = cs.primary, modifier = Modifier.size(26.dp))
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(
                stringResource(R.string.confirm_keep_heading),
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
                color = cs.onPrimaryContainer,
                modifier = Modifier.padding(top = 2.dp, bottom = 8.dp).semantics { heading() },
            )
            if (plan.keeps.isNotEmpty()) PartRows(plan.keeps)
            Text(
                stringResource(R.string.confirm_keep_uses, bytesText(newBytes)),
                fontSize = 13.5.sp,
                color = cs.onPrimaryContainer,
                modifier = Modifier.padding(top = 10.dp),
            )
        }
    }
}

@Composable
private fun BeforeAfter(plan: Plan) {
    val cs = MaterialTheme.colorScheme
    Row(Modifier.fillMaxWidth().padding(vertical = 18.dp), verticalAlignment = Alignment.Bottom) {
        Column(Modifier.weight(1f)) {
            Text(stringResource(R.string.confirm_now), style = Ob.type.caption, fontWeight = FontWeight.SemiBold, color = cs.onSurfaceVariant)
            Spacer(Modifier.height(6.dp))
            UsageBar(plan.before.map { BarPart(it.kind, it.bytes) }, height = 22.dp)
        }
        Box(Modifier.width(48.dp).height(22.dp), contentAlignment = Alignment.Center) {
            Icon(Icons.AutoMirrored.Rounded.ArrowForward, contentDescription = null, tint = cs.onSurfaceVariant)
        }
        Column(Modifier.weight(1f)) {
            Text(stringResource(R.string.confirm_after), style = Ob.type.caption, fontWeight = FontWeight.SemiBold, color = cs.onSurfaceVariant)
            Spacer(Modifier.height(6.dp))
            UsageBar(plan.after.map { BarPart(it.kind, it.bytes) }, height = 22.dp)
        }
    }
}

@Composable
private fun IdRow(byId: String) {
    val cs = MaterialTheme.colorScheme
    val context = LocalContext.current
    val path = stringResource(R.string.confirm_by_id_path, byId)
    val clipLabel = stringResource(R.string.confirm_copy_label)
    Row(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 16.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(cs.surfaceContainerLow)
            .padding(start = 16.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Rounded.Badge, contentDescription = null, tint = cs.onSurfaceVariant, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(10.dp))
        SelectionContainer(Modifier.weight(1f)) {
            Text(path, style = Ob.type.mono, color = cs.onSurface)
        }
        IconButton(
            onClick = {
                context.getSystemService(ClipboardManager::class.java)
                    ?.setPrimaryClip(ClipData.newPlainText(clipLabel, path))
            },
            modifier = Modifier.focusRing(RoundedCornerShape(50)),
        ) {
            Icon(Icons.Rounded.ContentCopy, contentDescription = stringResource(R.string.confirm_copy), tint = cs.onSurfaceVariant)
        }
    }
}

@Composable
private fun ConfirmField(vm: InstallerViewModel, plan: Plan) {
    val ext = Ob.colors
    val matches = vm.typedMatches
    val keyboard = LocalSoftwareKeyboardController.current
    val colors = if (matches) {
        OutlinedTextFieldDefaults.colors(
            focusedBorderColor = ext.success,
            unfocusedBorderColor = ext.success,
            focusedLabelColor = ext.success,
            unfocusedLabelColor = ext.success,
        )
    } else {
        OutlinedTextFieldDefaults.colors()
    }
    OutlinedTextField(
        value = vm.typed,
        onValueChange = vm::updateTyped,
        singleLine = true,
        label = { Text(stringResource(R.string.confirm_type_label, plan.confirmText)) },
        trailingIcon = if (matches) {
            { Icon(Icons.Rounded.CheckCircle, contentDescription = stringResource(R.string.confirm_matches_icon), tint = ext.success) }
        } else {
            null
        },
        supportingText = {
            Text(
                if (matches) stringResource(R.string.confirm_matches) else stringResource(R.string.confirm_type_help),
                color = if (matches) ext.success else Color.Unspecified,
            )
        },
        textStyle = MaterialTheme.typography.bodyLarge.copy(fontSize = 19.sp, fontWeight = FontWeight.SemiBold),
        keyboardOptions = KeyboardOptions(autoCorrectEnabled = false, imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { keyboard?.hide() }),
        shape = RoundedCornerShape(16.dp),
        colors = colors,
        modifier = Modifier
            .widthIn(max = 460.dp)
            .fillMaxWidth()
            // Enter never confirms: it must not reach the red button or the IME action.
            .onPreviewKeyEvent { it.key == Key.Enter || it.key == Key.NumPadEnter },
    )
}
