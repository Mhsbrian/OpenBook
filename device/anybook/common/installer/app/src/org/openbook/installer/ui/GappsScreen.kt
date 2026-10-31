// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Apps
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FolderOpen
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.Load
import org.openbook.installer.R
import org.openbook.installer.WizardStep
import org.openbook.installer.daemon.GappsApp
import org.openbook.installer.daemon.GappsCheck

/**
 * Step 4, advanced (ANAL-211, docs/gapps.md section 5): a Google apps package the user provides. Off unless the disk
 * screen's switch is on. The file comes from the system file picker (this stick's storage or a USB drive); the
 * daemon checks it and stages what it may install. The user sees every app it brings with its signing certificate,
 * and must confirm that this system will not be certified before the plan includes it. OpenBook never downloads one.
 */
@Composable
fun GappsScreen(vm: InstallerViewModel, rail: RailModel) {
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) vm.checkGapps(uri)
    }
    val pick = { picker.launch(arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream")) }
    val check = vm.gappsCheck
    WizardScaffold(
        step = WizardStep.DISK,
        rail = rail,
        overline = stringResource(
            R.string.overline_step_named,
            4,
            WizardStep.entries.size,
            stringResource(R.string.gapps_overline),
        ),
        title = stringResource(R.string.gapps_title),
        lede = stringResource(R.string.gapps_lede),
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
        when (check) {
            Load.Idle -> {
                Notice(icon = Icons.Rounded.Info, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.gapps_requirements), style = Ob.type.body)
                }
                Spacer(Modifier.height(14.dp))
                TonalButton(stringResource(R.string.gapps_choose), onClick = pick, icon = Icons.Rounded.FolderOpen)
            }
            Load.Loading -> Receiving(vm.gappsReceived, vm.gappsTotal)
            is Load.Failed -> {
                ErrorNotice(stringResource(R.string.gapps_failed, errorSentence(check.code, check.message)))
                Spacer(Modifier.height(14.dp))
                TonalButton(stringResource(R.string.gapps_choose_other), onClick = pick, icon = Icons.Rounded.FolderOpen)
            }
            is Load.Ready -> {
                val c = check.value
                if (c.ok) Accepted(vm, c) else Refused(c)
                Spacer(Modifier.height(14.dp))
                TonalButton(stringResource(R.string.gapps_choose_other), onClick = pick, icon = Icons.Rounded.FolderOpen)
                if (c.ok) {
                    Spacer(Modifier.height(18.dp))
                    Warning(vm)
                }
            }
        }
        vm.planError?.let {
            Spacer(Modifier.height(14.dp))
            ErrorNotice(stringResource(R.string.plan_failed, it))
        }
    }
}

@Composable
private fun Receiving(received: Long, total: Long) {
    val checking = total > 0 && received >= total
    Column(Modifier.widthIn(max = 640.dp).semantics { liveRegion = LiveRegionMode.Polite }) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(Modifier.size(24.dp))
            Spacer(Modifier.width(14.dp))
            Text(
                if (checking) stringResource(R.string.gapps_checking)
                else stringResource(R.string.gapps_reading, bytesText(received), bytesText(total)),
                style = Ob.type.body,
            )
        }
        if (total > 0 && !checking) {
            Spacer(Modifier.height(10.dp))
            LinearProgressIndicator(progress = { (received.toFloat() / total).coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun Accepted(vm: InstallerViewModel, c: GappsCheck) {
    val cs = MaterialTheme.colorScheme
    SectionLabel(stringResource(R.string.gapps_package_label))
    Surface(shape = RoundedCornerShape(24.dp), color = cs.surfaceContainerLow, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 22.dp, vertical = 18.dp)) {
            Text(
                listOfNotNull(c.name, c.version).joinToString(" ").ifEmpty { c.file },
                fontSize = 18.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                stringResource(R.string.gapps_package_detail, c.file, bytesText(c.fileBytes), c.files, bytesText(c.bytes)),
                style = Ob.type.caption,
                color = cs.onSurfaceVariant,
            )
            c.packageSha256?.let { Mono(stringResource(R.string.gapps_sha256, it)) }
            Spacer(Modifier.height(12.dp))
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { c.apps.forEach { AppRow(it) } }
        }
    }
    if ("multi_abi" in c.warnings.joinToString(" ") { it.substringBefore(':') }) {
        Spacer(Modifier.height(10.dp))
        Notice(icon = Icons.Rounded.Info, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.gapps_multi_abi), style = Ob.type.caption)
        }
    }
}

@Composable
private fun AppRow(a: GappsApp) {
    val cs = MaterialTheme.colorScheme
    Row(Modifier.semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.Top) {
        androidx.compose.material3.Icon(Icons.Rounded.Apps, contentDescription = null, tint = cs.primary, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(a.packageName, style = Ob.type.body, fontWeight = FontWeight.SemiBold)
            Text(
                stringResource(
                    R.string.gapps_app_detail,
                    a.versionName.ifEmpty { a.versionCode.toString() },
                    stringResource(if (a.privileged) R.string.gapps_app_privileged else R.string.gapps_app_normal),
                    when (a.native) {
                        "x86_64" -> stringResource(R.string.gapps_app_native)
                        else -> stringResource(R.string.gapps_app_no_native)
                    },
                ),
                style = Ob.type.caption,
                color = cs.onSurfaceVariant,
            )
            a.signer?.let { Text(stringResource(R.string.gapps_app_signer, it), style = Ob.type.caption, color = cs.onSurfaceVariant) }
            a.signerSha256?.let { Mono(stringResource(R.string.gapps_app_signer_sha256, it)) }
        }
    }
}

@Composable
private fun Mono(text: String) {
    Text(text, fontFamily = FontFamily.Monospace, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun Refused(c: GappsCheck) {
    val cs = MaterialTheme.colorScheme
    ErrorNotice(stringResource(R.string.gapps_refused, c.error.orEmpty()))
    if (c.refused.isNotEmpty()) {
        Spacer(Modifier.height(12.dp))
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            c.refused.take(MAX_SHOWN).forEach { r ->
                Column(Modifier.semantics(mergeDescendants = true) {}) {
                    Mono(r.path)
                    Text(r.why, style = Ob.type.caption, color = cs.onSurface)
                }
            }
            val more = c.refused.size - MAX_SHOWN + c.refusedMore
            if (more > 0) Text(stringResource(R.string.gapps_refused_more, more), style = Ob.type.caption)
        }
    }
}

@Composable
private fun Warning(vm: InstallerViewModel) {
    val ext = Ob.colors
    Surface(
        shape = RoundedCornerShape(24.dp),
        color = ext.warningContainer,
        contentColor = ext.onWarningContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(horizontal = 22.dp, vertical = 18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                androidx.compose.material3.Icon(Icons.Rounded.Warning, contentDescription = null, modifier = Modifier.size(24.dp))
                Spacer(Modifier.width(10.dp))
                Text(stringResource(R.string.gapps_warning_title), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            }
            Spacer(Modifier.height(8.dp))
            listOf(
                R.string.gapps_warning_certified,
                R.string.gapps_warning_integrity,
                R.string.gapps_warning_system,
                R.string.gapps_warning_no_bypass,
            ).forEach { Text("•  " + stringResource(it), style = Ob.type.body, modifier = Modifier.padding(vertical = 3.dp)) }
            Spacer(Modifier.height(8.dp))
            Row(
                Modifier
                    .fillMaxWidth()
                    .focusRing(RoundedCornerShape(16.dp))
                    .clip(RoundedCornerShape(16.dp))
                    .toggleable(value = vm.gappsConfirmed, role = Role.Checkbox, onValueChange = vm::confirmGapps)
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(checked = vm.gappsConfirmed, onCheckedChange = null)
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.gapps_confirm), style = Ob.type.body, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

private const val MAX_SHOWN = 12
