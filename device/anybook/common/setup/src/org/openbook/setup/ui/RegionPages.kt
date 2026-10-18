// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.setup.ui

import android.content.Intent
import android.provider.Settings
import android.text.format.DateFormat
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.EditCalendar
import androidx.compose.material.icons.rounded.Keyboard
import androidx.compose.material.icons.rounded.KeyboardAlt
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlinx.coroutines.delay
import org.openbook.installer.ui.Notice
import org.openbook.installer.ui.Ob
import org.openbook.installer.ui.SectionLabel
import org.openbook.installer.ui.TextActionButton
import org.openbook.setup.R
import org.openbook.setup.SetupModel
import org.openbook.setup.SetupSystem
import org.openbook.setup.SetupSystem.KeyboardLayoutChoice

// ------------------------------------------------------------------------------------------------ Language and region

@Composable
fun LanguagePage(model: SetupModel) {
    val ui = Locale.getDefault()
    var query by remember { mutableStateOf("") }
    val regions = remember(model.language) { SetupSystem.regionsFor(model.language, Locale.forLanguageTag(model.language)) }
    PageFrame(model, stringResource(R.string.language_title), stringResource(R.string.language_lede), scroll = false) {
        Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(36.dp)) {
            Column(Modifier.weight(1f).fillMaxHeight()) {
                SectionLabel(stringResource(R.string.language_label))
                LazyColumn(Modifier.weight(1f)) {
                    items(SetupSystem.languages) { tag ->
                        ChoiceRow(
                            label = SetupSystem.nativeName(tag),
                            selected = tag == model.language,
                            trailing = Locale.forLanguageTag(tag).getDisplayLanguage(ui).replaceFirstChar { it.titlecase(ui) },
                            onClick = {
                                if (tag != model.language) {
                                    model.language = tag
                                    query = ""
                                    model.locale = SetupSystem.regionsFor(tag, Locale.forLanguageTag(tag)).firstOrNull()
                                        ?: Locale.forLanguageTag(tag)
                                }
                            },
                        )
                    }
                }
            }
            Column(Modifier.weight(1f).fillMaxHeight()) {
                SectionLabel(stringResource(R.string.region_label))
                SearchField(query, { query = it }, stringResource(R.string.region_search), "region-search")
                Spacer(Modifier.height(8.dp))
                val shown = regions.filter { region(it).contains(query.trim(), ignoreCase = true) || it.country.equals(query.trim(), true) }
                LazyColumn(Modifier.weight(1f)) {
                    items(shown, key = { it.toLanguageTag() }) { loc ->
                        ChoiceRow(region(loc), loc == model.locale, onClick = { model.locale = loc }, trailing = loc.country)
                    }
                }
            }
        }
    }
}

/** The region's name in the region's own language, e.g. "Deutschland", "Österreich". */
private fun region(loc: Locale): String = SetupSystem.countryName(loc.country, loc)

/** "English (United Kingdom)" for the Done page. */
fun localeName(loc: Locale): String = loc.getDisplayName(loc).replaceFirstChar { it.titlecase(loc) }

// ------------------------------------------------------------------------------------------------ Keyboard

/** The installer's pick, the layout in use, then the layouts made for the chosen language and region. */
private fun suggestions(all: List<KeyboardLayoutChoice>, inUse: String?, locale: Locale): List<KeyboardLayoutChoice> {
    val byName = all.associateBy { it.name }
    val byDescriptor = all.associateBy { it.descriptor }
    val exact = all.filter { l -> l.locales.any { it.language == locale.language && it.country == locale.country } }
    val language = all.filter { l -> l.locales.any { it.language == locale.language && it.country.isEmpty() } }
    return listOfNotNull(
        SetupSystem.installerLayoutName()?.let { byName[it] },
        inUse?.let { byDescriptor[it] },
    ).plus(exact).plus(language).plus(listOfNotNull(byName["keyboard_layout_english_us"]))
        .distinctBy { it.descriptor }.take(3)
}

@Composable
fun KeyboardPage(model: SetupModel) {
    val ctx = LocalContext.current
    var refresh by remember { mutableIntStateOf(0) }
    val layouts = remember { SetupSystem.keyboardLayouts(ctx) }
    val keyboards = remember(refresh) { SetupSystem.physicalKeyboards(ctx) }
    val inUse = remember(refresh) { keyboards.firstOrNull()?.let { SetupSystem.currentLayout(ctx, it) } }
    val suggested = remember(model.locale) { suggestions(layouts, inUse, model.locale) }
    var query by remember { mutableStateOf("") }
    var trial by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { if (model.layout == null) model.layout = suggested.firstOrNull()?.descriptor }
    val pick: (String) -> Unit = {
        model.layout = it
        model.layoutsApplied = SetupSystem.applyKeyboardLayout(ctx, it)
        refresh++
    }
    PageFrame(model, stringResource(R.string.keyboard_title), stringResource(R.string.keyboard_lede), scroll = false) {
        Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(36.dp)) {
            Column(Modifier.weight(1f).fillMaxHeight()) {
                SectionLabel(stringResource(R.string.keyboard_layout_label))
                SearchField(query, { query = it }, stringResource(R.string.keyboard_search), "keyboard-search")
                Spacer(Modifier.height(8.dp))
                LazyColumn(Modifier.weight(1f)) {
                    val q = query.trim()
                    if (q.isEmpty()) {
                        item { SubLabel(stringResource(R.string.keyboard_suggested)) }
                        items(suggested, key = { "s/" + it.descriptor }) { l ->
                            ChoiceRow(l.label, l.descriptor == model.layout, onClick = { pick(l.descriptor) })
                        }
                        item { SubLabel(stringResource(R.string.keyboard_all)) }
                    }
                    items(layouts.filter { q.isEmpty() || it.label.contains(q, ignoreCase = true) }, key = { it.descriptor }) { l ->
                        ChoiceRow(l.label, l.descriptor == model.layout, onClick = { pick(l.descriptor) })
                    }
                }
            }
            Column(Modifier.weight(0.85f).fillMaxHeight()) {
                SectionLabel(stringResource(R.string.keyboard_devices_label))
                if (keyboards.isEmpty()) {
                    Notice(Icons.Rounded.KeyboardAlt) { Text(stringResource(R.string.keyboard_none), style = Ob.type.body) }
                }
                keyboards.forEach { device ->
                    val current = SetupSystem.currentLayout(ctx, device)
                    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.Keyboard, contentDescription = null, tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(26.dp))
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }) {
                            Text(device.name, style = Ob.type.title.copy(fontSize = 16.sp))
                            Text(
                                stringResource(R.string.keyboard_in_use,
                                    layouts.firstOrNull { it.descriptor == current }?.label ?: stringResource(R.string.keyboard_default)),
                                style = Ob.type.body, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
                Spacer(Modifier.height(18.dp))
                SectionLabel(stringResource(R.string.keyboard_try))
                OutlinedTextField(trial, { trial = it }, label = { Text(stringResource(R.string.keyboard_try_hint)) },
                    singleLine = true, modifier = Modifier.fillMaxWidth().testTag("keyboard-try"))
                Spacer(Modifier.height(14.dp))
                BodyText(stringResource(R.string.keyboard_keys_note))
            }
        }
    }
}

@Composable
private fun SubLabel(text: String) {
    Text(text, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(start = 12.dp, top = 10.dp, bottom = 4.dp))
}

// ------------------------------------------------------------------------------------------------ Date and time

@Composable
fun TimePage(model: SetupModel) {
    val ctx = LocalContext.current
    var settings by remember { mutableStateOf(SetupSystem.readTime(ctx)) }
    var use24 by remember { mutableStateOf(DateFormat.is24HourFormat(ctx)) }
    var world by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    val country = model.locale.country.takeIf { it.length == 2 }
    val regional = remember(country, model.locale) { country?.let { SetupSystem.zones(it, model.locale) }.orEmpty() }
    val everywhere = remember(model.locale) { lazy { SetupSystem.zones(null, model.locale) } }
    LaunchedEffect(regional) {
        // A one-zone region (Germany, Japan...) on a system still at its default zone: that zone is the answer.
        if (!model.zoneChosen && regional.size == 1 && regional.none { it.id == model.zoneId }) {
            model.zoneId = regional[0].id
            model.zoneChosen = true
        }
        if (regional.isEmpty()) world = true
    }
    // The clock shows minutes: redraw on the minute, so the window is otherwise idle.
    val now by produceState(System.currentTimeMillis()) {
        while (true) {
            value = System.currentTimeMillis()
            delay(60_000 - value % 60_000 + 50)
        }
    }
    val zone = TimeZone.getTimeZone(model.zoneId)
    fun fmt(skeleton: String) = SimpleDateFormat(DateFormat.getBestDateTimePattern(model.locale, skeleton), model.locale)
        .apply { timeZone = zone }.format(Date(now))
    PageFrame(model, stringResource(R.string.time_title), stringResource(R.string.time_lede), scroll = false) {
        Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(36.dp)) {
            Column(Modifier.weight(0.9f).fillMaxHeight()) {
                Text(fmt(if (use24) "Hm" else "hma"), fontSize = 64.sp, lineHeight = 70.sp, fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface)
                Text(fmt("EEEEMMMMdy"), style = Ob.type.lede, color = MaterialTheme.colorScheme.onSurfaceVariant)
                val chosen = (regional + if (everywhere.isInitialized()) everywhere.value else emptyList()).firstOrNull { it.id == model.zoneId }
                Text(
                    chosen?.let { "${it.city} · ${it.name} · ${it.offsetLabel}" } ?: model.zoneId,
                    style = Ob.type.body, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 6.dp, bottom = 18.dp),
                )
                if (settings.canAutoTime) {
                    SwitchRow(stringResource(R.string.time_auto), stringResource(R.string.time_auto_detail), settings.autoTime, {
                        SetupSystem.setAutoTime(ctx, it)
                        settings = SetupSystem.readTime(ctx)
                    })
                }
                if (settings.canAutoZone) {
                    SwitchRow(stringResource(R.string.time_zone_auto), null, settings.autoZone, {
                        SetupSystem.setAutoZone(ctx, it)
                        settings = SetupSystem.readTime(ctx)
                    })
                }
                SwitchRow(stringResource(R.string.time_24h), stringResource(R.string.time_24h_detail), use24, {
                    if (SetupSystem.set24Hour(ctx, it)) use24 = it
                })
                Spacer(Modifier.height(8.dp))
                TextActionButton(stringResource(R.string.time_manual), icon = Icons.Rounded.EditCalendar, onClick = {
                    ctx.startActivity(Intent(Settings.ACTION_DATE_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                })
            }
            Column(Modifier.weight(1.1f).fillMaxHeight()) {
                SectionLabel(stringResource(R.string.time_zone_label))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (regional.isNotEmpty()) {
                        FilterChip(selected = !world, onClick = { world = false },
                            label = { Text(stringResource(R.string.time_zone_region, SetupSystem.countryName(country!!, model.locale))) })
                    }
                    FilterChip(selected = world, onClick = { world = true }, label = { Text(stringResource(R.string.time_zone_all)) })
                }
                Spacer(Modifier.height(8.dp))
                SearchField(query, { query = it }, stringResource(R.string.time_zone_search), "zone-search")
                Spacer(Modifier.height(8.dp))
                val q = query.trim()
                val list = (if (world) everywhere.value else regional).filter {
                    q.isEmpty() || it.city.contains(q, true) || it.name.contains(q, true) || it.id.contains(q, true)
                }
                val manual = settings.canSetZone && !settings.autoZone
                if (!manual) Notice(Icons.Rounded.EditCalendar) { Text(stringResource(R.string.time_zone_detected), style = Ob.type.body) }
                LazyColumn(Modifier.weight(1f)) {
                    items(list, key = { it.id }) { z ->
                        ChoiceRow(z.city, z.id == model.zoneId, trailing = "${z.name} · ${z.offsetLabel}", onClick = {
                            if (manual) {
                                model.zoneId = z.id
                                model.zoneChosen = true
                            }
                        })
                    }
                }
            }
        }
    }
}
