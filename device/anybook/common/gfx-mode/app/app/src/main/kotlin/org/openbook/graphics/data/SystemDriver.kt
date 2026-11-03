// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.data

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.UserManager
import android.provider.Settings
import android.util.Log
import androidx.core.content.edit
import java.util.concurrent.TimeUnit

/**
 * Android's side of the games rule: Settings.Global (WRITE_SECURE_SETTINGS, a privileged permission on the
 * allow-list), the installed apps (QUERY_ALL_PACKAGES) and ro.gfx.driver.0 through getprop. Public API only.
 */
class SystemDriverBackend(context: Context) : DriverBackend {
    private val ctx = context.applicationContext
    private val pm = ctx.packageManager
    private val cr = ctx.contentResolver

    override fun apps(): List<AppInfo> {
        val launchable = pm.queryIntentActivities(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER),
                                                  PackageManager.ResolveInfoFlags.of(0))
            .mapTo(HashSet()) { it.activityInfo.packageName }
        return pm.getInstalledApplications(PackageManager.ApplicationInfoFlags.of(0))
            .filter { it.packageName != ctx.packageName }
            .map { ai ->
                AppInfo(ai.packageName, runCatching { pm.getApplicationLabel(ai).toString() }.getOrDefault(ai.packageName),
                        AppDriver.isGame(ai.category, ai.flags), eligible(ai), ai.packageName in launchable)
            }
    }

    /**
     * GraphicsEnvironment refuses privileged apps and never-updated built-in apps. An updated built-in app is
     * privileged if its factory copy is in a priv-app directory: what ApplicationInfo.isPrivilegedApp (a system API
     * that needs INSTALL_PACKAGES) says, read through the factory copy's path. Unknown counts as built-in.
     */
    @SuppressLint("WrongConstant")  // MATCH_FACTORY_ONLY is not in the public SDK's list of flags
    private fun eligible(ai: ApplicationInfo): Boolean {
        if (ai.flags and ApplicationInfo.FLAG_SYSTEM == 0) return true
        if (ai.flags and ApplicationInfo.FLAG_UPDATED_SYSTEM_APP == 0) return false
        val factory = runCatching {
            pm.getPackageInfo(ai.packageName, PackageManager.PackageInfoFlags.of(MATCH_FACTORY_ONLY)).applicationInfo?.sourceDir
        }.getOrNull() ?: return false
        return "/priv-app/" !in factory
    }

    override fun getString(name: String): String? = Settings.Global.getString(cr, name)

    override fun getInt(name: String, default: Int): Int = Settings.Global.getInt(cr, name, default)

    override fun putString(name: String, value: String): Boolean = put(name) { Settings.Global.putString(cr, name, value) }

    override fun putInt(name: String, value: Int): Boolean = put(name) { Settings.Global.putInt(cr, name, value) }

    private fun put(name: String, write: () -> Boolean): Boolean = runCatching(write)
        .onFailure { Log.w(TAG, "games: could not write $name", it) }.getOrDefault(false)

    /**
     * GraphicsEnvironment.chooseDriver looks the driver package up with MATCH_SYSTEM_ONLY: only a system app (or an
     * update of one) can be a driver. This app sees every package (QUERY_ALL_PACKAGES).
     */
    override fun driverInstalled(pkg: String): Boolean = runCatching {
        pm.getPackageInfo(pkg, PackageManager.PackageInfoFlags.of(PackageManager.MATCH_SYSTEM_ONLY.toLong()))
        true
    }.getOrDefault(false)

    override fun offeredDriver(): String? = runCatching {
        val p = ProcessBuilder("/system/bin/getprop", "ro.gfx.driver.0").redirectErrorStream(true).start()
        val out = p.inputStream.bufferedReader().use { it.readText() }.trim()
        if (!p.waitFor(5, TimeUnit.SECONDS)) {
            p.destroyForcibly()
            null
        } else out.takeIf { p.exitValue() == 0 && it.isNotEmpty() }
    }.getOrNull()

    companion object {
        private const val TAG = "OpenBookGraphics"
        /**
         * PackageManager.MATCH_FACTORY_ONLY (a system API flag; the package manager honours it for any caller,
         * ComputerEngine.getPackageInfoInternalBody): the system image's copy of an updated app.
         */
        private const val MATCH_FACTORY_ONLY = 0x00200000L

        /**
         * The rule runs in the owner's user (an admin), never in Googlebook's headless system user (user 0) or a
         * guest's: the settings are device-wide, and the owner's apps are the ones that count.
         */
        fun runsHere(context: Context): Boolean {
            val users = context.getSystemService(UserManager::class.java)
            return users.isAdminUser && !(UserManager.isHeadlessSystemUserMode() && users.isSystemUser)
        }
    }
}

/** RulePrefs in this app's own shared preferences (the owner's user, credential storage). */
class SharedRulePrefs(context: Context) : RulePrefs {
    private val p = context.applicationContext.getSharedPreferences("games", Context.MODE_PRIVATE)

    override var gamesOn: Boolean
        get() = p.getBoolean("games_on", true)
        set(v) = p.edit(commit = true) { putBoolean("games_on", v) }

    override var allAppsReplaced: Boolean
        get() = p.getBoolean("all_apps_replaced", false)
        set(v) = p.edit(commit = true) { putBoolean("all_apps_replaced", v) }
}
