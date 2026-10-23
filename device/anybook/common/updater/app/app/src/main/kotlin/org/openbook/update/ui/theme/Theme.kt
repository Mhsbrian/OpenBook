// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

// OpenBook blue, used only where Material You colors are unavailable.
private val Light = lightColorScheme(
    primary = Color(0xFF2B5BD7), onPrimary = Color.White,
    primaryContainer = Color(0xFFDCE1FF), onPrimaryContainer = Color(0xFF00164E),
    secondaryContainer = Color(0xFFDDE1F9), onSecondaryContainer = Color(0xFF151B2C),
    tertiaryContainer = Color(0xFFFFD7F1), onTertiaryContainer = Color(0xFF390035),
)
private val Dark = darkColorScheme(
    primary = Color(0xFFB6C4FF), onPrimary = Color(0xFF00287C),
    primaryContainer = Color(0xFF143DAE), onPrimaryContainer = Color(0xFFDCE1FF),
    secondaryContainer = Color(0xFF41465A), onSecondaryContainer = Color(0xFFDDE1F9),
    tertiaryContainer = Color(0xFF6D2E66), onTertiaryContainer = Color(0xFFFFD7F1),
)

/** Material You: colors from the wallpaper, the system's typography (Googlebook's own font). */
@Composable
fun OpenBookUpdateTheme(dark: Boolean = isSystemInDarkTheme(), dynamic: Boolean = true, content: @Composable () -> Unit) {
    val context = LocalContext.current
    val colors = when {
        dynamic -> if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        dark -> Dark
        else -> Light
    }
    MaterialTheme(colorScheme = colors, content = content)
}
