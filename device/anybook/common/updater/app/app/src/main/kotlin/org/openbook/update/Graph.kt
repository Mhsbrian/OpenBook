// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import android.annotation.SuppressLint
import android.content.Context
import android.os.UserManager
import org.openbook.update.data.History
import org.openbook.update.data.Settings
import org.openbook.update.engine.EngineRunner
import org.openbook.update.notify.Notifier
import org.openbook.update.system.UpdateEngineClient
import java.io.File

/** The app's single instances. Holds only the application context, which lives as long as the process. */
@SuppressLint("StaticFieldLeak")
object Graph {
    private lateinit var app: Context

    fun init(context: Context) {
        app = context.applicationContext
    }

    val settings by lazy { Settings(app) }
    val history by lazy { History(File(app.filesDir, "history.json")) }
    val notifier by lazy { Notifier(app) }
    val updateEngine by lazy { UpdateEngineClient() }

    /** Instrumented tests point the engine at a synthetic listing; release builds always use Google's. */
    @Volatile
    var listingForTests: String? = null
        set(value) {
            check(BuildConfig.DEBUG) { "Only debug builds take another release listing" }
            field = value
        }

    /** Instrumented tests on a small emulator: a smaller space reserve than the engine's 20 GiB. */
    @Volatile
    var engineEnvironmentForTests: Map<String, String> = emptyMap()
        set(value) {
            check(BuildConfig.DEBUG) { "Only debug builds change the engine's environment" }
            field = value
        }

    fun engine() = EngineRunner(app, listing = listingForTests, environment = engineEnvironmentForTests)

    /**
     * Whether this user runs the updater: the laptop's admin (the owner), never a guest or other user, and
     * never Googlebook's headless system user (user 0), which sysconfig keeps the app out of anyway. Only an
     * admin approves system updates, and only an admin's copy may restart the laptop.
     */
    fun runsHere(): Boolean {
        val users = app.getSystemService(UserManager::class.java)
        return users.isAdminUser && !(UserManager.isHeadlessSystemUserMode() && users.isSystemUser)
    }
}
