// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.openbook.update.data.Inputs
import org.openbook.update.data.SystemInfo
import org.openbook.update.data.UpdateStateReducer
import org.openbook.update.data.UpdateUiState
import org.openbook.update.engine.EngineExit
import org.openbook.update.engine.EngineRunner
import org.openbook.update.engine.Release
import org.openbook.update.engine.ReleaseKind
import java.io.File

/** The real engine, run by the app as its child process on Android's own mksh, toybox, awk and curl. */
@RunWith(AndroidJUnit4::class)
class EngineOnDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private lateinit var fx: Fixtures
    private lateinit var dir: File

    @Before fun setUp() {
        fx = Fixtures(context)
        dir = File(context.filesDir, "test-updater").apply { deleteRecursively() }
    }

    private fun runner(listing: String?) = EngineRunner(context, dataDir = dir, listing = listing, environment = fx.environment)

    @Test fun checkDownloadVerifyThenTheChecklist() = runBlocking {
        val engine = runner(fx.listing("monthly.json", fx.monthly))
        val check = engine.run("check")
        assertEquals(check.output, EngineExit.UPDATE_AVAILABLE, check.exit)
        val release = Release.of(engine.readRelease())!!
        assertEquals(ReleaseKind.MONTHLY, release.kind)
        val download = engine.run("download")
        assertEquals(download.output, EngineExit.OK, download.exit)
        assertEquals("${fx.newer}_${fx.monthly}", engine.readState()["verified"])
        assertTrue(File(dir, "${fx.newer}/recovery.zip").readBytes().contentEquals(fx.release.readBytes()))
        // A later check keeps the verified download in view (the release record and the files on disk).
        assertEquals(EngineExit.UPDATE_AVAILABLE, engine.run("check").exit)
        val shown = UpdateStateReducer.reduce(Inputs(engine.readState(), engine.readRelease(), engine.downloadFacts(release),
                                                     system = SystemInfo.read()))
        assertTrue(shown.toString(), shown is UpdateUiState.Preparing)
    }

    @Test fun theNextQuartersReleaseIsHeld() = runBlocking {
        val engine = runner(fx.listing("quarterly.json", fx.quarterly))
        val r = engine.run("download")
        assertEquals(r.output, EngineExit.HELD, r.exit)
        assertEquals(ReleaseKind.QUARTERLY, Release.of(engine.readRelease())!!.kind)
        assertTrue(!File(dir, fx.newer.toString()).exists())
    }

    @Test fun cancellingStopsTheTransferAndKeepsThePartial() = runBlocking {
        // An endless source: only a working stop ends this download.
        val engine = runner(fx.listing("endless.json", fx.monthly, url = "file:///dev/zero"))
        val part = File(dir, "${fx.newer}/recovery.zip.part")
        val job = async { engine.run("download") }
        withTimeout(30_000) { while (part.length() < 1_000_000) delay(50) }
        job.cancel()
        runCatching { job.await() }
        withTimeout(15_000) { while (engine.readState().result != "stopped") delay(50) }
        val size = part.length()
        delay(1_000)
        assertEquals("the transfer must have ended", size, part.length())
        assertTrue(size > 1_000_000)
        assertTrue(part.delete())
    }

    @Test fun liveGoogleListingFromTheAppDomain() = runBlocking {
        // A real HTTPS request to Google's public listing; an emulator is not a listed device.
        val r = runner(null).run("check")
        assertEquals(r.output, EngineExit.NOT_LISTED, r.exit)
    }
}
