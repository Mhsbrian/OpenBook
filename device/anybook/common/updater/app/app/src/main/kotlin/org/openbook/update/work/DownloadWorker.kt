// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.Context
import android.content.pm.ServiceInfo
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkInfo
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.openbook.update.Graph
import org.openbook.update.data.HistoryEntry
import org.openbook.update.engine.EngineExit
import org.openbook.update.engine.Release
import org.openbook.update.notify.Notifier

/**
 * Runs the engine's `download` as a foreground job with a progress notification. When the network
 * becomes metered or the owner pauses, WorkManager stops the job: the engine ends its transfer (or
 * checksum) and keeps the partial file, and the next run resumes it.
 */
class DownloadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = coroutineScope {
        if (!Graph.runsHere()) return@coroutineScope Result.success()
        val engine = Graph.engine()
        var visible = showProgress(Release.of(engine.readRelease())?.label(), 0, null)
        val progress = launch {
            var tick = 0
            while (isActive) {
                // The engine's own check may have found a newer release than the last one: read it each time.
                val release = Release.of(engine.readRelease())
                val state = engine.readState()
                val done = engine.downloadFacts(release).partBytes
                val total = state.bytes?.takeIf { release != null && state.build == release.identifier }
                setProgress(workDataOf(DONE to done, TOTAL to (total ?: 0)))
                // Without a foreground notification (not allowed at the start, or the daily limit), try again
                // now and then: opening the app makes it allowed.
                if (visible || tick % 30 == 0) visible = showProgress(release?.label(), done, total)
                tick++
                delay(2_000)
            }
        }
        val result = try {
            engine.run("download")
        } catch (e: CancellationException) {
            // Android 15+ caps a data-sync foreground job at 6 hours a day: then it continues in the
            // background, more slowly, and the owner learns why.
            if (stopReason == WorkInfo.STOP_REASON_FOREGROUND_SERVICE_TIMEOUT) Graph.notifier.downloadSlowed()
            throw e
        } finally {
            progress.cancel()
        }
        Log.i(TAG, "download finished: exit ${result.code} (${result.exit})")
        val settings = Graph.settings
        val state = engine.readState()
        val release = Release.of(engine.readRelease())
        val label = release?.label()
        when (result.exit) {
            EngineExit.OK -> {
                if (release != null && state["verified"] == release.identifier) {
                    if (settings.announcedDownloaded != release.number) {
                        Graph.history.add(HistoryEntry(System.currentTimeMillis(), HistoryEntry.Type.DOWNLOADED, release.label()))
                        settings.announcedDownloaded = release.number
                    }
                    if (settings.notifiedDownloaded != release.number && Graph.notifier.downloaded(release)) {
                        settings.notifiedDownloaded = release.number
                    }
                    Scheduler.adapt(applicationContext) // build it for this laptop (phase 3)
                }
                Result.success()
            }
            EngineExit.HELD, EngineExit.LISTING_REFUSED, EngineExit.NOT_LISTED -> Result.success()
            EngineExit.CHECKSUM -> {
                val number = release?.number ?: 0
                settings.addChecksumFailure(number)
                Graph.history.add(HistoryEntry(System.currentTimeMillis(), HistoryEntry.Type.VERIFICATION_FAILED, label.orEmpty()))
                Graph.notifier.checksumFailed()
                // One more attempt from the start; a second mismatch waits for the next check instead of looping.
                if (settings.checksumFailures(number) < 2) Result.retry() else Result.failure()
            }
            EngineExit.SPACE -> { Graph.notifier.storage(); Result.failure() }
            EngineExit.NETWORK, EngineExit.BUSY, EngineExit.STOPPED -> Result.retry()
            else -> Result.failure()
        }
    }

    /** The progress notification as a foreground job; false when Android does not allow one now. */
    private suspend fun showProgress(label: String?, done: Long, total: Long?): Boolean = try {
        setForeground(ForegroundInfo(Notifier.PROGRESS_ID, Graph.notifier.progress(label, done, total),
                                     ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC))
        true
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) { // ForegroundServiceStartNotAllowedException, or the daily data-sync limit reached
        Log.w(TAG, "download runs without a foreground notification: $e")
        false
    }

    companion object {
        const val TAG = "OpenBookUpdate"
        const val DONE = "done"
        const val TOTAL = "total"
    }
}
