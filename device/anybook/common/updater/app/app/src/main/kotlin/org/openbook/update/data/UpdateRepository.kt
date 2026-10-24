// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.data

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.PowerManager
import android.util.Log
import androidx.work.WorkInfo
import androidx.work.WorkManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import org.openbook.update.Graph
import org.openbook.update.engine.AdaptFacts
import org.openbook.update.engine.DownloadFacts
import org.openbook.update.engine.EngineState
import org.openbook.update.engine.Release
import org.openbook.update.work.RestartWatch
import org.openbook.update.work.Scheduler

/** The screen's view of the updater: the engine's files, background work, update_engine and settings, combined. */
class UpdateRepository(private val context: Context) {
    private val work = WorkManager.getInstance(context)
    private val connectivity = context.getSystemService(ConnectivityManager::class.java)

    private data class Snapshot(
        val system: SystemInfo, val state: EngineState, val release: EngineState, val disk: DownloadFacts,
        val downloaded: Release?, val lastChecked: Long, val unmetered: Boolean, val pausedRelease: Long,
        val adapt: AdaptFacts,
    )

    /** The engine replaces its files atomically; reading them once a second is cheap and always consistent. */
    private fun snapshots(): Flow<Snapshot> = flow {
        val engine = Graph.engine()
        val system = SystemInfo.read()                               // spawns getprop: here, on the IO dispatcher
        while (true) {
            val release = engine.readRelease()
            val downloaded = engine.verifiedDownload()
            emit(Snapshot(system, engine.readState(), release, engine.downloadFacts(Release.of(release)),
                          downloaded, Graph.settings.lastCheckedMillis, unmetered(),
                          Graph.settings.pausedRelease, engine.adaptFacts(downloaded)))
            delay(1_000)
        }
    }.distinctUntilChanged().flowOn(Dispatchers.IO)

    private fun unmetered(): Boolean = connectivity.getNetworkCapabilities(connectivity.activeNetwork)
        ?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED) == true

    private fun running(infos: List<WorkInfo>) = infos.any { it.state == WorkInfo.State.RUNNING }

    fun state(): Flow<UpdateUiState> = combine(
        snapshots(),
        combine(work.getWorkInfosForUniqueWorkFlow(Scheduler.CHECK_NOW),
                work.getWorkInfosForUniqueWorkFlow(Scheduler.CHECK_PERIODIC)) { now, periodic -> running(now) || running(periodic) },
        work.getWorkInfosForUniqueWorkFlow(Scheduler.DOWNLOAD),
        Graph.updateEngine.status,
        Graph.settings.preferences,
    ) { snap, checking, downloads, installer, prefs ->
        val download = when {
            downloads.any { it.state == WorkInfo.State.RUNNING } -> DownloadWork.RUNNING
            downloads.any { it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.BLOCKED } -> DownloadWork.WAITING
            else -> DownloadWork.NONE
        }
        val paused = Release.of(snap.release)?.number?.let { it == snap.pausedRelease } ?: false
        UpdateStateReducer.reduce(Inputs(
            snap.state, snap.release, snap.disk, checking, download,
            if (snap.unmetered) WaitReason.LATER else WaitReason.UNMETERED_NETWORK,
            installer, snap.system, snap.lastChecked, prefs.autoDownload && !paused, downloaded = snap.downloaded,
            adapt = snap.adapt,
        ))
    }.distinctUntilChanged()

    fun checkNow() = Scheduler.checkNow(context)

    /** Starts or resumes the download the owner asked for; a pause they set earlier no longer applies. */
    fun download() {
        Graph.settings.pausedRelease = 0
        Scheduler.download(context)
    }

    /** Pauses the download and remembers it, so the next check does not start it again by itself. */
    fun pauseDownload() {
        Release.of(Graph.engine().readRelease())?.let { Graph.settings.pausedRelease = it.number }
        Scheduler.stopDownload(context)
    }

    fun setAutoDownload(value: Boolean) = Graph.settings.setAutoDownload(value)
    fun setCheckEveryDays(days: Int) {
        Graph.settings.setCheckEveryDays(days)
        Scheduler.ensurePeriodic(context, replace = true)
    }

    /** Restarts into the installed update after the owner confirmed. False when this app may not restart. */
    fun restart(): Boolean {
        if (!Graph.runsHere()) return false
        val settings = Graph.settings
        val before = settings.pendingRestart
        settings.pendingRestart = (before ?: PendingRestart(SystemInfo.read().mark, RestartWatch.bootCount(context)))
            .copy(confirmedByOwner = true)
        return try {
            context.getSystemService(PowerManager::class.java).reboot(null)
            true
        } catch (e: SecurityException) {
            Log.w("OpenBookUpdate", "restart refused: $e")
            settings.pendingRestart = before
            false
        }
    }
}
