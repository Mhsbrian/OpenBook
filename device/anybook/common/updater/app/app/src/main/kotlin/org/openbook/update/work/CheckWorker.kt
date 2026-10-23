// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import org.openbook.update.Graph
import org.openbook.update.data.HistoryEntry
import org.openbook.update.engine.EngineExit
import org.openbook.update.engine.Release

/** Runs the engine's `check`; announces a new release once and starts its download if allowed. */
class CheckWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        if (!Graph.runsHere()) return Result.success()
        Graph.updateEngine.refresh()                          // a waiting install is noticed on each check too
        val settings = Graph.settings
        settings.lastAttemptMillis = System.currentTimeMillis()
        val engine = Graph.engine()
        val result = engine.run("check")
        Log.i(TAG, "check finished: exit ${result.code} (${result.exit})")
        if (result.exit == EngineExit.OK || result.exit == EngineExit.UPDATE_AVAILABLE) {
            settings.lastCheckedMillis = System.currentTimeMillis()
        }
        if (result.exit == EngineExit.UPDATE_AVAILABLE) {
            val release = Release.of(engine.readRelease()) ?: return Result.success()
            val held = release.kind.held
            val downloaded = engine.downloadFacts(release).verified
            if (settings.announcedFound != release.number) {
                Graph.history.add(HistoryEntry(System.currentTimeMillis(),
                    if (held) HistoryEntry.Type.HELD else HistoryEntry.Type.FOUND, release.label()))
                settings.announcedFound = release.number
            }
            // Shown once the owner can see notifications (an OpenBook update may arrive before they allow them).
            if (settings.notifiedFound != release.number && !downloaded &&
                (if (held) Graph.notifier.held(release) else Graph.notifier.updateFound(release))) {
                settings.notifiedFound = release.number
            }
            if (downloaded && settings.notifiedDownloaded != release.number && Graph.notifier.downloaded(release)) {
                settings.notifiedDownloaded = release.number
            }
            if (!held && !downloaded && settings.preferences.value.autoDownload && settings.pausedRelease != release.number) {
                Scheduler.download(applicationContext)
            }
        }
        // A failed check is recorded by the engine and shown in the app; the next period tries again.
        return Result.success()
    }

    companion object {
        const val TAG = "OpenBookUpdate"
    }
}

fun Release.label() = if (buildId.isNotEmpty()) "$buildId ($number)" else number.toString()
