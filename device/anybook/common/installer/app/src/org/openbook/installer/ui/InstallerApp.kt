// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ReceiptLong
import androidx.compose.material.icons.rounded.VerifiedUser
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.Languages
import org.openbook.installer.LiveSystem
import org.openbook.installer.R
import org.openbook.installer.WizardStep
import org.openbook.installer.valueOrNull

/** The wizard: one screen per [WizardStep]. Escape and Back go back, except while installing (and on Done). */
@Composable
fun InstallerApp(vm: InstallerViewModel, onClose: () -> Unit, onRestart: () -> Unit) {
    OpenBookTheme {
        Surface(
            color = MaterialTheme.colorScheme.surface,
            // The desktop window's caption bar and the IME are insets: keep the action row clear of both.
            modifier = Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing),
        ) {
            WindowFitProvider {
                BackHandler(enabled = vm.step != WizardStep.WELCOME) { vm.back() }
                val rail = railModel(vm)
                when (vm.step) {
                    WizardStep.WELCOME -> WelcomeScreen(vm, live = LiveSystem.isLiveSession() || vm.hello.valueOrNull?.live == true)
                    WizardStep.HARDWARE -> HardwareScreen(vm, rail)
                    WizardStep.CHOOSE -> ChooseScreen(vm, rail, onTry = onClose)
                    WizardStep.DISK -> if (vm.gappsPage) GappsScreen(vm, rail) else DiskScreen(vm, rail)
                    WizardStep.CONFIRM -> ConfirmScreen(vm, rail)
                    WizardStep.INSTALL -> InstallScreen(vm, rail)
                    WizardStep.DONE -> DoneScreen(vm, rail, onKeepTrying = onClose, onRestart = onRestart)
                }
                val plan = vm.plan
                if (vm.planDialog && plan != null) PlanDialog(plan) { vm.planDialog = false }
            }
        }
    }
}

@Composable
private fun railModel(vm: InstallerViewModel): RailModel {
    val step = vm.step
    val hints = HashMap<WizardStep, String>()
    // Done steps keep their answers in the rail until the install starts (as in the design).
    val showAnswers = step.ordinal <= WizardStep.CONFIRM.ordinal
    if (showAnswers) {
        Languages.byTag(vm.languageTag)?.let { lang ->
            hints[WizardStep.WELCOME] = stringResource(lang.nativeName)
        }
        vm.hw.valueOrNull?.let { hw ->
            hints[WizardStep.HARDWARE] = stringResource(
                when (hw.verdict) {
                    "ready" -> R.string.verdict_ready
                    "limited" -> R.string.verdict_limited
                    else -> R.string.verdict_unsupported
                },
            )
        }
        hints[WizardStep.CHOOSE] = stringResource(R.string.rail_hint_install)
        vm.selectedDiskInfo?.let { hints[WizardStep.DISK] = it.model }
    }
    when (step) {
        WizardStep.HARDWARE -> hints[step] = stringResource(R.string.rail_hint_hardware)
        WizardStep.CHOOSE -> hints[step] = stringResource(R.string.rail_hint_choose)
        WizardStep.DISK -> hints[step] = stringResource(if (vm.gappsPage) R.string.rail_hint_gapps else R.string.rail_hint_disk)
        WizardStep.CONFIRM -> hints[step] = stringResource(R.string.rail_hint_confirm)
        WizardStep.INSTALL -> vm.install.current?.let { hints[step] = stepLabel(it, done = false) }
        WizardStep.DONE -> hints[step] = stringResource(R.string.rail_hint_done)
        else -> {}
    }
    return when (step) {
        WizardStep.CONFIRM -> RailModel(hints, Icons.Rounded.VerifiedUser, stringResource(R.string.rail_note_confirm))
        WizardStep.INSTALL -> RailModel(
            hints,
            Icons.AutoMirrored.Rounded.ReceiptLong,
            stringResource(if (vm.hello.valueOrNull?.logsOnStick == false) R.string.rail_note_install_memory else R.string.rail_note_install),
        )
        WizardStep.DONE -> RailModel(hints, Icons.AutoMirrored.Rounded.ReceiptLong, stringResource(R.string.rail_note_done))
        else -> RailModel(hints, Icons.Rounded.VerifiedUser, stringResource(R.string.rail_note_default))
    }
}
