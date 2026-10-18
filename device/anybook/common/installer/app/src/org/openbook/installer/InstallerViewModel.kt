// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import android.app.Application
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.io.IOException
import java.util.Locale
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.openbook.installer.daemon.Addon
import org.openbook.installer.daemon.DaemonClient
import org.openbook.installer.daemon.DaemonException
import org.openbook.installer.daemon.Disk
import org.openbook.installer.daemon.HwInfo
import org.openbook.installer.daemon.Hello
import org.openbook.installer.daemon.INSTALL_STEPS
import org.openbook.installer.daemon.InstallEvent
import org.openbook.installer.daemon.InstallResult
import org.openbook.installer.daemon.JobStatus
import org.openbook.installer.daemon.Parse
import org.openbook.installer.daemon.Plan
import org.openbook.installer.daemon.text

enum class WizardStep { WELCOME, HARDWARE, CHOOSE, DISK, CONFIRM, INSTALL, DONE;

    val number: Int get() = ordinal + 1
}

/** A daemon call's state. [Failed.code] is the protocol's error code, or [UNREACHABLE]. */
sealed interface Load<out T> {
    data object Idle : Load<Nothing>
    data object Loading : Load<Nothing>
    data class Ready<T>(val value: T) : Load<T>
    data class Failed(val code: String, val message: String) : Load<Nothing>

    companion object {
        const val UNREACHABLE = "unreachable"
    }
}

val <T> Load<T>.valueOrNull: T? get() = (this as? Load.Ready<T>)?.value

/** Why the install path is not available in this session (the Try path always is). */
enum class InstallBlocker { NONE, CHECKING, UNREACHABLE, NOT_LIVE, NO_SOURCE }

enum class InstallLayout(val id: String) { WHOLE("whole"), ALONGSIDE("alongside") }

data class InstallFailure(
    /** True when the engine refused before writing anything (plan_changed, confirm_mismatch, power, ...). */
    val notStarted: Boolean,
    val step: String?,
    val code: String?,
    val message: String?,
)

/** What the Install and Done screens show; observable Compose state. */
class InstallState {
    val steps = mutableStateMapOf<String, String>()
    var current by mutableStateOf<String?>(null)
    var pct by mutableDoubleStateOf(0.0)
    var etaSeconds by mutableStateOf<Int?>(null)
    var doneBytes by mutableLongStateOf(0L)
    var totalBytes by mutableLongStateOf(0L)
    val log = mutableStateListOf<String>()
    var running by mutableStateOf(false)
    var reconnecting by mutableStateOf(false)
    var result by mutableStateOf<InstallResult?>(null)
    var failure by mutableStateOf<InstallFailure?>(null)
    var showDetails by mutableStateOf(false)
    var layout by mutableStateOf<String?>(null)
    var targetModel by mutableStateOf<String?>(null)

    /** The one system kept next to OpenBook ("Windows"), for the Done screen's boot entry text. */
    var keptSystem by mutableStateOf<String?>(null)
    internal var sawEvent = false

    fun reset() {
        steps.clear()
        INSTALL_STEPS.forEach { steps[it] = "pending" }
        current = null
        pct = 0.0
        etaSeconds = null
        doneBytes = 0L
        totalBytes = 0L
        log.clear()
        result = null
        failure = null
        showDetails = false
        sawEvent = false
    }

    fun restore(job: JobStatus) {
        reset()
        steps.putAll(job.steps)
        current = job.step
        pct = job.pct
    }
}

/** Remembered for the process lifetime: the wizard reopens where it makes sense after "Try" or a closed window. */
private object Session {
    var tried = false
    var installLayout: String? = null
    var installModel: String? = null
    var installKeptSystem: String? = null
}

class InstallerViewModel(app: Application) : AndroidViewModel(app) {
    private val client = DaemonClient()
    private val context get() = getApplication<Application>()

    var step by mutableStateOf(WizardStep.WELCOME)
        private set

    // Daemon state
    var hello by mutableStateOf<Load<Hello>>(Load.Idle)
        private set
    var hw by mutableStateOf<Load<HwInfo>>(Load.Idle)
        private set
    var disks by mutableStateOf<Load<List<Disk>>>(Load.Idle)
        private set

    // 1 Welcome
    var languageTag by mutableStateOf(Languages.closest(Locale.getDefault())?.tag ?: "en-US")
        private set
    var keyboardId by mutableStateOf(Languages.byTag(languageTag)?.keyboard ?: "us")
        private set
    private var keyboardChosen = false
    var a11y by mutableStateOf(AccessibilitySettings.State(largerText = false, highContrast = false, reduceMotion = false))
        private set

    // 2 Hardware
    var reportSaving by mutableStateOf(false)
        private set
    var reportPath by mutableStateOf<String?>(null)
        private set
    var reportError by mutableStateOf<String?>(null)
        private set

    // 3 Try or install
    var chooseInstall by mutableStateOf(true)

    // 4 Disk
    var selectedDisk by mutableStateOf<String?>(null)
        private set
    var layout by mutableStateOf(InstallLayout.WHOLE)
        private set
    /** S7: changing the firmware's boot order on a disk that keeps another OS needs consent. */
    var alongsideSetDefault by mutableStateOf(false)
        private set
    /** App add-ons the user ticked (ANAL-210): off by default; none means the plan is exactly as before add-ons. */
    var selectedAddons by mutableStateOf<Set<String>>(emptySet())
        private set
    var plan by mutableStateOf<Plan?>(null)
        private set
    private var planKey: String? = null
    var planLoading by mutableStateOf(false)
        private set
    var planError by mutableStateOf<String?>(null)
        private set
    var planDialog by mutableStateOf(false)
    private var planJob: Job? = null

    // 5 Confirm
    var typed by mutableStateOf("")
        private set

    // 6 Install, 7 Done
    val install = InstallState()
    private var installJob: Job? = null

    init {
        if (Session.tried) {
            chooseInstall = true
            step = WizardStep.CHOOSE
        }
        viewModelScope.launch {
            a11y = withContext(Dispatchers.IO) { AccessibilitySettings.read(context) }
        }
        loadHello()
    }

    override fun onCleared() {
        client.close()
    }

    // -----------------------------------------------------------------------------------------------------------
    // Navigation
    // -----------------------------------------------------------------------------------------------------------

    val canGoBack: Boolean
        get() = when (step) {
            WizardStep.WELCOME, WizardStep.DONE -> false
            WizardStep.INSTALL -> install.failure != null && !install.running
            else -> true
        }

    fun goTo(target: WizardStep) {
        step = target
        when (target) {
            WizardStep.HARDWARE -> if (hw !is Load.Ready && hw !is Load.Loading) loadHardware()
            WizardStep.DISK -> loadDisks()
            WizardStep.CONFIRM -> {
                // S3: the confirmation is typed again every time the screen is shown.
                typed = ""
                refreshHello()
            }
            else -> {}
        }
    }

    fun back() {
        if (!canGoBack) return
        when (step) {
            WizardStep.HARDWARE -> goTo(WizardStep.WELCOME)
            WizardStep.CHOOSE -> goTo(WizardStep.HARDWARE)
            WizardStep.DISK -> goTo(WizardStep.CHOOSE)
            WizardStep.CONFIRM -> goTo(WizardStep.DISK)
            WizardStep.INSTALL -> {
                val f = install.failure
                if (f?.notStarted == true && f.code != "plan_changed" && plan != null) {
                    goTo(WizardStep.CONFIRM)
                } else {
                    invalidatePlan()
                    goTo(WizardStep.DISK)
                }
            }
            else -> {}
        }
    }

    /** "Try OpenBook": the activity closes; the launcher shortcut brings the wizard back at this step. */
    fun markTried() {
        Session.tried = true
    }

    // -----------------------------------------------------------------------------------------------------------
    // hello
    // -----------------------------------------------------------------------------------------------------------

    val installBlocker: InstallBlocker
        get() = when (val h = hello) {
            Load.Idle, Load.Loading -> InstallBlocker.CHECKING
            is Load.Failed -> InstallBlocker.UNREACHABLE
            is Load.Ready -> when {
                !h.value.live -> InstallBlocker.NOT_LIVE
                !h.value.source.ok -> InstallBlocker.NO_SOURCE
                else -> InstallBlocker.NONE
            }
        }

    fun loadHello() {
        if (hello is Load.Loading) return
        hello = Load.Loading
        viewModelScope.launch {
            hello = call { LocalFacts.withPower(getApplication(), Parse.hello(client.request("hello", timeoutMs = 15_000))) }
            val job = hello.valueOrNull?.job ?: return@launch
            // An install ran in this boot (the window was closed, or the app restarted): show it.
            if (!install.running && install.result == null && install.failure == null) {
                install.restore(job)
                install.layout = Session.installLayout
                install.targetModel = Session.installModel
                install.keptSystem = Session.installKeptSystem
                step = WizardStep.INSTALL
                val result = job.result
                if (job.running || result == null) runStream(null) else finish(result, "attach")
            }
        }
    }

    /** Re-reads `hello` (power state for S8 and the charger chip) without dropping the current answer. */
    private fun refreshHello() {
        if (hello !is Load.Ready || install.running) return
        viewModelScope.launch {
            val fresh = call { LocalFacts.withPower(getApplication(), Parse.hello(client.request("hello", timeoutMs = 15_000))) }
            if (fresh is Load.Ready) hello = fresh
        }
    }

    // -----------------------------------------------------------------------------------------------------------
    // 1 Welcome
    // -----------------------------------------------------------------------------------------------------------

    fun selectLanguage(language: Language) {
        if (language.tag == languageTag) return
        languageTag = language.tag
        if (!keyboardChosen) keyboardId = language.keyboard
        invalidatePlan()
        viewModelScope.launch(Dispatchers.IO) { LiveSystem.applyLocale(language.tag) }
    }

    fun selectKeyboard(id: String) {
        keyboardChosen = true
        keyboardId = id
        invalidatePlan()
    }

    fun setLargerText(on: Boolean) = updateA11y(a11y.copy(largerText = on)) {
        AccessibilitySettings.setLargerText(context, on)
    }

    fun setHighContrast(on: Boolean) = updateA11y(a11y.copy(highContrast = on)) {
        AccessibilitySettings.setHighContrast(context, on)
    }

    fun setReduceMotion(on: Boolean) = updateA11y(a11y.copy(reduceMotion = on)) {
        AccessibilitySettings.setReduceMotion(context, on)
    }

    private fun updateA11y(next: AccessibilitySettings.State, write: () -> Boolean) {
        val previous = a11y
        a11y = next
        viewModelScope.launch {
            if (!withContext(Dispatchers.IO) { write() }) a11y = previous
        }
    }

    // -----------------------------------------------------------------------------------------------------------
    // 2 Hardware
    // -----------------------------------------------------------------------------------------------------------

    fun loadHardware() {
        hw = Load.Loading
        viewModelScope.launch {
            hw = call { LocalFacts.merge(getApplication(), Parse.hwinfo(client.request("hwinfo", timeoutMs = 90_000))) }
            if (hello is Load.Failed && hw is Load.Ready) loadHello()
        }
    }

    fun saveReport() {
        if (reportSaving) return
        reportSaving = true
        reportError = null
        viewModelScope.launch {
            when (val r = call { client.request("save_report").text("path") }) {
                is Load.Ready -> reportPath = r.value
                is Load.Failed -> reportError = r.message
                else -> {}
            }
            reportSaving = false
        }
    }

    // -----------------------------------------------------------------------------------------------------------
    // 4 Disk
    // -----------------------------------------------------------------------------------------------------------

    fun loadDisks() {
        if (disks is Load.Loading) return
        disks = Load.Loading
        viewModelScope.launch {
            val loaded = call { Parse.disks(client.request("disks")) }
            disks = loaded
            val list = loaded.valueOrNull ?: return@launch
            val current = list.firstOrNull { it.byId == selectedDisk }
            if (current == null || !current.selectable) {
                val pick = list.firstOrNull { it.selectable && !it.external } ?: list.firstOrNull { it.selectable }
                if (pick != null) selectDisk(pick) else {
                    selectedDisk = null
                    invalidatePlan()
                }
            } else if (!layoutAllowed(current, layout)) {
                selectDisk(current)
            }
        }
    }

    val selectedDiskInfo: Disk? get() = disks.valueOrNull?.firstOrNull { it.byId == selectedDisk }

    fun selectDisk(disk: Disk) {
        if (!disk.selectable) return
        if (selectedDisk != disk.byId) alongsideSetDefault = false
        selectedDisk = disk.byId
        if (!layoutAllowed(disk, layout)) {
            layout = if (disk.whole.ok) InstallLayout.WHOLE else InstallLayout.ALONGSIDE
        }
        invalidatePlan()
    }

    fun selectLayout(next: InstallLayout) {
        val disk = selectedDiskInfo ?: return
        if (!layoutAllowed(disk, next)) return
        layout = next
        invalidatePlan()
    }

    fun setAlongsideDefault(on: Boolean) {
        alongsideSetDefault = on
        invalidatePlan()
    }

    /** The add-ons this stick carries, as the daemon reports them in `hello`. */
    val availableAddons: List<Addon>
        get() = (hello as? Load.Ready)?.value?.addons?.filter { it.onStick } ?: emptyList()

    fun setAddon(name: String, on: Boolean) {
        selectedAddons = if (on) selectedAddons + name else selectedAddons - name
        invalidatePlan()
    }

    private fun planAddons() = selectedAddons.filter { n -> availableAddons.any { it.name == n } }.sorted()

    private fun layoutAllowed(disk: Disk, l: InstallLayout) =
        if (l == InstallLayout.WHOLE) disk.whole.ok else disk.alongside.ok

    private fun invalidatePlan() {
        planJob?.cancel()
        planJob = null
        planLoading = false
        plan = null
        planKey = null
        planError = null
        typed = ""
    }

    private fun currentPlanKey(): String? {
        val target = selectedDisk ?: return null
        return (listOf(target, layout.id, languageTag, keyboardId, setDefault().toString()) + planAddons()).joinToString("|")
    }

    private fun setDefault() = layout == InstallLayout.WHOLE || alongsideSetDefault

    val canPlan: Boolean
        get() = installBlocker == InstallBlocker.NONE && selectedDiskInfo?.let { layoutAllowed(it, layout) } == true

    /** "View the plan" ([toConfirm] false) or Continue ([toConfirm] true). Both run the read-only `plan`. */
    fun requestPlan(toConfirm: Boolean) {
        val key = currentPlanKey() ?: return
        val existing = plan
        if (existing != null && planKey == key) {
            if (toConfirm) goTo(WizardStep.CONFIRM) else planDialog = true
            return
        }
        val target = selectedDisk ?: return
        if (planLoading) return
        planLoading = true
        planError = null
        val args: JSONObject.() -> Unit = {
            put("target", target)
            put("layout", layout.id)
            put("locale", languageTag)
            put("keyboard", keyboardId)
            put("set_default", setDefault())
            planAddons().takeIf { it.isNotEmpty() }?.let { put("addons", JSONArray(it)) }
        }
        planJob = viewModelScope.launch {
            val result = call { Parse.plan(client.request("plan", timeoutMs = DaemonClient.PLAN_TIMEOUT_MS, args = args)) }
            planLoading = false
            when (result) {
                is Load.Ready -> {
                    plan = result.value
                    planKey = key
                    if (toConfirm) goTo(WizardStep.CONFIRM) else planDialog = true
                }
                is Load.Failed -> {
                    planError = result.message
                    if (result.code == "not_eligible" || result.code == "no_target") loadDisks()
                }
                else -> {}
            }
        }
    }

    // -----------------------------------------------------------------------------------------------------------
    // 5 Confirm
    // -----------------------------------------------------------------------------------------------------------

    fun updateTyped(value: String) {
        typed = value.take(200)
    }

    /** S3: the model name, case-insensitive and ignoring whitespace (the daemon checks the same rule again). */
    val typedMatches: Boolean
        get() {
            val expected = normalizeConfirm(plan?.confirmText ?: return false)
            return expected.isNotEmpty() && normalizeConfirm(typed) == expected
        }

    // -----------------------------------------------------------------------------------------------------------
    // 6 Install
    // -----------------------------------------------------------------------------------------------------------

    fun startInstall() {
        val p = plan ?: return
        if (!typedMatches || install.running) return
        val typedNow = typed
        install.reset()
        install.layout = p.layout
        install.targetModel = p.targetModel
        install.keptSystem = p.keptSystem
        Session.installLayout = p.layout
        Session.installModel = p.targetModel
        Session.installKeptSystem = install.keptSystem
        step = WizardStep.INSTALL
        runStream {
            put("plan_sha256", p.sha256)
            put("target", p.targetById)
            put("typed", typedNow)
            put("power", LocalFacts.powerJson(getApplication()))
        }
    }

    /**
     * Runs `apply` (when [applyArgs] is set) or `attach`, and follows the install to its end. If the connection
     * drops, reconnects and sends `attach` (never `apply` again): the engine keeps installing without a client.
     */
    private fun runStream(applyArgs: (JSONObject.() -> Unit)?) {
        if (installJob?.isActive == true) return
        install.running = true
        installJob = viewModelScope.launch {
            var cmd = if (applyArgs != null) "apply" else "attach"
            var args: JSONObject.() -> Unit = applyArgs ?: {}
            var failures = 0
            try {
                while (true) {
                    var follow = false
                    try {
                        client.stream(cmd, args).collect { event ->
                            failures = 0
                            install.reconnecting = false
                            if (event is InstallEvent.Final && !event.ok && event.code == "busy" && cmd == "apply") {
                                follow = true // an install is already running (another window): follow it
                            } else {
                                onEvent(event, cmd)
                            }
                        }
                        if (!follow) break
                    } catch (e: IOException) {
                        Log.w(TAG, "install stream: ${e.message}")
                        failures++
                        if (failures > RECONNECT_ATTEMPTS) {
                            install.failure = InstallFailure(
                                notStarted = false,
                                step = install.current,
                                code = Load.UNREACHABLE,
                                message = e.message,
                            )
                            break
                        }
                        install.reconnecting = true
                        delay(RECONNECT_DELAY_MS * minOf(failures, 5))
                    }
                    cmd = "attach"
                    args = {}
                }
            } finally {
                install.running = false
                install.reconnecting = false
            }
            install.failure?.let { f ->
                if (!f.notStarted) install.showDetails = true // a failed install shows its log
                fetchLog()
            }
        }
    }

    private fun onEvent(event: InstallEvent, cmd: String) {
        when (event) {
            is InstallEvent.Step -> {
                install.sawEvent = true
                install.steps[event.step] = event.state
                if (event.state == "running") install.current = event.step
            }
            is InstallEvent.Progress -> {
                install.sawEvent = true
                install.current = event.step
                install.pct = event.pct.coerceIn(0.0, 100.0)
                install.etaSeconds = event.etaSeconds
                install.doneBytes = event.done
                install.totalBytes = event.total
            }
            is InstallEvent.Log -> {
                install.log.add(event.line)
                if (install.log.size > MAX_LOG_LINES) install.log.removeRange(0, install.log.size - MAX_LOG_LINES)
            }
            is InstallEvent.Final -> {
                if (event.ok) {
                    val result = event.result
                    if (result == null) {
                        install.failure = InstallFailure(
                            notStarted = !install.sawEvent && cmd == "attach",
                            step = install.current,
                            code = null,
                            message = null,
                        )
                    } else {
                        finish(result, cmd)
                    }
                } else {
                    val started = install.steps.values.any { it != "pending" }
                    install.failure = InstallFailure(
                        notStarted = !started,
                        step = if (started) failedStep(null) else null,
                        code = event.code,
                        message = event.error,
                    )
                }
            }
        }
    }

    private fun finish(result: InstallResult, @Suppress("UNUSED_PARAMETER") cmd: String) {
        install.result = result
        if (result.ok) {
            INSTALL_STEPS.forEach { if (install.steps[it] != "skipped") install.steps[it] = "done" }
            install.pct = 100.0
            install.etaSeconds = 0
            step = WizardStep.DONE
        } else {
            install.failure = InstallFailure(
                notStarted = false,
                step = failedStep(result.failedStep),
                code = null,
                message = result.error,
            )
            install.showDetails = true
            fetchLog() // no-op while the stream still runs; runStream fetches it when the stream ends
            step = WizardStep.INSTALL
        }
    }

    private fun failedStep(reported: String?): String? =
        reported ?: install.steps.entries.firstOrNull { it.value == "failed" }?.key ?: install.current

    fun toggleDetails() {
        install.showDetails = !install.showDetails
        if (install.showDetails && !install.running) fetchLog()
    }

    /** The daemon's own log (only when no stream is running: requests on the connection are served in order). */
    private fun fetchLog() {
        if (install.running) return
        viewModelScope.launch {
            val lines = call {
                val reply = client.request("log", retryOnce = true) { put("tail", 200) }
                val arr = reply.optJSONArray("lines")
                List(arr?.length() ?: 0) { i -> arr!!.optString(i) }
            }
            val got = lines.valueOrNull ?: return@launch
            if (got.isNotEmpty()) {
                install.log.clear()
                install.log.addAll(got)
            }
        }
    }

    /** Turns daemon failures into [Load.Failed]; cancellation still propagates. */
    private suspend fun <T> call(block: suspend () -> T): Load<T> = try {
        Load.Ready(block())
    } catch (e: CancellationException) {
        throw e
    } catch (e: DaemonException) {
        Log.w(TAG, "daemon: ${e.code}: ${e.message}")
        Load.Failed(e.code, e.message ?: "")
    } catch (e: IOException) {
        Log.w(TAG, "daemon unreachable: ${e.message}")
        Load.Failed(Load.UNREACHABLE, e.message ?: "")
    } catch (e: RuntimeException) {
        Log.e(TAG, "unexpected daemon reply", e)
        Load.Failed("internal", e.message ?: "")
    }

    companion object {
        private const val TAG = "OpenBookInstaller"
        private const val RECONNECT_ATTEMPTS = 30
        private const val RECONNECT_DELAY_MS = 1_000L
        private const val MAX_LOG_LINES = 1_000

        fun normalizeConfirm(s: String): String = s.filterNot { it.isWhitespace() }.lowercase(Locale.ROOT)
    }
}
