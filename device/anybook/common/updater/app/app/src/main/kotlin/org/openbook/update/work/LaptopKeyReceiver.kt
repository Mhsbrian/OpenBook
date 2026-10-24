// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import org.openbook.update.Graph
import org.openbook.update.system.LaptopKey
import kotlin.concurrent.thread

/**
 * Gives OpenBook's update tooling this laptop's update certificate, for the one OpenBook update that
 * enrolls it (creating the key first if needed): `am broadcast -a org.openbook.update.action.LAPTOP_KEY
 * -n org.openbook.update/.work.LaptopKeyReceiver` returns the certificate (PEM) as the result data. Only the
 * shell and the system hold DUMP; the certificate is public, the key never leaves Android Keystore.
 */
class LaptopKeyReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION || !Graph.runsHere()) return
        val pending = goAsync()
        thread(name = "laptop-key") {
            try {
                pending.resultData = LaptopKey.certificatePem(LaptopKey.ensure())
                pending.resultCode = 0
            } catch (t: Throwable) {
                Log.w(TAG, "this laptop's update key is not available: $t")
                pending.resultCode = 1
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        const val ACTION = "org.openbook.update.action.LAPTOP_KEY"
        private const val TAG = "OpenBookUpdate"
    }
}
