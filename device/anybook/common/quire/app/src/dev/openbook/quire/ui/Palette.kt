// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.ui

import android.content.Context
import android.content.res.Configuration
import android.graphics.Color

/**
 * The note's colour roles (docs/quire-design.md §7.3): Material 3 TonalSpot, which Android derives from the wallpaper.
 * Every role comes from the system's own `system_*` colours, never from constants, so the note follows the wallpaper
 * like the rest of the desktop. The only fixed colours are the success green (the system has no green role) and the
 * brand hues, which appear only on the leaf, the halo, the agent's pointer and the glass's rim.
 *
 * The materials (§4, ANAL-227): glass (the note), paper (cards, the field, pills) and ink (text and marks). With [glass]
 * false, the platform has turned window blur off (battery saver, thermal, Developer options): the note becomes
 * near-opaque paper with the same layout (§4.5 Blur off).
 */
class Palette private constructor(context: Context, val dark: Boolean, val glass: Boolean) {
    private val res = context.resources
    private fun c(light: Int, night: Int) = res.getColor(if (dark) night else light, null)

    val primary = c(android.R.color.system_primary_light, android.R.color.system_primary_dark)
    val onPrimary = c(android.R.color.system_on_primary_light, android.R.color.system_on_primary_dark)
    val primaryContainer =
        c(android.R.color.system_primary_container_light, android.R.color.system_primary_container_dark)
    val onPrimaryContainer =
        c(android.R.color.system_on_primary_container_light, android.R.color.system_on_primary_container_dark)
    val secondaryContainer =
        c(android.R.color.system_secondary_container_light, android.R.color.system_secondary_container_dark)
    val onSecondaryContainer =
        c(android.R.color.system_on_secondary_container_light, android.R.color.system_on_secondary_container_dark)
    val tertiary = c(android.R.color.system_tertiary_light, android.R.color.system_tertiary_dark)
    val tertiaryContainer =
        c(android.R.color.system_tertiary_container_light, android.R.color.system_tertiary_container_dark)
    val onTertiaryContainer =
        c(android.R.color.system_on_tertiary_container_light, android.R.color.system_on_tertiary_container_dark)
    val error = c(android.R.color.system_error_light, android.R.color.system_error_dark)
    val errorContainer = c(android.R.color.system_error_container_light, android.R.color.system_error_container_dark)
    val surface = c(android.R.color.system_surface_light, android.R.color.system_surface_dark)
    val surfaceDim = c(android.R.color.system_surface_dim_light, android.R.color.system_surface_dim_dark)
    val surfaceLowest = c(android.R.color.system_surface_container_lowest_light,
        android.R.color.system_surface_container_lowest_dark)
    val surfaceContainer =
        c(android.R.color.system_surface_container_light, android.R.color.system_surface_container_dark)
    val surfaceHigh =
        c(android.R.color.system_surface_container_high_light, android.R.color.system_surface_container_high_dark)
    val surfaceHighest = c(android.R.color.system_surface_container_highest_light,
        android.R.color.system_surface_container_highest_dark)
    val onSurface = c(android.R.color.system_on_surface_light, android.R.color.system_on_surface_dark)
    private val onSurfaceVariantRole =
        c(android.R.color.system_on_surface_variant_light, android.R.color.system_on_surface_variant_dark)
    val outline = c(android.R.color.system_outline_light, android.R.color.system_outline_dark)
    val outlineVariant = c(android.R.color.system_outline_variant_light, android.R.color.system_outline_variant_dark)
    val inverseSurface = c(android.R.color.system_inverse_surface_light, android.R.color.system_inverse_surface_dark)
    val inverseOnSurface =
        c(android.R.color.system_inverse_on_surface_light, android.R.color.system_inverse_on_surface_dark)

    /** §4.3: the system has no green role, so the done check and the mic indicator use fixed greens. */
    val success = if (dark) 0xFF9BD5A8.toInt() else 0xFF2F6B45.toInt()
    val successContainer = if (dark) 0xFF1E4A2F.toInt() else 0xFFBDEBCB.toInt()
    val onSuccessContainer = if (dark) 0xFFBDEBCB.toInt() else 0xFF0B3B20.toInt()

    /** The note's own colour, before alpha: `surface` in light, `surfaceContainer` in dark (§4.1 tint). */
    private val noteBase = if (dark) surfaceContainer else surface

    /**
     * Glass (§4.1): the note's colour at 80 % over the system's background blur; 80 % is the lowest alpha at which
     * every pair in §7.4 passes at the worst backdrop. With blur off, 96 % and no blur.
     */
    val noteBackground = withAlpha(noteBase, if (glass) NOTE_ALPHA else NOTE_ALPHA_SOLID)

    /**
     * Soft ink (§4.3): `onSurface` blended 85 % over the note's colour, for the quiet line, kind icons, pending steps,
     * placeholders and sub-lines. `onSurfaceVariant` fails at the worst backdrop on 80 % glass, so it is derived.
     */
    val onSurfaceVariant = blend(onSurface, noteBase, 0.85f)

    /** The glass's edge where it meets the desktop, 1 dp inside (§4.1 outline). */
    val noteOutline = if (dark) Color.argb(36, 255, 255, 255) else Color.argb(140, 255, 255, 255)
    val shadow = if (dark) Color.argb(140, 0, 0, 0) else Color.argb(56, 0x1B, 0x1B, 0x21)

    /** Light on the top edge of the pane (§4.1 specular). Off with blur. */
    val specular = if (dark) Color.argb(46, 255, 255, 255) else Color.argb(191, 255, 255, 255)

    /** Light falling on the glass from the top-left (§4.1 bloom). Off with blur. */
    val bloom = if (dark) Color.argb(18, 255, 255, 255) else Color.argb(87, 255, 255, 255)

    /** The holographic rim's hues (§4.1 rim), at its alpha: 70 % light, 80 % dark, 60 % of that with blur off. */
    val rim: IntArray = (if (dark) RIM_DARK else RIM_LIGHT).map {
        withAlpha(it, (if (dark) 0.80f else 0.70f) * if (glass) 1f else 0.6f)
    }.toIntArray()

    /** Paper (§4.2): cards inside the note, the folded-steps chip, the undo pill, paper buttons. */
    val card = if (!glass) (if (dark) surfaceHigh else surfaceLowest)
        else withAlpha(if (dark) surfaceHigh else surfaceLowest, if (dark) 0.80f else 0.72f)

    /** The lit top edge of a sheet of paper (§4.2 paper.line). */
    val paperLine = if (dark) Color.argb(26, 255, 255, 255) else Color.argb(230, 255, 255, 255)

    /** The field, change rows, the command chip and the diff (§4.2 field). */
    val field = if (!glass) (if (dark) surfaceHighest else surfaceLowest)
        else withAlpha(if (dark) surfaceHighest else surfaceLowest, if (dark) 0.85f else 0.80f)
    val cardOutline = withAlpha(outlineVariant, if (dark) 0.60f else 0.40f)
    val scrim = if (dark) Color.argb(115, 0, 0, 0) else Color.argb(82, 14, 14, 18)

    companion object {
        const val NOTE_ALPHA = 0.80f
        const val NOTE_ALPHA_SOLID = 0.96f

        /** The halo's hues, caught in the glass (§4.1 rim). */
        private val RIM_LIGHT = intArrayOf(0xFF7E8CFF.toInt(), 0xFFC58BFF.toInt(), 0xFFFF7A9C.toInt(),
            0xFFFFB38A.toInt(), 0xFF8FD6FF.toInt())
        private val RIM_DARK = intArrayOf(0xFFA9B6FF.toInt(), 0xFFDDBDFF.toInt(), 0xFFFFB0C4.toInt(),
            0xFFFFD3B3.toInt(), 0xFFB8E8FF.toInt())

        /** The brand gradient (§4.3): only on the leaf, the halo and the agent's pointer. */
        const val BRAND_A = 0xFF7E8CFF.toInt()
        const val BRAND_B = 0xFF4355B9.toInt()
        const val FOLD_A = 0xFFFFB38A.toInt()
        const val FOLD_B = 0xFFFF7A9C.toInt()

        fun of(context: Context): Palette {
            val night = context.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
                Configuration.UI_MODE_NIGHT_YES
            return Palette(context, night, glassOn(context))
        }

        /** Whether the platform blurs behind windows now (§4.5: battery saver, thermal and Developer options turn it off). */
        fun glassOn(context: Context): Boolean = try {
            context.getSystemService(android.view.WindowManager::class.java)?.isCrossWindowBlurEnabled ?: false
        } catch (e: RuntimeException) {
            false
        }

        /** [top] at [amount] over [bottom], opaque. */
        fun blend(top: Int, bottom: Int, amount: Float): Int {
            fun ch(a: Int, b: Int) = (a * amount + b * (1 - amount)).toInt().coerceIn(0, 255)
            return Color.rgb(ch(Color.red(top), Color.red(bottom)), ch(Color.green(top), Color.green(bottom)),
                ch(Color.blue(top), Color.blue(bottom)))
        }

        fun withAlpha(color: Int, alpha: Float): Int =
            Color.argb((alpha * 255).toInt().coerceIn(0, 255), Color.red(color), Color.green(color), Color.blue(color))
    }
}
