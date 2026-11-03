// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.openbook.graphics.data.AppChoice
import org.openbook.graphics.data.AppDriver
import org.openbook.graphics.data.AppInfo
import org.openbook.graphics.data.Decision
import org.openbook.graphics.data.DriverBackend
import org.openbook.graphics.data.DriverSettings
import org.openbook.graphics.data.GamesRule
import org.openbook.graphics.data.Gpu
import org.openbook.graphics.data.Reason
import org.openbook.graphics.data.RulePrefs
import org.openbook.graphics.data.SyncResult

private fun app(pkg: String, game: Boolean = false, eligible: Boolean = true, launchable: Boolean = true, label: String = pkg) =
    AppInfo(pkg, label, game, eligible, launchable)

class AppDriverTest {
    private val game = app("com.example.game", game = true)
    private val mail = app("com.example.mail")

    @Test
    fun gamesByCategoryOrTheOlderFlag() {
        assertTrue(AppDriver.isGame(category = 0, flags = 0))            // CATEGORY_GAME
        assertTrue(AppDriver.isGame(category = -1, flags = 1 shl 25))    // FLAG_IS_GAME, no category
        assertFalse(AppDriver.isGame(category = -1, flags = 0))          // CATEGORY_UNDEFINED
        assertFalse(AppDriver.isGame(category = 1, flags = 0))           // CATEGORY_AUDIO
        assertFalse(AppDriver.isGame(category = 7, flags = (1 shl 25) - 1))
    }

    @Test
    fun splitsSettingsAsGraphicsEnvironmentDoes() {
        assertEquals(emptyList<String>(), AppDriver.list(null))
        assertEquals(listOf(""), AppDriver.list(""))
        assertEquals(listOf("a.b", "", "c.d"), AppDriver.list("a.b,,c.d"))
    }

    private fun d(app: AppInfo, s: DriverSettings, offered: Boolean = true) = AppDriver.decide(app, s, offered)

    @Test
    fun theGamesRuleOnItsOwn() {
        val s = DriverSettings(allowlist = listOf("com.example.game"))
        assertEquals(Decision(Gpu.NVIDIA, Reason.GAME), d(game, s))
        assertEquals(Decision(Gpu.RADEON, Reason.NOT_ALLOWED), d(mail, s))
        // Nothing is offered (Eco, NVIDIA's driver not loaded): every app stays on the Radeon.
        assertEquals(Decision(Gpu.RADEON, Reason.NOT_OFFERED), d(game, s, offered = false))
        // Android never gives a privileged or never-updated built-in app another driver, even when chosen.
        val builtIn = app("com.example.game", game = true, eligible = false)
        assertEquals(Reason.BUILT_IN, d(builtIn, s.copy(optIn = listOf("com.example.game"))).reason)
        // No allow-list at all (GpuService never wrote one, the rule never ran): only opted-in apps.
        assertEquals(Reason.NOT_ALLOWED, d(game, DriverSettings()).reason)
        assertEquals(Reason.NOT_ALLOWED, d(game, DriverSettings(allowlist = AppDriver.list(""))).reason)
    }

    @Test
    fun androidsOrderOfPrecedence() {
        // 1. updatable_driver_all_apps decides before everything else.
        val all = DriverSettings(allApps = AppDriver.ALL_APPS_PRODUCTION, optOut = listOf(mail.pkg))
        assertEquals(Decision(Gpu.NVIDIA, Reason.ALL_APPS), d(mail, all))
        assertEquals(Reason.ALL_APPS_OFF, d(game, DriverSettings(allApps = 3, optIn = listOf(game.pkg),
                                                                 allowlist = listOf(game.pkg))).reason)
        assertEquals(Decision(Gpu.RADEON, Reason.ALL_APPS_PRERELEASE), d(game, DriverSettings(allApps = 2)))
        // 2. The opt-out list beats the opt-in list and the allow-list.
        val both = DriverSettings(optIn = listOf(game.pkg), optOut = listOf(game.pkg), allowlist = listOf(game.pkg))
        assertEquals(Decision(Gpu.RADEON, Reason.CHOSEN_RADEON), d(game, both))
        // 3. The prerelease opt-in list: OpenBook offers no prerelease driver, so the system driver.
        assertEquals(Reason.PRERELEASE, d(game, DriverSettings(prereleaseOptIn = listOf(game.pkg), allowlist = listOf(game.pkg))).reason)
        // 4. Opt-in skips the allow-list and the deny-list.
        assertEquals(Decision(Gpu.NVIDIA, Reason.CHOSEN_NVIDIA),
                     d(mail, DriverSettings(optIn = listOf(mail.pkg), denylist = listOf(mail.pkg))))
        // 5. The deny-list, for apps that did not opt in.
        assertEquals(Reason.DENYLISTED, d(game, DriverSettings(allowlist = listOf(game.pkg), denylist = listOf(game.pkg))).reason)
        // 6. "*" counts only as the first entry, as in GraphicsEnvironment (indexOf("*") == 0).
        assertEquals(Reason.ALLOWLIST_ALL, d(mail, DriverSettings(allowlist = listOf("*"))).reason)
        assertEquals(Reason.NOT_ALLOWED, d(mail, DriverSettings(allowlist = listOf("com.example.game", "*"))).reason)
        // Lists match whole package names only.
        assertEquals(Reason.NOT_ALLOWED, d(app("com.example.ga"), DriverSettings(allowlist = listOf(game.pkg))).reason)
    }

    @Test
    fun theAllowListIsTheEligibleGames() {
        val apps = listOf(app("org.z.game", game = true), mail, app("org.a.game", game = true),
                          app("org.builtin.game", game = true, eligible = false), app("org.a.game", game = true),
                          app("org.service.game", game = true, launchable = false))
        assertEquals("org.a.game,org.service.game,org.z.game", AppDriver.allowlist(apps, gamesOn = true))
        assertEquals("", AppDriver.allowlist(apps, gamesOn = false))
        assertEquals("", AppDriver.allowlist(listOf(mail), gamesOn = true))
    }

    @Test
    fun choicesEditTheListsAsGraphicsDriverPreferencesDoes() {
        val s = DriverSettings(optIn = listOf("", "a.one", "x.y", "a.one"), prereleaseOptIn = listOf("x.y"),
                               optOut = listOf("b.two"))
        val nvidia = AppDriver.choose(s, "x.y", AppChoice.NVIDIA)
        assertEquals(listOf("a.one", "x.y"), nvidia.optIn)
        assertEquals(emptyList<String>(), nvidia.prereleaseOptIn)
        assertEquals(listOf("b.two"), nvidia.optOut)
        assertEquals(AppChoice.NVIDIA, nvidia.choice("x.y"))
        val radeon = AppDriver.choose(nvidia, "x.y", AppChoice.RADEON)
        assertEquals(listOf("a.one"), radeon.optIn)
        assertEquals(listOf("b.two", "x.y"), radeon.optOut)
        assertEquals(AppChoice.RADEON, radeon.choice("x.y"))
        val auto = AppDriver.choose(radeon, "x.y", AppChoice.AUTOMATIC)
        assertEquals(listOf("a.one"), auto.optIn)
        assertEquals(listOf("b.two"), auto.optOut)
        assertEquals(AppChoice.AUTOMATIC, auto.choice("x.y"))
        // The other apps' choices are untouched throughout.
        assertEquals(AppChoice.NVIDIA, auto.choice("a.one"))
        assertEquals(AppChoice.RADEON, auto.choice("b.two"))
    }

    @Test
    fun anOfferedDriverThatIsNotInstalled() {
        // OpenBook's AOSP image: init offers org.openbook.nvk once NVIDIA's driver binds, and no such package is
        // installed. GraphicsEnvironment picks it for a game or a chosen app, cannot find it and keeps the system
        // driver; apps it never picks keep their own reason.
        val s = DriverSettings(allowlist = listOf("com.example.game"), optIn = listOf("com.example.mail"))
        assertEquals(Decision(Gpu.RADEON, Reason.NOT_INSTALLED), AppDriver.decide(game, s, offered = true, installed = false))
        assertEquals(Decision(Gpu.RADEON, Reason.NOT_INSTALLED), AppDriver.decide(mail, s, offered = true, installed = false))
        assertEquals(Decision(Gpu.RADEON, Reason.NOT_INSTALLED),
                     AppDriver.decide(mail, DriverSettings(allApps = AppDriver.ALL_APPS_PRODUCTION), offered = true, installed = false))
        assertEquals(Reason.NOT_ALLOWED, AppDriver.decide(app("com.example.other"), s, offered = true, installed = false).reason)
        assertEquals(Reason.NOT_OFFERED, AppDriver.decide(game, s, offered = false, installed = false).reason)
        assertEquals(Decision(Gpu.NVIDIA, Reason.GAME), AppDriver.decide(game, s, offered = true, installed = true))
    }

    @Test
    fun packageNames() {
        for (ok in listOf("com.example.game", "a.b", "org.openbook.nvk", "com.a_b.C9")) assertTrue(ok, AppDriver.validPackage(ok))
        for (bad in listOf("", "single", "a,b.c", "a.b,c.d", "*", ".a.b", "a..b", "1a.b", "a.b ")) {
            assertFalse(bad, AppDriver.validPackage(bad))
        }
    }
}

/** Settings.Global and the installed apps, as Android keeps them. */
private class FakeDriverBackend(var installed: List<AppInfo>, val global: MutableMap<String, String> = HashMap()) : DriverBackend {
    var refuse = false
    var offered: String? = "org.openbook.nvk"
    /** System apps that are driver packages: the Ruby image's OpenBook NVK package unless a test removes it. */
    val drivers = mutableSetOf("org.openbook.nvk")
    val writes = mutableListOf<String>()

    override fun apps() = installed
    override fun getString(name: String) = global[name]
    override fun getInt(name: String, default: Int) = global[name]?.toIntOrNull() ?: default
    override fun putString(name: String, value: String): Boolean {
        if (refuse) return false
        writes += name
        global[name] = value
        return true
    }
    override fun putInt(name: String, value: Int) = putString(name, value.toString())
    override fun offeredDriver() = offered
    override fun driverInstalled(pkg: String) = pkg in drivers
}

private class FakePrefs(override var gamesOn: Boolean = true, override var allAppsReplaced: Boolean = false) : RulePrefs

class GamesRuleTest {
    private val apps = listOf(app("com.android.chrome", label = "Chrome"), app("com.google.android.gm", label = "Gmail"),
                              app("com.zillow.android.zillowmap", label = "Zillow"),
                              app("com.example.vkgame", game = true, label = "Vulkan Game"),
                              app("com.example.glgame", game = true, label = "GL Game"),
                              app("com.google.android.youtube", game = false, eligible = false, label = "YouTube"))

    @Test
    fun theOwnersLaptopMovesFromAllAppsToGames() {
        // As on the G14 today: "all apps" on, Chrome opted out once in a test, Zillow chosen for the NVIDIA GPU.
        val b = FakeDriverBackend(apps, mutableMapOf(AppDriver.ALL_APPS to "1", AppDriver.OPT_OUT to "com.android.chrome",
                                                     AppDriver.OPT_IN to "com.zillow.android.zillowmap"))
        val prefs = FakePrefs()
        val r = GamesRule(b, prefs).sync()
        assertTrue(r.replacedAllApps)
        assertTrue(r.changed)
        assertFalse(r.refused)
        assertEquals(2, r.games)
        assertEquals("0", b.global[AppDriver.ALL_APPS])
        assertEquals("com.example.glgame,com.example.vkgame", b.global[AppDriver.ALLOWLIST])
        assertTrue(prefs.allAppsReplaced)
        val s = GamesRule(b, prefs).settings()
        val gpu = apps.associate { it.label to AppDriver.decide(it, s, offered = true).gpu }
        assertEquals(mapOf("Chrome" to Gpu.RADEON, "Gmail" to Gpu.RADEON, "Zillow" to Gpu.NVIDIA, "Vulkan Game" to Gpu.NVIDIA,
                           "GL Game" to Gpu.NVIDIA, "YouTube" to Gpu.RADEON), gpu)
        // The owner's own lists are untouched.
        assertEquals("com.android.chrome", b.global[AppDriver.OPT_OUT])
        assertEquals("com.zillow.android.zillowmap", b.global[AppDriver.OPT_IN])
    }

    @Test
    fun allAppsIsReplacedOnceOnly() {
        val b = FakeDriverBackend(apps, mutableMapOf(AppDriver.ALL_APPS to "1"))
        val prefs = FakePrefs()
        assertTrue(GamesRule(b, prefs).sync().replacedAllApps)
        // The owner turns "all apps" on again in Developer options: the rule leaves it.
        b.global[AppDriver.ALL_APPS] = "1"
        val again = GamesRule(b, prefs).sync()
        assertFalse(again.replacedAllApps)
        assertEquals("1", b.global[AppDriver.ALL_APPS])
        // An image where "all apps" was never on: nothing to replace, and later choices stay too.
        val fresh = FakeDriverBackend(apps)
        val p2 = FakePrefs()
        assertFalse(GamesRule(fresh, p2).sync().replacedAllApps)
        assertTrue(p2.allAppsReplaced)
        assertNull(fresh.global[AppDriver.ALL_APPS])
        fresh.global[AppDriver.ALL_APPS] = "1"
        GamesRule(fresh, p2).sync()
        assertEquals("1", fresh.global[AppDriver.ALL_APPS])
        // "Off" (3) is the owner's choice too and is never replaced.
        val off = FakeDriverBackend(apps, mutableMapOf(AppDriver.ALL_APPS to "3"))
        GamesRule(off, FakePrefs()).sync()
        assertEquals("3", off.global[AppDriver.ALL_APPS])
    }

    @Test
    fun concurrentSyncsReplaceAllAppsOnce() {
        // As at boot: the boot receiver and the job's first run, each with its own GamesRule, at the same moment.
        repeat(50) {
            val b = FakeDriverBackend(apps, java.util.concurrent.ConcurrentHashMap(mapOf(AppDriver.ALL_APPS to "1")))
            val prefs = FakePrefs()
            val start = java.util.concurrent.CountDownLatch(1)
            val results = java.util.Collections.synchronizedList(mutableListOf<org.openbook.graphics.data.SyncResult>())
            val threads = List(4) { Thread { start.await(); results += GamesRule(b, prefs).sync() } }
            threads.forEach { it.start() }
            start.countDown()
            threads.forEach { it.join() }
            assertEquals(1, results.count { it.replacedAllApps })
            assertEquals(1, results.count { it.changed })
            assertEquals("0", b.global[AppDriver.ALL_APPS])
        }
    }

    @Test
    fun writesOnlyWhenTheGamesChange() {
        val b = FakeDriverBackend(apps)
        val rule = GamesRule(b, FakePrefs())
        assertTrue(rule.sync().changed)
        b.writes.clear()
        val same = rule.sync()
        assertFalse(same.changed)
        assertEquals(emptyList<String>(), b.writes)
        // A new game is installed; the next sync adds it. One is removed; the next sync drops it.
        b.installed = apps + app("com.example.newgame", game = true)
        assertTrue(rule.sync().changed)
        assertEquals("com.example.glgame,com.example.newgame,com.example.vkgame", b.global[AppDriver.ALLOWLIST])
        b.installed = apps.filter { it.pkg != "com.example.glgame" }
        rule.sync()
        assertEquals("com.example.vkgame", b.global[AppDriver.ALLOWLIST])
        // A hand-set "*" (every app) is replaced by the games too.
        b.global[AppDriver.ALLOWLIST] = "*"
        assertTrue(rule.sync().changed)
        assertEquals("com.example.vkgame", b.global[AppDriver.ALLOWLIST])
    }

    @Test
    fun theGamesRuleSwitchedOff() {
        val b = FakeDriverBackend(apps, mutableMapOf(AppDriver.OPT_IN to "com.example.vkgame"))
        val prefs = FakePrefs()
        val rule = GamesRule(b, prefs)
        rule.sync()
        val off = rule.setGamesOn(false)
        assertFalse(prefs.gamesOn)
        assertEquals(0, off.games)
        assertEquals("", b.global[AppDriver.ALLOWLIST])
        val s = rule.settings()
        assertEquals(Gpu.RADEON, AppDriver.decide(apps[4], s, offered = true).gpu)   // GL Game
        assertEquals(Gpu.NVIDIA, AppDriver.decide(apps[3], s, offered = true).gpu)   // Vulkan Game, chosen
        assertEquals(2, rule.setGamesOn(true).games)
    }

    @Test
    fun refusedWritesAreReportedAndRetried() {
        val b = FakeDriverBackend(apps, mutableMapOf(AppDriver.ALL_APPS to "1"))
        b.refuse = true
        val prefs = FakePrefs()
        val r = GamesRule(b, prefs).sync()
        assertTrue(r.refused)
        assertFalse(r.changed)
        assertFalse(r.replacedAllApps)
        assertFalse(prefs.allAppsReplaced)   // tried again next time
        assertFalse(GamesRule(b, prefs).choose("com.android.chrome", AppChoice.NVIDIA))
        b.refuse = false
        val ok = GamesRule(b, prefs).sync()
        assertTrue(ok.replacedAllApps)
        assertFalse(ok.refused)
    }

    @Test
    fun choicesThroughTheRule() {
        val b = FakeDriverBackend(apps, mutableMapOf(AppDriver.OPT_OUT to "com.android.chrome"))
        val rule = GamesRule(b, FakePrefs())
        assertTrue(rule.choose("com.google.android.gm", AppChoice.NVIDIA))
        assertTrue(rule.choose("com.example.vkgame", AppChoice.RADEON))
        assertEquals("com.google.android.gm", b.global[AppDriver.OPT_IN])
        assertEquals("com.android.chrome,com.example.vkgame", b.global[AppDriver.OPT_OUT])
        assertTrue(rule.choose("com.example.vkgame", AppChoice.AUTOMATIC))
        assertEquals("com.android.chrome", b.global[AppDriver.OPT_OUT])
        assertFalse(rule.choose("bad,name", AppChoice.NVIDIA))
        assertFalse(rule.choose("", AppChoice.NVIDIA))
        assertTrue(rule.useGamesRule())
        assertEquals("0", b.global[AppDriver.ALL_APPS])
    }

    @Test
    fun noAppDriverMeansNoWritesAndNoChoices() {
        // OpenBook's AOSP image, in Hybrid with NVIDIA's driver bound: org.openbook.nvk offered, not installed.
        // Even "all apps" from an earlier image stays as it is: no list Android keeps changes anything here.
        val b = FakeDriverBackend(apps, mutableMapOf(AppDriver.ALL_APPS to "1"))
        b.drivers.clear()
        val prefs = FakePrefs()
        val rule = GamesRule(b, prefs)
        assertFalse(rule.hasAppDriver())
        assertEquals(SyncResult.NO_DRIVER, rule.sync())
        assertEquals(SyncResult.NO_DRIVER, rule.setGamesOn(false))
        assertTrue(prefs.gamesOn)
        assertFalse(prefs.allAppsReplaced)
        assertFalse(rule.choose("com.example.vkgame", AppChoice.NVIDIA))
        assertFalse(rule.choose("com.android.chrome", AppChoice.RADEON))
        assertFalse(rule.useGamesRule())
        assertEquals(emptyList<String>(), b.writes)
        assertEquals(mapOf(AppDriver.ALL_APPS to "1"), b.global)
        // The screen gets no apps to choose for, and says why (appDriver = false).
        val st = rule.state()
        assertFalse(st.appDriver)
        assertTrue(st.offered)
        assertEquals(emptyList<AppInfo>(), st.apps)
        assertEquals(emptyList<String>(), b.writes)
        // Eco or the driver not loaded yet: nothing offered, the package init would offer is looked up, still absent.
        b.offered = null
        assertEquals("org.openbook.nvk", rule.driverPackage())
        assertFalse(rule.state().offered)
        assertEquals(SyncResult.NO_DRIVER, rule.sync())
        assertEquals(emptyList<String>(), b.writes)
    }

    @Test
    fun theNvidiaForAppsSwitch() {
        // ANAL-327: "NVIDIA GPU for apps" off keeps every app on the Radeon and the owner's choices as they are; on
        // gives them back. It is updatable_driver_all_apps 3 or 0, as Developer options writes it.
        val b = FakeDriverBackend(apps, mutableMapOf(AppDriver.OPT_IN to "com.zillow.android.zillowmap"))
        val rule = GamesRule(b, FakePrefs())
        rule.sync()
        assertTrue(rule.appsOn())
        assertTrue(rule.state().appsOn)
        val zillow = apps.first { it.pkg == "com.zillow.android.zillowmap" }
        val game = apps.first { it.pkg == "com.example.vkgame" }
        assertEquals(Decision(Gpu.NVIDIA, Reason.CHOSEN_NVIDIA), rule.state().decision(zillow))
        assertEquals(Decision(Gpu.NVIDIA, Reason.GAME), rule.state().decision(game))

        assertTrue(rule.setAppsOn(false))
        assertEquals("3", b.global[AppDriver.ALL_APPS])
        assertFalse(rule.appsOn())
        val off = rule.state()
        assertFalse(off.appsOn)
        assertEquals(Decision(Gpu.RADEON, Reason.ALL_APPS_OFF), off.decision(zillow))
        assertEquals(Decision(Gpu.RADEON, Reason.ALL_APPS_OFF), off.decision(game))
        // The choices and the games stay, for when it is on again; a sync while off changes nothing else.
        assertEquals("com.zillow.android.zillowmap", b.global[AppDriver.OPT_IN])
        assertTrue(AppDriver.list(b.global[AppDriver.ALLOWLIST]).contains("com.example.vkgame"))
        assertEquals("3", b.global[AppDriver.ALL_APPS])

        assertTrue(rule.setAppsOn(true))
        assertEquals("0", b.global[AppDriver.ALL_APPS])
        assertEquals(Decision(Gpu.NVIDIA, Reason.CHOSEN_NVIDIA), rule.state().decision(zillow))
        // Already on: no write.
        b.writes.clear()
        assertTrue(rule.setAppsOn(true))
        assertEquals(emptyList<String>(), b.writes)
    }

    @Test
    fun theSwitchWithDeveloperOptionsSettings() {
        // "Every app" (1) from Developer options counts as on and stays until the owner turns it off; a prerelease
        // driver (2), which OpenBook does not have, counts as off and the switch turns it into the rule (0).
        val b = FakeDriverBackend(apps, mutableMapOf(AppDriver.ALL_APPS to "1"))
        val rule = GamesRule(b, FakePrefs(allAppsReplaced = true))
        assertTrue(rule.appsOn())
        assertTrue(rule.setAppsOn(true))
        assertEquals("1", b.global[AppDriver.ALL_APPS])
        assertTrue(rule.setAppsOn(false))
        assertEquals("3", b.global[AppDriver.ALL_APPS])
        b.global[AppDriver.ALL_APPS] = "2"
        assertFalse(rule.appsOn())
        assertTrue(rule.setAppsOn(true))
        assertEquals("0", b.global[AppDriver.ALL_APPS])
    }

    @Test
    fun theSwitchNeedsAnAppDriverAndAWrite() {
        val b = FakeDriverBackend(apps)
        b.drivers.clear()
        val rule = GamesRule(b, FakePrefs())
        assertFalse(rule.setAppsOn(false))
        assertEquals(emptyList<String>(), b.writes)
        b.drivers += "org.openbook.nvk"
        b.refuse = true
        assertFalse(rule.setAppsOn(false))
        assertNull(b.global[AppDriver.ALL_APPS])
    }

    @Test
    fun theDriverPackageIsTheOfferedOne() {
        val b = FakeDriverBackend(apps)
        val rule = GamesRule(b, FakePrefs())
        // The Ruby image in Eco: nothing offered, but the NVK package is in the image, so the rule keeps the list.
        b.offered = null
        assertEquals("org.openbook.nvk", rule.driverPackage())
        assertTrue(rule.hasAppDriver())
        assertTrue(rule.sync().changed)
        assertTrue(rule.state().appDriver)
        // Another driver package offered: that one has to be installed.
        b.offered = "com.example.driver"
        assertFalse(rule.hasAppDriver())
        assertEquals(SyncResult.NO_DRIVER, rule.sync())
        b.drivers += "com.example.driver"
        assertTrue(rule.hasAppDriver())
        b.offered = ""
        assertEquals("org.openbook.nvk", rule.driverPackage())
    }

    @Test
    fun theAppsScreenList() {
        val more = apps + listOf(app("com.example.widget", launchable = false), app("com.example.service", launchable = false),
                                 app("com.example.hidden.game", game = true, launchable = false))
        val b = FakeDriverBackend(more, mutableMapOf(AppDriver.OPT_IN to "com.example.service"))
        val st = GamesRule(b, FakePrefs()).state()
        // Games first, then by label; built-in apps and apps without an entry or a choice are left out.
        assertEquals(listOf("com.example.hidden.game", "GL Game", "Vulkan Game", "Chrome", "com.example.service", "Gmail", "Zillow"),
                     st.apps.map { it.label })
        assertTrue(st.offered)
        assertTrue(st.gamesOn)
        assertEquals(Reason.GAME, st.decision(st.apps[0]).reason)
        assertEquals(Reason.CHOSEN_NVIDIA, st.decision(st.apps.first { it.pkg == "com.example.service" }).reason)
        // state() synced first; the read-only state (a non-owner's) does not.
        assertEquals("com.example.glgame,com.example.hidden.game,com.example.vkgame", b.global[AppDriver.ALLOWLIST])
        val ro = FakeDriverBackend(apps)
        ro.offered = null
        val s2 = GamesRule(ro, FakePrefs()).state(sync = false)
        assertFalse(s2.offered)
        assertNull(ro.global[AppDriver.ALLOWLIST])
    }
}
