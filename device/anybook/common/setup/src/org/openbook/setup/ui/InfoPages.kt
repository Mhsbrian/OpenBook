// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.setup.ui

import android.content.ClipData
import android.content.ClipboardManager
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Apps
import androidx.compose.material.icons.rounded.Extension
import androidx.compose.material.icons.rounded.GppMaybe
import androidx.compose.material.icons.rounded.Keyboard
import androidx.compose.material.icons.rounded.Language
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.Public
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Shop
import androidx.compose.material.icons.rounded.Wifi
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Fingerprint
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.TimeZone
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers
import org.openbook.installer.ui.Ob
import org.openbook.installer.ui.OpenBookMark
import org.openbook.installer.ui.PrimaryButton
import org.openbook.installer.ui.StatusPill
import org.openbook.installer.ui.TextActionButton
import org.openbook.installer.ui.TonalButton
import org.openbook.installer.ui.Tone
import org.openbook.installer.ui.drawHeroBackground
import org.openbook.setup.LockKind
import org.openbook.setup.Page
import org.openbook.setup.R
import org.openbook.setup.SetupModel
import org.openbook.setup.SetupSystem

// ------------------------------------------------------------------------------------------------ Welcome

@Composable
fun WelcomePage(model: SetupModel, onSkipAll: () -> Unit) {
    val compact = LocalCompact.current
    Row(Modifier.fillMaxSize()) {
        Box(
            Modifier.width(if (compact) 360.dp else 470.dp).fillMaxHeight().drawBehind { drawHeroBackground() }
                .padding(horizontal = 42.dp, vertical = 46.dp),
        ) {
            Column(Modifier.fillMaxHeight()) {
                Spacer(Modifier.weight(1f))
                OpenBookMark(92.dp)
                Text(stringResource(R.string.hero_hello), style = Ob.type.hero, color = Color.White,
                    modifier = Modifier.padding(top = 26.dp, bottom = 12.dp))
                Text(stringResource(R.string.hero_tag), style = Ob.type.heroTag, color = Color.White.copy(alpha = 0.92f))
                Spacer(Modifier.weight(1.3f))
            }
        }
        Column(Modifier.weight(1f).fillMaxHeight().padding(horizontal = if (compact) 32.dp else 64.dp, vertical = 44.dp)) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).widthIn(max = 820.dp)) {
                Text(stringResource(R.string.overline, model.number(Page.WELCOME), model.pages.size,
                    stringResource(R.string.rail_welcome)).uppercase(),
                    style = Ob.type.overline, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(bottom = 10.dp))
                Text(stringResource(R.string.welcome_title), style = Ob.type.headline, color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.padding(bottom = 10.dp).semantics { heading() })
                Text(stringResource(R.string.welcome_lede), style = Ob.type.lede, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(bottom = 28.dp))
                WelcomeItem(Icons.Rounded.Language, stringResource(R.string.welcome_item_region))
                WelcomeItem(Icons.Rounded.Wifi, stringResource(R.string.welcome_item_network))
                WelcomeItem(Icons.Rounded.Lock, stringResource(R.string.welcome_item_account))
                WelcomeItem(Icons.Rounded.Extension, stringResource(R.string.welcome_item_extras))
                Spacer(Modifier.height(20.dp))
                BodyText(stringResource(R.string.welcome_skip_note))
            }
            Row(Modifier.fillMaxWidth().padding(top = 18.dp), verticalAlignment = Alignment.CenterVertically) {
                TextActionButton(stringResource(R.string.action_skip_setup), onClick = onSkipAll)
                Spacer(Modifier.weight(1f))
                PrimaryButton(stringResource(R.string.action_get_started), onClick = { model.next() },
                    icon = Icons.AutoMirrored.Rounded.ArrowForward, big = true)
            }
        }
    }
}

@Composable
private fun WelcomeItem(icon: ImageVector, text: String) {
    Row(Modifier.padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(26.dp))
        Spacer(Modifier.width(16.dp))
        Text(text, style = Ob.type.lede, color = MaterialTheme.colorScheme.onSurface)
    }
}

// ------------------------------------------------------------------------------------------------ This device

@Composable
fun NoticePage(model: SetupModel) {
    val state = remember { SetupSystem.verifiedBootState() }
    PageFrame(model, stringResource(R.string.notice_title), stringResource(R.string.notice_lede)) {
        Column(Modifier.widthIn(max = 900.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            InfoCard(Icons.Rounded.GppMaybe, stringResource(R.string.notice_boot_title), iconTint = Ob.colors.warning) {
                BodyText(stringResource(R.string.notice_boot_body))
                StatusPill(stringResource(R.string.notice_boot_state, state.ifEmpty { stringResource(R.string.unknown) }),
                    if (state == "green") Tone.OK else Tone.WARN)
            }
            InfoCard(Icons.Rounded.Apps, stringResource(R.string.notice_apps_title)) {
                BodyText(stringResource(R.string.notice_apps_body))
            }
            InfoCard(Icons.Rounded.Public, stringResource(R.string.notice_google_title)) {
                BodyText(stringResource(R.string.notice_google_body))
            }
        }
    }
}

// ------------------------------------------------------------------------------------------------ Extras

@Composable
fun ExtrasPage(model: SetupModel) {
    val ctx = LocalContext.current
    val gms = remember { SetupSystem.installedVersion(ctx, SetupSystem.PKG_GMS) }
    val gmsLabel = remember {
        runCatching { ctx.packageManager.getApplicationLabel(ctx.packageManager.getApplicationInfo(SetupSystem.PKG_GMS, 0)).toString() }
            .getOrNull().orEmpty()
    }
    val microG = gms != null && gmsLabel.contains("microG", ignoreCase = true)
    PageFrame(model, stringResource(R.string.extras_title), stringResource(R.string.extras_lede)) {
        Column(Modifier.widthIn(max = 900.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            InfoCard(Icons.Rounded.Extension, stringResource(R.string.microg_title)) {
                BodyText(stringResource(R.string.microg_body))
                if (microG) {
                    StatusPill(stringResource(R.string.microg_installed, gms.orEmpty()), Tone.OK)
                    SetupSystem.launchIntent(ctx, SetupSystem.PKG_GMS)?.let { intent ->
                        TonalButton(stringResource(R.string.microg_open), onClick = {
                            ctx.startActivity(intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                        })
                    }
                } else {
                    StatusPill(stringResource(R.string.microg_not_installed), Tone.OFF)
                    BodyText(stringResource(R.string.microg_how))
                }
            }
            InfoCard(Icons.Rounded.Shop, stringResource(R.string.gapps_title)) {
                BodyText(stringResource(R.string.gapps_body))
                model.gapps?.let {
                    StatusPill(stringResource(R.string.gapps_installed, it.name), Tone.INFO)
                    BodyText(stringResource(R.string.gapps_register_next))
                }
            }
            BodyText(stringResource(R.string.extras_note))
        }
    }
}

// ------------------------------------------------------------------------------------------------ Register (ANAL-211)

/** The GSF Android ID of a system installed with the user's own Google apps package, and how to register it. */
@Composable
fun RegisterPage(model: SetupModel) {
    val ctx = LocalContext.current
    val g = model.gapps
    var attempt by remember { mutableIntStateOf(0) }
    var id by remember { mutableStateOf<String?>(null) }
    var looked by remember { mutableStateOf(false) }
    LaunchedEffect(attempt) {
        id = withContext(Dispatchers.IO) { if (g?.hasGsf == true) SetupSystem.gsfId(ctx) else null }
        looked = true
    }
    PageFrame(model, stringResource(R.string.register_title), stringResource(R.string.register_lede, g?.name.orEmpty())) {
        Column(Modifier.widthIn(max = 900.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            if (g?.hasGsf != true) {
                BodyText(stringResource(R.string.register_no_gsf))
                return@Column
            }
            InfoCard(Icons.Rounded.Fingerprint, stringResource(R.string.register_id_label)) {
                val value = id
                if (value != null) {
                    SelectionContainer {
                        Text(value, fontFamily = FontFamily.Monospace, fontSize = 30.sp, fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.onSurface)
                    }
                    Text(stringResource(R.string.register_id_hex, SetupSystem.hex(value)), style = Ob.type.mono.copy(fontSize = 14.sp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else if (looked) {
                    BodyText(stringResource(R.string.register_no_id))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (value != null) {
                        TextActionButton(stringResource(R.string.register_copy), icon = Icons.Rounded.ContentCopy, onClick = {
                            ctx.getSystemService(ClipboardManager::class.java)
                                ?.setPrimaryClip(ClipData.newPlainText("GSF Android ID", value))
                        })
                    }
                    TextActionButton(stringResource(R.string.register_retry), icon = Icons.Rounded.Refresh, onClick = { attempt++ })
                }
            }
            BodyText(stringResource(R.string.register_steps))
            BodyText(stringResource(R.string.register_note))
        }
    }
}

// ------------------------------------------------------------------------------------------------ Done

@Composable
fun DonePage(model: SetupModel, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val link = rememberLink()
    val layouts = remember { SetupSystem.keyboardLayouts(ctx) }
    val keyboard = when {
        model.layoutsApplied == 0 -> stringResource(R.string.summary_keyboard_none)
        else -> layouts.firstOrNull { it.descriptor == model.layout }?.label ?: stringResource(R.string.keyboard_default)
    }
    // As the time page shows it ("London · United Kingdom Time"), not the standard-time name in summer.
    val zone = SetupSystem.zone(TimeZone.getDefault().id, java.util.Locale.getDefault())
    val rows = listOf(
        Triple(Icons.Rounded.Language, R.string.summary_language, localeName(java.util.Locale.getDefault())),
        Triple(Icons.Rounded.Keyboard, R.string.summary_keyboard, keyboard),
        Triple(Icons.Rounded.Wifi, R.string.summary_network, linkName(link)),
        Triple(Icons.Rounded.Schedule, R.string.summary_time, "${zone.city} · ${zone.name} (${zone.offsetLabel})"),
        Triple(Icons.Rounded.Person, R.string.summary_name, SetupSystem.userName(ctx)),
        Triple(Icons.Rounded.Lock, R.string.summary_lock, if (model.lockSet == LockKind.NONE) stringResource(R.string.lock_none) else lockName(model.lockSet)),
    )
    PageFrame(model, stringResource(R.string.done_title), stringResource(R.string.done_lede), primary = {
        PrimaryButton(stringResource(R.string.action_finish), onClick = onDone, icon = Icons.AutoMirrored.Rounded.ArrowForward, big = true)
    }) {
        Column(Modifier.widthIn(max = 760.dp)) {
            rows.forEach { (icon, label, value) ->
                Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(24.dp))
                    Spacer(Modifier.width(16.dp))
                    Text(stringResource(label), style = Ob.type.body, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.width(220.dp))
                    Text(value, style = Ob.type.title.copy(fontSize = 16.sp), color = MaterialTheme.colorScheme.onSurface)
                }
            }
        }
    }
}
