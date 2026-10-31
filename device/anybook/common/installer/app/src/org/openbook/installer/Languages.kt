// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import androidx.annotation.StringRes
import java.util.Locale

/**
 * A language on the Welcome screen. [nativeName] is the language's own name (a string resource that is not
 * translated); the secondary column is the language's name in the current UI language, from [Locale].
 */
data class Language(val tag: String, @param:StringRes val nativeName: Int, val keyboard: String) {
    val locale: Locale get() = Locale.forLanguageTag(tag)

    fun displayLanguage(inLocale: Locale): String =
        locale.getDisplayLanguage(inLocale).replaceFirstChar { it.titlecase(inLocale) }
}

object Languages {
    val all = listOf(
        Language("en-US", R.string.lang_en_us, "us"),
        Language("en-GB", R.string.lang_en_gb, "gb"),
        Language("es-ES", R.string.lang_es, "es"),
        Language("fr-FR", R.string.lang_fr, "fr"),
        Language("de-DE", R.string.lang_de, "de"),
        Language("it-IT", R.string.lang_it, "it"),
        Language("pt-BR", R.string.lang_pt_br, "br"),
        Language("nl-NL", R.string.lang_nl, "nl"),
        Language("pl-PL", R.string.lang_pl, "pl"),
        Language("sv-SE", R.string.lang_sv, "se"),
        Language("tr-TR", R.string.lang_tr, "tr"),
        Language("el-GR", R.string.lang_el, "gr"),
        Language("ru-RU", R.string.lang_ru, "ru"),
        Language("uk-UA", R.string.lang_uk, "ua"),
        Language("vi-VN", R.string.lang_vi, "us"),
        Language("ja-JP", R.string.lang_ja, "jp"),
        Language("ko-KR", R.string.lang_ko, "kr"),
        Language("zh-Hans-CN", R.string.lang_zh_hans, "us"),
    )

    fun byTag(tag: String): Language? = all.firstOrNull { it.tag.equals(tag, ignoreCase = true) }

    /** The list entry closest to [locale]: same language and region (or script), else same language, else null. */
    fun closest(locale: Locale): Language? {
        val exact = all.firstOrNull {
            val l = it.locale
            l.language == locale.language &&
                (l.country == locale.country || (l.script.isNotEmpty() && l.script == locale.script))
        }
        if (exact != null) return exact
        if (locale.language == "zh" && (locale.country == "TW" || locale.country == "HK" || locale.script == "Hant")) {
            return null
        }
        return all.firstOrNull { it.locale.language == locale.language }
    }
}

/** A keyboard layout the install engine writes into the boot entry (`androidboot.openbook.keyboard`). */
data class KeyboardLayout(val id: String, @param:StringRes val label: Int)

object KeyboardLayouts {
    val all = listOf(
        KeyboardLayout("us", R.string.kbd_us),
        KeyboardLayout("gb", R.string.kbd_gb),
        KeyboardLayout("de", R.string.kbd_de),
        KeyboardLayout("fr", R.string.kbd_fr),
        KeyboardLayout("es", R.string.kbd_es),
        KeyboardLayout("it", R.string.kbd_it),
        KeyboardLayout("br", R.string.kbd_br),
        KeyboardLayout("nl", R.string.kbd_nl),
        KeyboardLayout("pl", R.string.kbd_pl),
        KeyboardLayout("se", R.string.kbd_se),
        KeyboardLayout("tr", R.string.kbd_tr),
        KeyboardLayout("gr", R.string.kbd_gr),
        KeyboardLayout("ru", R.string.kbd_ru),
        KeyboardLayout("ua", R.string.kbd_ua),
        KeyboardLayout("jp", R.string.kbd_jp),
        KeyboardLayout("kr", R.string.kbd_kr),
    )

    fun byId(id: String): KeyboardLayout = all.firstOrNull { it.id == id } ?: all.first()
}
