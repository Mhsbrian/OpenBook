// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.ui

import android.content.Context
import android.graphics.Typeface
import android.util.TypedValue
import android.widget.TextView
import dev.openbook.quire.R

/**
 * Type for the note (docs/quire-design.md §4.1). Google Sans Text is the system's `google-sans-text` family
 * (ANAL-202); Google Sans Code and the Material Symbols subset ship inside Quire (res/font, licences in fonts/).
 * Sizes are the prototype's, which the renders show.
 */
class Type private constructor(context: Context) {
    private val base: Typeface = Typeface.create(FAMILY, Typeface.NORMAL)
    val regular: Typeface = Typeface.create(base, 400, false)
    val medium: Typeface = Typeface.create(base, 500, false)
    val semibold: Typeface = Typeface.create(base, 600, false)
    val bold: Typeface = Typeface.create(base, 700, false)
    val code: Typeface = context.resources.getFont(R.font.quire_code)
    val symbols: Typeface = context.resources.getFont(R.font.quire_symbols)

    fun weight(w: Int): Typeface =
        when {
            w >= 700 -> bold
            w >= 600 -> semibold
            w >= 500 -> medium
            else -> regular
        }

    companion object {
        const val FAMILY = "google-sans-text"

        @Volatile private var instance: Type? = null

        fun of(context: Context): Type =
            instance ?: synchronized(this) { instance ?: Type(context.applicationContext).also { instance = it } }
    }
}

/** One text role: size and line height in sp, and weight. */
data class TextRole(val size: Float, val line: Float, val weight: Int) {
    companion object {
        val PROMPT = TextRole(15f, 22f, 500)
        val BODY = TextRole(15f, 22f, 400)
        val LABEL = TextRole(13.5f, 20f, 400)
        val FIELD = TextRole(14f, 20f, 400)
        val CHIP = TextRole(13f, 20f, 500)
        val INTAKE = TextRole(12.5f, 18f, 500)
        val BUTTON = TextRole(13.5f, 20f, 500)
        val TITLE = TextRole(13f, 20f, 600)
        val META = TextRole(12f, 16f, 400)
        val META_MEDIUM = TextRole(12f, 16f, 500)
        val SUB = TextRole(12.5f, 18f, 400)
        val CODE = TextRole(12.5f, 18f, 400)
        val KBD = TextRole(11f, 14f, 500)
        val HEADING = TextRole(11.5f, 16f, 600)
    }
}

fun TextView.role(role: TextRole, color: Int, type: Type = Type.of(context)) {
    setTextSize(TypedValue.COMPLEX_UNIT_SP, role.size)
    setLineHeight(TypedValue.COMPLEX_UNIT_SP, role.line)
    typeface = type.weight(role.weight)
    setTextColor(color)
    includeFontPadding = false
}
