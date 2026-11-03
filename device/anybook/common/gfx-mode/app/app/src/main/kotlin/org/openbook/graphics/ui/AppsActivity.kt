// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle

/** Apps on the NVIDIA GPU: the games rule and each app's choice (docs/nvidia-offload-ruby.md). */
class AppsActivity : ComponentActivity() {
    private val vm: AppsViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            GraphicsTheme {
                val ui by vm.ui.collectAsStateWithLifecycle()
                AppsScreen(ui, onBack = ::finish, onAppsOn = vm::setAppsOn, onGamesOn = vm::setGamesOn, onChoose = vm::choose,
                           onUseGamesRule = vm::useGamesRule, onDismissMessage = vm::dismissMessage)
            }
        }
    }

    override fun onStart() {
        super.onStart()
        vm.refresh()
    }
}
