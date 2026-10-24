// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import org.openbook.update.Graph
import java.util.concurrent.TimeUnit

/** The app's background work, all in WorkManager (visible in Android's settings like any app's). */
object Scheduler {
    const val CHECK_PERIODIC = "check-periodic"
    const val CHECK_NOW = "check-now"
    const val DOWNLOAD = "download"
    const val ADAPT = "adapt"
    const val INSTALL = "install"

    /** The regular check: every day or week, when a network is connected. */
    fun ensurePeriodic(context: Context, replace: Boolean = false) {
        val days = Graph.settings.preferences.value.checkEveryDays.toLong()
        val request = PeriodicWorkRequestBuilder<CheckWorker>(days, TimeUnit.DAYS)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 15, TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            CHECK_PERIODIC, if (replace) ExistingPeriodicWorkPolicy.UPDATE else ExistingPeriodicWorkPolicy.KEEP, request,
        )
    }

    /** A check the owner asked for: runs at once, so an offline laptop says so instead of waiting. */
    fun checkNow(context: Context) {
        val request = OneTimeWorkRequestBuilder<CheckWorker>()
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(CHECK_NOW, ExistingWorkPolicy.KEEP, request)
    }

    /** Downloads run only on unmetered networks, with enough storage; an interrupted one resumes. */
    fun download(context: Context) {
        val request = OneTimeWorkRequestBuilder<DownloadWorker>()
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.UNMETERED)
                    .setRequiresStorageNotLow(true)
                    .build(),
            )
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 1, TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(DOWNLOAD, ExistingWorkPolicy.KEEP, request)
    }

    /** Builds a verified download for this laptop: local work, when storage and battery allow. */
    fun adapt(context: Context) {
        if (!org.openbook.update.data.Capabilities.CURRENT.adaptOnLaptop) return
        val request = OneTimeWorkRequestBuilder<AdaptWorker>()
            .setConstraints(Constraints.Builder().setRequiresStorageNotLow(true).setRequiresBatteryNotLow(true).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(ADAPT, ExistingWorkPolicy.KEEP, request)
    }

    /** Installs this laptop's signed build: only after the owner approved it in the app. */
    fun install(context: Context, restartAfter: Boolean) {
        val request = OneTimeWorkRequestBuilder<InstallWorker>()
            .setInputData(androidx.work.workDataOf(InstallWorker.RESTART_AFTER to restartAfter))
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(INSTALL, ExistingWorkPolicy.KEEP, request)
    }

    /** Stops a download; the engine keeps the partial file for a later resume. */
    fun stopDownload(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(DOWNLOAD)
    }
}
