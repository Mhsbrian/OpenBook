// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.system

import android.os.Handler
import android.os.Looper
import android.os.UpdateEngine
import android.os.UpdateEngineCallback
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Android's update_engine as the app sees it. */
sealed interface InstallerStatus {
    /** No update_engine here (not an A/B device), or the app may not use it. */
    data object Unavailable : InstallerStatus
    data object Idle : InstallerStatus
    data class Installing(val stage: Stage, val percent: Int) : InstallerStatus
    /** An update is installed in the other slot and takes effect at the next restart. */
    data object RestartRequired : InstallerStatus

    enum class Stage { DOWNLOADING, VERIFYING, FINALIZING }

    companion object {
        /** update_engine's UpdateStatus values (system/update_engine). */
        fun of(status: Int, percent: Float): InstallerStatus = when (status) {
            3 -> Installing(Stage.DOWNLOADING, (percent * 100).toInt().coerceIn(0, 100))
            4 -> Installing(Stage.VERIFYING, (percent * 100).toInt().coerceIn(0, 100))
            5 -> Installing(Stage.FINALIZING, (percent * 100).toInt().coerceIn(0, 100))
            6 -> RestartRequired
            9 -> Unavailable
            else -> Idle // idle, error reporting, cleanup of the previous update (merge)
        }
    }
}

/**
 * Observes update_engine through the framework's UpdateEngine API. Binding reports the current status
 * at once, so a status is known moments after [connect] or [refresh]. The app only watches in this phase:
 * it never applies, cancels or resets.
 */
class UpdateEngineClient {
    private val _status = MutableStateFlow<InstallerStatus>(InstallerStatus.Unavailable)
    val status: StateFlow<InstallerStatus> = _status.asStateFlow()
    private var engine: UpdateEngine? = null

    private val callback = object : UpdateEngineCallback() {
        override fun onStatusUpdate(status: Int, percent: Float) {
            _status.value = InstallerStatus.of(status, percent)
        }

        override fun onPayloadApplicationComplete(errorCode: Int) {
            Log.i(TAG, "update_engine finished applying a payload: error code $errorCode")
        }
    }

    /**
     * Binds again, so the status is current even if update_engine restarted since (binding reports the
     * current status at once). Called when the app opens and on each check.
     */
    @Synchronized
    fun refresh(): Boolean {
        runCatching { engine?.unbind() }
        engine = null
        return connect()
    }

    @Synchronized
    fun connect(): Boolean {
        if (engine != null) return true
        return try {
            val e = UpdateEngine()
            if (!e.bind(callback, Handler(Looper.getMainLooper()))) {
                Log.w(TAG, "update_engine refused the binding")
                false
            } else {
                engine = e
                Log.i(TAG, "watching update_engine")
                true
            }
        } catch (t: Throwable) { // no service on this device, or not allowed: the app works without it
            Log.w(TAG, "update_engine is not available: $t")
            _status.value = InstallerStatus.Unavailable
            false
        }
    }

    companion object {
        private const val TAG = "OpenBookUpdate"
    }
}
