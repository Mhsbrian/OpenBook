// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext

/** Material You, as OpenBook Update: colors from the wallpaper, the system's typography. */
@Composable
fun GraphicsTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val context = LocalContext.current
    MaterialTheme(colorScheme = if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context),
                  content = content)
}
