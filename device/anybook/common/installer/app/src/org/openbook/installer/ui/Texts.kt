// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import android.content.res.Resources
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import java.text.NumberFormat
import kotlin.math.abs
import kotlin.math.ceil
import org.openbook.installer.R
import org.openbook.installer.daemon.Partition

/*
 * Everything the app renders from the daemon's ids, states and codes (PROTOCOL.md: "the app localises everything it
 * renders from ids and states"). Unknown codes fall back to the daemon's own text.
 */

/** Decimal sizes with three significant digits, as in the design: 1.02 TB, 412 GB, 69 GB, 260 MB. */
fun formatBytes(res: Resources, bytes: Long): String {
    val units = intArrayOf(R.string.size_b, R.string.size_kb, R.string.size_mb, R.string.size_gb, R.string.size_tb)
    var value = abs(bytes).toDouble()
    var unit = 0
    while (value >= 999.5 && unit < units.lastIndex) {
        value /= 1000.0
        unit++
    }
    val nf = NumberFormat.getNumberInstance(res.configuration.locales[0])
    nf.minimumFractionDigits = 0
    nf.maximumFractionDigits = when {
        unit == 0 -> 0
        value < 9.995 -> 2
        value < 99.95 -> 1
        else -> 0
    }
    return res.getString(units[unit], nf.format(value))
}

@Composable
fun bytesText(bytes: Long): String {
    LocalConfiguration.current // re-read on locale changes
    return formatBytes(LocalContext.current.resources, bytes)
}

/** RAM as marketed (32 GB for 31.25 GiB usable). */
fun marketingRamGb(bytes: Long): Int {
    if (bytes <= 0) return 0
    val gib = ceil(bytes / (1024.0 * 1024.0 * 1024.0)).toInt()
    return if (gib > 2 && gib % 2 == 1) gib + 1 else gib
}

@Composable
fun componentName(id: String, value: String): String = when (id) {
    "cpu" -> stringResource(R.string.hw_cpu)
    "gpu" -> stringResource(R.string.hw_gpu)
    "display" -> stringResource(R.string.hw_display)
    "wifi" -> stringResource(R.string.hw_wifi)
    "touchpad" -> stringResource(R.string.hw_touchpad)
    "storage" -> stringResource(R.string.hw_storage)
    "audio" -> stringResource(R.string.hw_audio)
    "sleep" -> stringResource(R.string.hw_sleep)
    "dgpu" -> when {
        value.contains("nvidia", ignoreCase = true) -> stringResource(R.string.hw_dgpu_nvidia)
        value.contains("radeon", ignoreCase = true) || value.contains("amd", ignoreCase = true) ->
            stringResource(R.string.hw_dgpu_amd)
        else -> stringResource(R.string.hw_dgpu)
    }
    "battery" -> stringResource(R.string.hw_battery)
    else -> id
}

/** A reason code from a component's `detail`, as a sentence; null if [detail] is not a known code. */
@Composable
fun reasonSentence(detail: String): String? = when (detail) {
    "speaker_tuning_missing" -> stringResource(R.string.reason_speaker_tuning_missing)
    "untested_model" -> stringResource(R.string.reason_untested_model)
    "powered_down" -> stringResource(R.string.reason_powered_down)
    "software_rendering" -> stringResource(R.string.reason_software_rendering)
    "no_driver" -> stringResource(R.string.reason_no_driver)
    "not_found" -> stringResource(R.string.reason_not_found)
    "s0i3_not_reached" -> stringResource(R.string.reason_s0i3_not_reached)
    "charging" -> stringResource(R.string.reason_charging)
    "on_battery" -> stringResource(R.string.reason_on_battery)
    else -> null
}

enum class Tone { OK, WARN, OFF, INFO, ERROR }

data class StateChip(val label: String, val tone: Tone)

@Composable
fun componentChip(state: String, detail: String): StateChip = when (state) {
    "ready" -> StateChip(stringResource(R.string.state_ready), Tone.OK)
    "limited" -> if (detail == "speaker_tuning_missing") {
        StateChip(stringResource(R.string.state_quieter), Tone.WARN)
    } else {
        StateChip(stringResource(R.string.state_limited), Tone.WARN)
    }
    "new" -> StateChip(stringResource(R.string.state_new), Tone.WARN)
    "off" -> StateChip(stringResource(R.string.state_off), Tone.OFF)
    "missing" -> StateChip(stringResource(R.string.state_missing), Tone.ERROR)
    else -> StateChip(stringResource(R.string.state_unknown), Tone.OFF)
}

/** `why` codes of the disk layouts. */
@Composable
fun whySentence(why: String?): String = when (why) {
    null, "" -> ""
    "boot_disk" -> stringResource(R.string.why_boot_disk)
    "mounted" -> stringResource(R.string.why_mounted)
    "read_only" -> stringResource(R.string.why_read_only)
    "too_small" -> stringResource(R.string.why_too_small)
    "no_space" -> stringResource(R.string.why_no_space)
    "no_gpt" -> stringResource(R.string.why_no_gpt)
    "table_full" -> stringResource(R.string.why_table_full)
    "name_clash" -> stringResource(R.string.why_name_clash)
    "busy" -> stringResource(R.string.why_busy)
    else -> why
}

/** `source.why` when the stick cannot be installed from. */
@Composable
fun sourceWhySentence(why: String?): String = when (why) {
    null, "" -> stringResource(R.string.source_why_unknown)
    "no_manifest", "manifest_missing" -> stringResource(R.string.source_why_no_manifest)
    "no_install_data" -> stringResource(R.string.source_why_no_install_data)
    else -> why
}

@Composable
fun diskWarningSentence(code: String): String = when (code) {
    "external" -> stringResource(R.string.disk_warning_external)
    "encrypted" -> stringResource(R.string.disk_warning_encrypted)
    else -> code
}

@Composable
fun planWarningSentence(code: String, alongside: Boolean): String = when (code) {
    "nvram_unavailable" -> if (alongside) {
        stringResource(R.string.plan_warning_nvram_alongside)
    } else {
        stringResource(R.string.plan_warning_nvram_whole)
    }
    "boot_order_unchanged" -> stringResource(R.string.plan_warning_boot_order_unchanged)
    "external" -> stringResource(R.string.plan_warning_external)
    "encrypted_kept" -> stringResource(R.string.plan_warning_encrypted_kept)
    "encrypted_erased" -> stringResource(R.string.plan_warning_encrypted_erased)
    "battery" -> stringResource(R.string.plan_warning_battery)
    else -> code
}

/** Error codes of `plan` / `apply` that the user can act on. */
@Composable
fun errorSentence(code: String?, fallback: String?): String = when (code) {
    "unreachable" -> stringResource(R.string.error_unreachable)
    "busy" -> stringResource(R.string.error_busy)
    "no_source" -> stringResource(R.string.error_no_source)
    "no_target" -> stringResource(R.string.error_no_target)
    "not_eligible" -> stringResource(R.string.error_not_eligible)
    "plan_changed" -> stringResource(R.string.error_plan_changed)
    "confirm_mismatch" -> stringResource(R.string.error_confirm_mismatch)
    "power" -> stringResource(R.string.error_power)
    else -> fallback?.takeIf { it.isNotBlank() } ?: stringResource(R.string.error_generic)
}

@Composable
fun busLabel(bus: String): String = when (bus) {
    "nvme" -> stringResource(R.string.bus_nvme)
    "sata", "ata" -> stringResource(R.string.bus_sata)
    "usb" -> stringResource(R.string.bus_usb)
    "mmc", "emmc" -> stringResource(R.string.bus_mmc)
    "virtio" -> stringResource(R.string.bus_virtio)
    "scsi" -> stringResource(R.string.bus_scsi)
    "" -> ""
    else -> bus.uppercase()
}

/** Bar segment kinds: windows, linux, efi, openbook, other, free (PROTOCOL.md, plan before/after). */
fun partitionKind(p: Partition): String = when {
    p.type == "free" -> "free"
    p.os.equals("windows", ignoreCase = true) || p.type == "msreserved" || p.type == "msrecovery" -> "windows"
    p.type == "esp" || p.type == "xbootldr" -> "efi"
    p.os.equals("linux", ignoreCase = true) || p.type.startsWith("linux") || p.type == "luks" -> "linux"
    p.type == "android" -> "openbook"
    else -> "other"
}

@Composable
fun kindLabel(kind: String): String = when (kind) {
    "windows" -> stringResource(R.string.kind_windows)
    "linux" -> stringResource(R.string.kind_linux)
    "efi" -> stringResource(R.string.kind_efi)
    "openbook" -> stringResource(R.string.kind_openbook)
    "free" -> stringResource(R.string.kind_free)
    else -> stringResource(R.string.kind_other)
}

fun fsLabel(fs: String): String = when (fs) {
    "ntfs" -> "NTFS"
    "vfat" -> "FAT32"
    "exfat" -> "exFAT"
    "btrfs" -> "Btrfs"
    "xfs" -> "XFS"
    "f2fs" -> "F2FS"
    "bitlocker" -> "BitLocker"
    "luks" -> "LUKS"
    "erofs" -> "EROFS"
    else -> fs
}

@Composable
fun stepLabel(step: String, done: Boolean): String = when (step) {
    "check_source" -> stringResource(if (done) R.string.step_check_source_done else R.string.step_check_source)
    "prepare_disk" -> stringResource(if (done) R.string.step_prepare_disk_done else R.string.step_prepare_disk)
    "boot_images" -> stringResource(if (done) R.string.step_boot_images_done else R.string.step_boot_images)
    "system" -> stringResource(if (done) R.string.step_system_done else R.string.step_system)
    "boot_entry" -> stringResource(if (done) R.string.step_boot_entry_done else R.string.step_boot_entry)
    "verify" -> stringResource(if (done) R.string.step_verify_done else R.string.step_verify)
    "report" -> stringResource(if (done) R.string.step_report_done else R.string.step_report)
    else -> step
}

/** A duration such as "about 2 minutes" (plan summary). */
@Composable
fun etaText(seconds: Int): String {
    if (seconds < 60) return stringResource(R.string.duration_under_minute)
    val minutes = (seconds + 59) / 60
    return pluralStringResource(R.plurals.duration_minutes, minutes, minutes)
}
