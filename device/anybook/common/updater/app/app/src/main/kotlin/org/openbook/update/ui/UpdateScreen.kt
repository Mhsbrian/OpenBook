// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.ui

import androidx.annotation.DrawableRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import org.openbook.update.R
import org.openbook.update.data.Capabilities
import org.openbook.update.data.HoldReason
import org.openbook.update.data.Problem
import org.openbook.update.data.UpdateUiState
import org.openbook.update.data.WaitReason
import org.openbook.update.engine.Release
import org.openbook.update.system.InstallerStatus

/** What the main screen's buttons do. */
data class UpdateActions(
    val check: () -> Unit = {},
    val download: () -> Unit = {},
    val pause: () -> Unit = {},
    val review: () -> Unit = {},
    val restart: () -> Unit = {},
    val settings: () -> Unit = {},
    val history: () -> Unit = {},
    val enableNotifications: () -> Unit = {},
)

private data class Hero(@DrawableRes val icon: Int?, val title: String, val body: String?, val tone: Tone, val busy: Boolean = false)
private enum class Tone { PRIMARY, SECONDARY, TERTIARY, ERROR }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UpdateScreen(state: UpdateUiState, actions: UpdateActions, notificationsOn: Boolean = true) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.app_name)) },
                actions = {
                    IconButton(onClick = actions.history) {
                        Icon(painterResource(R.drawable.ic_history), contentDescription = stringResource(R.string.action_history))
                    }
                    IconButton(onClick = actions.settings) {
                        Icon(Icons.Filled.Settings, contentDescription = stringResource(R.string.action_settings))
                    }
                },
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()), contentAlignment = Alignment.TopCenter) {
            Column(Modifier.widthIn(max = 640.dp).fillMaxWidth().padding(horizontal = 24.dp),
                   verticalArrangement = Arrangement.spacedBy(16.dp)) {
                val hero = hero(state)
                val scheme = MaterialTheme.colorScheme
                val (container, onContainer) = when (hero.tone) {
                    Tone.PRIMARY -> scheme.primaryContainer to scheme.onPrimaryContainer
                    Tone.SECONDARY -> scheme.secondaryContainer to scheme.onSecondaryContainer
                    Tone.TERTIARY -> scheme.tertiaryContainer to scheme.onTertiaryContainer
                    Tone.ERROR -> scheme.errorContainer to scheme.onErrorContainer
                }
                StatusHero(hero.icon, container, onContainer, hero.title, hero.body, hero.busy)
                Progress(state)
                Actions(state, actions)
                if (!notificationsOn) NotificationsOff(actions.enableNotifications)
                if (state is UpdateUiState.Preparing) Checklist(state.steps)
                release(state)?.let { ReleaseCard(it, state) }
                SystemCard(state)
                OpenBookMark()
            }
        }
    }
}

@Composable
private fun hero(state: UpdateUiState): Hero = when (state) {
    is UpdateUiState.Loading -> Hero(R.drawable.ic_system_update, stringResource(R.string.app_name), null, Tone.PRIMARY, busy = true)
    is UpdateUiState.NeverChecked -> Hero(R.drawable.ic_system_update, stringResource(R.string.never_checked_title),
        stringResource(R.string.never_checked_body), Tone.PRIMARY)
    is UpdateUiState.Checking -> Hero(R.drawable.ic_system_update, stringResource(R.string.checking_title),
        stringResource(R.string.checking_body), Tone.PRIMARY, busy = true)
    is UpdateUiState.UpToDate -> Hero(R.drawable.ic_verified, stringResource(R.string.up_to_date_title),
        stringResource(R.string.up_to_date_body), Tone.PRIMARY)
    is UpdateUiState.Available -> Hero(R.drawable.ic_new_release, stringResource(R.string.available_title),
        stringResource(if (state.autoDownload) R.string.available_body_auto else R.string.available_body_manual), Tone.TERTIARY)
    is UpdateUiState.Downloading ->
        Hero(R.drawable.ic_download, stringResource(R.string.downloading_title), stringResource(R.string.downloading_body), Tone.PRIMARY)
    is UpdateUiState.Waiting -> when (state.reason) {
        WaitReason.UNMETERED_NETWORK -> Hero(R.drawable.ic_wifi, stringResource(R.string.waiting_wifi_title),
            stringResource(R.string.waiting_wifi_body), Tone.SECONDARY)
        WaitReason.LATER -> Hero(R.drawable.ic_schedule, stringResource(R.string.waiting_later_title),
            stringResource(R.string.waiting_later_body), Tone.SECONDARY)
    }
    is UpdateUiState.Paused -> Hero(R.drawable.ic_pause, stringResource(R.string.paused_title),
        stringResource(R.string.paused_body), Tone.SECONDARY)
    is UpdateUiState.Verifying -> Hero(R.drawable.ic_verified, stringResource(R.string.verifying_title),
        stringResource(R.string.verifying_body), Tone.PRIMARY, busy = true)
    is UpdateUiState.Preparing -> Hero(R.drawable.ic_laptop, stringResource(R.string.preparing_title),
        stringResource(R.string.preparing_body), Tone.SECONDARY)
    is UpdateUiState.Held -> when (state.reason) {
        HoldReason.NEW_RELEASE_TRAIN -> Hero(R.drawable.ic_schedule, stringResource(R.string.held_new_train_title),
            stringResource(R.string.held_new_train_body, state.release.buildId.ifEmpty { state.release.number.toString() }), Tone.SECONDARY)
        HoldReason.UNRECOGNIZED -> Hero(R.drawable.ic_schedule, stringResource(R.string.held_unrecognized_title),
            stringResource(R.string.held_unrecognized_body, state.release.buildId.ifEmpty { state.release.number.toString() }), Tone.SECONDARY)
    }
    is UpdateUiState.ReadyToInstall -> Hero(R.drawable.ic_system_update, stringResource(R.string.ready_title),
        stringResource(R.string.ready_body), Tone.TERTIARY)
    is UpdateUiState.Installing -> Hero(R.drawable.ic_system_update, stringResource(R.string.installing_title),
        stringResource(R.string.installing_body), Tone.PRIMARY, busy = true)
    is UpdateUiState.RestartRequired -> Hero(R.drawable.ic_restart, stringResource(R.string.restart_title),
        stringResource(R.string.restart_body), Tone.TERTIARY)
    is UpdateUiState.Failed -> {
        val (title, body) = when (state.problem) {
            Problem.NETWORK -> R.string.failed_network_title to stringResource(R.string.failed_network_body)
            Problem.CHECKSUM -> R.string.failed_checksum_title to stringResource(R.string.failed_checksum_body)
            Problem.LISTING_REFUSED -> R.string.failed_listing_title to stringResource(R.string.failed_listing_body, state.detail.orEmpty())
            Problem.STORAGE -> R.string.failed_storage_title to stringResource(R.string.failed_storage_body)
            Problem.NOT_LISTED -> R.string.failed_not_listed_title to stringResource(R.string.failed_not_listed_body)
            Problem.BUSY -> R.string.failed_busy_title to stringResource(R.string.failed_busy_body)
            Problem.INTERNAL -> R.string.failed_internal_title to stringResource(R.string.failed_internal_body, state.detail.orEmpty())
        }
        Hero(R.drawable.ic_error, stringResource(title), body, Tone.ERROR)
    }
}

private fun release(state: UpdateUiState): Release? = when (state) {
    is UpdateUiState.Available -> state.release
    is UpdateUiState.Downloading -> state.release
    is UpdateUiState.Waiting -> state.release
    is UpdateUiState.Paused -> state.release
    is UpdateUiState.Verifying -> state.release
    is UpdateUiState.Preparing -> state.release
    is UpdateUiState.Held -> state.release
    is UpdateUiState.ReadyToInstall -> state.release
    is UpdateUiState.Failed -> state.release
    else -> null
}

@Composable
private fun Progress(state: UpdateUiState) {
    val (fraction, text) = when (state) {
        is UpdateUiState.Downloading -> fraction(state.doneBytes, state.totalBytes) to progressText(state.doneBytes, state.totalBytes)
        is UpdateUiState.Paused -> fraction(state.doneBytes, state.totalBytes) to progressText(state.doneBytes, state.totalBytes)
        is UpdateUiState.Waiting -> if (state.doneBytes > 0)
            fraction(state.doneBytes, state.totalBytes) to progressText(state.doneBytes, state.totalBytes) else return
        is UpdateUiState.Installing -> state.percent / 100f to stringResource(when (state.stage) {
            InstallerStatus.Stage.DOWNLOADING -> R.string.installing_stage_downloading
            InstallerStatus.Stage.VERIFYING -> R.string.installing_stage_verifying
            InstallerStatus.Stage.FINALIZING -> R.string.installing_stage_finalizing
        }, state.percent)
        else -> return
    }
    Column(Modifier.fillMaxWidth()) {
        if (fraction != null) LinearProgressIndicator(progress = { fraction }, modifier = Modifier.fillMaxWidth())
        else LinearProgressIndicator(Modifier.fillMaxWidth())
        Spacer(Modifier.size(8.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
             modifier = Modifier.align(Alignment.CenterHorizontally))
    }
}

private fun fraction(done: Long, total: Long?) = if (total != null && total > 0) (done.toFloat() / total).coerceIn(0f, 1f) else null

@Composable
private fun progressText(done: Long, total: Long?): String {
    val context = LocalContext.current
    return if (total != null && total > 0) stringResource(R.string.progress_of, Format.bytes(context, done), Format.bytes(context, total))
           else stringResource(R.string.progress_unknown_total, Format.bytes(context, done))
}

@Composable
private fun Actions(state: UpdateUiState, a: UpdateActions) {
    val primary: Pair<String, () -> Unit>? = when (state) {
        is UpdateUiState.NeverChecked, is UpdateUiState.UpToDate -> stringResource(R.string.action_check) to a.check
        is UpdateUiState.Available -> stringResource(R.string.action_download) to a.download
        is UpdateUiState.Paused -> stringResource(R.string.action_resume) to a.download
        is UpdateUiState.ReadyToInstall -> if (Capabilities.CURRENT.installOnLaptop) stringResource(R.string.action_review) to a.review else null
        is UpdateUiState.RestartRequired -> stringResource(R.string.action_restart) to a.restart
        is UpdateUiState.Failed -> stringResource(R.string.action_try_again) to a.check
        is UpdateUiState.Held, is UpdateUiState.Preparing -> stringResource(R.string.action_check) to a.check
        else -> null
    }
    val secondary: Pair<String, () -> Unit>? = when (state) {
        is UpdateUiState.Downloading, is UpdateUiState.Waiting -> stringResource(R.string.action_pause) to a.pause
        else -> null
    }
    if (primary == null && secondary == null) return
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterHorizontally)) {
        secondary?.let { (label, onClick) -> OutlinedButton(onClick = onClick) { Text(label) } }
        primary?.let { (label, onClick) ->
            if (state is UpdateUiState.Held || state is UpdateUiState.Preparing) OutlinedButton(onClick = onClick) { Text(label) }
            else Button(onClick = onClick) { Text(label) }
        }
    }
}

@Composable
private fun NotificationsOff(onEnable: () -> Unit) {
    OutlinedCard(Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 20.dp, end = 12.dp, top = 12.dp, bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Notifications, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.size(16.dp))
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.notifications_off_title), style = MaterialTheme.typography.titleSmall)
                Text(stringResource(R.string.notifications_off_body), style = MaterialTheme.typography.bodyMedium,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            TextButton(onClick = onEnable) { Text(stringResource(R.string.action_turn_on)) }
        }
    }
}

@Composable
private fun ReleaseCard(release: Release, state: UpdateUiState) {
    val context = LocalContext.current
    val rows = buildList {
        add(stringResource(R.string.release_build) to
            if (release.buildId.isNotEmpty()) stringResource(R.string.build_value, release.buildId, release.number.toString())
            else release.number.toString())
        if (release.date.isNotEmpty()) add(stringResource(R.string.release_listed) to Format.date(release.date))
        val total = when (state) {
            is UpdateUiState.Downloading -> state.totalBytes
            is UpdateUiState.Waiting -> state.totalBytes
            is UpdateUiState.Paused -> state.totalBytes
            else -> null
        }
        if (total != null) add(stringResource(R.string.release_size) to Format.bytes(context, total))
    }
    DetailsCard(title = null, rows = rows) {
        // A label, not a control: the release's kind.
        Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = RoundedCornerShape(8.dp)) {
            Text(stringResource(Format.kind(release.kind)), style = MaterialTheme.typography.labelLarge,
                 color = MaterialTheme.colorScheme.onSecondaryContainer,
                 modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
        }
        Spacer(Modifier.size(8.dp))
    }
}

@Composable
private fun SystemCard(state: UpdateUiState) {
    val s = state.system
    val rows = buildList {
        add(stringResource(R.string.info_build) to stringResource(R.string.build_value, s.buildId, s.incremental))
        add(stringResource(R.string.info_security) to Format.date(s.securityPatch))
        Format.slot(s.slot)?.let { add(stringResource(R.string.info_slot) to it) }
        if (state is UpdateUiState.UpToDate) add(stringResource(R.string.info_last_checked) to
            if (state.lastCheckedMillis > 0) Format.ago(state.lastCheckedMillis) else stringResource(R.string.info_never))
    }
    DetailsCard(title = null, rows = rows) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(painterResource(R.drawable.ic_laptop), contentDescription = null, tint = MaterialTheme.colorScheme.primary,
                 modifier = Modifier.size(20.dp))
            Spacer(Modifier.size(8.dp))
            Text("Googlebook", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
        }
        Spacer(Modifier.size(8.dp))
    }
}

/** For a guest or another non-admin user: system updates are the owner's. */
@Composable
fun NotAdminScreen() {
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Column(Modifier.widthIn(max = 640.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            StatusHero(R.drawable.ic_laptop, MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.colorScheme.onSecondaryContainer,
                       stringResource(R.string.not_admin_title), stringResource(R.string.not_admin_body))
            OpenBookMark()
        }
    }
}
