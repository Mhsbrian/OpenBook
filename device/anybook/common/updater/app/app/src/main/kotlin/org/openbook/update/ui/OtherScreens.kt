// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import org.openbook.update.BuildConfig
import org.openbook.update.R
import org.openbook.update.data.HistoryEntry
import org.openbook.update.data.Preferences
import org.openbook.update.engine.Release
import org.openbook.update.engine.ReleaseKind

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SubScreen(title: String, onBack: () -> Unit, content: @Composable (PaddingValues) -> Unit) {
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(title) },
            navigationIcon = {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.action_back))
                }
            },
        )
    }, content = content)
}

@Composable
private fun Centered(padding: PaddingValues, content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()), contentAlignment = Alignment.TopCenter) {
        Column(Modifier.widthIn(max = 640.dp).fillMaxWidth().padding(horizontal = 24.dp, vertical = 8.dp),
               verticalArrangement = Arrangement.spacedBy(16.dp)) { content() }
    }
}

/** Review before installing: what changes, what OpenBook re-applies, what stays and what keeps it safe. */
@Composable
fun ReviewScreen(release: Release, onBack: () -> Unit, onInstallAndRestart: () -> Unit, onInstallLater: () -> Unit) {
    SubScreen(stringResource(R.string.review_title), onBack) { padding ->
        Centered(padding) {
            Section(stringResource(R.string.review_new), listOf(
                stringResource(Format.kind(release.kind)),
                stringResource(R.string.build_value, release.buildId, release.number.toString()),
            ))
            Section(stringResource(R.string.review_reapplied), stringResource(R.string.review_reapplied_items).split('\n'))
            Section(stringResource(R.string.review_data), listOf(stringResource(R.string.review_data_body)))
            Section(stringResource(R.string.review_safety), listOf(stringResource(R.string.review_safety_body)))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.End)) {
                TextButton(onClick = onBack) { Text(stringResource(R.string.action_not_now)) }
                OutlinedButton(onClick = onInstallLater) { Text(stringResource(R.string.action_install_later)) }
                Button(onClick = onInstallAndRestart) { Text(stringResource(R.string.action_install_restart)) }
            }
            OpenBookMark()
        }
    }
}

@Composable
private fun Section(title: String, lines: List<String>) {
    OutlinedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
            lines.forEach { Text(it, style = MaterialTheme.typography.bodyLarge) }
        }
    }
}

/** "Install update and restart?" — nothing installs without this confirmation. */
@Composable
fun ConfirmInstallDialog(onConfirm: () -> Unit, onDismiss: () -> Unit) = AlertDialog(
    onDismissRequest = onDismiss,
    icon = { Icon(painterResource(R.drawable.ic_system_update), contentDescription = null) },
    title = { Text(stringResource(R.string.confirm_install_title)) },
    text = { Text(stringResource(R.string.confirm_install_body)) },
    confirmButton = { Button(onClick = onConfirm) { Text(stringResource(R.string.action_install_restart)) } },
    dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) } },
)

/** "Restart now?" — the restart into an installed update, only after this confirmation. */
@Composable
fun ConfirmRestartDialog(onConfirm: () -> Unit, onDismiss: () -> Unit) = AlertDialog(
    onDismissRequest = onDismiss,
    icon = { Icon(painterResource(R.drawable.ic_restart), contentDescription = null) },
    title = { Text(stringResource(R.string.confirm_restart_title)) },
    text = { Text(stringResource(R.string.confirm_restart_body)) },
    confirmButton = { Button(onClick = onConfirm) { Text(stringResource(R.string.action_restart_confirm)) } },
    dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) } },
)

@Composable
fun SettingsScreen(
    preferences: Preferences,
    onBack: () -> Unit,
    onAutoDownload: (Boolean) -> Unit,
    onCheckEveryDays: (Int) -> Unit,
    onNotifications: () -> Unit,
    onAbout: () -> Unit,
) {
    SubScreen(stringResource(R.string.settings_title), onBack) { padding ->
        Centered(padding) {
            OutlinedCard(Modifier.fillMaxWidth()) {
                ListItem(
                    headlineContent = { Text(stringResource(R.string.settings_auto_download)) },
                    supportingContent = { Text(stringResource(R.string.settings_auto_download_summary)) },
                    trailingContent = { Switch(checked = preferences.autoDownload, onCheckedChange = null) },
                    modifier = Modifier.toggleable(preferences.autoDownload, role = Role.Switch, onValueChange = onAutoDownload),
                )
                HorizontalDivider()
                ListItem(headlineContent = { Text(stringResource(R.string.settings_check)) })
                listOf(1 to R.string.settings_daily, 7 to R.string.settings_weekly).forEach { (days, label) ->
                    ListItem(
                        headlineContent = { Text(stringResource(label)) },
                        leadingContent = { RadioButton(selected = preferences.checkEveryDays == days, onClick = null) },
                        modifier = Modifier.selectable(preferences.checkEveryDays == days, role = Role.RadioButton) { onCheckEveryDays(days) },
                    )
                }
                HorizontalDivider()
                ListItem(
                    headlineContent = { Text(stringResource(R.string.settings_always_ask)) },
                    supportingContent = { Text(stringResource(R.string.settings_always_ask_summary)) },
                    trailingContent = { Switch(checked = true, onCheckedChange = null, enabled = false) },
                )
            }
            OutlinedCard(Modifier.fillMaxWidth()) {
                ListItem(
                    headlineContent = { Text(stringResource(R.string.settings_notifications)) },
                    supportingContent = { Text(stringResource(R.string.settings_notifications_summary)) },
                    modifier = Modifier.clickable(onClick = onNotifications),
                )
                HorizontalDivider()
                ListItem(
                    headlineContent = { Text(stringResource(R.string.settings_about)) },
                    supportingContent = { Text(stringResource(R.string.settings_about_summary)) },
                    modifier = Modifier.clickable(onClick = onAbout),
                )
                HorizontalDivider()
                ListItem(
                    headlineContent = { Text(stringResource(R.string.settings_version)) },
                    supportingContent = { Text(stringResource(R.string.settings_version_value, BuildConfig.VERSION_NAME,
                                                             BuildConfig.ENGINE_SHA256.take(12))) },
                )
            }
            OpenBookMark()
        }
    }
}

@Composable
fun HistoryScreen(entries: List<HistoryEntry>, onBack: () -> Unit) {
    SubScreen(stringResource(R.string.history_title), onBack) { padding ->
        if (entries.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(painterResource(R.drawable.ic_history), contentDescription = null,
                         tint = MaterialTheme.colorScheme.outline, modifier = Modifier.size(48.dp))
                    Spacer(Modifier.size(12.dp))
                    Text(stringResource(R.string.history_empty), style = MaterialTheme.typography.bodyLarge,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            return@SubScreen
        }
        Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.TopCenter) {
            LazyColumn(Modifier.widthIn(max = 640.dp).fillMaxWidth()) {
                items(entries) { e ->
                    val (icon, text) = when (e.type) {
                        HistoryEntry.Type.FOUND -> R.drawable.ic_new_release to stringResource(R.string.history_found, e.build)
                        HistoryEntry.Type.HELD -> R.drawable.ic_schedule to stringResource(R.string.history_held, e.build)
                        HistoryEntry.Type.DOWNLOADED -> R.drawable.ic_download to stringResource(R.string.history_downloaded, e.build)
                        HistoryEntry.Type.VERIFICATION_FAILED -> R.drawable.ic_error to stringResource(R.string.history_verification_failed, e.build)
                        HistoryEntry.Type.INSTALLED -> R.drawable.ic_verified to stringResource(R.string.history_installed, e.build)
                        HistoryEntry.Type.WENT_BACK -> R.drawable.ic_restart to stringResource(R.string.history_went_back, e.build)
                        HistoryEntry.Type.SYSTEM_CHANGED -> R.drawable.ic_system_update to stringResource(R.string.history_changed, e.build)
                        HistoryEntry.Type.RESTART_REQUESTED -> R.drawable.ic_restart to stringResource(R.string.history_restart_requested)
                    }
                    ListItem(
                        leadingContent = { Icon(painterResource(icon), contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
                        headlineContent = { Text(text) },
                        supportingContent = { Text(Format.ago(e.timeMillis)) },
                    )
                }
            }
        }
    }
}

/** Every kind of release and how it is handled. */
@Composable
fun AboutUpdatesScreen(onBack: () -> Unit) {
    SubScreen(stringResource(R.string.about_title), onBack) { padding ->
        Centered(padding) {
            Text(stringResource(R.string.about_intro), style = MaterialTheme.typography.bodyLarge)
            OutlinedCard(Modifier.fillMaxWidth()) {
                listOf(
                    ReleaseKind.MONTHLY to R.string.about_monthly, ReleaseKind.QUARTERLY to R.string.about_quarterly,
                    ReleaseKind.UNKNOWN to R.string.about_unknown,
                ).forEach { (kind, text) ->
                    ListItem(headlineContent = { Text(stringResource(Format.kind(kind))) }, supportingContent = { Text(stringResource(text)) })
                }
                listOf(
                    R.string.about_beta_title to R.string.about_beta, R.string.about_play_title to R.string.about_play,
                    R.string.about_openbook_title to R.string.about_openbook, R.string.about_changed_title to R.string.about_changed,
                ).forEach { (title, text) ->
                    ListItem(headlineContent = { Text(stringResource(title)) }, supportingContent = { Text(stringResource(text)) })
                }
            }
            OpenBookMark()
        }
    }
}
