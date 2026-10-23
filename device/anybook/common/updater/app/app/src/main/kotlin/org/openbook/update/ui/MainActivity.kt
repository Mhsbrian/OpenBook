// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.ui

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.edit
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.delay
import org.openbook.update.data.Capabilities
import org.openbook.update.R
import org.openbook.update.data.UpdateUiState
import org.openbook.update.notify.Notifier
import org.openbook.update.ui.theme.OpenBookUpdateTheme

class MainActivity : ComponentActivity() {
    private val model: UpdateViewModel by viewModels()
    private var confirmRestart by mutableStateOf(false)
    private var notificationsOn by mutableStateOf(true)
    // A refusal the system no longer asks about returns false at once: then the app's notification settings open.
    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        refreshNotifications()
        if (!granted && !shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)) openNotificationSettings()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handle(intent, fresh = savedInstanceState == null)
        // Asked once on the first start; afterwards the main screen offers it while notifications are off.
        if (savedInstanceState == null && !notificationPermission() && !asked()) {
            getPreferences(MODE_PRIVATE).edit { putBoolean(ASKED, true) }
            registerForActivityResult(ActivityResultContracts.RequestPermission()) { refreshNotifications() }
                .launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent { OpenBookUpdateTheme { App() } }
    }

    override fun onResume() {
        super.onResume()
        refreshNotifications()
    }

    private fun asked() = getPreferences(MODE_PRIVATE).getBoolean(ASKED, false)
    private fun notificationPermission() =
        checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    private fun refreshNotifications() {
        notificationsOn = notificationPermission() && NotificationManagerCompat.from(this).areNotificationsEnabled()
    }
    private fun openNotificationSettings() =
        startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
    private fun enableNotifications() {
        if (!notificationPermission()) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS) else openNotificationSettings()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent, fresh = true)
    }

    override fun onStart() {
        super.onStart()
        model.onOpened()
    }

    /**
     * The restart confirmation opens only through the app's own notification (a non-exported alias), only
     * for a new launch (not a recreation or Recents), and only once: the intent is consumed.
     */
    private fun handle(intent: Intent?, fresh: Boolean) {
        if (intent == null) return
        val fromHistory = intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY != 0
        if (fresh && !fromHistory && intent.component?.className == Notifier.CONFIRM_RESTART_ALIAS) confirmRestart = true
        setIntent(Intent(intent).setComponent(ComponentName(this, MainActivity::class.java)))
    }

    private fun restart() = model.restart {
        Toast.makeText(this, R.string.restart_not_allowed, Toast.LENGTH_LONG).show()
    }

    @Composable
    private fun App() {
        if (!model.runsHere) {
            NotAdminScreen()
            return
        }
        val state by model.state.collectAsStateWithLifecycle()
        val preferences by model.preferences.collectAsStateWithLifecycle()
        val history by model.history.collectAsStateWithLifecycle()
        var screen by rememberSaveable { mutableStateOf(Screen.MAIN) }
        var confirmInstall by rememberSaveable { mutableStateOf(false) }
        BackHandler(enabled = screen != Screen.MAIN) { screen = if (screen == Screen.ABOUT) Screen.SETTINGS else Screen.MAIN }

        when (screen) {
            Screen.MAIN -> UpdateScreen(state, UpdateActions(
                check = model::check, download = model::download, pause = model::pause,
                review = { screen = Screen.REVIEW }, restart = { confirmRestart = true },
                settings = { screen = Screen.SETTINGS }, history = { screen = Screen.HISTORY },
                enableNotifications = ::enableNotifications,
            ), notificationsOn)
            Screen.REVIEW -> when (val ready = state) {
                is UpdateUiState.ReadyToInstall -> if (Capabilities.CURRENT.installOnLaptop) {
                    ReviewScreen(ready.release, onBack = { screen = Screen.MAIN },
                                 onInstallAndRestart = { confirmInstall = true }, onInstallLater = { screen = Screen.MAIN })
                } else LaunchedEffect(Unit) { screen = Screen.MAIN }
                else -> LaunchedEffect(Unit) { screen = Screen.MAIN } // the release is no longer ready
            }
            Screen.SETTINGS -> SettingsScreen(preferences, onBack = { screen = Screen.MAIN },
                onAutoDownload = model::setAutoDownload, onCheckEveryDays = model::setCheckEveryDays,
                onNotifications = ::openNotificationSettings,
                onAbout = { screen = Screen.ABOUT })
            Screen.HISTORY -> HistoryScreen(history, onBack = { screen = Screen.MAIN })
            Screen.ABOUT -> AboutUpdatesScreen(onBack = { screen = Screen.SETTINGS })
        }
        // Installing from a review needs the laptop's own build (phase 4): the review is not offered before it.
        if (confirmInstall) ConfirmInstallDialog(onConfirm = { confirmInstall = false }, onDismiss = { confirmInstall = false })
        if (confirmRestart && state is UpdateUiState.RestartRequired) {
            ConfirmRestartDialog(onConfirm = { confirmRestart = false; restart() }, onDismiss = { confirmRestart = false })
        }
        // A restart request that finds no installed update (status not yet known, or withdrawn) lapses.
        LaunchedEffect(confirmRestart) {
            if (confirmRestart) {
                delay(10_000)
                if (model.state.value !is UpdateUiState.RestartRequired) confirmRestart = false
            }
        }
    }

    private enum class Screen { MAIN, REVIEW, SETTINGS, HISTORY, ABOUT }

    companion object {
        private const val ASKED = "asked_notifications"
    }
}
