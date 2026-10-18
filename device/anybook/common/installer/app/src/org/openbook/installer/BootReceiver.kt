// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * At boot:
 *  - live session (`ro.boot.openbook.live=1`): enable the "Install OpenBook" shortcut, skip the insecure keyguard and
 *    open the wizard;
 *  - installed system: remove the shortcut, and apply the language picked in the wizard once
 *    (`ro.boot.openbook.locale`, written into the boot entry by the install engine); show the Google apps
 *    registration entry in Settings › About only if the user installed their own package (ANAL-211).
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (LiveSystem.isLiveSession()) {
            LiveSystem.setLauncherAliasEnabled(context, true)
            LiveSystem.disableKeyguard(context)
            try {
                context.startActivity(
                    Intent(context, MainActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        .putExtra(MainActivity.EXTRA_FROM_BOOT, true),
                )
            } catch (e: RuntimeException) {
                Log.w(TAG, "could not open the installer at boot", e)
            }
        } else {
            LiveSystem.setLauncherAliasEnabled(context, false)
            applyInstalledLocaleOnce(context)
            GappsInfo.setSettingsEntryEnabled(context, GappsInfo.installed() != null)
        }
    }

    private fun applyInstalledLocaleOnce(context: Context) {
        val tag = LiveSystem.installedLocale()
        if (tag.isEmpty()) return
        val prefs = context.createDeviceProtectedStorageContext()
            .getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (prefs.getBoolean(KEY_LOCALE_APPLIED, false)) return
        if (LiveSystem.applyLocale(tag)) {
            prefs.edit().putBoolean(KEY_LOCALE_APPLIED, true).apply()
            Log.i(TAG, "applied the install-time language $tag")
        }
    }

    companion object {
        private const val TAG = "OpenBookInstaller"
        private const val PREFS = "installer"
        private const val KEY_LOCALE_APPLIED = "install_locale_applied"
    }
}
