// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.ui

import androidx.compose.foundation.Image
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.unit.dp
import org.openbook.graphics.R
import org.openbook.graphics.data.AppChoice
import org.openbook.graphics.data.AppDriver
import org.openbook.graphics.data.AppInfo
import org.openbook.graphics.data.AppsState
import org.openbook.graphics.data.Gpu
import org.openbook.graphics.data.Reason

@OptIn(ExperimentalMaterial3Api::class, ExperimentalComposeUiApi::class)
@Composable
fun AppsScreen(
    ui: AppsUi,
    onBack: () -> Unit,
    onAppsOn: (Boolean) -> Unit,
    onGamesOn: (Boolean) -> Unit,
    onChoose: (String, AppChoice) -> Unit,
    onUseGamesRule: () -> Unit,
    onDismissMessage: () -> Unit,
) {
    Scaffold(Modifier.semantics { testTagsAsResourceId = true },
             topBar = {
                 TopAppBar(title = { Text(stringResource(R.string.apps_title)) },
                           navigationIcon = {
                               IconButton(onClick = onBack) {
                                   Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.action_back))
                               }
                           })
             }) { pad ->
        Box(Modifier.padding(pad).fillMaxSize(), contentAlignment = Alignment.TopCenter) {
            val s = ui.state
            if (ui.loading || s == null) {
                CircularProgressIndicator(Modifier.padding(32.dp))
                return@Box
            }
            LazyColumn(Modifier.widthIn(max = 720.dp).fillMaxWidth().padding(horizontal = 24.dp),
                       verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (!s.appDriver) {
                    // No NVIDIA app driver in this image (OpenBook's AOSP image): every choice would do nothing.
                    item { Spacer(Modifier.padding(2.dp)) }
                    item { Plain(R.string.apps_no_driver, Modifier.testTag("apps-no-driver")) }
                    return@LazyColumn
                }
                item { Header(ui, s, onAppsOn, onGamesOn, onUseGamesRule) }
                ui.message?.let { m -> item { AppsMessage(m, onDismissMessage) } }
                if (s.apps.isEmpty()) item { Text(stringResource(R.string.apps_none), style = MaterialTheme.typography.bodyMedium) }
                items(s.apps, key = { it.pkg }) { app ->
                    AppRow(app, s, ui.icons[app.pkg], enabled = ui.owner && !ui.busy, onChoose)
                }
                item { Spacer(Modifier.padding(8.dp)) }
            }
        }
    }
}

@Composable
private fun Header(ui: AppsUi, s: AppsState, onAppsOn: (Boolean) -> Unit, onGamesOn: (Boolean) -> Unit,
                   onUseGamesRule: () -> Unit) =
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Spacer(Modifier.padding(2.dp))
        AppsSwitch(s.appsOn, enabled = ui.owner && !ui.busy, onAppsOn, Modifier.testTag("apps-switch"))
        if (!s.offered && s.appsOn) Plain(R.string.apps_not_offered)
        when (s.settings.allApps) {
            AppDriver.ALL_APPS_PRODUCTION -> Override(R.string.apps_all_on, ui, onUseGamesRule)
            AppDriver.ALL_APPS_PRERELEASE -> Override(R.string.apps_all_prerelease, ui, onUseGamesRule)
        }
        Card(Modifier.fillMaxWidth()) {
            Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(stringResource(R.string.games_title), style = MaterialTheme.typography.titleMedium)
                    Text(stringResource(if (s.gamesOn) R.string.games_on else R.string.games_off),
                         style = MaterialTheme.typography.bodyMedium)
                }
                Switch(checked = s.gamesOn, enabled = ui.owner && !ui.busy && s.appsOn, onCheckedChange = onGamesOn,
                       modifier = Modifier.testTag("games-switch"))
            }
        }
        Text(stringResource(if (ui.owner) R.string.apps_explain else R.string.apps_not_owner),
             style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }

/**
 * "NVIDIA GPU for apps" (ANAL-327): on, the games rule and each app's choice below decide; off, every app uses the
 * Radeon and the choices are kept. The main screen shows the same switch.
 */
@Composable
fun AppsSwitch(on: Boolean, enabled: Boolean, onAppsOn: (Boolean) -> Unit, modifier: Modifier = Modifier) =
    Card(modifier.fillMaxWidth()) {
        Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(R.string.apps_switch_title), style = MaterialTheme.typography.titleMedium)
                Text(stringResource(if (on) R.string.apps_switch_on else R.string.apps_switch_off),
                     style = MaterialTheme.typography.bodyMedium)
            }
            Switch(checked = on, enabled = enabled, onCheckedChange = onAppsOn, modifier = Modifier.testTag("apps-switch-toggle"))
        }
    }

@Composable
private fun Plain(text: Int, modifier: Modifier = Modifier) = Card(modifier.fillMaxWidth()) {
    Text(stringResource(text), Modifier.padding(20.dp), style = MaterialTheme.typography.bodyMedium)
}

/** Developer options' "all apps" setting decides before the games rule: say so, and offer the rule back. */
@Composable
private fun Override(text: Int, ui: AppsUi, onUseGamesRule: () -> Unit) = Card(
    Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(MaterialTheme.colorScheme.tertiaryContainer),
) {
    Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(stringResource(text), style = MaterialTheme.typography.bodyMedium)
        if (ui.owner) OutlinedButton(onClick = onUseGamesRule, enabled = !ui.busy, modifier = Modifier.testTag("use-games-rule")) {
            Text(stringResource(R.string.action_use_games_rule))
        }
    }
}

@Composable
private fun AppsMessage(m: Message, onDismiss: () -> Unit) = Card(
    Modifier.fillMaxWidth().testTag("apps-message"),
    colors = CardDefaults.cardColors(if (m.error) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer),
) {
    Row(Modifier.padding(start = 20.dp, end = 8.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(m.text), Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_ok)) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AppRow(app: AppInfo, s: AppsState, icon: ImageBitmap?, enabled: Boolean, onChoose: (String, AppChoice) -> Unit) {
    val d = s.decision(app)
    val choice = s.settings.choice(app.pkg)
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                if (icon != null) Image(icon, null, Modifier.size(40.dp)) else Spacer(Modifier.size(40.dp))
                Column(Modifier.weight(1f)) {
                    Text(app.label, style = MaterialTheme.typography.titleMedium)
                    Text(stringResource(where(d.gpu, d.reason, app.game)), style = MaterialTheme.typography.bodySmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("gpu-${app.pkg}"))
                }
            }
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                val options = AppChoice.entries
                options.forEachIndexed { i, c ->
                    SegmentedButton(selected = choice == c, onClick = { if (choice != c) onChoose(app.pkg, c) }, enabled = enabled,
                                    shape = SegmentedButtonDefaults.itemShape(i, options.size),
                                    modifier = Modifier.testTag("choice-${app.pkg}-${c.name.lowercase()}")) {
                        Text(stringResource(when (c) {
                            AppChoice.AUTOMATIC -> R.string.choice_automatic
                            AppChoice.NVIDIA -> R.string.choice_nvidia
                            AppChoice.RADEON -> R.string.choice_radeon
                        }))
                    }
                }
            }
        }
    }
}

/** One line under the app's name: where it runs in Hybrid, and why. */
private fun where(gpu: Gpu, r: Reason, game: Boolean) = when (r) {
    Reason.GAME -> R.string.where_game
    Reason.CHOSEN_NVIDIA -> R.string.where_chosen_nvidia
    Reason.ALL_APPS, Reason.ALLOWLIST_ALL -> R.string.where_all_apps
    Reason.CHOSEN_RADEON -> if (game) R.string.where_game_chosen_radeon else R.string.where_chosen_radeon
    Reason.DENYLISTED -> R.string.where_denylisted
    Reason.NOT_ALLOWED -> if (game) R.string.where_game_rule_off else R.string.where_not_game
    Reason.ALL_APPS_OFF -> R.string.where_apps_off
    else -> if (gpu == Gpu.NVIDIA) R.string.where_all_apps else R.string.where_radeon
}
