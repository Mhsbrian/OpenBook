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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.BatteryFull
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.DesktopWindows
import androidx.compose.material.icons.rounded.DeveloperBoard
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.Memory
import androidx.compose.material.icons.rounded.Palette
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Speaker
import androidx.compose.material.icons.rounded.Storage
import androidx.compose.material.icons.rounded.TouchApp
import androidx.compose.material.icons.rounded.VerifiedUser
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material.icons.rounded.Wifi
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.InstallBlocker
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.Load
import org.openbook.installer.R
import org.openbook.installer.WizardStep
import org.openbook.installer.daemon.Component
import org.openbook.installer.daemon.HwInfo
import org.openbook.installer.daemon.Machine

/** Step 2: `hwinfo` as one verdict, a machine card and a tile per component; "Save report to USB". */
@Composable
fun HardwareScreen(vm: InstallerViewModel, rail: RailModel) {
    val hw = vm.hw
    val info = (hw as? Load.Ready)?.value
    val title = when {
        info == null && hw is Load.Failed -> stringResource(R.string.hw_title_failed)
        info == null -> stringResource(R.string.hw_title_checking)
        info.verdict == "ready" -> stringResource(R.string.hw_title_ready)
        info.verdict == "limited" -> stringResource(R.string.hw_title_limited)
        else -> stringResource(R.string.hw_title_unsupported)
    }
    val lede = when {
        info == null && hw is Load.Failed -> null
        info == null -> stringResource(R.string.hw_lede_checking)
        info.verdict == "ready" -> {
            val different = info.components.count { it.state == "limited" || it.state == "new" }
            if (different == 0) {
                stringResource(R.string.hw_lede_ready_all)
            } else {
                pluralStringResource(R.plurals.hw_lede_ready_some, different, different)
            }
        }
        info.verdict == "limited" -> stringResource(R.string.hw_lede_limited)
        else -> stringResource(R.string.hw_lede_unsupported)
    }
    WizardScaffold(
        step = WizardStep.HARDWARE,
        rail = rail,
        overline = stringResource(R.string.overline_step, 2, WizardStep.entries.size),
        title = title,
        lede = lede,
        actionsLeading = {
            TextActionButton(
                stringResource(R.string.hw_save_report),
                onClick = vm::saveReport,
                icon = Icons.Rounded.Download,
                enabled = info != null,
                busy = vm.reportSaving,
            )
        },
        actionsTrailing = {
            TonalButton(stringResource(R.string.action_back), vm::back, icon = Icons.AutoMirrored.Rounded.ArrowBack)
            PrimaryButton(
                stringResource(R.string.action_continue),
                onClick = { vm.goTo(WizardStep.CHOOSE) },
                icon = Icons.AutoMirrored.Rounded.ArrowForward,
            )
        },
    ) {
        when (hw) {
            is Load.Ready -> {
                MachineCard(hw.value)
                Spacer(Modifier.height(18.dp))
                Tiles(hw.value.components)
            }
            is Load.Failed -> {
                ErrorNotice(
                    if (hw.code == Load.UNREACHABLE) stringResource(R.string.hw_unreachable) else errorSentence(hw.code, hw.message),
                )
                Spacer(Modifier.height(12.dp))
                TextActionButton(stringResource(R.string.action_try_again), vm::loadHardware, icon = Icons.Rounded.Refresh)
            }
            else -> Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(28.dp))
                Spacer(Modifier.width(16.dp))
                Text(stringResource(R.string.hw_checking_parts), style = Ob.type.body)
            }
        }
        val blocker = vm.installBlocker
        if (info != null && blocker != InstallBlocker.NONE && blocker != InstallBlocker.CHECKING) {
            Spacer(Modifier.height(16.dp))
            BlockerNotice(vm)
        }
        vm.reportPath?.let { path ->
            Spacer(Modifier.height(16.dp))
            Notice(
                icon = Icons.Rounded.CheckCircle,
                iconTint = Ob.colors.success,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            ) { Text(stringResource(R.string.hw_report_saved, path), style = Ob.type.body) }
        }
        vm.reportError?.let { error ->
            Spacer(Modifier.height(16.dp))
            ErrorNotice(stringResource(R.string.hw_report_failed, error))
        }
    }
}

@Composable
private fun MachineCard(hw: HwInfo) {
    val ext = Ob.colors
    val cs = MaterialTheme.colorScheme
    val (bg, fg) = when (hw.verdict) {
        "ready" -> ext.successContainer to ext.onSuccessContainer
        "limited" -> ext.warningContainer to ext.onWarningContainer
        else -> cs.errorContainer to cs.onErrorContainer
    }
    val chip = when (hw.verdict) {
        "ready" -> StateChip(stringResource(R.string.verdict_ready), Tone.OK)
        "limited" -> StateChip(stringResource(R.string.verdict_limited), Tone.WARN)
        else -> StateChip(stringResource(R.string.verdict_unsupported), Tone.ERROR)
    }
    val m = hw.machine
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(Brush.horizontalGradient(listOf(bg, lerp(cs.surfaceContainerLow, bg, 0.3f))))
            .padding(horizontal = 22.dp, vertical = 18.dp)
            .semantics(mergeDescendants = true) {},
        verticalAlignment = Alignment.CenterVertically,
    ) {
        LaptopIllustration(Modifier.size(width = 112.dp, height = 76.dp))
        Spacer(Modifier.width(22.dp))
        Column(Modifier.weight(1f)) {
            Text(machineTitle(m), fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = fg)
            Text(machineSubtitle(m), fontSize = 14.sp, color = fg.copy(alpha = 0.75f), modifier = Modifier.padding(top = 3.dp))
        }
        Spacer(Modifier.width(12.dp))
        StatusPill(
            chip.label,
            chip.tone,
            icon = when (chip.tone) {
                Tone.OK -> Icons.Rounded.CheckCircle
                Tone.WARN -> Icons.Rounded.Warning
                else -> Icons.Rounded.Error
            },
        )
    }
}

private val VendorNames = mapOf(
    "asustek" to "ASUS",
    "lenovo" to "Lenovo",
    "hp" to "HP",
    "hewlett" to "HP",
    "dell" to "Dell",
    "micro-star" to "MSI",
    "acer" to "Acer",
    "framework" to "Framework",
    "microsoft" to "Microsoft",
    "samsung" to "Samsung",
    "razer" to "Razer",
    "gigabyte" to "Gigabyte",
    "lg" to "LG",
    "huawei" to "Huawei",
    "qemu" to "QEMU",
)

private fun machineTitle(m: Machine): String {
    val first = m.vendor.trim().split(' ', ',').firstOrNull().orEmpty()
    val short = VendorNames.entries.firstOrNull { first.lowercase().startsWith(it.key) }?.value ?: first
    val product = m.product.removeSuffix(m.board).trim().ifEmpty { m.product }
    return when {
        product.isEmpty() -> short
        short.isEmpty() || product.contains(short, ignoreCase = true) -> product
        else -> "$short $product"
    }
}

@Composable
private fun machineSubtitle(m: Machine): String {
    val parts = mutableListOf<String>()
    if (m.board.isNotBlank()) parts += m.board
    if (m.cpu.isNotBlank()) parts += m.cpu
    val gb = marketingRamGb(m.ramBytes)
    if (gb > 0) parts += stringResource(R.string.hw_ram_gb, gb)
    val firmware = m.firmware.ifBlank { stringResource(R.string.hw_firmware_unknown) }
    parts += when (m.secureBoot) {
        "on" -> stringResource(R.string.hw_firmware_sb_on, firmware)
        "off" -> stringResource(R.string.hw_firmware_sb_off, firmware)
        else -> firmware
    }
    val ctx = LocalContext.current
    return parts.joinToString(ctx.getString(R.string.separator_dot))
}

@Composable
private fun Tiles(components: List<Component>) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val columns = when {
            maxWidth >= 820.dp -> 3
            maxWidth >= 500.dp -> 2
            else -> 1
        }
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            components.chunked(columns).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { Tile(it, Modifier.weight(1f)) }
                    repeat(columns - row.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        }
    }
}

private fun componentIcon(id: String): ImageVector = when (id) {
    "cpu" -> Icons.Rounded.Memory
    "gpu" -> Icons.Rounded.Palette
    "display" -> Icons.Rounded.DesktopWindows
    "wifi" -> Icons.Rounded.Wifi
    "touchpad" -> Icons.Rounded.TouchApp
    "storage" -> Icons.Rounded.Storage
    "audio" -> Icons.Rounded.Speaker
    "sleep" -> Icons.Rounded.Bedtime
    "dgpu" -> Icons.Rounded.Bolt
    "battery" -> Icons.Rounded.BatteryFull
    else -> Icons.Rounded.DeveloperBoard
}

@Composable
private fun Tile(c: Component, modifier: Modifier) {
    val cs = MaterialTheme.colorScheme
    val chip = componentChip(c.state, c.detail)
    val reason = reasonSentence(c.detail)
    val detail = reason ?: listOf(c.value, c.detail).filter { it.isNotBlank() }.joinToString(stringResource(R.string.separator_dot))
    Row(
        modifier
            .clip(RoundedCornerShape(20.dp))
            .background(cs.surfaceContainerLow)
            .padding(14.dp)
            .semantics(mergeDescendants = true) {},
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(42.dp).clip(RoundedCornerShape(14.dp)).background(cs.surfaceContainerHigh),
            contentAlignment = Alignment.Center,
        ) {
            Icon(componentIcon(c.id), contentDescription = null, tint = cs.primary, modifier = Modifier.size(22.dp))
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    componentName(c.id, c.value),
                    fontSize = 14.5.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                StatusPill(chip.label, chip.tone)
            }
            Text(
                detail,
                fontSize = 12.5.sp,
                color = cs.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
    }
}

/** "Installing needs the OpenBook USB stick ...": shown instead of the install path; Try still works. */
@Composable
fun BlockerNotice(vm: InstallerViewModel, modifier: Modifier = Modifier) {
    val text = when (vm.installBlocker) {
        InstallBlocker.UNREACHABLE -> stringResource(R.string.blocker_unreachable)
        InstallBlocker.NOT_LIVE -> stringResource(R.string.blocker_not_live)
        InstallBlocker.NO_SOURCE -> stringResource(
            R.string.blocker_no_source,
            sourceWhySentence((vm.hello as? Load.Ready)?.value?.source?.why),
        )
        InstallBlocker.CHECKING -> stringResource(R.string.blocker_checking)
        InstallBlocker.NONE -> return
    }
    Notice(
        icon = Icons.Rounded.VerifiedUser,
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
        modifier = modifier.semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Column {
            Text(text, style = Ob.type.body)
            if (vm.installBlocker == InstallBlocker.UNREACHABLE) {
                TextActionButton(stringResource(R.string.action_check_again), vm::loadHello, icon = Icons.Rounded.Refresh)
            }
        }
    }
}
