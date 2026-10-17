// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.os.PowerManager
import android.os.SystemProperties
import android.os.UserHandle
import android.provider.Settings
import android.util.Log
import com.android.internal.app.LocalePicker
import com.android.internal.widget.LockPatternUtils
import java.util.Locale

/** System-level actions of the installer. They need the privileged permissions in AndroidManifest.xml. */
object LiveSystem {
    private const val TAG = "OpenBookInstaller"

    /** Set by the live stick's boot entry (docs/installer.md §11). */
    const val PROP_LIVE = "ro.boot.openbook.live"

    /** Set by the installed system's boot entry: the language picked in the wizard (BCP-47). */
    const val PROP_LOCALE = "ro.boot.openbook.locale"

    private const val LAUNCHER_ALIAS = "org.openbook.installer.InstallLauncher"

    fun isLiveSession(): Boolean = SystemProperties.get(PROP_LIVE) == "1"

    fun installedLocale(): String = SystemProperties.get(PROP_LOCALE, "")

    /** The "Install OpenBook" launcher shortcut exists only in the live session. */
    fun setLauncherAliasEnabled(context: Context, enabled: Boolean) {
        val state = if (enabled) {
            PackageManager.COMPONENT_ENABLED_STATE_ENABLED
        } else {
            PackageManager.COMPONENT_ENABLED_STATE_DISABLED
        }
        try {
            context.packageManager.setComponentEnabledSetting(
                ComponentName(context.packageName, LAUNCHER_ALIAS),
                state,
                PackageManager.DONT_KILL_APP,
            )
        } catch (e: RuntimeException) {
            Log.w(TAG, "could not ${if (enabled) "enable" else "disable"} the launcher shortcut", e)
        }
    }

    /** The live session has no user credential; skip the insecure keyguard. */
    fun disableKeyguard(context: Context) {
        try {
            LockPatternUtils(context).setLockScreenDisabled(true, UserHandle.myUserId())
        } catch (e: Exception) {
            Log.w(TAG, "could not disable the keyguard for the live session", e)
        }
    }

    /** Applies [tag] (BCP-47) as the system language at once. */
    fun applyLocale(tag: String): Boolean {
        return try {
            LocalePicker.updateLocale(Locale.forLanguageTag(tag))
            true
        } catch (e: Exception) {
            Log.w(TAG, "could not apply the locale $tag", e)
            false
        }
    }

    fun reboot(context: Context) {
        val pm = context.getSystemService(PowerManager::class.java) ?: return
        // reboot() blocks until the system goes down; keep it off the main thread.
        Thread({
            try {
                pm.reboot(null)
            } catch (e: Exception) {
                Log.e(TAG, "reboot failed", e)
            }
        }, "openbook-reboot").start()
    }
}

/** The accessibility toggles on the Welcome screen. Writes need WRITE_SETTINGS / WRITE_SECURE_SETTINGS. */
object AccessibilitySettings {
    private const val TAG = "OpenBookInstaller"
    private const val HIGH_TEXT_CONTRAST = "high_text_contrast_enabled" // Settings.Secure, @hide
    const val LARGER_FONT_SCALE = 1.3f

    data class State(val largerText: Boolean, val highContrast: Boolean, val reduceMotion: Boolean)

    fun read(context: Context): State {
        val cr = context.contentResolver
        val scale = Settings.System.getFloat(cr, Settings.System.FONT_SCALE, 1.0f)
        val contrast = Settings.Secure.getInt(cr, HIGH_TEXT_CONTRAST, 0) != 0
        val animator = Settings.Global.getFloat(cr, Settings.Global.ANIMATOR_DURATION_SCALE, 1.0f)
        return State(largerText = scale > 1.05f, highContrast = contrast, reduceMotion = animator == 0f)
    }

    fun setLargerText(context: Context, on: Boolean): Boolean = write {
        Settings.System.putFloat(context.contentResolver, Settings.System.FONT_SCALE, if (on) LARGER_FONT_SCALE else 1.0f)
    }

    fun setHighContrast(context: Context, on: Boolean): Boolean = write {
        Settings.Secure.putInt(context.contentResolver, HIGH_TEXT_CONTRAST, if (on) 1 else 0)
    }

    fun setReduceMotion(context: Context, on: Boolean): Boolean = write {
        val cr = context.contentResolver
        val scale = if (on) 0f else 1f
        Settings.Global.putFloat(cr, Settings.Global.WINDOW_ANIMATION_SCALE, scale) &&
            Settings.Global.putFloat(cr, Settings.Global.TRANSITION_ANIMATION_SCALE, scale) &&
            Settings.Global.putFloat(cr, Settings.Global.ANIMATOR_DURATION_SCALE, scale)
    }

    private inline fun write(block: () -> Boolean): Boolean = try {
        block()
    } catch (e: SecurityException) {
        Log.w(TAG, "settings write refused", e)
        false
    }
}
