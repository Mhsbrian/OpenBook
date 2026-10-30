// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.ui

import android.app.Application
import android.content.Context
import android.os.PowerManager
import android.os.UserManager
import android.util.Log
import androidx.annotation.StringRes
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.openbook.graphics.R
import org.openbook.graphics.data.GfxBackend
import org.openbook.graphics.data.GfxState
import org.openbook.graphics.data.Mode
import org.openbook.graphics.data.Outcome
import org.openbook.graphics.data.Rules
import org.openbook.graphics.data.Switcher
import org.openbook.graphics.data.SystemBackend

data class Message(@StringRes val text: Int, val error: Boolean = false)

data class UiState(
    val loading: Boolean = true,
    /** Null: this image has no graphics switcher. */
    val gfx: GfxState? = null,
    val owner: Boolean = false,
    /** A request is on its way. */
    val busy: Boolean = false,
    val message: Message? = null,
    /** "Switch to …?" is open for this mode. */
    val confirm: Mode? = null,
    /** "Restart now to finish?" is open. */
    val restartPrompt: Boolean = false,
    /** The keep dialog's deadline (System.currentTimeMillis), once it was shown. */
    val keepDeadline: Long? = null,
)

class GraphicsViewModel(app: Application) : AndroidViewModel(app) {
    private val backend: GfxBackend = SystemBackend
    private val switcher = Switcher(backend)
    private val _state = MutableStateFlow(UiState(owner = isOwner(app)))
    val state: StateFlow<UiState> = _state.asStateFlow()
    private var poller: Job? = null

    /** Reads the state every second and a half while the screen is visible. */
    fun start() {
        if (poller?.isActive == true) return
        poller = viewModelScope.launch {
            while (isActive) {
                val gfx = withContext(Dispatchers.IO) { backend.read() }
                _state.update { it.copy(loading = false, gfx = gfx) }
                if (gfx != null && Rules.asksToKeep(gfx) && _state.value.keepDeadline == null) shownKeepDialog()
                delay(1500)
            }
        }
    }

    fun stop() {
        poller?.cancel()
    }

    fun ask(mode: Mode) = _state.update { it.copy(confirm = mode, message = null) }

    fun dismiss() = _state.update { it.copy(confirm = null, restartPrompt = false) }

    fun dismissMessage() = _state.update { it.copy(message = null) }

    fun switchTo(mode: Mode) = act(Switcher.Verb.SWITCH, mode)

    fun lock(on: Boolean) = act(if (on) Switcher.Verb.LOCK else Switcher.Verb.UNLOCK, null)

    fun keep() = act(Switcher.Verb.KEEP, null)

    fun goBack() = act(Switcher.Verb.REVERT, null)

    fun restart() {
        _state.update { it.copy(restartPrompt = false) }
        val pm = getApplication<Application>().getSystemService(PowerManager::class.java)
        runCatching { pm.reboot("openbook-gfx") }.onFailure {
            Log.w(TAG, "restart refused", it)
            _state.update { s -> s.copy(message = Message(R.string.message_restart_refused, error = true)) }
        }
    }

    /** The owner sees "Keep Ultimate graphics?": the switcher's 30 seconds start now. */
    private fun shownKeepDialog() {
        _state.update { it.copy(keepDeadline = System.currentTimeMillis() + KEEP_MILLIS) }
        viewModelScope.launch(Dispatchers.IO) { switcher.request(Switcher.Verb.SHOWN) }
    }

    private fun act(verb: Switcher.Verb, mode: Mode?) {
        _state.update { it.copy(busy = true, confirm = null, message = null) }
        viewModelScope.launch {
            val outcome = withContext(Dispatchers.IO) { switcher.request(verb, mode) }
            Log.i(TAG, "${verb.wire} ${mode?.wire ?: ""}: $outcome")
            val gfx = withContext(Dispatchers.IO) { backend.read() }
            _state.update {
                it.copy(busy = false, gfx = gfx ?: it.gfx, message = messageFor(verb, outcome),
                        restartPrompt = outcome == Outcome.RestartNeeded && verb == Switcher.Verb.SWITCH,
                        keepDeadline = if (verb == Switcher.Verb.KEEP) null else it.keepDeadline)
            }
        }
    }

    companion object {
        private const val TAG = "OpenBookGraphics"
        const val KEEP_MILLIS = 30_000L

        fun isOwner(context: Context) = context.getSystemService(UserManager::class.java).isAdminUser

        fun messageFor(verb: Switcher.Verb, o: Outcome): Message? = when (o) {
            Outcome.Done -> when (verb) {
                Switcher.Verb.SWITCH -> Message(R.string.message_switched)
                Switcher.Verb.KEEP -> Message(R.string.message_kept)
                else -> null
            }
            Outcome.RestartNeeded -> if (verb == Switcher.Verb.REVERT) Message(R.string.message_going_back)
                                     else Message(R.string.message_restart_to_finish)
            Outcome.Already -> null
            Outcome.WritesOff -> Message(R.string.message_writes_off, error = true)
            is Outcome.Refused -> Message(when (o.code) {
                "busy" -> R.string.message_refused_busy
                "locked" -> R.string.message_refused_locked
                "unsupported" -> R.string.message_unsupported
                "unverified", "not-offered" -> R.string.message_ultimate_not_available
                "invalid-firmware" -> R.string.message_refused_invalid
                else -> R.string.message_refused
            }, error = true)
            is Outcome.Failed -> Message(if (o.code == "firmware") R.string.message_failed_firmware
                                         else R.string.message_failed, error = true)
            Outcome.NoAnswer -> Message(R.string.message_no_answer, error = true)
        }
    }
}
