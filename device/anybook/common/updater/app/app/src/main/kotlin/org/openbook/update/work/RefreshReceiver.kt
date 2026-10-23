// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.openbook.update.Graph
import org.openbook.update.UpdateApp

/**
 * "Look at update_engine again": sent by OpenBook's update tooling after it staged an update, so the owner
 * sees "Restart to finish" at once. Only callers holding DUMP (the shell, the system) may send it.
 */
class RefreshReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!Graph.runsHere() || intent.action != ACTION) return
        val pending = goAsync()
        (context.applicationContext as UpdateApp).scope.launch(Dispatchers.IO) {
            try {
                Log.i("OpenBookUpdate", "refresh requested: binding update_engine again")
                Graph.updateEngine.refresh()
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        const val ACTION = "org.openbook.update.action.REFRESH"
    }
}
