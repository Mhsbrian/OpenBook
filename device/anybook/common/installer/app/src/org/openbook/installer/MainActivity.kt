// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import android.app.KeyguardManager
import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.ViewModelProvider
import org.openbook.installer.ui.InstallerApp

/**
 * The install wizard (ANAL-189 design, docs/installer.md §4.1) in a desktop window. The [InstallerViewModel] keeps
 * the daemon connection and an install's progress across configuration changes; if the activity is recreated from
 * scratch, `hello` reports the running job and the view model re-attaches to it.
 */
class MainActivity : ComponentActivity() {
    private lateinit var vm: InstallerViewModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        vm = ViewModelProvider(this)[InstallerViewModel::class.java]
        if (LiveSystem.isLiveSession()) {
            // The live session has no credential: get the insecure keyguard out of the way.
            getSystemService(KeyguardManager::class.java)?.requestDismissKeyguard(this, null)
        }
        setContent {
            InstallerApp(
                vm = vm,
                onClose = { finish() },
                onRestart = { LiveSystem.reboot(applicationContext) },
            )
        }
    }

    /** Escape is Back (the wizard's BackHandler ignores it while installing); not on the first screen. */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_ESCAPE && ::vm.isInitialized) {
            if (event.action == KeyEvent.ACTION_UP && !event.isCanceled && vm.step != WizardStep.WELCOME) {
                onBackPressedDispatcher.onBackPressed()
            }
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    companion object {
        const val EXTRA_FROM_BOOT = "org.openbook.installer.FROM_BOOT"
    }
}
