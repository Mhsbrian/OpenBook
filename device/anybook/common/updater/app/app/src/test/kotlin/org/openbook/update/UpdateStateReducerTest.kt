// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.openbook.update.data.Capabilities
import org.openbook.update.data.DownloadWork
import org.openbook.update.data.HoldReason
import org.openbook.update.data.Inputs
import org.openbook.update.data.Problem
import org.openbook.update.data.Step
import org.openbook.update.data.SystemInfo
import org.openbook.update.data.UpdateStateReducer.reduce
import org.openbook.update.data.UpdateUiState
import org.openbook.update.data.WaitReason
import org.openbook.update.engine.AdaptFacts
import org.openbook.update.engine.DownloadFacts
import org.openbook.update.engine.EngineState
import org.openbook.update.engine.ReleaseKind
import org.openbook.update.system.InstallerStatus

class UpdateStateReducerTest {
    private val system = SystemInfo("CL3B.260622.276.R4", "16658739", "2026-10-01", "google/ruby/ruby:17/CL3B…", "_b")
    private val newer = "number=16999999\nlatest=16999999_CL3B.260722.140\nlatest_id=CL3B.260722.140\n" +
        "latest_date=2026-11-20\nkind=monthly\nmd5=00\n"
    private val same = "number=16658739\nlatest=16658739_CL3B.260622.276.R4\nlatest_id=CL3B.260622.276.R4\n"

    private fun inputs(state: String, release: String = "", vararg changes: (Inputs) -> Inputs) =
        changes.fold(Inputs(EngineState.parse(state), EngineState.parse(release), system = system)) { i, f -> f(i) }

    @Test fun neverCheckedAndUpToDate() {
        assertTrue(reduce(inputs("")) is UpdateUiState.NeverChecked)
        assertEquals(UpdateUiState.UpToDate(system, 42), reduce(inputs("result=up-to-date\n", same, { it.copy(lastCheckedMillis = 42) })))
        // A release record that the running build already reached (installed since) is no update.
        assertEquals(UpdateUiState.UpToDate(system, 0), reduce(inputs("result=error:3\n", same).let { it.copy(engine = EngineState.EMPTY) }))
    }

    @Test fun availableCarriesTheReleaseAndItsKind() {
        val s = reduce(inputs("result=update-available\n", newer)) as UpdateUiState.Available
        assertEquals(16999999L, s.release.number)
        assertEquals("CL3B.260722.140", s.release.buildId)
        assertEquals(ReleaseKind.MONTHLY, s.release.kind)
    }

    @Test fun newTrainsAndUnknownsAreHeld() {
        val q = reduce(inputs("result=update-available\n", newer.replace("kind=monthly", "kind=quarterly"))) as UpdateUiState.Held
        assertEquals(HoldReason.NEW_RELEASE_TRAIN, q.reason)
        val u = reduce(inputs("result=held\n", newer.replace("kind=monthly", "kind=unknown"))) as UpdateUiState.Held
        assertEquals(HoldReason.UNRECOGNIZED, u.reason)
        // No kind recorded: held, never offered.
        assertTrue(reduce(inputs("", newer.replace("kind=monthly\n", ""))) is UpdateUiState.Held)
    }

    @Test fun aVerifiedDownloadOnDiskOutlivesLaterChecks() {
        val verified = DownloadFacts(verified = true)
        for (state in listOf("result=update-available\n", "result=error:3\ndetail=offline\n", "result=stopped\n", "")) {
            val s = reduce(inputs(state, newer, { it.copy(disk = verified) })) as UpdateUiState.Preparing
            assertEquals(listOf(Step.Status.DONE, Step.Status.DONE, Step.Status.NOT_YET_AVAILABLE, Step.Status.NOT_YET_AVAILABLE,
                                Step.Status.NOT_YET_AVAILABLE), s.steps.map { it.status })
        }
        val later = reduce(inputs("", newer, { it.copy(disk = verified, capabilities = Capabilities(adaptOnLaptop = true)) }))
        assertEquals(Step.Status.PENDING, (later as UpdateUiState.Preparing).steps[2].status)
    }

    @Test fun aVerifiedDownloadStaysWhenTheListingMovesOn() {
        val downloaded = org.openbook.update.engine.Release(16900000, "CL3B.260722.140", "2026-11-20", ReleaseKind.MONTHLY)
        val quarterly = "number=17100000\nlatest_id=CL4A.260915.088\nkind=quarterly\n"
        // Google now lists only a held quarterly release: the verified monthly download is still the update.
        val s = reduce(inputs("result=update-available\n", quarterly, { it.copy(downloaded = downloaded) }))
        assertEquals(16900000L, (s as UpdateUiState.Preparing).release.number)
        // A newer monthly release replaces it (offered for download).
        val monthly = "number=16950000\nlatest_id=CL3B.260722.200\nkind=monthly\n"
        assertTrue(reduce(inputs("result=update-available\n", monthly, { it.copy(downloaded = downloaded) })) is UpdateUiState.Available)
        // An installed one is no update.
        assertTrue(reduce(inputs("", "", { it.copy(downloaded = downloaded.copy(number = 16658739)) })) is UpdateUiState.NeverChecked)
    }

    @Test fun downloadProgressWaitingAndPaused() {
        val dl = "result=downloading\nbuild=16999999_CL3B.260722.140\nbytes=8000000000\n"
        val running = reduce(inputs(dl, newer, { it.copy(download = DownloadWork.RUNNING, disk = DownloadFacts(partBytes = 2_000_000_000)) }))
        assertEquals(UpdateUiState.Downloading(system, (running as UpdateUiState.Downloading).release, 2_000_000_000, 8_000_000_000), running)
        val waiting = reduce(inputs(dl, newer, { it.copy(download = DownloadWork.WAITING, waitReason = WaitReason.LATER) })) as UpdateUiState.Waiting
        assertEquals(WaitReason.LATER, waiting.reason)
        // A partial download with nothing queued (paused, or a check ran since): Paused with its progress.
        val paused = reduce(inputs("result=update-available\n", newer, { it.copy(disk = DownloadFacts(partBytes = 5)) }))
        assertEquals(5L, (paused as UpdateUiState.Paused).doneBytes)
        assertTrue(reduce(inputs("result=verifying\n", newer, { it.copy(download = DownloadWork.RUNNING) })) is UpdateUiState.Verifying)
        // A running download wins over a check started meanwhile.
        assertTrue(reduce(inputs(dl, newer, { it.copy(download = DownloadWork.RUNNING, checking = true) })) is UpdateUiState.Downloading)
        // The total is only the current release's.
        val other = reduce(inputs("result=downloading\nbuild=16888888_X\nbytes=9\n", newer, { it.copy(download = DownloadWork.RUNNING) }))
        assertEquals(null, (other as UpdateUiState.Downloading).totalBytes)
    }

    @Test fun errorsMapToProblems() {
        val expected = mapOf(3 to Problem.NETWORK, 4 to Problem.CHECKSUM, 5 to Problem.STORAGE, 7 to Problem.NOT_LISTED,
                             9 to Problem.LISTING_REFUSED, 2 to Problem.INTERNAL)
        expected.forEach { (code, problem) ->
            val s = reduce(inputs("result=error:$code\ndetail=why\n")) as UpdateUiState.Failed
            assertEquals(problem, s.problem)
            assertEquals("why", s.detail)
        }
        // A busy engine (another run holds the lock) is no failure.
        assertTrue(reduce(inputs("result=error:6\n", newer)) is UpdateUiState.Available)
        // With a known release, a failure of this run names it.
        assertEquals(16999999L, (reduce(inputs("result=error:4\n", newer)) as UpdateUiState.Failed).release?.number)
    }

    @Test fun updateEngineComesFirst() {
        assertEquals(UpdateUiState.RestartRequired(system),
                     reduce(inputs("", newer, { it.copy(installer = InstallerStatus.RestartRequired, checking = true) })))
        val installing = reduce(inputs("", "", { it.copy(installer = InstallerStatus.Installing(InstallerStatus.Stage.VERIFYING, 40)) }))
        assertEquals(UpdateUiState.Installing(system, InstallerStatus.Stage.VERIFYING, 40), installing)
        assertTrue(reduce(inputs("", newer, { it.copy(checking = true) })) is UpdateUiState.Checking)
    }

    @Test fun installerStatusCodes() {
        assertEquals(InstallerStatus.Idle, InstallerStatus.of(0, 0f))
        assertEquals(InstallerStatus.Installing(InstallerStatus.Stage.DOWNLOADING, 25), InstallerStatus.of(3, 0.25f))
        assertEquals(InstallerStatus.Installing(InstallerStatus.Stage.FINALIZING, 100), InstallerStatus.of(5, 1.5f))
        assertEquals(InstallerStatus.RestartRequired, InstallerStatus.of(6, 0f))
        assertEquals(InstallerStatus.Unavailable, InstallerStatus.of(9, 0f))
        assertEquals(InstallerStatus.Idle, InstallerStatus.of(11, 0f)) // cleanup of the previous update
    }

    // Phase 3/4: the checklist follows the laptop's own build of a verified download.
    private val verified = DownloadFacts(verified = true)
    private val tools = Capabilities(adaptOnLaptop = true, installOnLaptop = false)
    private val enrolled = Capabilities(adaptOnLaptop = true, installOnLaptop = true)
    private fun adapting(caps: Capabilities, facts: AdaptFacts) =
        reduce(inputs("", newer, { it.copy(disk = verified, capabilities = caps, adapt = facts) }))
    private val done = Step.Status.DONE
    private val active = Step.Status.ACTIVE
    private val pending = Step.Status.PENDING
    private val later = Step.Status.NOT_YET_AVAILABLE

    @Test fun theChecklistFollowsTheAdaptation() {
        fun steps(s: UpdateUiState) = (s as UpdateUiState.Preparing).steps.map { it.status }.drop(2)
        assertEquals(listOf(pending, pending, pending), steps(adapting(tools, AdaptFacts.NONE)))
        assertEquals(listOf(active, pending, pending), steps(adapting(tools, AdaptFacts(AdaptFacts.Status.RUNNING, "reconstruct"))))
        assertEquals(listOf(active, pending, pending), steps(adapting(tools, AdaptFacts(AdaptFacts.Status.RUNNING, "check"))))
        assertEquals(listOf(done, active, pending), steps(adapting(tools, AdaptFacts(AdaptFacts.Status.RUNNING, "build"))))
        assertEquals(listOf(done, done, active), steps(adapting(tools, AdaptFacts(AdaptFacts.Status.RUNNING, "payload"))))
    }

    @Test fun withoutAnEnrolledKeyItIsBuiltButNeverOffered() {
        for (status in listOf(AdaptFacts.Status.ADAPTED, AdaptFacts.Status.READY)) {
            val s = adapting(tools, AdaptFacts(status)) as UpdateUiState.Preparing
            assertTrue(s.awaitingKey)
            assertEquals(listOf(done, done, later), s.steps.map { it.status }.drop(2))
        }
        // Enrolled: signed means ready to install; built but not yet signed is the last step running.
        assertTrue(adapting(enrolled, AdaptFacts(AdaptFacts.Status.READY)) is UpdateUiState.ReadyToInstall)
        val signing = adapting(enrolled, AdaptFacts(AdaptFacts.Status.ADAPTED)) as UpdateUiState.Preparing
        assertEquals(listOf(done, done, active), signing.steps.map { it.status }.drop(2))
    }

    @Test fun aHeldOrFailedAdaptationSaysWhy() {
        val held = adapting(tools, AdaptFacts(AdaptFacts.Status.HELD, detail = "/system/build.prop: Google changed it")) as UpdateUiState.Held
        assertEquals(HoldReason.ADAPTATION, held.reason)
        assertEquals("/system/build.prop: Google changed it", held.detail)
        val failed = adapting(tools, AdaptFacts(AdaptFacts.Status.FAILED, detail = "no space")) as UpdateUiState.Failed
        assertEquals(Problem.ADAPT, failed.problem)
        // A system without the tools: the steps come with a later OpenBook update, whatever is on disk.
        val old = adapting(Capabilities(), AdaptFacts(AdaptFacts.Status.HELD)) as UpdateUiState.Preparing
        assertEquals(listOf(later, later, later), old.steps.map { it.status }.drop(2))
    }

    @Test fun adaptFactsFromTheEnginesFiles() {
        val id = "16999999_CL3B.260722.140"
        fun of(state: String, step: String? = null, payload: String? = null, held: String? = null) =
            AdaptFacts.of(EngineState.parse(state), id, step, payload, held)
        assertEquals(AdaptFacts(AdaptFacts.Status.RUNNING, "build"), of("result=adapting\nbuild=$id\n", "build\n"))
        assertEquals(AdaptFacts(AdaptFacts.Status.RUNNING, "reconstruct"), of("result=adapting\nbuild=$id\n"))
        assertEquals(AdaptFacts.NONE, of("result=adapting\nbuild=16000000_X\n", "build\n")) // another release's run
        assertEquals(AdaptFacts(AdaptFacts.Status.FAILED, detail = "boom"), of("result=error:11\nbuild=$id\ndetail=boom\n"))
        assertEquals(AdaptFacts(AdaptFacts.Status.HELD, detail = "x"), of("result=up-to-date\n", held = "layer=ab\ndetail=x\n"))
        assertEquals(AdaptFacts(AdaptFacts.Status.ADAPTED), of("", payload = "{\"signed\": false}"))
        assertEquals(AdaptFacts(AdaptFacts.Status.READY), of("", payload = "{\n  \"signed\": true\n}"))
    }
}
