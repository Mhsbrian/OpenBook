// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.InstallBlocker
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.R
import org.openbook.installer.WizardStep

/** Step 3: Try (close the wizard; the taskbar shortcut stays) or Install (go to Disk). */
@Composable
fun ChooseScreen(vm: InstallerViewModel, rail: RailModel, onTry: () -> Unit) {
    val blocker = vm.installBlocker
    val canInstall = blocker == InstallBlocker.NONE
    LaunchedEffect(blocker) {
        if (blocker != InstallBlocker.NONE && blocker != InstallBlocker.CHECKING) vm.chooseInstall = false
    }
    WizardScaffold(
        step = WizardStep.CHOOSE,
        rail = rail,
        overline = stringResource(R.string.overline_step, 3, WizardStep.entries.size),
        title = stringResource(R.string.choose_title),
        lede = stringResource(R.string.choose_lede),
        actionsTrailing = {
            TonalButton(stringResource(R.string.action_back), vm::back, icon = Icons.AutoMirrored.Rounded.ArrowBack)
            PrimaryButton(
                stringResource(R.string.action_continue),
                onClick = {
                    if (!vm.chooseInstall) {
                        vm.markTried()
                        onTry()
                    } else if (canInstall) {
                        vm.goTo(WizardStep.DISK)
                    }
                },
                enabled = !vm.chooseInstall || canInstall,
                icon = Icons.AutoMirrored.Rounded.ArrowForward,
            )
        },
    ) {
        val tryCard: @Composable (Modifier) -> Unit = { m ->
            ChoiceCard(
                install = false,
                title = stringResource(R.string.choose_try_title),
                body = stringResource(R.string.choose_try_body),
                bullets = listOf(
                    stringResource(R.string.choose_try_1),
                    stringResource(R.string.choose_try_2),
                    stringResource(R.string.choose_try_3),
                ),
                selected = !vm.chooseInstall,
                enabled = true,
                onClick = { vm.chooseInstall = false },
                modifier = m,
            )
        }
        val installCard: @Composable (Modifier) -> Unit = { m ->
            ChoiceCard(
                install = true,
                title = stringResource(R.string.choose_install_title),
                body = stringResource(R.string.choose_install_body),
                bullets = listOf(
                    stringResource(R.string.choose_install_1),
                    stringResource(R.string.choose_install_2),
                    stringResource(R.string.choose_install_3),
                ),
                selected = vm.chooseInstall,
                enabled = blocker == InstallBlocker.NONE || blocker == InstallBlocker.CHECKING,
                onClick = { vm.chooseInstall = true },
                modifier = m,
            )
        }
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            if (maxWidth >= 640.dp) {
                Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                    tryCard(Modifier.weight(1f))
                    installCard(Modifier.weight(1f))
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    tryCard(Modifier.fillMaxWidth())
                    installCard(Modifier.fillMaxWidth())
                }
            }
        }
        if (!canInstall) {
            Spacer(Modifier.height(16.dp))
            BlockerNotice(vm)
        }
    }
}

@Composable
private fun ChoiceCard(
    install: Boolean,
    title: String,
    body: String,
    bullets: List<String>,
    selected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier,
) {
    val cs = MaterialTheme.colorScheme
    val ext = Ob.colors
    val fit = LocalWindowFit.current
    val shape = RoundedCornerShape(28.dp)
    val bg = if (selected) lerp(cs.surfaceContainerLow, cs.primaryContainer, 0.35f) else cs.surfaceContainerLow
    Column(
        modifier
            .focusRing(shape)
            .alpha(if (enabled) 1f else 0.55f)
            .clip(shape)
            .background(bg)
            .then(if (selected) Modifier.border(2.5.dp, cs.primary, shape) else Modifier)
            .selectable(selected = selected, enabled = enabled, role = Role.RadioButton, onClick = onClick)
            // One node for automation and screen readers, named by the card's title ("Install OpenBook").
            .semantics { contentDescription = title },
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(if (fit.compact) 170.dp else 210.dp)
                .drawBehind {
                    drawRect(if (ext.dark) cs.surfaceContainerHigh else cs.surfaceContainer)
                    if (ext.dark) {
                        drawRect(
                            Brush.radialGradient(
                                listOf(Color(0x595A6EE6), Color.Transparent),
                                center = Offset(size.width * 0.3f, size.height * 0.3f),
                                radius = 240.dp.toPx(),
                            ),
                        )
                    } else {
                        val (a, b) = if (install) Color(0xFFDCD3FF) to Color(0xFFFFDCE8) else Color(0xFFCFE0FF) to Color(0xFFD9F3EC)
                        drawRect(
                            Brush.radialGradient(
                                listOf(a, a.copy(alpha = 0f)),
                                center = Offset(size.width * 0.28f, size.height * 0.28f),
                                radius = 220.dp.toPx(),
                            ),
                        )
                        drawRect(
                            Brush.radialGradient(
                                listOf(b, b.copy(alpha = 0f)),
                                center = Offset(size.width * 0.82f, size.height * 0.82f),
                                radius = 220.dp.toPx(),
                            ),
                        )
                    }
                }
                .clearAndSetSemantics {},
            contentAlignment = Alignment.Center,
        ) {
            ChoiceArt(install, Modifier.size(width = 250.dp, height = 150.dp))
            Box(
                Modifier
                    .align(Alignment.TopEnd)
                    .padding(16.dp)
                    .size(30.dp)
                    .then(
                        if (selected) {
                            Modifier.background(cs.primary, CircleShape)
                        } else {
                            Modifier.border(2.dp, cs.outline, CircleShape)
                        },
                    ),
                contentAlignment = Alignment.Center,
            ) {
                if (selected) Icon(Icons.Rounded.Check, null, tint = cs.onPrimary, modifier = Modifier.size(20.dp))
            }
        }
        Column(Modifier.padding(start = 24.dp, end = 24.dp, top = 20.dp, bottom = 22.dp)) {
            Text(title, fontSize = 22.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.2).sp)
            Text(
                body,
                style = Ob.type.body,
                color = cs.onSurfaceVariant,
                modifier = Modifier.padding(top = 6.dp, bottom = 12.dp),
            )
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                bullets.forEach { b ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.CheckCircle, null, tint = cs.primary, modifier = Modifier.size(19.dp))
                        Spacer(Modifier.width(9.dp))
                        Text(b, fontSize = 14.sp)
                    }
                }
            }
        }
    }
}
