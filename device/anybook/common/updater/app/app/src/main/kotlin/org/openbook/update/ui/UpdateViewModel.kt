// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.openbook.update.Graph
import org.openbook.update.data.SystemInfo
import org.openbook.update.data.UpdateRepository
import org.openbook.update.data.UpdateUiState
import org.openbook.update.work.Scheduler

class UpdateViewModel(app: Application) : AndroidViewModel(app) {
    private val repository = UpdateRepository(app)

    /** False for a guest or another non-admin user: they see who manages updates, nothing else. */
    val runsHere: Boolean = Graph.runsHere()
    val state: StateFlow<UpdateUiState> = repository.state()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), UpdateUiState.Loading(SystemInfo.basic()))
    val preferences = Graph.settings.preferences
    val history = Graph.history.entries

    /**
     * Opening the app refreshes update_engine's status and checks when the last attempt is over
     * [STALE_MILLIS] old (like Android's own update screen), but never in the middle of a download.
     */
    fun onOpened() {
        if (!runsHere) return
        val app = getApplication<Application>()
        Scheduler.ensurePeriodic(app)
        viewModelScope.launch(Dispatchers.IO) {
            Graph.updateEngine.refresh()
            // A verified download not yet built for this laptop (or held under an earlier system's layer).
            Graph.engine().verifiedDownload()?.let { Scheduler.adapt(app) }
            val downloading = WorkManager.getInstance(app).getWorkInfosForUniqueWork(Scheduler.DOWNLOAD).get()
                .any { it.state == WorkInfo.State.RUNNING }
            if (!downloading && System.currentTimeMillis() - Graph.settings.lastAttemptMillis > STALE_MILLIS) repository.checkNow()
        }
    }

    fun check() = repository.checkNow()

    /** Installs this laptop's own build after the owner approved it in the review ([restartAfter]: they confirmed the restart too). */
    fun install(restartAfter: Boolean) = Scheduler.install(getApplication(), restartAfter)
    fun download() = repository.download()
    fun pause() = repository.pauseDownload()

    /** Restarts into the installed update (after the owner confirmed); [onRefused] if this app may not. */
    fun restart(onRefused: () -> Unit) {
        viewModelScope.launch(Dispatchers.IO) {
            if (!repository.restart()) withContext(Dispatchers.Main) { onRefused() }
        }
    }

    fun setAutoDownload(value: Boolean) = repository.setAutoDownload(value)
    fun setCheckEveryDays(days: Int) = repository.setCheckEveryDays(days)

    companion object {
        const val STALE_MILLIS = 12 * 60 * 60 * 1000L
    }
}
