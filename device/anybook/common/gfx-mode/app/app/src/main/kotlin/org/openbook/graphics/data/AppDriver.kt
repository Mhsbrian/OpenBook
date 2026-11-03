// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.data

/** Where an app's graphics run in Hybrid (docs/nvidia-offload-ruby.md, "Games on the NVIDIA GPU"). */
enum class Gpu { NVIDIA, RADEON }

/**
 * The owner's choice for one app, kept in Android's own lists as Developer options › Graphics Driver Preferences
 * writes them: AUTOMATIC (neither list: games on the NVIDIA GPU, other apps on the Radeon), NVIDIA (opt-in list)
 * and RADEON (opt-out list).
 */
enum class AppChoice { AUTOMATIC, NVIDIA, RADEON }

/** Why an app runs where it does, in the order Android checks (GraphicsEnvironment.chooseDriverInternal). */
enum class Reason {
    /** No driver package is offered (ro.gfx.driver.0 unset): Eco, NVIDIA's driver not loaded, another laptop. */
    NOT_OFFERED,
    /** A privileged or never-updated built-in app: Android never gives it another driver. */
    BUILT_IN,
    /** updatable_driver_all_apps = 3: "NVIDIA GPU for apps" is off (this app's switch, or Developer options). */
    ALL_APPS_OFF,
    /** updatable_driver_all_apps = 1 (Developer options: every app). */
    ALL_APPS,
    /** updatable_driver_all_apps = 2: a prerelease driver, which OpenBook does not offer. */
    ALL_APPS_PRERELEASE,
    /** The owner chose the Radeon (opt-out list). */
    CHOSEN_RADEON,
    /** In the prerelease opt-in list: OpenBook offers no prerelease driver. */
    PRERELEASE,
    /** The owner chose the NVIDIA GPU (opt-in list). */
    CHOSEN_NVIDIA,
    /** On the allow-list, which this app fills with the games. */
    GAME,
    /** The allow-list starts with "*" (set over adb): every app. */
    ALLOWLIST_ALL,
    /** Not on the allow-list: not a game, or the games rule is off. */
    NOT_ALLOWED,
    /** On the driver's deny-list (updatable_driver_production_denylist). */
    DENYLISTED,
    /**
     * Android would choose the driver package, but no system app has its name: GraphicsEnvironment.chooseDriver logs
     * "updatable driver package '…' not installed" and keeps the system driver. OpenBook images before ANAL-327 were
     * this case; since then init offers org.openbook.nvk only when the image has it.
     */
    NOT_INSTALLED,
}

data class Decision(val gpu: Gpu, val reason: Reason)

/** An installed app, as the rule sees it. */
data class AppInfo(
    val pkg: String,
    val label: String,
    /** Android's game category, or the older isGame flag. */
    val game: Boolean,
    /** Android may give it the driver package: not privileged, and not a never-updated built-in app. */
    val eligible: Boolean,
    /** It has an entry in the launcher. */
    val launchable: Boolean = true,
)

/** Android's updatable-driver settings (Settings.Global), split the way GraphicsEnvironment splits them. */
data class DriverSettings(
    val allApps: Int = AppDriver.ALL_APPS_DEFAULT,
    val optIn: List<String> = emptyList(),
    val prereleaseOptIn: List<String> = emptyList(),
    val optOut: List<String> = emptyList(),
    val denylist: List<String> = emptyList(),
    val allowlist: List<String> = emptyList(),
) {
    fun choice(pkg: String): AppChoice = when (pkg) {
        in optOut -> AppChoice.RADEON
        in optIn -> AppChoice.NVIDIA
        else -> AppChoice.AUTOMATIC
    }
}

/**
 * The games rule (ANAL-312): in Hybrid, games get the OpenBook NVK driver package automatically and every other
 * app stays on the Radeon, with the owner's per-app choice on top. It uses only Android's own updatable-driver
 * settings, so Developer options › Graphics Driver Preferences shows and changes the same choices:
 *  - updatable_driver_production_allowlist: this app keeps it equal to the installed games;
 *  - updatable_driver_production_opt_in_apps / _opt_out_apps: the owner's NVIDIA / Radeon choices;
 *  - updatable_driver_all_apps: 0 (each app decides), or 3 with "NVIDIA GPU for apps" off (every app on the Radeon).
 *    Android checks it first, so 1 ("all apps", Developer options) overrides the rule.
 * Fail-safe: an app the rule has not seen yet (installed since the last sync) stays on the Radeon.
 */
object AppDriver {
    const val ALL_APPS = "updatable_driver_all_apps"
    const val OPT_IN = "updatable_driver_production_opt_in_apps"
    const val PRERELEASE_OPT_IN = "updatable_driver_prerelease_opt_in_apps"
    const val OPT_OUT = "updatable_driver_production_opt_out_apps"
    const val DENYLIST = "updatable_driver_production_denylist"
    const val ALLOWLIST = "updatable_driver_production_allowlist"

    /**
     * The OpenBook NVK driver package (docs/nvk-openbook.md), which init offers in ro.gfx.driver.0 once NVIDIA's driver
     * binds, in an image that has it (init.openbook.rc).
     */
    const val NVK_PACKAGE = "org.openbook.nvk"

    const val ALL_APPS_DEFAULT = 0
    const val ALL_APPS_PRODUCTION = 1
    const val ALL_APPS_PRERELEASE = 2
    const val ALL_APPS_OFF = 3

    /** ApplicationInfo.CATEGORY_GAME and the deprecated ApplicationInfo.FLAG_IS_GAME. */
    private const val CATEGORY_GAME = 0
    private const val FLAG_IS_GAME = 1 shl 25

    /**
     * "NVIDIA GPU for apps" is on: each app's choice and the games rule decide (0), or Developer options put every app
     * on it (1). Off is 3, and 2 (a prerelease driver OpenBook does not have) leaves every app on the Radeon too.
     */
    fun appsOn(allApps: Int) = allApps == ALL_APPS_DEFAULT || allApps == ALL_APPS_PRODUCTION

    /** GraphicsEnvironment.getGlobalSettingsString: null is empty, otherwise split on commas (empty parts kept). */
    fun list(raw: String?): List<String> = raw?.split(",") ?: emptyList()

    fun isGame(category: Int, flags: Int) = category == CATEGORY_GAME || (flags and FLAG_IS_GAME) != 0

    /**
     * Android's choice for a process of this app (GraphicsEnvironment.chooseDriverInternal, AOSP 17, production
     * driver only: OpenBook sets no ro.gfx.driver.1), then chooseDriver's look-up of the package. [offered]:
     * ro.gfx.driver.0 is set. [installed]: a system app has that name (MATCH_SYSTEM_ONLY, as chooseDriver asks).
     */
    fun decide(app: AppInfo, s: DriverSettings, offered: Boolean, installed: Boolean = true): Decision {
        val d = chooseInternal(app, s, offered)
        return if (d.gpu == Gpu.NVIDIA && !installed) Decision(Gpu.RADEON, Reason.NOT_INSTALLED) else d
    }

    private fun chooseInternal(app: AppInfo, s: DriverSettings, offered: Boolean): Decision {
        fun radeon(r: Reason) = Decision(Gpu.RADEON, r)
        if (!offered) return radeon(Reason.NOT_OFFERED)
        if (!app.eligible) return radeon(Reason.BUILT_IN)
        when (s.allApps) {
            ALL_APPS_OFF -> return radeon(Reason.ALL_APPS_OFF)
            ALL_APPS_PRODUCTION -> return Decision(Gpu.NVIDIA, Reason.ALL_APPS)
            ALL_APPS_PRERELEASE -> return radeon(Reason.ALL_APPS_PRERELEASE)
        }
        if (app.pkg in s.optOut) return radeon(Reason.CHOSEN_RADEON)
        if (app.pkg in s.prereleaseOptIn) return radeon(Reason.PRERELEASE)
        val optIn = app.pkg in s.optIn
        val all = s.allowlist.indexOf("*") == 0
        if (!optIn && !all && app.pkg !in s.allowlist) return radeon(Reason.NOT_ALLOWED)
        if (!optIn && app.pkg in s.denylist) return radeon(Reason.DENYLISTED)
        return Decision(Gpu.NVIDIA, if (optIn) Reason.CHOSEN_NVIDIA else if (all) Reason.ALLOWLIST_ALL else Reason.GAME)
    }

    /** The allow-list for these apps: every eligible game, sorted; empty with the games rule off. */
    fun allowlist(apps: List<AppInfo>, gamesOn: Boolean): String =
        if (!gamesOn) "" else apps.filter { it.eligible && it.game }.map { it.pkg }.distinct().sorted().joinToString(",")

    /**
     * The three lists after the owner's choice for [pkg], as Graphics Driver Preferences edits them: the package
     * leaves the other lists (the prerelease one too), every other entry stays, empty parts are dropped.
     */
    fun choose(s: DriverSettings, pkg: String, choice: AppChoice): DriverSettings {
        fun edit(l: List<String>, add: Boolean) = l.filter { it.isNotEmpty() && it != pkg }.distinct() +
            (if (add) listOf(pkg) else emptyList())
        return s.copy(optIn = edit(s.optIn, choice == AppChoice.NVIDIA),
                      prereleaseOptIn = edit(s.prereleaseOptIn, false),
                      optOut = edit(s.optOut, choice == AppChoice.RADEON))
    }

    /** A package name as Android accepts it (no comma can reach a list). */
    fun validPackage(pkg: String) = PACKAGE.matches(pkg)

    private val PACKAGE = Regex("""[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+""")
}
