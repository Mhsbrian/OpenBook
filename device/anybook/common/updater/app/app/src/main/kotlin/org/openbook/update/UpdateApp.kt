// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import android.app.Application
import android.util.Log
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.openbook.update.work.RestartWatch

class UpdateApp : Application() {
    // A failure in background work is logged, never a crash of the app (it may be the owner's only updater).
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default +
        CoroutineExceptionHandler { _, e -> Log.e("OpenBookUpdate", "background work failed", e) })

    override fun onCreate() {
        super.onCreate()
        Graph.init(this)
        if (!Graph.runsHere()) {
            Log.i("OpenBookUpdate", "headless system user: the updater runs in the owner's user")
            return
        }
        Graph.notifier.createChannels()
        // Watch update_engine for as long as the process lives: an installed update that waits for a
        // restart is announced and remembered for the after-restart result. A later refresh() can bind
        // even if this first attempt fails.
        Graph.updateEngine.connect()
        scope.launch { RestartWatch.follow(this@UpdateApp) }
    }
}
