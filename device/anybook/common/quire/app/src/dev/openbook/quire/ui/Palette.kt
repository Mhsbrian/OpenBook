// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.ui

import android.content.Context
import android.content.res.Configuration
import android.graphics.Color

/**
 * The note's colour roles (docs/quire-design.md §4.3): Material 3 TonalSpot, which Android derives from the wallpaper.
 * Every role comes from the system's own `system_*` colours, never from constants, so the note follows the wallpaper
 * like the rest of the desktop. The only fixed colours are the success green (the system has no green role) and the
 * brand gradient, which appears only on the leaf, the halo and the agent's pointer.
 */
class Palette private constructor(context: Context, val dark: Boolean) {
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
    val onSurfaceVariant =
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

    /**
     * The note itself: `surface` at 92 % in light, `surfaceContainer` at 92 % in dark (§3.1), over the background
     * blur. 92 % is the lowest alpha at which every pair in §4.5 passes at the worst backdrop.
     */
    val noteBackground = withAlpha(if (dark) surfaceContainer else surface, NOTE_ALPHA)
    val noteOutline = withAlpha(outlineVariant, if (dark) 0.6f else 0.5f)
    val shadow = if (dark) Color.argb(128, 0, 0, 0) else Color.argb(46, 0x1B, 0x1B, 0x21)

    /** Cards inside the note: `surfaceContainerLowest` in light, `surfaceContainerHigh` in dark (§4.3). */
    val card = if (dark) surfaceHigh else surfaceLowest

    /** The composer field, change rows, the command chip and the diff: `surfaceContainer` / `surfaceContainerHighest`. */
    val field = if (dark) surfaceHighest else surfaceContainer
    val cardOutline = withAlpha(outlineVariant, 0.55f)
    val scrim = if (dark) Color.argb(115, 0, 0, 0) else Color.argb(82, 14, 14, 18)

    companion object {
        const val NOTE_ALPHA = 0.92f

        /** The brand gradient (§4.3): only on the leaf, the halo and the agent's pointer. */
        const val BRAND_A = 0xFF7E8CFF.toInt()
        const val BRAND_B = 0xFF4355B9.toInt()
        const val FOLD_A = 0xFFFFB38A.toInt()
        const val FOLD_B = 0xFFFF7A9C.toInt()

        fun of(context: Context): Palette {
            val night = context.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
                Configuration.UI_MODE_NIGHT_YES
            return Palette(context, night)
        }

        fun withAlpha(color: Int, alpha: Float): Int =
            Color.argb((alpha * 255).toInt().coerceIn(0, 255), Color.red(color), Color.green(color), Color.blue(color))
    }
}
