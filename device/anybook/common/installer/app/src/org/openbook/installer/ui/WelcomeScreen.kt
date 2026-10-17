// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.automirrored.rounded.Help
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Contrast
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.MotionPhotosOff
import androidx.compose.material.icons.rounded.RecordVoiceOver
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.TextIncrease
import androidx.compose.material.icons.rounded.Usb
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.InstallerViewModel
import org.openbook.installer.KeyboardLayouts
import org.openbook.installer.Language
import org.openbook.installer.Languages
import org.openbook.installer.R
import org.openbook.installer.WizardStep

/** Step 1: brand panel, language (applied system-wide at once), keyboard layout, accessibility. */
@Composable
fun WelcomeScreen(vm: InstallerViewModel, live: Boolean) {
    val fit = LocalWindowFit.current
    var help by rememberSaveable { mutableStateOf(false) }
    Row(Modifier.fillMaxSize()) {
        Hero(live, Modifier.width(if (fit.compact) 300.dp else 400.dp).fillMaxHeight())
        ContentColumn(
            overline = stringResource(R.string.overline_step_named, 1, WizardStep.entries.size, stringResource(R.string.overline_welcome)),
            title = stringResource(R.string.welcome_title),
            lede = stringResource(R.string.welcome_lede),
            modifier = Modifier.weight(1f).fillMaxHeight(),
            actionsLeading = {
                TextActionButton(stringResource(R.string.action_help), { help = true }, icon = Icons.AutoMirrored.Rounded.Help)
            },
            actionsTrailing = {
                PrimaryButton(
                    stringResource(R.string.action_continue),
                    onClick = { vm.goTo(WizardStep.HARDWARE) },
                    icon = Icons.AutoMirrored.Rounded.ArrowForward,
                    big = true,
                )
            },
        ) {
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                if (maxWidth >= 620.dp) {
                    Row {
                        LanguagePicker(vm, Modifier.weight(1f))
                        Spacer(Modifier.width(22.dp))
                        SideColumn(vm, Modifier.width(262.dp))
                    }
                } else {
                    Column {
                        LanguagePicker(vm, Modifier.fillMaxWidth())
                        Spacer(Modifier.height(18.dp))
                        SideColumn(vm, Modifier.fillMaxWidth())
                    }
                }
            }
        }
    }
    if (help) {
        AlertDialog(
            onDismissRequest = { help = false },
            title = { Text(stringResource(R.string.help_title)) },
            text = { Text(stringResource(R.string.help_body), style = Ob.type.body) },
            confirmButton = {
                TextActionButton(stringResource(R.string.action_close), { help = false })
            },
        )
    }
}

@Composable
private fun Hero(live: Boolean, modifier: Modifier) {
    Box(modifier.drawBehind { drawHeroBackground() }.padding(horizontal = 42.dp, vertical = 46.dp)) {
        Column(Modifier.fillMaxHeight()) {
            Spacer(Modifier.weight(1f))
            OpenBookMark(92.dp)
            Text(
                stringResource(R.string.hero_hello),
                style = Ob.type.hero,
                color = Color.White,
                modifier = Modifier.padding(top = 26.dp, bottom = 12.dp).semantics { heading() },
            )
            Text(
                stringResource(R.string.hero_tag),
                style = Ob.type.heroTag,
                color = Color.White.copy(alpha = 0.92f),
            )
            Spacer(Modifier.weight(1.3f))
            if (live) {
                Surface(color = Color.White.copy(alpha = 0.18f), contentColor = Color.White, shape = RoundedCornerShape(14.dp)) {
                    Row(Modifier.padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.Usb, contentDescription = null, modifier = Modifier.size(17.dp))
                        Spacer(Modifier.width(6.dp))
                        Text(stringResource(R.string.hero_live_chip), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun LanguagePicker(vm: InstallerViewModel, modifier: Modifier) {
    var query by rememberSaveable { mutableStateOf("") }
    val uiLocale = LocalConfiguration.current.locales[0]
    val names = Languages.all.associateWith { stringResource(it.nativeName) }
    val filtered = Languages.all.filter { lang ->
        val q = query.trim()
        q.isEmpty() || names.getValue(lang).contains(q, ignoreCase = true) ||
            lang.displayLanguage(uiLocale).contains(q, ignoreCase = true) ||
            lang.locale.getDisplayLanguage(java.util.Locale.ENGLISH).contains(q, ignoreCase = true) ||
            lang.tag.startsWith(q, ignoreCase = true)
    }
    Column(modifier) {
        TextField(
            value = query,
            onValueChange = { query = it },
            singleLine = true,
            placeholder = { Text(stringResource(R.string.language_search)) },
            leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
            shape = RoundedCornerShape(24.dp),
            colors = TextFieldDefaults.colors(
                focusedContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                unfocusedContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                focusedIndicatorColor = Color.Transparent,
                unfocusedIndicatorColor = Color.Transparent,
            ),
            modifier = Modifier.fillMaxWidth().focusRing(RoundedCornerShape(24.dp)),
        )
        Spacer(Modifier.height(8.dp))
        if (filtered.isEmpty()) {
            Text(
                stringResource(R.string.language_none),
                style = Ob.type.body,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(16.dp),
            )
        }
        LazyColumn(Modifier.fillMaxWidth().heightIn(max = 380.dp)) {
            items(filtered, key = { it.tag }) { lang ->
                LanguageRow(
                    lang,
                    nativeName = names.getValue(lang),
                    secondary = lang.displayLanguage(uiLocale),
                    selected = lang.tag == vm.languageTag,
                    onClick = { vm.selectLanguage(lang) },
                )
            }
        }
    }
}

@Composable
private fun LanguageRow(lang: Language, nativeName: String, secondary: String, selected: Boolean, onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(16.dp)
    Row(
        Modifier
            .fillMaxWidth()
            .height(52.dp)
            .focusRing(shape, gap = 1.dp)
            .clip(shape)
            .background(if (selected) cs.primaryContainer else Color.Transparent)
            .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null)
        Spacer(Modifier.width(14.dp))
        Text(
            nativeName,
            fontSize = 15.5.sp,
            fontWeight = FontWeight.Medium,
            color = if (selected) cs.onPrimaryContainer else cs.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        if (secondary != nativeName) {
            Text(
                secondary,
                fontSize = 13.sp,
                color = if (selected) cs.onPrimaryContainer.copy(alpha = 0.8f) else cs.onSurfaceVariant,
                maxLines = 1,
                // The row's accessible name is the native name; this column repeats it in the UI language.
                modifier = Modifier.clearAndSetSemantics {},
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SideColumn(vm: InstallerViewModel, modifier: Modifier) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    var sample by rememberSaveable { mutableStateOf("") }
    val cs = MaterialTheme.colorScheme
    val layoutLabel = stringResource(KeyboardLayouts.byId(vm.keyboardId).label)
    Column(modifier) {
        SectionLabel(stringResource(R.string.keyboard_section))
        Box {
            Surface(
                onClick = { expanded = true },
                shape = RoundedCornerShape(14.dp),
                color = Color.Transparent,
                border = BorderStroke(1.5.dp, cs.outlineVariant),
                modifier = Modifier.fillMaxWidth().focusRing(RoundedCornerShape(14.dp)),
            ) {
                Column(Modifier.padding(start = 14.dp, end = 10.dp, top = 8.dp, bottom = 10.dp)) {
                    Text(
                        stringResource(R.string.keyboard_layout),
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = cs.onSurfaceVariant,
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            layoutLabel,
                            fontSize = 15.5.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.weight(1f),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Icon(Icons.Rounded.ExpandMore, contentDescription = null)
                    }
                }
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                KeyboardLayouts.all.forEach { k ->
                    val selected = k.id == vm.keyboardId
                    DropdownMenuItem(
                        text = { Text(stringResource(k.label)) },
                        onClick = {
                            vm.selectKeyboard(k.id)
                            expanded = false
                        },
                        leadingIcon = {
                            if (selected) Icon(Icons.Rounded.Check, contentDescription = null) else Spacer(Modifier.size(24.dp))
                        },
                    )
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        OutlinedTextField(
            value = sample,
            onValueChange = { sample = it.take(200) },
            singleLine = true,
            label = { Text(stringResource(R.string.keyboard_try)) },
            placeholder = { Text(stringResource(R.string.keyboard_try_hint)) },
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(22.dp))
        SectionLabel(stringResource(R.string.a11y_section))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            A11yChip(stringResource(R.string.a11y_larger_text), Icons.Rounded.TextIncrease, vm.a11y.largerText) {
                vm.setLargerText(it)
            }
            A11yChip(stringResource(R.string.a11y_high_contrast), Icons.Rounded.Contrast, vm.a11y.highContrast) {
                vm.setHighContrast(it)
            }
            A11yChip(stringResource(R.string.a11y_reduce_motion), Icons.Rounded.MotionPhotosOff, vm.a11y.reduceMotion) {
                vm.setReduceMotion(it)
            }
            A11yChip(stringResource(R.string.a11y_screen_reader), Icons.Rounded.RecordVoiceOver, false, enabled = false) {}
        }
        Text(
            stringResource(R.string.a11y_screen_reader_missing),
            style = Ob.type.caption,
            color = cs.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp, start = 4.dp),
        )
    }
}

@Composable
private fun A11yChip(
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    on: Boolean,
    enabled: Boolean = true,
    onChange: (Boolean) -> Unit,
) {
    FilterChip(
        selected = on,
        onClick = { onChange(!on) },
        enabled = enabled,
        label = { Text(label, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold) },
        leadingIcon = { Icon(icon, contentDescription = null, modifier = Modifier.size(19.dp)) },
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.heightIn(min = 36.dp).focusRing(RoundedCornerShape(12.dp)),
    )
}
