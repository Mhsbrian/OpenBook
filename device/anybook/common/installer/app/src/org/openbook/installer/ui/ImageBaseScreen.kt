// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import org.openbook.installer.ImageBase
import org.openbook.installer.InstallBlocker
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.R
import org.openbook.installer.WizardStep

/** A base is a whole OS source, separate from the AOSP Google-apps add-on. Research is inspectable, never installable. */
@Composable
fun ImageBaseScreen(vm: InstallerViewModel, rail: RailModel) {
    WizardScaffold(
        step = WizardStep.CHOOSE,
        rail = rail,
        overline = stringResource(R.string.overline_step, 3, WizardStep.entries.size),
        title = stringResource(R.string.base_title),
        lede = stringResource(R.string.base_lede),
        actionsTrailing = {
            TonalButton(stringResource(R.string.action_back), vm::back, icon = Icons.AutoMirrored.Rounded.ArrowBack)
            PrimaryButton(
                stringResource(R.string.action_continue),
                onClick = { vm.goTo(WizardStep.DISK) },
                enabled = vm.imageBase == ImageBase.AOSP && vm.installBlocker == InstallBlocker.NONE,
                icon = Icons.AutoMirrored.Rounded.ArrowForward,
            )
        },
    ) {
        val aosp: @Composable (Modifier) -> Unit = { m ->
            BaseCard(
                stringResource(R.string.base_aosp), stringResource(R.string.base_aosp_body),
                stringResource(R.string.base_aosp_status), Tone.INFO, vm.imageBase == ImageBase.AOSP,
                { vm.selectImageBase(ImageBase.AOSP) }, m,
            )
        }
        val google: @Composable (Modifier) -> Unit = { m ->
            BaseCard(
                stringResource(R.string.base_googlebook), stringResource(R.string.base_googlebook_body),
                stringResource(R.string.base_googlebook_status), Tone.WARN, vm.imageBase == ImageBase.GOOGLEBOOK,
                { vm.selectImageBase(ImageBase.GOOGLEBOOK) }, m,
            )
        }
        BoxWithConstraints(Modifier.fillMaxWidth().selectableGroup()) {
            if (maxWidth >= 640.dp) {
                Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                    aosp(Modifier.weight(1f).fillMaxHeight())
                    google(Modifier.weight(1f).fillMaxHeight())
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    aosp(Modifier.fillMaxWidth())
                    google(Modifier.fillMaxWidth())
                }
            }
        }
        Spacer(Modifier.height(20.dp))
        Notice(Icons.Rounded.Info, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) {
            Text(
                stringResource(if (vm.imageBase == ImageBase.AOSP) R.string.base_aosp_note else R.string.base_googlebook_note),
                style = Ob.type.body,
            )
        }
        if (vm.installBlocker != InstallBlocker.NONE) {
            Spacer(Modifier.height(16.dp))
            BlockerNotice(vm)
        }
    }
}

@Composable
private fun BaseCard(
    title: String, body: String, status: String, tone: Tone, selected: Boolean,
    onClick: () -> Unit, modifier: Modifier,
) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(28.dp)
    Column(
        modifier.focusRing(shape).clip(shape)
            .background(if (selected) lerp(cs.surfaceContainerLow, cs.primaryContainer, 0.35f) else cs.surfaceContainerLow)
            .border(if (selected) 2.dp else 1.dp, if (selected) cs.primary else cs.outlineVariant, shape)
            .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            StatusPill(status, tone)
            Spacer(Modifier.weight(1f))
            RadioButton(selected = selected, onClick = null)
        }
        Text(title, style = MaterialTheme.typography.headlineSmall)
        Text(body, style = Ob.type.body, color = cs.onSurfaceVariant)
    }
}
