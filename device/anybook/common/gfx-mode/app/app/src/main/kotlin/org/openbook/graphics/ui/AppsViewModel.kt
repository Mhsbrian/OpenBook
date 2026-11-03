// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.ui

import android.app.Application
import android.graphics.drawable.Drawable
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.core.graphics.drawable.toBitmap
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.openbook.graphics.GamesJob
import org.openbook.graphics.R
import org.openbook.graphics.data.AppChoice
import org.openbook.graphics.data.AppsState
import org.openbook.graphics.data.SystemDriverBackend

data class AppsUi(
    val loading: Boolean = true,
    val state: AppsState? = null,
    val owner: Boolean = false,
    val busy: Boolean = false,
    val message: Message? = null,
    val icons: Map<String, ImageBitmap> = emptyMap(),
)

class AppsViewModel(app: Application) : AndroidViewModel(app) {
    private val rule = GamesJob.rule(app)
    private val _ui = MutableStateFlow(AppsUi(owner = SystemDriverBackend.runsHere(app)))
    val ui: StateFlow<AppsUi> = _ui.asStateFlow()

    /** Syncs the rule (a game installed since the last sync is listed at once) and reads every app. */
    fun refresh() {
        viewModelScope.launch {
            val owner = _ui.value.owner
            val s = withContext(Dispatchers.IO) { rule.state(sync = owner) }
            _ui.update { it.copy(loading = false, state = s) }
            val missing = s.apps.map { it.pkg }.filter { it !in _ui.value.icons }
            if (missing.isNotEmpty()) {
                val icons = withContext(Dispatchers.IO) { missing.mapNotNull { p -> icon(p)?.let { p to it } }.toMap() }
                _ui.update { it.copy(icons = it.icons + icons) }
            }
        }
    }

    fun setGamesOn(on: Boolean) = act { rule.setGamesOn(on).refused.not() }

    fun choose(pkg: String, choice: AppChoice) = act { rule.choose(pkg, choice) }

    fun useGamesRule() = act { rule.useGamesRule() }

    fun setAppsOn(on: Boolean) = act { rule.setAppsOn(on) }

    fun dismissMessage() = _ui.update { it.copy(message = null) }

    private fun act(write: () -> Boolean) {
        if (!_ui.value.owner) return
        _ui.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            val ok = withContext(Dispatchers.IO) { write() }
            val s = withContext(Dispatchers.IO) { rule.state() }
            _ui.update {
                it.copy(busy = false, state = s,
                        message = if (ok) Message(R.string.apps_saved) else Message(R.string.apps_refused, error = true))
            }
        }
    }

    private fun icon(pkg: String): ImageBitmap? = runCatching {
        val pm = getApplication<Application>().packageManager
        val d: Drawable = pm.getApplicationIcon(pkg)
        d.toBitmap(ICON_PX, ICON_PX).asImageBitmap()
    }.getOrNull()

    companion object {
        private const val ICON_PX = 96
    }
}
