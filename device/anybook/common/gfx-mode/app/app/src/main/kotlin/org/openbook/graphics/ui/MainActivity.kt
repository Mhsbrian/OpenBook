// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle

/** OpenBook Graphics: Eco, Hybrid and Ultimate (docs/nvidia-graphics-modes.md §7). */
class MainActivity : ComponentActivity() {
    private val vm: GraphicsViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            GraphicsTheme {
                val ui by vm.state.collectAsStateWithLifecycle()
                GraphicsScreen(ui, onAsk = vm::ask, onSwitch = vm::switchTo, onLock = vm::lock, onRestart = vm::restart,
                               onDismiss = vm::dismiss, onDismissMessage = vm::dismissMessage, onKeep = vm::keep,
                               onGoBack = vm::goBack)
            }
        }
    }

    override fun onStart() {
        super.onStart()
        vm.start()
    }

    override fun onStop() {
        vm.stop()
        super.onStop()
    }
}
