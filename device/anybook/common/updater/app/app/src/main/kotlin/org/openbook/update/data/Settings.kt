// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.data

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** The owner's choices. "Always ask before installing" is not a setting: system updates always ask. */
data class Preferences(val autoDownload: Boolean = true, val checkEveryDays: Int = 1)

/**
 * An installed update waiting for a restart: the system as it was, the boot (Settings.Global.BOOT_COUNT) that
 * saw it, and whether the owner confirmed the restart in the app (only then may "went back" be claimed).
 */
data class PendingRestart(val from: SystemMark, val bootCount: Int, val confirmedByOwner: Boolean = false)

class Settings(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("openbook-update", Context.MODE_PRIVATE)
    private val _preferences = MutableStateFlow(load())
    val preferences: StateFlow<Preferences> = _preferences.asStateFlow()

    private fun load() = Preferences(
        autoDownload = prefs.getBoolean(AUTO_DOWNLOAD, true),
        checkEveryDays = prefs.getInt(CHECK_EVERY_DAYS, 1).takeIf { it in CHECK_CHOICES } ?: 1,
    )

    fun setAutoDownload(value: Boolean) = update { putBoolean(AUTO_DOWNLOAD, value) }
    fun setCheckEveryDays(days: Int) {
        require(days in CHECK_CHOICES)
        update { putInt(CHECK_EVERY_DAYS, days) }
    }

    private fun update(change: SharedPreferences.Editor.() -> Unit) {
        prefs.edit(action = change)
        _preferences.value = load()
    }

    /** The last successful check. */
    var lastCheckedMillis: Long
        get() = prefs.getLong(LAST_CHECKED, 0)
        set(value) = prefs.edit { putLong(LAST_CHECKED, value) }

    /** The last check attempted, successful or not: opening the app does not repeat a recent one. */
    var lastAttemptMillis: Long
        get() = prefs.getLong(LAST_ATTEMPT, 0)
        set(value) = prefs.edit { putLong(LAST_ATTEMPT, value) }

    /** The release whose download the owner paused: not started again automatically until they resume. */
    var pausedRelease: Long
        get() = prefs.getLong(PAUSED_RELEASE, 0)
        set(value) = prefs.edit { putLong(PAUSED_RELEASE, value) }

    /** Checksum failures of one release's download: one more attempt after the first, then the next check. */
    fun checksumFailures(release: Long): Int =
        if (prefs.getLong(CHECKSUM_RELEASE, 0) == release) prefs.getInt(CHECKSUM_FAILURES, 0) else 0

    fun addChecksumFailure(release: Long) = prefs.edit {
        putInt(CHECKSUM_FAILURES, checksumFailures(release) + 1).putLong(CHECKSUM_RELEASE, release)
    }

    /** The release number the owner was last told about (found / downloaded), so each is announced once. */
    var announcedFound: Long
        get() = prefs.getLong(ANNOUNCED_FOUND, 0)
        set(value) = prefs.edit { putLong(ANNOUNCED_FOUND, value) }
    var announcedDownloaded: Long
        get() = prefs.getLong(ANNOUNCED_DOWNLOADED, 0)
        set(value) = prefs.edit { putLong(ANNOUNCED_DOWNLOADED, value) }

    /** What the owner was actually shown as a notification (history records the events regardless): a
     *  notification that could not be shown (no permission yet) is shown at a later check. */
    var notifiedFound: Long
        get() = prefs.getLong(NOTIFIED_FOUND, 0)
        set(value) = prefs.edit { putLong(NOTIFIED_FOUND, value) }
    var notifiedDownloaded: Long
        get() = prefs.getLong(NOTIFIED_DOWNLOADED, 0)
        set(value) = prefs.edit { putLong(NOTIFIED_DOWNLOADED, value) }
    var restartNotified: Boolean
        get() = prefs.getBoolean(RESTART_NOTIFIED, false)
        set(value) = prefs.edit { putBoolean(RESTART_NOTIFIED, value) }

    var pendingRestart: PendingRestart?
        get() = readMark(PENDING)?.let {
            PendingRestart(it, prefs.getInt("$PENDING.boot_count", 0), prefs.getBoolean("$PENDING.confirmed", false))
        }
        set(value) {
            writeMark(PENDING, value?.from)
            prefs.edit(commit = true) {
                if (value == null) remove("$PENDING.boot_count").remove("$PENDING.confirmed")
                else putInt("$PENDING.boot_count", value.bootCount).putBoolean("$PENDING.confirmed", value.confirmedByOwner)
            }
        }
    var lastSeen: SystemMark?
        get() = readMark(LAST_SEEN)
        set(value) = writeMark(LAST_SEEN, value)

    private fun readMark(key: String): SystemMark? {
        val fingerprint = prefs.getString("$key.fingerprint", null) ?: return null
        return SystemMark(fingerprint, prefs.getString("$key.incremental", "")!!, prefs.getString("$key.build_id", "")!!,
                          prefs.getString("$key.slot", null))
    }

    /** Synchronous (commit): a restart can follow at once, and the next boot reads it. */
    private fun writeMark(key: String, mark: SystemMark?) {
        prefs.edit(commit = true) {
            if (mark == null) listOf("fingerprint", "incremental", "build_id", "slot").forEach { remove("$key.$it") }
            else putString("$key.fingerprint", mark.fingerprint).putString("$key.incremental", mark.incremental)
                .putString("$key.build_id", mark.buildId).putString("$key.slot", mark.slot)
        }
    }

    companion object {
        val CHECK_CHOICES = setOf(1, 7)
        private const val AUTO_DOWNLOAD = "auto_download"
        private const val CHECK_EVERY_DAYS = "check_every_days"
        private const val LAST_CHECKED = "last_checked_millis"
        private const val LAST_ATTEMPT = "last_attempt_millis"
        private const val PAUSED_RELEASE = "paused_release"
        private const val CHECKSUM_RELEASE = "checksum_release"
        private const val CHECKSUM_FAILURES = "checksum_failures"
        private const val ANNOUNCED_FOUND = "announced_found"
        private const val ANNOUNCED_DOWNLOADED = "announced_downloaded"
        private const val NOTIFIED_FOUND = "notified_found"
        private const val NOTIFIED_DOWNLOADED = "notified_downloaded"
        private const val RESTART_NOTIFIED = "restart_notified"
        private const val PENDING = "pending_restart"
        private const val LAST_SEEN = "last_seen"
    }
}
