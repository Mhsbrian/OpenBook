// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.notify

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.text.format.Formatter
import androidx.core.app.NotificationCompat
import org.openbook.update.R
import org.openbook.update.data.RestartOutcome
import org.openbook.update.engine.Release
import org.openbook.update.engine.ReleaseKind
import org.openbook.update.ui.MainActivity
import org.openbook.update.work.label

/** The app's notifications. Each opens the app; nothing installs or restarts from a notification. */
class Notifier(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)

    fun createChannels() {
        manager.createNotificationChannels(listOf(
            NotificationChannel(UPDATES, context.getString(R.string.channel_updates), NotificationManager.IMPORTANCE_DEFAULT)
                .apply { description = context.getString(R.string.channel_updates_description) },
            NotificationChannel(PROGRESS, context.getString(R.string.channel_progress), NotificationManager.IMPORTANCE_LOW)
                .apply { description = context.getString(R.string.channel_progress_description) },
            NotificationChannel(ACTION, context.getString(R.string.channel_action), NotificationManager.IMPORTANCE_HIGH)
                .apply { description = context.getString(R.string.channel_action_description) },
        ))
    }

    private fun open() = PendingIntent.getActivity(
        context, 0,
        Intent(context, MainActivity::class.java).setAction(Intent.ACTION_MAIN)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    /** The restart confirmation, through the app's non-exported alias: no other app can open it. */
    private fun confirmRestart() = PendingIntent.getActivity(
        context, 1,
        Intent().setComponent(ComponentName(context, CONFIRM_RESTART_ALIAS))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun builder(channel: String, title: String, text: String?) = NotificationCompat.Builder(context, channel)
        .setSmallIcon(R.drawable.ic_notification)
        .setContentTitle(title)
        .setContentText(text)
        .setStyle(NotificationCompat.BigTextStyle().bigText(text))
        .setContentIntent(open())
        .setAutoCancel(true)
        .setCategory(NotificationCompat.CATEGORY_STATUS)

    /** Posts it when the owner can see it; false otherwise (no permission yet, notifications or channel off). */
    private fun post(id: Int, notification: Notification): Boolean {
        if (context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return false
        if (!manager.areNotificationsEnabled()) return false
        val channel = manager.getNotificationChannel(notification.channelId)
        if (channel != null && channel.importance == NotificationManager.IMPORTANCE_NONE) return false
        manager.notify(id, notification)
        return true
    }

    private fun kindLabel(kind: ReleaseKind) = context.getString(when (kind) {
        ReleaseKind.MONTHLY -> R.string.kind_monthly
        ReleaseKind.QUARTERLY -> R.string.kind_quarterly
        ReleaseKind.UNKNOWN -> R.string.kind_unknown
    })

    fun updateFound(release: Release) = post(FOUND_ID, builder(UPDATES, context.getString(R.string.notify_found_title),
        context.getString(R.string.notify_found_text, kindLabel(release.kind), release.label())).build())

    fun held(release: Release) = post(FOUND_ID, if (release.kind == ReleaseKind.QUARTERLY)
        builder(UPDATES, context.getString(R.string.notify_held_title), context.getString(R.string.notify_held_text, release.label())).build()
        else builder(UPDATES, context.getString(R.string.notify_review_title), context.getString(R.string.notify_review_text, release.label())).build())

    fun downloaded(release: Release) = post(FOUND_ID, builder(UPDATES, context.getString(R.string.notify_downloaded_title),
        context.getString(R.string.notify_downloaded_text, release.label())).build())

    fun progress(label: String?, done: Long, total: Long?): Notification {
        val text = if (total != null && total > 0) context.getString(R.string.progress_of,
            Formatter.formatShortFileSize(context, done), Formatter.formatShortFileSize(context, total))
            else context.getString(R.string.progress_unknown_total, Formatter.formatShortFileSize(context, done))
        val percent = if (total != null && total > 0) (done * 100 / total).toInt().coerceIn(0, 100) else 0
        return NotificationCompat.Builder(context, PROGRESS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.downloading_title))
            .setSubText(label)
            .setContentText(text)
            .setProgress(100, percent, total == null || total <= 0)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(open())
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .build()
    }

    fun restartRequired() = post(RESTART_ID, builder(ACTION, context.getString(R.string.notify_restart_title),
        context.getString(R.string.notify_restart_text))
        .setAutoCancel(false)
        .addAction(0, context.getString(R.string.notify_restart_action), confirmRestart())
        .build())

    fun cancelRestart() = manager.cancel(RESTART_ID)

    fun outcome(outcome: RestartOutcome, label: String): Boolean {
        val (title, text) = when (outcome) {
            is RestartOutcome.Updated -> R.string.outcome_updated_title to context.getString(R.string.outcome_updated_body, label)
            is RestartOutcome.WentBack -> R.string.outcome_went_back_title to context.getString(R.string.outcome_went_back_body, label)
            is RestartOutcome.Changed -> R.string.outcome_changed_title to context.getString(R.string.outcome_updated_body, label)
            RestartOutcome.None -> return false
        }
        cancelRestart()
        return post(OUTCOME_ID, builder(UPDATES, context.getString(title), text).build())
    }

    fun storage() = post(PROBLEM_ID, builder(UPDATES, context.getString(R.string.notify_storage_title),
        context.getString(R.string.failed_storage_body)).build())

    fun checksumFailed() = post(PROBLEM_ID, builder(UPDATES, context.getString(R.string.notify_verification_title),
        context.getString(R.string.notify_verification_text)).build())

    fun downloadSlowed() = post(PROBLEM_ID, builder(UPDATES, context.getString(R.string.notify_slowed_title),
        context.getString(R.string.notify_slowed_text)).build())

    companion object {
        const val UPDATES = "updates"
        const val PROGRESS = "progress"
        const val ACTION = "restart"
        const val FOUND_ID = 1
        const val PROGRESS_ID = 2
        const val RESTART_ID = 3
        const val OUTCOME_ID = 4
        const val PROBLEM_ID = 5
        const val CONFIRM_RESTART_ALIAS = "org.openbook.update.ui.ConfirmRestart"
    }
}
