// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.data

/** The system side of the games rule, so the logic runs in unit tests too. Blocking: call off the main thread. */
interface DriverBackend {
    /** The apps installed for this user. */
    fun apps(): List<AppInfo>

    /** A Settings.Global string; null if unset. */
    fun getString(name: String): String?

    fun getInt(name: String, default: Int): Int

    /** False if Android refused the write (no WRITE_SECURE_SETTINGS). */
    fun putString(name: String, value: String): Boolean

    fun putInt(name: String, value: Int): Boolean

    /** ro.gfx.driver.0: the driver package offered to apps (set by vendor init once NVIDIA's driver binds). */
    fun offeredDriver(): String?

    /** A system app named [pkg] is installed: the only kind GraphicsEnvironment loads a driver from. */
    fun driverInstalled(pkg: String): Boolean
}

/** The owner's settings for the rule, in this app's own storage. */
interface RulePrefs {
    var gamesOn: Boolean
    /** "All apps" (updatable_driver_all_apps = 1) was replaced by the games rule once (ANAL-312). */
    var allAppsReplaced: Boolean
}

data class SyncResult(
    /** Games now on the allow-list. */
    val games: Int,
    /** The allow-list was rewritten. */
    val changed: Boolean,
    /** This sync replaced "all apps" with the games rule. */
    val replacedAllApps: Boolean,
    /** Android refused a write. */
    val refused: Boolean,
    /** No NVIDIA app driver is installed, so the rule wrote nothing (GamesRule.hasAppDriver). */
    val noDriver: Boolean = false,
) {
    companion object {
        val NO_DRIVER = SyncResult(games = 0, changed = false, replacedAllApps = false, refused = false, noDriver = true)
    }
}

/** What the apps screen shows. */
data class AppsState(
    val settings: DriverSettings,
    val offered: Boolean,
    val gamesOn: Boolean,
    /** Eligible apps with a launcher entry, a choice, or the game category; games first, then by label. */
    val apps: List<AppInfo>,
    /** An NVIDIA app driver is installed. Without one there is nothing to choose: [apps] is empty. */
    val appDriver: Boolean = true,
) {
    /** "NVIDIA GPU for apps" (AppDriver.appsOn). */
    val appsOn: Boolean get() = AppDriver.appsOn(settings.allApps)

    fun decision(app: AppInfo) = AppDriver.decide(app, settings, offered = true)
}

/**
 * Keeps updatable_driver_production_allowlist equal to the installed games (AppDriver) and writes the owner's
 * choices. Runs at boot, when an app is removed, when the apps screen opens and every 15 minutes (GamesJob).
 * Only with an NVIDIA app driver installed ([hasAppDriver]): without one, Android's lists change nothing, so the rule
 * leaves them as they are and the screen offers no choice (OpenBook's AOSP image, ANAL-323).
 */
class GamesRule(private val backend: DriverBackend, private val prefs: RulePrefs) {
    /**
     * The NVIDIA app driver's package: the one offered in ro.gfx.driver.0, or, while none is offered (Eco, NVIDIA's
     * driver not loaded yet), the OpenBook NVK package that init offers once it is.
     */
    fun driverPackage(): String = backend.offeredDriver()?.takeIf { it.isNotEmpty() } ?: AppDriver.NVK_PACKAGE

    /**
     * Whether that package is installed as a system app. A driver package reaches the system only with an image
     * update, which restarts the laptop, so a check per sync or screen is enough.
     */
    fun hasAppDriver(): Boolean = backend.driverInstalled(driverPackage())

    fun settings() = DriverSettings(
        allApps = backend.getInt(AppDriver.ALL_APPS, AppDriver.ALL_APPS_DEFAULT),
        optIn = AppDriver.list(backend.getString(AppDriver.OPT_IN)),
        prereleaseOptIn = AppDriver.list(backend.getString(AppDriver.PRERELEASE_OPT_IN)),
        optOut = AppDriver.list(backend.getString(AppDriver.OPT_OUT)),
        denylist = AppDriver.list(backend.getString(AppDriver.DENYLIST)),
        allowlist = AppDriver.list(backend.getString(AppDriver.ALLOWLIST)),
    )

    /**
     * One sync. The boot receiver, the job and the screen each make their own GamesRule in one process, often at
     * the same moment (scheduling the job runs it at once), so the lock is the process's, not the instance's.
     */
    fun sync(apps: List<AppInfo>? = null): SyncResult = synchronized(LOCK) {
        if (!hasAppDriver()) SyncResult.NO_DRIVER else syncLocked(apps ?: backend.apps())
    }

    private fun syncLocked(apps: List<AppInfo>): SyncResult {
        var refused = false
        var replaced = false
        if (!prefs.allAppsReplaced) {
            // Once, on the first run of this version: the owner's "all apps" (every window on the NVIDIA GPU)
            // becomes the games rule, as approved on ANAL-247. A later "all apps" from Developer options stays.
            if (backend.getInt(AppDriver.ALL_APPS, AppDriver.ALL_APPS_DEFAULT) == AppDriver.ALL_APPS_PRODUCTION) {
                replaced = backend.putInt(AppDriver.ALL_APPS, AppDriver.ALL_APPS_DEFAULT)
                refused = !replaced
            }
            if (!refused) prefs.allAppsReplaced = true
        }
        val want = AppDriver.allowlist(apps, prefs.gamesOn)
        val changed = backend.getString(AppDriver.ALLOWLIST).orEmpty() != want
        val wrote = !changed || backend.putString(AppDriver.ALLOWLIST, want)
        val games = if (want.isEmpty()) 0 else want.count { it == ',' } + 1
        return SyncResult(games, changed && wrote, replaced, refused || !wrote)
    }

    fun setGamesOn(on: Boolean): SyncResult = synchronized(LOCK) {
        if (!hasAppDriver()) return SyncResult.NO_DRIVER
        prefs.gamesOn = on
        syncLocked(backend.apps())
    }

    /**
     * The owner's choice for one app; false if the package name is invalid, no app driver is installed (a choice
     * would do nothing) or Android refused the write.
     */
    fun choose(pkg: String, choice: AppChoice): Boolean = synchronized(LOCK) {
        if (!AppDriver.validPackage(pkg) || !hasAppDriver()) return false
        val before = settings()
        val after = AppDriver.choose(before, pkg, choice)
        write(AppDriver.OPT_IN, before.optIn, after.optIn) &&
            write(AppDriver.PRERELEASE_OPT_IN, before.prereleaseOptIn, after.prereleaseOptIn) &&
            write(AppDriver.OPT_OUT, before.optOut, after.optOut)
    }

    /** "All apps" or "off" from Developer options back to each app deciding (the games rule). */
    fun useGamesRule(): Boolean = hasAppDriver() && backend.putInt(AppDriver.ALL_APPS, AppDriver.ALL_APPS_DEFAULT)

    /** "NVIDIA GPU for apps" now (AppDriver.appsOn). */
    fun appsOn(): Boolean = AppDriver.appsOn(backend.getInt(AppDriver.ALL_APPS, AppDriver.ALL_APPS_DEFAULT))

    /**
     * The "NVIDIA GPU for apps" switch (ANAL-327): on is updatable_driver_all_apps = 0, where the games rule and each
     * app's choice decide; off is 3, which keeps every app on the Radeon and leaves the choices as they are, for when it
     * is on again. Turning it on from Developer options' "every app" (1) keeps that setting. False without an app driver
     * (nothing to switch) or when Android refused the write. Applies at each app's next start.
     */
    fun setAppsOn(on: Boolean): Boolean = synchronized(LOCK) {
        if (!hasAppDriver()) return false
        if (on && appsOn()) return true
        backend.putInt(AppDriver.ALL_APPS, if (on) AppDriver.ALL_APPS_DEFAULT else AppDriver.ALL_APPS_OFF)
    }

    /**
     * The apps screen's state; [sync] first unless the reader is not the owner (who may not write). Without an app
     * driver: no apps, nothing synced.
     */
    fun state(sync: Boolean = true): AppsState {
        val offered = !backend.offeredDriver().isNullOrEmpty()
        if (!hasAppDriver()) return AppsState(settings(), offered, prefs.gamesOn, emptyList(), appDriver = false)
        val apps = backend.apps()
        if (sync) sync(apps)
        val s = settings()
        val shown = apps.filter { it.eligible && (it.launchable || it.game || s.choice(it.pkg) != AppChoice.AUTOMATIC) }
            .sortedWith(compareBy<AppInfo>({ !it.game }, { it.label.lowercase() }, { it.pkg }))
        return AppsState(s, offered, prefs.gamesOn, shown)
    }

    private fun write(name: String, before: List<String>, after: List<String>): Boolean =
        before == after || backend.putString(name, after.joinToString(","))

    companion object {
        private val LOCK = Any()
    }
}
