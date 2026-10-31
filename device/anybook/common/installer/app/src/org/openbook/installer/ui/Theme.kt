// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

/*
 * Color roles from docs/installer-design/index.html (Material 3, seed #4A5BD4). Contrast is AA in both themes.
 */

private val LightColors: ColorScheme = lightColorScheme(
    primary = Color(0xFF4355B9), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFDEE0FF), onPrimaryContainer = Color(0xFF00105C),
    secondary = Color(0xFF5B5D72), onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFE0E1F9), onSecondaryContainer = Color(0xFF181A2C),
    tertiary = Color(0xFF8A4A62), onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFFFFD9E3), onTertiaryContainer = Color(0xFF390A1E),
    error = Color(0xFFBA1A1A), onError = Color(0xFFFFFFFF),
    errorContainer = Color(0xFFFFDAD6), onErrorContainer = Color(0xFF410002),
    background = Color(0xFFFBF8FF), onBackground = Color(0xFF1B1B21),
    surface = Color(0xFFFBF8FF), onSurface = Color(0xFF1B1B21),
    surfaceVariant = Color(0xFFE3E1EA), onSurfaceVariant = Color(0xFF46464F),
    outline = Color(0xFF767680), outlineVariant = Color(0xFFC6C5D0),
    surfaceContainerLowest = Color(0xFFFFFFFF), surfaceContainerLow = Color(0xFFF5F2FB),
    surfaceContainer = Color(0xFFEFEDF6), surfaceContainerHigh = Color(0xFFE9E7F0),
    surfaceContainerHighest = Color(0xFFE3E1EA),
    surfaceTint = Color(0xFF4355B9),
)

private val DarkColors: ColorScheme = darkColorScheme(
    primary = Color(0xFFBAC3FF), onPrimary = Color(0xFF08218A),
    primaryContainer = Color(0xFF293CA0), onPrimaryContainer = Color(0xFFDEE0FF),
    secondary = Color(0xFFC4C5DD), onSecondary = Color(0xFF2D2F42),
    secondaryContainer = Color(0xFF43465A), onSecondaryContainer = Color(0xFFE0E1F9),
    tertiary = Color(0xFFFFB0C9), onTertiary = Color(0xFF531D33),
    tertiaryContainer = Color(0xFF6E3349), onTertiaryContainer = Color(0xFFFFD9E3),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
    errorContainer = Color(0xFF93000A), onErrorContainer = Color(0xFFFFDAD6),
    background = Color(0xFF121318), onBackground = Color(0xFFE4E1E9),
    surface = Color(0xFF121318), onSurface = Color(0xFFE4E1E9),
    surfaceVariant = Color(0xFF35343A), onSurfaceVariant = Color(0xFFC6C5D0),
    outline = Color(0xFF90909A), outlineVariant = Color(0xFF46464F),
    surfaceContainerLowest = Color(0xFF0D0E13), surfaceContainerLow = Color(0xFF1B1B21),
    surfaceContainer = Color(0xFF1F1F25), surfaceContainerHigh = Color(0xFF2A292F),
    surfaceContainerHighest = Color(0xFF35343A),
    surfaceTint = Color(0xFFBAC3FF),
)

/** Roles the design adds to Material 3: success / warning, and the partition bar colors. */
@Immutable
data class ExtendedColors(
    val success: Color,
    val successContainer: Color,
    val onSuccessContainer: Color,
    val warning: Color,
    val warningContainer: Color,
    val onWarningContainer: Color,
    val barWindows: Color,
    val barLinux: Color,
    val barEfi: Color,
    val barOther: Color,
    val barOpenBookStart: Color,
    val barOpenBookEnd: Color,
    val dark: Boolean,
)

private val LightExtended = ExtendedColors(
    success = Color(0xFF276A3B), successContainer = Color(0xFFB6F1BE), onSuccessContainer = Color(0xFF00210B),
    warning = Color(0xFF775A00), warningContainer = Color(0xFFFFDF9A), onWarningContainer = Color(0xFF251A00),
    barWindows = Color(0xFF4C74E6), barLinux = Color(0xFFE8A23C), barEfi = Color(0xFF8D8FA3),
    barOther = Color(0xFFB0789A), barOpenBookStart = Color(0xFF4355B9), barOpenBookEnd = Color(0xFF8A5CF0),
    dark = false,
)

private val DarkExtended = ExtendedColors(
    success = Color(0xFF9BD5A3), successContainer = Color(0xFF0B5225), onSuccessContainer = Color(0xFFB6F1BE),
    warning = Color(0xFFEFC048), warningContainer = Color(0xFF5A4300), onWarningContainer = Color(0xFFFFDF9A),
    barWindows = Color(0xFF7F9CFF), barLinux = Color(0xFFF2B95E), barEfi = Color(0xFF9FA1B5),
    barOther = Color(0xFFD9A2C2), barOpenBookStart = Color(0xFF8E9CFF), barOpenBookEnd = Color(0xFFC49BFF),
    dark = true,
)

val LocalExtendedColors = staticCompositionLocalOf { LightExtended }

/** Text styles from the design (Roboto, the system sans-serif; Roboto Flex is not bundled). */
@Immutable
data class InstallerType(
    val overline: TextStyle,
    val headline: TextStyle,
    val lede: TextStyle,
    val hero: TextStyle,
    val heroTag: TextStyle,
    val title: TextStyle,
    val body: TextStyle,
    val caption: TextStyle,
    val sectionLabel: TextStyle,
    val percent: TextStyle,
    val mono: TextStyle,
)

private val Type = InstallerType(
    overline = TextStyle(fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.02.em),
    headline = TextStyle(fontSize = 40.sp, lineHeight = 48.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.02).em),
    lede = TextStyle(fontSize = 16.5.sp, lineHeight = 25.sp),
    hero = TextStyle(fontSize = 52.sp, lineHeight = 56.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.035).em),
    heroTag = TextStyle(fontSize = 18.sp, lineHeight = 26.sp),
    title = TextStyle(fontSize = 18.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.01).em),
    body = TextStyle(fontSize = 14.5.sp, lineHeight = 21.sp),
    caption = TextStyle(fontSize = 13.sp, lineHeight = 18.sp),
    sectionLabel = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.02.em),
    percent = TextStyle(fontSize = 76.sp, lineHeight = 76.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.04).em),
    mono = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 12.5.sp, lineHeight = 18.sp),
)

val LocalInstallerType = staticCompositionLocalOf { Type }

object Ob {
    val colors: ExtendedColors
        @Composable get() = LocalExtendedColors.current
    val type: InstallerType
        @Composable get() = LocalInstallerType.current
}

@Composable
fun OpenBookTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val base = Typography()
    val typography = base.copy(
        labelLarge = base.labelLarge.copy(fontSize = 15.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.01.em),
    )
    CompositionLocalProvider(
        LocalExtendedColors provides if (dark) DarkExtended else LightExtended,
        LocalInstallerType provides Type,
    ) {
        MaterialTheme(colorScheme = if (dark) DarkColors else LightColors, typography = typography, content = content)
    }
}
