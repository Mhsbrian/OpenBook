// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import android.graphics.Bitmap
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.isDialog
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.openbook.update.data.HistoryEntry
import org.openbook.update.data.HoldReason
import org.openbook.update.data.Preferences
import org.openbook.update.data.Problem
import org.openbook.update.data.Step
import org.openbook.update.data.SystemInfo
import org.openbook.update.data.UpdateUiState
import org.openbook.update.data.WaitReason
import org.openbook.update.engine.Release
import org.openbook.update.engine.ReleaseKind
import org.openbook.update.system.InstallerStatus
import org.openbook.update.ui.AboutUpdatesScreen
import org.openbook.update.ui.ConfirmInstallDialog
import org.openbook.update.ui.ConfirmRestartDialog
import org.openbook.update.ui.HistoryScreen
import org.openbook.update.ui.NotAdminScreen
import org.openbook.update.ui.ReviewScreen
import org.openbook.update.ui.SettingsScreen
import org.openbook.update.ui.UpdateActions
import org.openbook.update.ui.UpdateScreen
import org.openbook.update.ui.theme.OpenBookUpdateTheme
import java.io.File

/**
 * Every screen state, light and dark, rendered on the device and saved as PNG in the app's files
 * (screenshots/; emulator-test.sh copies them out with run-as). The system is the G14's (RB-20261023-02); the newer release is synthetic.
 */
@RunWith(AndroidJUnit4::class)
class ScreenshotTest {
    @get:Rule val compose = createComposeRule()
    private val out = File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "screenshots")
        .apply { deleteRecursively(); mkdirs() }

    private val system = SystemInfo("CL3B.260622.276.R4", "16658739", "2026-10-01", "google/ruby/ruby", "_b")
    private val monthly = Release(16999999, "CL3B.260622.301", "2026-11-20", ReleaseKind.MONTHLY)
    private val quarterly = Release(17400000, "CL4A.260915.088", "2026-12-15", ReleaseKind.QUARTERLY)
    private val now = System.currentTimeMillis()

    private val states: List<Pair<String, @Composable () -> Unit>> = listOf(
        "00-loading" to { Main(UpdateUiState.Loading(system)) },
        "01-never-checked" to { Main(UpdateUiState.NeverChecked(system)) },
        "02-checking" to { Main(UpdateUiState.Checking(system)) },
        "03-up-to-date" to { Main(UpdateUiState.UpToDate(system, now - 3 * 60_000)) },
        "03b-up-to-date-notifications-off" to { Main(UpdateUiState.UpToDate(system, now - 3 * 60_000), notificationsOn = false) },
        "04-update-available" to { Main(UpdateUiState.Available(system, monthly, autoDownload = false)) },
        "05-downloading" to { Main(UpdateUiState.Downloading(system, monthly, 3_100_000_000, 7_820_000_000)) },
        "06-waiting-for-wifi" to { Main(UpdateUiState.Waiting(system, monthly, 3_100_000_000, 7_820_000_000, WaitReason.UNMETERED_NETWORK)) },
        "06b-waiting-later" to { Main(UpdateUiState.Waiting(system, monthly, 0, null, WaitReason.LATER)) },
        "07-paused" to { Main(UpdateUiState.Paused(system, monthly, 3_100_000_000, 7_820_000_000)) },
        "08-verifying" to { Main(UpdateUiState.Verifying(system, monthly)) },
        "09-preparing-checklist" to { Main(UpdateUiState.Preparing(system, monthly, listOf(
            Step(Step.Id.DOWNLOADED, Step.Status.DONE), Step(Step.Id.VERIFIED, Step.Status.DONE),
            Step(Step.Id.CHECKED_ADAPTATIONS, Step.Status.NOT_YET_AVAILABLE),
            Step(Step.Id.BUILT_FOR_LAPTOP, Step.Status.NOT_YET_AVAILABLE), Step(Step.Id.READY, Step.Status.NOT_YET_AVAILABLE)))) },
        "10-preparing-phase3-design" to { Main(UpdateUiState.Preparing(system, monthly, listOf(
            Step(Step.Id.DOWNLOADED, Step.Status.DONE), Step(Step.Id.VERIFIED, Step.Status.DONE),
            Step(Step.Id.CHECKED_ADAPTATIONS, Step.Status.DONE), Step(Step.Id.BUILT_FOR_LAPTOP, Step.Status.ACTIVE),
            Step(Step.Id.READY, Step.Status.PENDING)))) },
        "10b-preparing-checking" to { Main(UpdateUiState.Preparing(system, monthly, listOf(
            Step(Step.Id.DOWNLOADED, Step.Status.DONE), Step(Step.Id.VERIFIED, Step.Status.DONE),
            Step(Step.Id.CHECKED_ADAPTATIONS, Step.Status.ACTIVE), Step(Step.Id.BUILT_FOR_LAPTOP, Step.Status.PENDING),
            Step(Step.Id.READY, Step.Status.PENDING)))) },
        "10c-built-awaiting-key" to { Main(UpdateUiState.Preparing(system, monthly, listOf(
            Step(Step.Id.DOWNLOADED, Step.Status.DONE), Step(Step.Id.VERIFIED, Step.Status.DONE),
            Step(Step.Id.CHECKED_ADAPTATIONS, Step.Status.DONE), Step(Step.Id.BUILT_FOR_LAPTOP, Step.Status.DONE),
            Step(Step.Id.READY, Step.Status.NOT_YET_AVAILABLE)), awaitingKey = true)) },
        "11-held-quarterly" to { Main(UpdateUiState.Held(system, quarterly, HoldReason.NEW_RELEASE_TRAIN)) },
        "11b-held-adaptation" to { Main(UpdateUiState.Held(system, monthly, HoldReason.ADAPTATION,
            "/system/build.prop: OpenBook changes it, but Google changed it too")) },
        "12-ready-to-install-design" to { Main(UpdateUiState.ReadyToInstall(system, monthly)) },
        "13-review-design" to { OpenBookUpdateTheme(dark) { ReviewScreen(monthly, {}, {}, {}) } },
        "14-installing" to { Main(UpdateUiState.Installing(system, InstallerStatus.Stage.DOWNLOADING, 42)) },
        "15-restart-required" to { Main(UpdateUiState.RestartRequired(system)) },
        "16-failed-network" to { Main(UpdateUiState.Failed(system, Problem.NETWORK, null, null)) },
        "16b-failed-listing" to { Main(UpdateUiState.Failed(system, Problem.LISTING_REFUSED, null, "unexpected download location https://example.com/x.zip")) },
        "17-failed-storage" to { Main(UpdateUiState.Failed(system, Problem.STORAGE, monthly, null)) },
        "18-failed-adapt" to { Main(UpdateUiState.Failed(system, Problem.ADAPT, monthly, "not enough space to adapt")) },
        "18-settings" to { OpenBookUpdateTheme(dark) { SettingsScreen(Preferences(), {}, {}, {}, {}, {}) } },
        "19-history" to { OpenBookUpdateTheme(dark) { HistoryScreen(listOf(
            HistoryEntry(now - 60_000, HistoryEntry.Type.INSTALLED, "CL3B.260722.140 (16999999)"),
            HistoryEntry(now - 3_600_000, HistoryEntry.Type.RESTART_REQUESTED),
            HistoryEntry(now - 7_200_000, HistoryEntry.Type.DOWNLOADED, "CL3B.260722.140 (16999999)"),
            HistoryEntry(now - 90_000_000, HistoryEntry.Type.FOUND, "CL3B.260722.140 (16999999)")), {}) } },
        "20-about-updates" to { OpenBookUpdateTheme(dark) { AboutUpdatesScreen {} } },
        "23-not-admin" to { OpenBookUpdateTheme(dark) { NotAdminScreen() } },
    )
    private var dark by mutableStateOf(false)

    @Composable
    private fun Main(state: UpdateUiState, notificationsOn: Boolean = true) =
        OpenBookUpdateTheme(dark) { UpdateScreen(state, UpdateActions(), notificationsOn) }

    @Test fun everyStateLightAndDark() {
        var current: @Composable () -> Unit by mutableStateOf({})
        compose.setContent { current() }
        for (theme in listOf("light", "dark")) {
            dark = theme == "dark"
            for ((name, content) in states) {
                current = content
                compose.waitForIdle()
                save("$name-$theme", compose.onRoot().captureToImage().asAndroidBitmap())
            }
            current = { OpenBookUpdateTheme(dark) { Main(UpdateUiState.RestartRequired(system)); ConfirmRestartDialog({}, {}) } }
            compose.waitForIdle()
            save("21-confirm-restart-$theme", compose.onNode(isDialog()).captureToImage().asAndroidBitmap())
            current = { OpenBookUpdateTheme(dark) { ReviewScreen(monthly, {}, {}, {}); ConfirmInstallDialog({}, {}) } }
            compose.waitForIdle()
            save("22-confirm-install-design-$theme", compose.onNode(isDialog()).captureToImage().asAndroidBitmap())
        }
    }

    private fun save(name: String, bitmap: Bitmap) =
        File(out, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
}
