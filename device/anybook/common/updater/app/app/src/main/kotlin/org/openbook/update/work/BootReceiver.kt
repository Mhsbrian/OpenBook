// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import kotlinx.coroutines.launch
import org.openbook.update.Graph
import org.openbook.update.UpdateApp

/** At boot (and after the app itself is updated): keep the regular check scheduled; judge a restart; build a waiting download. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!Graph.runsHere()) return
        val pending = goAsync()
        (context.applicationContext as UpdateApp).scope.launch {
            try {
                Scheduler.ensurePeriodic(context)
                Log.i("OpenBookUpdate", "${intent.action}: regular checks scheduled")
                if (intent.action == Intent.ACTION_BOOT_COMPLETED) RestartWatch.atBoot(context)
                // A verified download not yet built for this laptop, or held under the previous system's layer.
                if (Graph.engine().verifiedDownload() != null) Scheduler.adapt(context)
            } finally {
                pending.finish()
            }
        }
    }
}
