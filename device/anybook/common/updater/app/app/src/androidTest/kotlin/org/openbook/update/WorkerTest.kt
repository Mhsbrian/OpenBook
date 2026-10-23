// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import android.app.NotificationManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.NetworkType
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.testing.TestListenableWorkerBuilder
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.openbook.update.data.HistoryEntry
import org.openbook.update.work.CheckWorker
import org.openbook.update.work.Scheduler
import java.io.File

/** The check job, end to end on the device: engine, history, notification and the queued Wi-Fi download. */
@RunWith(AndroidJUnit4::class)
class WorkerTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val work = WorkManager.getInstance(context)

    @Before fun setUp() {
        work.cancelAllWork().result.get()
        File(context.filesDir, "updater").deleteRecursively()
    }

    @After fun tearDown() {
        work.cancelAllWork().result.get()
        Graph.listingForTests = null
        Graph.engineEnvironmentForTests = emptyMap()
    }

    @Test fun checkAnnouncesOnceAndQueuesTheWifiDownload() = runBlocking {
        val fx = Fixtures(context)
        Graph.engineEnvironmentForTests = fx.environment
        Graph.listingForTests = fx.listing("monthly.json", fx.monthly)
        Graph.settings.announcedFound = 0
        Graph.settings.notifiedFound = 0
        Graph.settings.pausedRelease = 0
        Graph.settings.setAutoDownload(true)
        // The queued download may start and finish meanwhile (adding its own entry): count announcements only.
        fun found() = Graph.history.entries.value.count { it.type == HistoryEntry.Type.FOUND && it.build.contains("${fx.newer}") }
        val before = found()
        TestListenableWorkerBuilder<CheckWorker>(context).build().doWork()
        assertEquals(before + 1, found())
        assertEquals(fx.newer, Graph.settings.announcedFound)
        // Shown (the worker records it only when the owner can see it). The queued download may already have
        // finished and replaced it with "downloaded" (the same notification slot).
        assertEquals(fx.newer, Graph.settings.notifiedFound)
        val nm = context.getSystemService(NotificationManager::class.java)
        assertTrue(nm.activeNotifications.any {
            it.notification.extras.getString("android.title") in setOf("Googlebook update available", "Update downloaded and verified") })
        val queued = work.getWorkInfosForUniqueWork(Scheduler.DOWNLOAD).get()
        assertTrue(queued.any { it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.RUNNING })
        assertEquals(NetworkType.UNMETERED, queued.first().constraints.requiredNetworkType)
        // The same release found again is not announced again; and a download the owner paused is not
        // started again by the check.
        work.cancelUniqueWork(Scheduler.DOWNLOAD).result.get()
        Graph.settings.pausedRelease = fx.newer
        TestListenableWorkerBuilder<CheckWorker>(context).build().doWork()
        assertEquals(before + 1, found())
        assertTrue(work.getWorkInfosForUniqueWork(Scheduler.DOWNLOAD).get().none {
            it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.RUNNING })
        Graph.settings.pausedRelease = 0
    }

    @Test fun theNextQuartersReleaseIsAnnouncedAsHeldAndNotDownloaded() = runBlocking {
        val fx = Fixtures(context)
        Graph.engineEnvironmentForTests = fx.environment
        Graph.listingForTests = fx.listing("quarterly.json", fx.quarterly)
        Graph.settings.announcedFound = 0
        TestListenableWorkerBuilder<CheckWorker>(context).build().doWork()
        assertEquals(HistoryEntry.Type.HELD, Graph.history.entries.value.first().type)
        assertTrue(work.getWorkInfosForUniqueWork(Scheduler.DOWNLOAD).get().isEmpty())
    }
}
