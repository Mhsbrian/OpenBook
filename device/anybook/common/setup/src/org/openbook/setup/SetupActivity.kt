// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.setup

import android.content.Intent
import android.os.Bundle
import android.os.UserManager
import android.util.Log
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import java.util.Locale
import org.openbook.installer.ui.OpenBookTheme
import org.openbook.setup.ui.SetupApp

/**
 * OpenBook setup (docs/setup.md): the home screen of a new OpenBook system until the user finishes or skips it. It
 * replaces AOSP's Provision and ends the same way: device_provisioned and user_setup_complete are set to 1 and this
 * activity disables itself, so the launcher becomes home.
 *
 * It steps aside at once, without showing anything, on the live stick (the install wizard is the first screen there),
 * on boots with androidboot.openbook.setup=skip (unattended runs) and with ro.setupwizard.mode=DISABLED (Cuttlefish's
 * default).
 */
class SetupActivity : ComponentActivity() {
    private lateinit var model: SetupModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val skip = SetupSystem.skipReason(this)
        if (skip != null) {
            finishSetup("step aside: $skip")
            return
        }
        // The installer's language choice (androidboot.openbook.locale) is the starting point.
        val preset = android.os.SystemProperties.get(SetupSystem.PROP_LOCALE, "")
        if (savedInstanceState == null && preset.isNotEmpty() && Locale.getDefault().toLanguageTag() != preset) {
            SetupSystem.applyLocale(Locale.forLanguageTag(preset))
        }
        enableEdgeToEdge()
        // The model outlives a relaunch: the framework restarts the activity once right after the first boot (an
        // asset change), and the user's progress must survive any later one too.
        val holder = ViewModelProvider(this, object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = Holder(SetupModel(applicationContext)) as T
        })[Holder::class.java]
        model = holder.model
        if (savedInstanceState == null) Log.i(SetupSystem.TAG, "setup started (locale ${Locale.getDefault().toLanguageTag()})")
        setContent {
            OpenBookTheme {
                SetupApp(
                    model = model,
                    onSkipAll = { finishSetup("skipped by the user on ${model.page.name.lowercase()}") },
                    onDone = { finishSetup("finished") },
                )
            }
        }
    }

    /** Escape is Back, except on the first page. */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_ESCAPE && ::model.isInitialized) {
            if (event.action == KeyEvent.ACTION_UP && !event.isCanceled && model.page != Page.WELCOME) model.back()
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    class Holder(val model: SetupModel) : ViewModel()

    /**
     * What Provision does, then this activity leaves the home list for good and the launcher takes over. While the
     * user is still locked (a live stick's first boot steps aside that early) the only other home is Settings'
     * FallbackHome, which can't be started from here: then finishing is enough, the system starts it, and the
     * launcher once the user is unlocked. Provision never starts home itself.
     */
    private fun finishSetup(why: String) {
        val ok = SetupSystem.markComplete(this)
        Log.i(SetupSystem.TAG, "setup complete ($why); provisioned=$ok")
        SetupSystem.disable(this, SetupActivity::class.java)
        if (getSystemService(UserManager::class.java)?.isUserUnlocked != false) {
            try {
                startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            } catch (e: RuntimeException) {
                Log.w(SetupSystem.TAG, "could not start home; the system will", e)
            }
        }
        finish()
    }
}
