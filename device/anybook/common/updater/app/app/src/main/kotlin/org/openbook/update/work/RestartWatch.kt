// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.Context
import android.provider.Settings.Global
import android.util.Log
import org.openbook.update.Graph
import org.openbook.update.data.AfterRestart
import org.openbook.update.data.HistoryEntry
import org.openbook.update.data.PendingRestart
import org.openbook.update.data.RestartOutcome
import org.openbook.update.data.SystemInfo
import org.openbook.update.system.InstallerStatus

/** Connects update_engine's "installed, restart required" to the result shown after the restart. */
object RestartWatch {
    private const val TAG = "OpenBookUpdate"

    fun bootCount(context: Context) = Global.getInt(context.contentResolver, Global.BOOT_COUNT, 0)

    /** While the process lives: remember a waiting update and announce it once. */
    suspend fun follow(context: Context) {
        Graph.updateEngine.status.collect { status ->
            val settings = Graph.settings
            val boot = bootCount(context)
            when (status) {
                InstallerStatus.RestartRequired -> {
                    if (settings.pendingRestart == null) {
                        settings.pendingRestart = PendingRestart(SystemInfo.read().mark, boot)
                        Graph.history.add(HistoryEntry(System.currentTimeMillis(), HistoryEntry.Type.RESTART_REQUESTED))
                        Log.i(TAG, "an installed update waits for a restart")
                    }
                    if (!settings.restartNotified) settings.restartNotified = Graph.notifier.restartRequired()
                }
                // Recorded in this boot and gone again (the waiting update was withdrawn): forget it.
                // A record from an earlier boot is judged by atBoot instead.
                InstallerStatus.Idle -> settings.pendingRestart?.takeIf { it.bootCount == boot }?.let {
                    settings.pendingRestart = null
                    settings.restartNotified = false
                    Graph.notifier.cancelRestart()
                }
                else -> Unit
            }
        }
    }

    /** At boot: judge the restart against what was waiting, then remember this system. */
    fun atBoot(context: Context) {
        val settings = Graph.settings
        val current = SystemInfo.read().mark
        val pending = settings.pendingRestart?.takeIf { it.bootCount < bootCount(context) }
        val outcome = AfterRestart.evaluate(current, pending?.from, settings.lastSeen, pending?.confirmedByOwner ?: false)
        val now = System.currentTimeMillis()
        val label = "${current.buildId} (${current.incremental})"
        Log.i(TAG, "boot: running $label from slot ${current.slot ?: "unknown"}")
        when (outcome) {
            is RestartOutcome.Updated -> Graph.history.add(HistoryEntry(now, HistoryEntry.Type.INSTALLED, label))
            is RestartOutcome.WentBack -> Graph.history.add(HistoryEntry(now, HistoryEntry.Type.WENT_BACK, label))
            is RestartOutcome.Changed -> Graph.history.add(HistoryEntry(now, HistoryEntry.Type.SYSTEM_CHANGED, label))
            RestartOutcome.None -> Unit
        }
        if (outcome != RestartOutcome.None) {
            Graph.notifier.outcome(outcome, label)
            Log.i(TAG, "after the restart: $outcome")
        }
        if (pending != null) settings.pendingRestart = null
        settings.restartNotified = false
        settings.lastSeen = current
    }
}
