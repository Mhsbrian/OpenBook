// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.Context
import android.content.pm.ServiceInfo
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import org.openbook.update.Graph
import org.openbook.update.data.Capabilities
import org.openbook.update.data.HistoryEntry
import org.openbook.update.data.UpdateRepository
import org.openbook.update.engine.AdaptFacts
import org.openbook.update.notify.Notifier
import org.openbook.update.system.PayloadServer
import java.io.File

/**
 * Installs this laptop's own signed build into the other slot after the owner approved it in the app
 * (phase 4): the payload is served on the loopback interface for the time update_engine reads it, and
 * update_engine checks its signature against the running system's certificates before writing anything.
 * The restart stays the owner's (RESTART_AFTER: right after the install, otherwise when they confirm).
 */
class InstallWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        if (!Graph.runsHere() || !Capabilities.CURRENT.installOnLaptop) return Result.success()
        val engine = Graph.engine()
        val release = engine.verifiedDownload() ?: return Result.failure()
        if (engine.adaptFacts(release).status != AdaptFacts.Status.READY) return Result.failure()
        val dir = engine.payloadDir(release)
        val payload = File(dir, "payload.bin")
        val properties = JSONObject(File(dir, "payload.json").readText()).getJSONArray("properties")
            .let { a -> List(a.length()) { a.getString(it) } }
        runCatching {
            setForeground(ForegroundInfo(Notifier.PROGRESS_ID, Graph.notifier.installing(release.label()),
                                         ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC))
        }.onFailure { if (it is CancellationException) throw it }
        val client = Graph.updateEngine
        PayloadServer(payload).use { server ->
            Log.i(TAG, "installing ${release.label()} from this laptop's build")
            client.apply(server.url, payload.length(), properties)
            // update_engine reads the payload while it writes; the loopback server lives until it reports.
            val code = withTimeoutOrNull(TIMEOUT_MILLIS) { client.completed.filterNotNull().first() }
            Log.i(TAG, "install finished: update_engine error code $code")
            if (code != 0) {
                Graph.history.add(HistoryEntry(System.currentTimeMillis(), HistoryEntry.Type.INSTALL_FAILED, release.label()))
                Graph.notifier.installFailed(code)
                return Result.failure()
            }
        }
        Graph.history.add(HistoryEntry(System.currentTimeMillis(), HistoryEntry.Type.INSTALLED_PENDING_RESTART, release.label()))
        // "Install and restart": the owner confirmed the restart with the install.
        if (inputData.getBoolean(RESTART_AFTER, false)) UpdateRepository(applicationContext).restart()
        return Result.success()
    }

    companion object {
        const val TAG = "OpenBookUpdate"
        const val RESTART_AFTER = "restart_after"
        private const val TIMEOUT_MILLIS = 3 * 60 * 60 * 1000L
    }
}
