// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.WorkManager
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.openbook.update.ui.MainActivity
import java.io.File

/** The real app: opening it checks Google's live listing, and the screens are reachable. */
@RunWith(AndroidJUnit4::class)
class MainScreenTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun openingTheAppChecksAndShowsTheResult() {
        WorkManager.getInstance(context).cancelAllWork().result.get()
        File(context.filesDir, "updater").deleteRecursively()
        Graph.settings.lastCheckedMillis = 0
        ActivityScenario.launch(MainActivity::class.java).use {
            // An emulator is not a device Google lists releases for.
            compose.waitUntil(90_000) { compose.onAllNodes(hasText("No releases for this device")).fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithText("OpenBook Update").assertExists()
            compose.onNodeWithContentDescription("Settings").performClick()
            compose.onNodeWithText("Always ask before installing").assertExists()
            compose.onNodeWithText("About updates").performClick()
            compose.onNodeWithText("Beta releases").assertExists()
        }
    }
}
