// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.delay
import org.openbook.graphics.R
import org.openbook.graphics.data.Choice
import org.openbook.graphics.data.GfxState
import org.openbook.graphics.data.Mode
import org.openbook.graphics.data.Phase
import org.openbook.graphics.data.Rules

@OptIn(ExperimentalMaterial3Api::class, ExperimentalComposeUiApi::class)
@Composable
fun GraphicsScreen(
    ui: UiState,
    onAsk: (Mode) -> Unit,
    onSwitch: (Mode) -> Unit,
    onLock: (Boolean) -> Unit,
    onRestart: () -> Unit,
    onDismiss: () -> Unit,
    onDismissMessage: () -> Unit,
    onKeep: () -> Unit,
    onGoBack: () -> Unit,
) {
    // Test tags double as resource IDs, so the VM check (uiautomator) finds the buttons.
    Scaffold(Modifier.semantics { testTagsAsResourceId = true },
             topBar = { TopAppBar(title = { Text(stringResource(R.string.app_name)) }) }) { pad ->
        Column(
            Modifier.padding(pad).fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(Modifier.widthIn(max = 720.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                val gfx = ui.gfx
                when {
                    ui.loading -> Centered { CircularProgressIndicator() }
                    gfx == null -> Note(R.string.note_no_switcher)
                    else -> Content(ui, gfx, onAsk, onLock, onRestart)
                }
                ui.message?.let { MessageCard(it, onDismissMessage) }
                Spacer(Modifier.padding(8.dp))
            }
        }
    }
    val gfx = ui.gfx
    ui.confirm?.let { mode -> ConfirmDialog(gfx?.mode ?: Mode.UNKNOWN, mode, { onSwitch(mode) }, onDismiss) }
    if (ui.restartPrompt) RestartDialog(onRestart, onDismiss)
    if (gfx != null && Rules.asksToKeep(gfx)) KeepDialog(ui.keepDeadline, onKeep, onGoBack)
}

@Composable
private fun Centered(content: @Composable () -> Unit) =
    Row(Modifier.fillMaxWidth().padding(32.dp), horizontalArrangement = Arrangement.Center) { content() }

@Composable
private fun Content(ui: UiState, gfx: GfxState, onAsk: (Mode) -> Unit, onLock: (Boolean) -> Unit, onRestart: () -> Unit) {
    Text(stringResource(R.string.now, stringResource(modeName(gfx.mode))), style = MaterialTheme.typography.headlineSmall,
         modifier = Modifier.testTag("now"))
    if (!gfx.switchable) {
        Note(R.string.note_unsupported)
        return
    }
    PhaseNote(gfx, onRestart)
    if (!gfx.writesOn) Note(R.string.note_writes_off)
    if (!ui.owner) Note(R.string.note_not_owner)
    for (mode in Rules.MODES) ModeCard(mode, Rules.choice(gfx, mode, ui.owner), ui.busy) { onAsk(mode) }
    Card(Modifier.fillMaxWidth()) {
        Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.lock_title), style = MaterialTheme.typography.titleMedium)
                Text(stringResource(if (gfx.locked != null) R.string.lock_on else R.string.lock_off,
                                    stringResource(modeName(gfx.locked ?: gfx.mode))),
                     style = MaterialTheme.typography.bodyMedium)
            }
            Switch(checked = gfx.locked != null, enabled = Rules.canLock(gfx, ui.owner) && !ui.busy, onCheckedChange = onLock,
                   modifier = Modifier.testTag("lock"))
        }
    }
}

@Composable
private fun PhaseNote(gfx: GfxState, onRestart: () -> Unit) {
    when (gfx.phase) {
        Phase.PENDING -> Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(MaterialTheme.colorScheme.primaryContainer)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.phase_pending, stringResource(modeName(gfx.target))))
                Button(onClick = onRestart, modifier = Modifier.testTag("restart")) { Text(stringResource(R.string.action_restart)) }
            }
        }
        Phase.TRIAL -> Note(R.string.phase_trial)
        Phase.ROLLBACK -> Note(R.string.phase_rollback)
        Phase.FAILED -> Note(R.string.phase_failed)
        else -> if (gfx.rolledBack) Note(R.string.note_rolled_back)
    }
}

@Composable
private fun ModeCard(mode: Mode, choice: Choice, busy: Boolean, onAsk: () -> Unit) {
    val current = choice == Choice.CURRENT
    Card(
        Modifier.fillMaxWidth().semantics { contentDescription = "mode-${mode.wire}" },
        colors = if (current) CardDefaults.cardColors(MaterialTheme.colorScheme.secondaryContainer) else CardDefaults.cardColors(),
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(modeName(mode)), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                if (current) Text(stringResource(R.string.badge_current), style = MaterialTheme.typography.labelLarge)
            }
            Text(stringResource(modeSummary(mode)), style = MaterialTheme.typography.bodyMedium)
            Text(stringResource(modeCost(mode)), style = MaterialTheme.typography.bodySmall)
            when (choice) {
                Choice.CURRENT -> Unit
                Choice.AVAILABLE -> OutlinedButton(onClick = onAsk, enabled = !busy, modifier = Modifier.testTag("switch-${mode.wire}")) {
                    Text(stringResource(R.string.action_switch, stringResource(modeName(mode))))
                }
                else -> Text(stringResource(reason(choice)), style = MaterialTheme.typography.bodySmall,
                             color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun Note(text: Int) = Card(Modifier.fillMaxWidth()) {
    Text(stringResource(text), Modifier.padding(20.dp), style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun MessageCard(m: Message, onDismiss: () -> Unit) = Card(
    Modifier.fillMaxWidth().testTag("message"),
    colors = CardDefaults.cardColors(if (m.error) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.tertiaryContainer),
) {
    Row(Modifier.padding(start = 20.dp, end = 8.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(m.text), Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_ok)) }
    }
}

@OptIn(ExperimentalComposeUiApi::class)
@Composable
private fun ConfirmDialog(from: Mode, to: Mode, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    val restart = Rules.needsRestart(from, to)
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.semantics { testTagsAsResourceId = true },
        title = { Text(stringResource(R.string.confirm_title, stringResource(modeName(to)))) },
        text = { Text(stringResource(when (to) {
            Mode.ECO -> R.string.confirm_eco
            Mode.ULTIMATE -> R.string.confirm_ultimate
            else -> if (restart) R.string.confirm_hybrid_restart else R.string.confirm_hybrid
        })) },
        confirmButton = { Button(onClick = onConfirm, modifier = Modifier.testTag("confirm")) {
            Text(stringResource(R.string.action_switch, stringResource(modeName(to))))
        } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) } },
    )
}

@OptIn(ExperimentalComposeUiApi::class)
@Composable
private fun RestartDialog(onRestart: () -> Unit, onDismiss: () -> Unit) = AlertDialog(
    onDismissRequest = onDismiss,
    modifier = Modifier.semantics { testTagsAsResourceId = true },
    title = { Text(stringResource(R.string.restart_title)) },
    text = { Text(stringResource(R.string.restart_body)) },
    confirmButton = { Button(onClick = onRestart, modifier = Modifier.testTag("restart-now")) { Text(stringResource(R.string.action_restart)) } },
    dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.testTag("later")) {
        Text(stringResource(R.string.action_later))
    } },
)

/** After the restart into a new Ultimate: Keep, or go back; without an answer the laptop goes back by itself. */
@OptIn(ExperimentalComposeUiApi::class)
@Composable
private fun KeepDialog(deadline: Long?, onKeep: () -> Unit, onGoBack: () -> Unit) {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(deadline) {
        while (true) {
            now = System.currentTimeMillis()
            delay(250)
        }
    }
    val left = deadline?.let { ((it - now + 999) / 1000).coerceAtLeast(0) } ?: (GraphicsViewModel.KEEP_MILLIS / 1000)
    Dialog(onDismissRequest = {}, properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false,
                                                                 usePlatformDefaultWidth = false)) {
        Card(Modifier.fillMaxWidth().padding(24.dp).semantics { testTagsAsResourceId = true }) {
            Column(Modifier.padding(28.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(stringResource(R.string.keep_title), style = MaterialTheme.typography.headlineSmall)
                Text(pluralStringResource(R.plurals.keep_body, left.toInt(), left.toInt()), style = MaterialTheme.typography.bodyLarge)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick = onGoBack, modifier = Modifier.weight(1f).testTag("go-back")) {
                        Text(stringResource(R.string.action_go_back))
                    }
                    Button(onClick = onKeep, modifier = Modifier.weight(1f).testTag("keep")) { Text(stringResource(R.string.action_keep)) }
                }
            }
        }
    }
}

fun modeName(m: Mode) = when (m) {
    Mode.ECO -> R.string.mode_eco
    Mode.HYBRID -> R.string.mode_hybrid
    Mode.ULTIMATE -> R.string.mode_ultimate
    Mode.INVALID -> R.string.mode_invalid
    Mode.UNKNOWN -> R.string.mode_unknown
}

private fun modeSummary(m: Mode) = when (m) {
    Mode.ECO -> R.string.eco_summary
    Mode.ULTIMATE -> R.string.ultimate_summary
    else -> R.string.hybrid_summary
}

private fun modeCost(m: Mode) = when (m) {
    Mode.ECO -> R.string.eco_cost
    Mode.ULTIMATE -> R.string.ultimate_cost
    else -> R.string.hybrid_cost
}

private fun reason(c: Choice) = when (c) {
    Choice.NOT_OWNER -> R.string.reason_not_owner
    Choice.LOCKED -> R.string.reason_locked
    Choice.BUSY -> R.string.reason_busy
    Choice.WRITES_OFF -> R.string.reason_writes_off
    Choice.NOT_AVAILABLE -> R.string.reason_not_available
    else -> R.string.reason_unsupported
}
