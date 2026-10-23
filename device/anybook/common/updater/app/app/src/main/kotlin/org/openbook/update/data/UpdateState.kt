// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.data

import org.openbook.update.engine.DownloadFacts
import org.openbook.update.engine.EngineState
import org.openbook.update.engine.Release
import org.openbook.update.engine.ReleaseKind
import org.openbook.update.system.InstallerStatus

/** What the laptop can do on its own today (docs/googlebook-on-device-updater.md, phases). */
data class Capabilities(
    /** Phase 3: rebuild Google's release with the OpenBook layer and check it. */
    val adaptOnLaptop: Boolean = false,
    /** Phase 4: build, sign and install the laptop's own update. */
    val installOnLaptop: Boolean = false,
) {
    companion object { val CURRENT = Capabilities() }
}

/** Where a download job stands in WorkManager. */
enum class DownloadWork { NONE, WAITING, RUNNING }

/** Why a queued download is not running. */
enum class WaitReason {
    /** No network, or only a metered one: downloads use Wi-Fi, Ethernet or another unmetered network. */
    UNMETERED_NETWORK,
    /** On a suitable network, but waiting for free storage or a retry: it continues by itself. */
    LATER,
}

/**
 * Everything the screen state is derived from: durable facts (Google's newest release from the last
 * successful check, what is on disk), the engine's last run, background work and update_engine.
 */
data class Inputs(
    val engine: EngineState,
    val release: EngineState = EngineState.EMPTY,
    val disk: DownloadFacts = DownloadFacts.NONE,
    val checking: Boolean = false,
    val download: DownloadWork = DownloadWork.NONE,
    val waitReason: WaitReason = WaitReason.UNMETERED_NETWORK,
    val installer: InstallerStatus = InstallerStatus.Unavailable,
    val system: SystemInfo,
    val lastCheckedMillis: Long = 0,
    val autoDownload: Boolean = true,
    val capabilities: Capabilities = Capabilities.CURRENT,
    /** The newest verified download on disk, which may be an earlier listing's release. */
    val downloaded: Release? = null,
)

/** Why an update cannot go further for now. */
enum class HoldReason {
    /** A new release train (a quarterly release, possibly a new Android version): it arrives as an OpenBook update. */
    NEW_RELEASE_TRAIN,
    /** The build IDs do not show what kind of release it is: OpenBook reviews it first. */
    UNRECOGNIZED,
}

enum class Problem { NETWORK, CHECKSUM, STORAGE, NOT_LISTED, BUSY, LISTING_REFUSED, INTERNAL }

/** One line of the preparation checklist. */
data class Step(val id: Id, val status: Status) {
    enum class Id { DOWNLOADED, VERIFIED, CHECKED_ADAPTATIONS, BUILT_FOR_LAPTOP, READY }
    enum class Status { DONE, ACTIVE, PENDING, NOT_YET_AVAILABLE, FAILED }
}

/** The single state the main screen shows. */
sealed interface UpdateUiState {
    val system: SystemInfo

    /** Before the first reading of the updater's files. */
    data class Loading(override val system: SystemInfo) : UpdateUiState
    data class NeverChecked(override val system: SystemInfo) : UpdateUiState
    data class Checking(override val system: SystemInfo) : UpdateUiState
    data class UpToDate(override val system: SystemInfo, val lastCheckedMillis: Long) : UpdateUiState
    data class Available(override val system: SystemInfo, val release: Release, val autoDownload: Boolean) : UpdateUiState
    data class Downloading(override val system: SystemInfo, val release: Release, val doneBytes: Long, val totalBytes: Long?) : UpdateUiState
    data class Waiting(override val system: SystemInfo, val release: Release, val doneBytes: Long, val totalBytes: Long?,
                       val reason: WaitReason) : UpdateUiState
    data class Paused(override val system: SystemInfo, val release: Release, val doneBytes: Long, val totalBytes: Long?) : UpdateUiState
    data class Verifying(override val system: SystemInfo, val release: Release) : UpdateUiState
    data class Preparing(override val system: SystemInfo, val release: Release, val steps: List<Step>) : UpdateUiState
    data class Held(override val system: SystemInfo, val release: Release, val reason: HoldReason) : UpdateUiState
    /** A version of [release] for this laptop is built and verified; the owner reviews and approves it (phase 4). */
    data class ReadyToInstall(override val system: SystemInfo, val release: Release) : UpdateUiState
    data class Installing(override val system: SystemInfo, val stage: InstallerStatus.Stage, val percent: Int) : UpdateUiState
    data class RestartRequired(override val system: SystemInfo) : UpdateUiState
    data class Failed(override val system: SystemInfo, val problem: Problem, val release: Release?, val detail: String?) : UpdateUiState
}

object UpdateStateReducer {
    fun reduce(i: Inputs): UpdateUiState {
        val s = i.system
        when (val installer = i.installer) {
            InstallerStatus.RestartRequired -> return UpdateUiState.RestartRequired(s)
            is InstallerStatus.Installing -> return UpdateUiState.Installing(s, installer.stage, installer.percent)
            else -> Unit
        }
        val e = i.engine
        // Only a release newer than the running build is an update (a record can outlive an install).
        val running = i.system.incremental.toLongOrNull()
        fun newer(r: Release?) = r?.takeIf { running != null && it.number > running }
        val release = newer(Release.of(i.release))
        // A verified download stays the laptop's update even when Google's listing moved on (the listing
        // names one build per device), unless a newer monthly release can replace it.
        val downloaded = newer(i.downloaded)?.takeIf { d -> release == null || release.kind.held || release.number <= d.number }
        val total = e.bytes?.takeIf { release != null && e.build == release.identifier }
        if (i.download == DownloadWork.RUNNING && release != null) {
            return if (e.result == "verifying") UpdateUiState.Verifying(s, release)
                   else UpdateUiState.Downloading(s, release, i.disk.partBytes, total)
        }
        if (i.checking) return UpdateUiState.Checking(s)
        if (downloaded != null) return prepared(s, downloaded, i.capabilities)
        val problem = problem(e.errorCode)
        if (release != null) {
            return when {
                i.disk.verified -> prepared(s, release, i.capabilities)
                release.kind.held -> UpdateUiState.Held(
                    s, release, if (release.kind == ReleaseKind.QUARTERLY) HoldReason.NEW_RELEASE_TRAIN else HoldReason.UNRECOGNIZED)
                i.download == DownloadWork.WAITING -> UpdateUiState.Waiting(s, release, i.disk.partBytes, total, i.waitReason)
                // A failure of this run's check or download is said plainly; a busy engine is not a failure.
                problem != null && problem != Problem.BUSY -> UpdateUiState.Failed(s, problem, release, e.detail)
                i.disk.partBytes > 0 -> UpdateUiState.Paused(s, release, i.disk.partBytes, total)
                else -> UpdateUiState.Available(s, release, i.autoDownload)
            }
        }
        return when {
            problem != null && problem != Problem.BUSY -> UpdateUiState.Failed(s, problem, null, e.detail)
            i.release.values.isNotEmpty() -> UpdateUiState.UpToDate(s, i.lastCheckedMillis)
            else -> UpdateUiState.NeverChecked(s)
        }
    }

    fun problem(code: Int?): Problem? = when (code) {
        null -> null
        3 -> Problem.NETWORK
        4 -> Problem.CHECKSUM
        5 -> Problem.STORAGE
        6 -> Problem.BUSY
        7 -> Problem.NOT_LISTED
        9 -> Problem.LISTING_REFUSED
        else -> Problem.INTERNAL
    }

    /** A verified download. Until the laptop can adapt releases itself (phase 3), the checklist says so. */
    private fun prepared(s: SystemInfo, release: Release, caps: Capabilities): UpdateUiState {
        val next = if (caps.adaptOnLaptop) Step.Status.PENDING else Step.Status.NOT_YET_AVAILABLE
        return UpdateUiState.Preparing(
            s, release,
            listOf(
                Step(Step.Id.DOWNLOADED, Step.Status.DONE),
                Step(Step.Id.VERIFIED, Step.Status.DONE),
                Step(Step.Id.CHECKED_ADAPTATIONS, next),
                Step(Step.Id.BUILT_FOR_LAPTOP, next),
                Step(Step.Id.READY, next),
            ),
        )
    }
}
