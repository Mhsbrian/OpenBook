// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ReceiptLong
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Start
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.R
import org.openbook.installer.WizardStep
import org.openbook.installer.daemon.InstallResult

/** Step 7: the read-back result (S9), the boot entry and the report; "Keep trying" or "Restart now". */
@Composable
fun DoneScreen(vm: InstallerViewModel, rail: RailModel, onKeepTrying: () -> Unit, onRestart: () -> Unit) {
    val fit = LocalWindowFit.current
    val result = vm.install.result
    WizardScaffold(
        step = WizardStep.DONE,
        rail = rail,
        overline = "",
        title = null,
        actionsTrailing = {
            OutlinedPillButton(stringResource(R.string.action_keep_trying), onKeepTrying)
            PrimaryButton(
                stringResource(R.string.action_restart),
                onClick = onRestart,
                icon = Icons.Rounded.RestartAlt,
                iconAfter = false,
                big = true,
            )
        },
    ) {
        if (fit.compact) {
            Column {
                CookieCheck(150.dp, Modifier.padding(start = 20.dp, top = 12.dp, bottom = 28.dp))
                Summary(vm, result)
            }
        } else {
            Row(Modifier.fillMaxWidth().padding(top = 40.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.width(300.dp), contentAlignment = Alignment.Center) { CookieCheck(240.dp) }
                Spacer(Modifier.width(38.dp))
                Box(Modifier.weight(1f)) { Summary(vm, result) }
            }
        }
    }
}

@Composable
private fun Summary(vm: InstallerViewModel, result: InstallResult?) {
    val cs = MaterialTheme.colorScheme
    Column(Modifier.widthIn(max = 640.dp)) {
        Text(stringResource(R.string.done_overline), style = Ob.type.overline, color = cs.primary, modifier = Modifier.padding(bottom = 10.dp))
        Text(
            stringResource(R.string.done_title),
            style = Ob.type.headline.copy(fontSize = 46.sp, lineHeight = 54.sp),
            modifier = Modifier
                .padding(bottom = 10.dp)
                .semantics {
                    heading()
                    liveRegion = LiveRegionMode.Polite
                },
        )
        Text(
            stringResource(R.string.done_lede),
            style = Ob.type.lede,
            color = cs.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 22.dp),
        )
        // Boot entry: whole-disk installs boot through the fallback path when the firmware's NVRAM can't be written;
        // installs next to another system then need the firmware's boot menu.
        val nvramMissing = result?.nvram == "unavailable" || result?.nvram == "failed"
        val needsFirmwareMenu = result != null && nvramMissing && (!result.fallbackPath || vm.install.layout == "alongside")
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            ResultRow(
                Icons.Rounded.Verified,
                stringResource(R.string.done_verified),
                stringResource(R.string.done_verified_detail),
            )
            if (needsFirmwareMenu) {
                ResultRow(
                    Icons.Rounded.Info,
                    stringResource(R.string.done_boot_entry),
                    stringResource(R.string.done_boot_firmware_menu),
                    warn = true,
                )
            } else {
                ResultRow(
                    Icons.Rounded.Start,
                    stringResource(R.string.done_boot_entry_added),
                    stringResource(R.string.done_boot_entry_detail),
                )
            }
            ResultRow(
                Icons.AutoMirrored.Rounded.ReceiptLong,
                stringResource(R.string.done_report),
                result?.report?.let { stringResource(R.string.done_report_path, it) }
                    ?: stringResource(R.string.done_report_detail),
            )
        }
    }
}

@Composable
private fun ResultRow(icon: ImageVector, title: String, detail: String, warn: Boolean = false) {
    val cs = MaterialTheme.colorScheme
    val ext = Ob.colors
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(cs.surfaceContainerLow)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .semantics(mergeDescendants = true) {},
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(44.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(if (warn) ext.warningContainer else ext.successContainer),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                icon,
                contentDescription = null,
                tint = if (warn) ext.onWarningContainer else ext.onSuccessContainer,
                modifier = Modifier.size(24.dp),
            )
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(title, fontSize = 15.5.sp, fontWeight = FontWeight.SemiBold, color = cs.onSurface)
            Text(detail, fontSize = 13.5.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 2.dp))
        }
    }
}
