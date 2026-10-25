// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import org.openbook.graphics.data.GfxState
import org.openbook.graphics.data.Rules
import org.openbook.graphics.data.SystemBackend
import org.openbook.graphics.ui.MainActivity

/**
 * After a boot (docs/nvidia-graphics-modes.md §7): a new Ultimate that waits for the owner's Keep, or a failed one
 * the laptop came back from by itself, gets a notification that opens the app.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val pending = goAsync()
        Thread {
            try {
                SystemBackend.read()?.let { notify(context, it) }
            } finally {
                pending.finish()
            }
        }.start()
    }

    companion object {
        private const val TAG = "OpenBookGraphics"
        private const val CHANNEL = "graphics"
        private const val ID_KEEP = 1
        private const val ID_ROLLED_BACK = 2

        fun notify(context: Context, s: GfxState) {
            val text = when {
                Rules.asksToKeep(s) -> R.string.notify_keep
                s.rolledBack -> R.string.notify_rolled_back
                else -> return
            }
            val nm = context.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(CHANNEL, context.getString(R.string.channel_name),
                                                             NotificationManager.IMPORTANCE_HIGH))
            val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE)
            val n = android.app.Notification.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_graphics)
                .setContentTitle(context.getString(R.string.app_name))
                .setContentText(context.getString(text))
                .setStyle(android.app.Notification.BigTextStyle().bigText(context.getString(text)))
                .setContentIntent(open)
                .setAutoCancel(true)
                .build()
            Log.i(TAG, "boot: ${context.getString(text)}")
            runCatching { nm.notify(if (text == R.string.notify_keep) ID_KEEP else ID_ROLLED_BACK, n) }
                .onFailure { Log.w(TAG, "notification refused", it) }
        }
    }
}
