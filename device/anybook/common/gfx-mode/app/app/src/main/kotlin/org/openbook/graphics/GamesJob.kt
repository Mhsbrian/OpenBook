// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import android.util.Log
import org.openbook.graphics.data.GamesRule
import org.openbook.graphics.data.SharedRulePrefs
import org.openbook.graphics.data.SyncResult
import org.openbook.graphics.data.SystemDriverBackend

/**
 * The games rule's periodic sync (docs/nvidia-offload-ruby.md, "Games on the NVIDIA GPU"). Android 8+ delivers no
 * PACKAGE_ADDED to a manifest receiver, and a persistent process that crashed in a loop would wake Rescue Party, so
 * a game installed between syncs starts on the Radeon until the next one: at most about 15 minutes, or at once
 * when the owner opens Apps on the NVIDIA GPU.
 */
class GamesJob : JobService() {
    override fun onStartJob(params: JobParameters): Boolean {
        Thread {
            try {
                sync(this, "job")
            } finally {
                jobFinished(params, false)
            }
        }.start()
        return true
    }

    override fun onStopJob(params: JobParameters) = false

    companion object {
        private const val TAG = "OpenBookGraphics"
        const val JOB_ID = 312
        private const val PERIOD_MILLIS = 15 * 60 * 1000L

        fun rule(context: Context) = GamesRule(SystemDriverBackend(context), SharedRulePrefs(context))

        /** One sync, in the owner's user only; logs one line. Blocking. */
        fun sync(context: Context, why: String): SyncResult? {
            if (!SystemDriverBackend.runsHere(context)) return null
            val rule = rule(context)
            val r = runCatching { rule.sync() }
                .onFailure { Log.w(TAG, "games: sync ($why) failed", it) }.getOrNull() ?: return null
            if (r.noDriver) {
                if (why != "job") Log.i(TAG, "games: no NVIDIA app driver installed (${rule.driverPackage()}), every app " +
                    "uses the Radeon; Android's driver lists left as they are ($why)")
                return r
            }
            if (r.changed || r.replacedAllApps || r.refused || why != "job") {
                Log.i(TAG, "games: ${r.games} on the NVIDIA GPU's list ($why)" +
                    (if (r.changed) ", list updated" else "") +
                    (if (r.replacedAllApps) ", \"all apps\" replaced by the games rule" else "") +
                    (if (r.refused) ", a settings write was refused" else ""))
            }
            return r
        }

        /**
         * The periodic job, unless it is already scheduled the same way (keeps its period across boots). None without
         * an NVIDIA app driver: one comes only with an image update, whose boot schedules it.
         */
        fun schedule(context: Context) {
            if (!SystemDriverBackend.runsHere(context)) return
            val js = context.getSystemService(JobScheduler::class.java)
            if (!rule(context).hasAppDriver()) {
                if (js.getPendingJob(JOB_ID) != null) js.cancel(JOB_ID)
                return
            }
            val pending = js.getPendingJob(JOB_ID)
            if (pending != null && pending.isPeriodic && pending.intervalMillis == PERIOD_MILLIS && pending.isPersisted) return
            val job = JobInfo.Builder(JOB_ID, ComponentName(context, GamesJob::class.java))
                .setPeriodic(PERIOD_MILLIS)
                .setPersisted(true)
                .build()
            if (js.schedule(job) != JobScheduler.RESULT_SUCCESS) Log.w(TAG, "games: the periodic sync was not scheduled")
        }
    }
}
