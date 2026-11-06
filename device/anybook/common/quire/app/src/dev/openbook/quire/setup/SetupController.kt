// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.setup

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.R
import dev.openbook.quire.acp.Endpoint
import dev.openbook.quire.agents.AcpError
import dev.openbook.quire.agents.AgentHost
import dev.openbook.quire.agents.Agents
import dev.openbook.quire.agents.Connectors
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicLong
import org.json.JSONArray
import org.json.JSONObject

/**
 * Drives [SetupModel] (docs/quire-setup.md §2, §4): the Terminal app's bridge for the Linux environment, `quired`'s
 * setup methods for agents and sign-in, and the admin worker for Debian packages and `quired` updates. It lives in the
 * application, so a running download or install outlives the window. Work runs on [QuireApplication.agentWork]; the
 * model changes only on the main thread. Every line it logs is "setup: …" under [TAG].
 */
class SetupController(private val app: QuireApplication) {
    val model = SetupModel()
    private val main = Handler(Looper.getMainLooper())
    private val listeners = CopyOnWriteArrayList<() -> Unit>()
    private val prefs = app.getSharedPreferences("setup", Context.MODE_PRIVATE)
    private val jobIds = AtomicLong(SystemClock.elapsedRealtime())
    private val extensionHandlers = ConcurrentHashMap<String, (String, JSONObject) -> Unit>()
    @Volatile private var linuxRunning = false
    @Volatile private var catalogRunning = false
    @Volatile private var installRunning = false
    @Volatile private var loginJob: String? = null
    @Volatile private var hostWired: AgentHost? = null
    @Volatile private var updateTried = false

    /** The window is on screen; when it isn't, a finished step 1 posts a notification instead. */
    @Volatile var visible = false

    init {
        model.open(prefs.getBoolean(KEY_FINISHED, false))
        model.defaultAgent = prefs.getString(KEY_DEFAULT, null)
    }

    fun addListener(l: () -> Unit) = listeners.add(l)

    fun removeListener(l: () -> Unit) = listeners.remove(l)

    /** Changes the model on the main thread, then redraws. */
    private fun ui(change: SetupModel.() -> Unit) = main.post {
        model.change()
        listeners.forEach { it() }
    }

    private fun work(name: String, block: () -> Unit) = app.agentWork.execute {
        try {
            block()
        } catch (e: Exception) {
            Log.w(TAG, "setup: $name failed", e)
        }
    }

    // ----------------------------------------------------------------------------------------- the environment

    private fun envOf(s: Connectors.Status): SetupModel.Env = when (s.state) {
        Connectors.State.READY -> SetupModel.Env.READY
        Connectors.State.NO_AVF, Connectors.State.TERMINAL_MISSING -> SetupModel.Env.NO_AVF
        Connectors.State.NO_KVM -> SetupModel.Env.NO_KVM
        Connectors.State.TERMINAL_OFF -> SetupModel.Env.OFF
        Connectors.State.NOT_INSTALLED -> SetupModel.Env.NOT_INSTALLED
        Connectors.State.NO_IMAGE -> SetupModel.Env.NO_IMAGE
        Connectors.State.INSTALLING -> SetupModel.Env.INSTALLING
        Connectors.State.STOPPED -> SetupModel.Env.STOPPED
        Connectors.State.STARTING -> SetupModel.Env.STARTING
        Connectors.State.ERROR -> SetupModel.Env.ERROR
        Connectors.State.NOT_PAIRED -> SetupModel.Env.UNKNOWN
    }

    private fun publish(s: Connectors.Status) {
        val env = envOf(s)
        ui { onEnv(env, s.detail.orEmpty(), s.phase.orEmpty(), s.bytes, s.total) }
    }

    /** What is there now: the environment's state and, when it runs, the agents. Cheap; starts nothing. */
    fun refresh() = work("refresh") {
        val s = Connectors.LinuxEnvironment.status(app)
        publish(s)
        when {
            s.state == Connectors.State.READY -> catalog(QUIRED_WAIT_MS)
            // After setup, the agents page needs quired: a Linux environment that is merely stopped (after every
            // reboot) is started, as the note does when it is called (ANAL-225).
            model.finished && s.state == Connectors.State.STOPPED -> startLinux(showPage = false)
        }
    }

    /**
     * Step 1: turns the Linux environment on if it is off, installs it if it isn't, starts it, and waits for quired to
     * answer, reporting each phase. A laptop without virtualization, a build with no image, or a lasting error stops
     * here with its reason; the page shows the way out.
     */
    fun startLinux(showPage: Boolean = true) {
        if (linuxRunning) return
        linuxRunning = true
        if (showPage) ui { go(SetupModel.Page.LINUX) }
        work("linux") {
            try {
                runLinux()
            } finally {
                linuxRunning = false
            }
        }
    }

    private fun runLinux() {
        var s = Connectors.LinuxEnvironment.status(app)
        Log.i(TAG, "setup: linux ${s.state}")
        s = when (s.state) {
            Connectors.State.TERMINAL_OFF -> Connectors.LinuxEnvironment.setUp(app)
            Connectors.State.NOT_INSTALLED, Connectors.State.STOPPED, Connectors.State.ERROR ->
                Connectors.LinuxEnvironment.start(app)
            else -> s
        }
        publish(s)
        val started = SystemClock.elapsedRealtime()
        var errorSince = -1L
        var askedAt = started
        var asks = 1
        while (s.state != Connectors.State.READY) {
            val now = SystemClock.elapsedRealtime()
            // The Terminal app can drop a start that arrives as it is turned on, or while its service winds down: a
            // Linux environment still stopped (or not installed) well after the last start is asked again, three times
            // at most (C, Cuttlefish 2026-11-06: the second start ran the VM at once).
            if ((s.state == Connectors.State.STOPPED || s.state == Connectors.State.NOT_INSTALLED) &&
                now - askedAt > RESTART_MS && asks < 3) {
                Log.i(TAG, "setup: linux still ${s.state} ${(now - askedAt) / 1000} s after a start, asking again")
                s = Connectors.LinuxEnvironment.start(app)
                askedAt = now
                asks++
                publish(s)
                continue
            }
            if ((s.state == Connectors.State.STOPPED || s.state == Connectors.State.NOT_INSTALLED) &&
                now - askedAt > RESTART_MS && asks >= 3) {
                publish(Connectors.Status(s.connector, Connectors.State.ERROR, "the Terminal app didn’t start it"))
                return
            }
            when (s.state) {
                Connectors.State.NO_AVF, Connectors.State.TERMINAL_MISSING, Connectors.State.NO_KVM,
                Connectors.State.NO_IMAGE, Connectors.State.TERMINAL_OFF -> return
                // Right after a start the bridge can say "error" for a moment; only a lasting one is an error.
                Connectors.State.ERROR -> {
                    if (errorSince < 0) errorSince = now
                    if (now - errorSince > ERROR_GRACE_MS) return
                }
                else -> errorSince = -1L
            }
            if (now - started > LINUX_TIMEOUT_MS) {
                publish(Connectors.Status(s.connector, Connectors.State.ERROR, "it didn’t finish in 30 minutes"))
                return
            }
            SystemClock.sleep(POLL_MS)
            s = Connectors.LinuxEnvironment.status(app)
            publish(s)
        }
        val ok = catalog(QUIRED_WAIT_MS)
        Log.i(TAG, "setup: linux ready, quired ${if (ok) "answered" else "did not answer"}")
        if (!visible) notifyLinux(ok)
    }

    fun stopLinux() = work("stop") {
        publish(Connectors.LinuxEnvironment.stop(app))
        app.agents.disconnect()
    }

    // ----------------------------------------------------------------------------------------- quired

    /** quired's connection, with its notifications routed to the job that asked. */
    private fun host(): AgentHost {
        val h = app.agents.connect()
        if (hostWired !== h) {
            h.extensions = { method, params -> extensionHandlers[params.optString("job")]?.invoke(method, params) }
            hostWired = h
        }
        return h
    }

    /** Lists quired's catalog into the model, asking again for up to [waitMs] while quired starts. */
    private fun catalog(waitMs: Long): Boolean {
        if (catalogRunning) return true
        catalogRunning = true
        try {
            val deadline = SystemClock.elapsedRealtime() + waitMs
            while (true) {
                try {
                    val h = host()
                    val res = h.call("_quire/catalog", JSONObject(), CALL_MS)
                    val agents = parseCatalog(res.optJSONArray("agents") ?: JSONArray())
                    val version = res.optString("quired", h.quiredVersion)
                    Log.i(TAG, "setup: catalog quired=$version agents=${agents.size} installed=" +
                        agents.filter { it.installed }.joinToString(",") { it.id })
                    ui { onEnv(SetupModel.Env.READY); onCatalog(version, agents) }
                    checkSignIns(agents.filter { it.installed && it.supported && !it.needsNoAccount }.map { it.id })
                    keepQuiredCurrent(h)
                    return true
                } catch (e: AcpError) {
                    if (e.code == AcpError.METHOD_NOT_FOUND) {
                        Log.i(TAG, "setup: quired has no setup methods (older than 0.4.0)")
                        ui { onEnv(SetupModel.Env.OLD_HELPER) }
                        return false
                    }
                    if (SystemClock.elapsedRealtime() > deadline) throw e
                } catch (e: Exception) {
                    if (SystemClock.elapsedRealtime() > deadline) {
                        Log.i(TAG, "setup: quired did not answer: ${e.javaClass.simpleName}: ${e.message}")
                        ui { onEnv(SetupModel.Env.ERROR, "Quire’s helper in the Linux environment didn’t answer") }
                        return false
                    }
                    app.agents.disconnect()
                    SystemClock.sleep(2000)
                }
            }
        } finally {
            catalogRunning = false
        }
    }

    private fun parseCatalog(list: JSONArray): List<SetupModel.Agent> = (0 until list.length()).map { i ->
        val a = list.getJSONObject(i)
        val recipe = a.optJSONObject("recipe") ?: JSONObject()
        val steps = recipe.optJSONArray("steps") ?: JSONArray()
        val methods = a.optJSONArray("signin") ?: JSONArray()
        val keys = a.optJSONArray("keys") ?: JSONArray()
        val debian = recipe.optJSONArray("debian") ?: JSONArray()
        SetupModel.Agent(
            id = a.optString("id"), name = a.optString("name"), maker = a.optString("maker"),
            needs = a.optString("needs"), supported = a.optBoolean("supported"), installed = a.optBoolean("installed"),
            version = a.optString("version"),
            methods = (0 until methods.length()).map {
                val m = methods.getJSONObject(it)
                SetupModel.Method(m.optString("id"), SetupModel.kind(m.optString("kind")), m.optString("label"))
            },
            keys = (0 until keys.length()).map {
                val k = keys.getJSONObject(it)
                SetupModel.Key(k.optString("name"), k.optString("label"))
            },
            hasKey = a.optBoolean("hasKey"),
            debian = (0 until debian.length()).map { debian.getString(it) },
            steps = (0 until steps.length()).map {
                val s = steps.getJSONObject(it)
                SetupModel.Step(s.optString("title"), s.optString("command"), s.optString("source"))
            },
        )
    }

    private fun checkSignIns(ids: List<String>) {
        for (id in ids) work("signin $id") {
            val r = host().call("_quire/signin", JSONObject().put("agent", id), SIGNIN_MS)
            val state = when {
                r.isNull("signedIn") && r.optString("detail").contains("key is stored") -> SetupModel.SignState.IN
                r.isNull("signedIn") -> SetupModel.SignState.UNKNOWN
                r.optBoolean("signedIn") -> SetupModel.SignState.IN
                else -> SetupModel.SignState.OUT
            }
            Log.i(TAG, "setup: $id sign-in $state")
            ui { if (signIns[id] != SetupModel.SignState.IN || state == SetupModel.SignState.IN) onSignIn(id, state) }
        }
    }

    // ----------------------------------------------------------------------------------------- agents

    /** Install: Debian prerequisites through the admin worker first, then each agent's recipe in quired, in order. */
    fun install() {
        if (installRunning || model.selected.isEmpty()) return
        installRunning = true
        val ids = model.startInstall()
        listeners.forEach { it() }
        val debian = model.debianFor(ids)
        Log.i(TAG, "setup: install ${ids.joinToString(",")} debian=${debian.joinToString(",")}")
        work("install") {
            try {
                if (debian.isNotEmpty() && !installDebian(ids, debian)) return@work
                for (id in ids) installOne(id, "_quire/install")
                catalog(CALL_MS)
                main.post { connectInNote(ids) }
            } finally {
                installRunning = false
                ui {}
            }
        }
    }

    private fun installDebian(ids: List<String>, debian: List<String>): Boolean {
        val first = ids.first()
        ui { jobs[first]?.apply { state = SetupModel.JobState.RUNNING; title = app.getString(R.string.setup_debian, debian.joinToString(", ")) } }
        return try {
            AdminClient.open(app) { line -> ui { jobs[first]?.line = line } }.use { it.debianInstall(debian) }
            true
        } catch (e: Exception) {
            Log.w(TAG, "setup: Debian packages failed: ${e.message}")
            val why = app.getString(R.string.setup_debian_failed, debian.joinToString(", "))
            ui { ids.forEach { jobs[it]?.apply { state = SetupModel.JobState.FAILED; error = why; output = e.message.orEmpty() } } }
            false
        }
    }

    private fun installOne(id: String, method: String) {
        val job = "install-${jobIds.incrementAndGet()}"
        ui { jobs.getOrPut(id) { SetupModel.Job(id) }.apply { state = SetupModel.JobState.RUNNING; line = ""; error = "" } }
        extensionHandlers[job] = { m, p ->
            if (m == "_quire/progress") ui {
                jobs[id]?.apply {
                    step = p.optInt("step", step)
                    steps = p.optInt("steps", steps)
                    title = p.optString("title", title)
                    line = p.optString("line", line)
                }
            }
        }
        try {
            val r = try {
                host().call(method, JSONObject().put("agent", id).put("job", job), INSTALL_MS)
            } catch (e: AcpError) {
                // quired checks the recipe's Debian packages first and names the missing ones (-32600): the admin
                // worker installs them, then the recipe runs once more.
                val missing = ((e.data as? JSONObject)?.optJSONArray("missing"))?.let { a -> (0 until a.length()).map { a.getString(it) } }
                if (e.code != INVALID_REQUEST || missing.isNullOrEmpty() || !installDebian(listOf(id), missing)) throw e
                host().call(method, JSONObject().put("agent", id).put("job", job), INSTALL_MS)
            }
            Log.i(TAG, "setup: $method $id done: ${r.optString("version")}")
            ui { jobs[id]?.apply { state = SetupModel.JobState.DONE; line = r.optString("version") } }
        } catch (e: Exception) {
            val output = (e as? AcpError)?.data?.let { (it as? JSONObject)?.optString("output") }.orEmpty()
            Log.w(TAG, "setup: $method $id failed: ${e.message}")
            ui { jobs[id]?.apply { state = SetupModel.JobState.FAILED; error = e.message.orEmpty(); this.output = output } }
        } finally {
            extensionHandlers.remove(job)
        }
    }

    /** Try again on one card. */
    fun retry(id: String) {
        if (installRunning) return
        installRunning = true
        work("retry") {
            try {
                val debian = model.debianFor(listOf(id))
                if (debian.isEmpty() || installDebian(listOf(id), debian)) installOne(id, "_quire/install")
                catalog(CALL_MS)
                main.post { connectInNote(listOf(id)) }
            } finally {
                installRunning = false
                ui {}
            }
        }
    }

    fun update(id: String) = work("update") {
        installOne(id, "_quire/update")
        catalog(CALL_MS)
    }

    fun remove(id: String, settings: Boolean) = work("remove") {
        host().call("_quire/remove", JSONObject().put("agent", id).put("job", "remove-${jobIds.incrementAndGet()}")
            .put("settings", settings), INSTALL_MS)
        main.post { app.surface.agents.remove(Endpoint.LINUX + id) }
        catalog(CALL_MS)
    }

    /**
     * Installing an agent from the wizard is the person's choice of it, so the note lists it as connected
     * (docs/quire.md §5.3: nothing is sent to an agent before the person connects it).
     */
    private fun connectInNote(ids: List<String>) {
        val dir = app.surface.agents
        val installed = model.installedAgents.filter { it.id in ids }
        dir.foundInLinux(installed.map {
            Endpoint(id = Endpoint.LINUX + it.id, name = it.name, where = app.getString(R.string.q_where_linux),
                address = Endpoint.LINUX + it.id, cwd = "", local = true)
        })
        installed.forEach { a -> dir.find(Endpoint.LINUX + a.id)?.let { dir.setConnected(it, true) } }
        model.defaultAgent?.let { d -> dir.find(Endpoint.LINUX + d)?.let { dir.use(it) } }
    }

    // ----------------------------------------------------------------------------------------- sign-in

    fun signIn(id: String, method: SetupModel.Method) {
        if (loginJob != null) cancelSignIn()
        val job = "login-${jobIds.incrementAndGet()}"
        loginJob = job
        model.prompt = SetupModel.Prompt(id, method)
        listeners.forEach { it() }
        if (method.kind == SetupModel.Kind.KEY) return
        if (method.kind == SetupModel.Kind.ACP) return signInAcp(id, job)
        extensionHandlers[job] = { m, p ->
            if (m == "_quire/login/prompt") ui {
                prompt?.takeIf { it.agent == id }?.apply {
                    if (p.has("url")) url = p.optString("url")
                    if (p.has("code")) code = p.optString("code")
                    if (p.optBoolean("paste")) paste = true
                }
            }
        }
        work("login") {
            try {
                val r = host().call("_quire/login", JSONObject().put("agent", id).put("method", method.id).put("job", job), LOGIN_MS)
                val state = when {
                    r.isNull("signedIn") -> null
                    r.optBoolean("signedIn") -> SetupModel.SignState.IN
                    else -> SetupModel.SignState.OUT
                }
                Log.i(TAG, "setup: login $id ended: $state")
                if (state == null) checkSignIns(listOf(id))
                ui {
                    if (state == SetupModel.SignState.IN) {
                        onSignIn(id, state)
                        if (prompt?.agent == id) prompt = null
                    } else if (state == SetupModel.SignState.OUT) {
                        prompt?.takeIf { it.agent == id }?.failed = app.getString(R.string.setup_signin_failed)
                    } else if (prompt?.agent == id) {
                        prompt = null
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "setup: login $id failed: ${e.message}")
                ui { prompt?.takeIf { it.agent == id }?.failed = app.getString(R.string.setup_signin_failed) }
            } finally {
                extensionHandlers.remove(job)
                if (loginJob == job) loginJob = null
            }
        }
    }

    /**
     * An agent that signs in through ACP itself (Antigravity): its own `authMethods`, from its initialize, and
     * `authenticate` with the first one that isn't a key. Any address it prints for the browser is shown to open.
     */
    private fun signInAcp(id: String, job: String) = work("acp-login") {
        try {
            val methods = app.agents.describe(id).optJSONArray("authMethods") ?: JSONArray()
            val pick = (0 until methods.length()).map { methods.getJSONObject(it) }
                .firstOrNull { !it.optString("id").contains("key") && it.optString("type") != "terminal" }
                ?: throw IllegalStateException("no sign-in method Quire can start")
            ui { prompt?.takeIf { it.agent == id }?.paste = false }
            app.agents.authenticate(id, pick.optString("id"))
            Log.i(TAG, "setup: acp login $id with ${pick.optString("id")} done")
            ui { onSignIn(id, SetupModel.SignState.IN); if (prompt?.agent == id) prompt = null }
        } catch (e: Exception) {
            Log.w(TAG, "setup: acp login $id failed: ${e.message}")
            ui { prompt?.takeIf { it.agent == id }?.failed = app.getString(R.string.setup_signin_terminal) }
        } finally {
            if (loginJob == job) loginJob = null
        }
    }

    /** The code the person pasted, written once to the login's terminal. Not kept here or logged. */
    fun paste(text: String) {
        val job = loginJob ?: return
        work("paste") { host().call("_quire/login/input", JSONObject().put("job", job).put("text", text.trim()), CALL_MS) }
    }

    /** A key for one agent, stored only in the guest (docs/quire-setup.md §6). Not kept here or logged. */
    fun saveKey(id: String, name: String, value: String) {
        work("key") {
            try {
                host().call("_quire/key", JSONObject().put("agent", id).put("name", name).put("value", value.trim()), CALL_MS)
                Log.i(TAG, "setup: key saved for $id ($name)")
                ui { onSignIn(id, SetupModel.SignState.IN); if (prompt?.agent == id) prompt = null }
            } catch (e: Exception) {
                Log.w(TAG, "setup: key for $id failed: ${e.message}")
                ui { prompt?.takeIf { it.agent == id }?.failed = app.getString(R.string.setup_key_failed) }
            }
        }
    }

    fun cancelSignIn() {
        val job = loginJob
        loginJob = null
        model.prompt = null
        listeners.forEach { it() }
        if (job != null) work("cancel") { host().call("_quire/cancel", JSONObject().put("job", job), CALL_MS) }
    }

    fun signOut(id: String) = work("signout") {
        val r = host().call("_quire/signout", JSONObject().put("agent", id), LOGIN_MS)
        Log.i(TAG, "setup: signed out $id: ran=${r.optString("ran")}")
        ui { onSignIn(id, SetupModel.SignState.OUT) }
    }

    // ----------------------------------------------------------------------------------------- try it

    /** Try it: one real request to the default agent, streamed into the page. */
    fun sayHello() {
        val id = model.defaultAgent ?: return
        model.helloAgent = id
        model.helloText = ""
        model.helloDone = false
        model.helloFailed = ""
        listeners.forEach { it() }
        val stream = object : Agents.Listener {
            override fun onAgentsChanged(summary: String) {
                ui { if (helloAgent == id && !helloDone) helloText = summary }
            }
        }
        work("hello") {
            app.agents.addListener(stream)
            try {
                val a = app.agents.prompt(id, app.getString(R.string.setup_hello_prompt), Agents.Approve.NONE)
                Log.i(TAG, "setup: hello from $id in ${a.millis} ms, stop=${a.stopReason}")
                ui { if (helloAgent == id) { helloText = a.text.ifEmpty { helloText }; helloDone = true } }
            } catch (e: Exception) {
                Log.w(TAG, "setup: hello from $id failed: ${e.message}")
                ui { if (helloAgent == id) { helloDone = true; helloFailed = e.message.orEmpty() } }
            } finally {
                app.agents.removeListener(stream)
            }
        }
    }

    fun setDefault(id: String) {
        model.defaultAgent = id
        prefs.edit().putString(KEY_DEFAULT, id).apply()
        app.surface.agents.find(Endpoint.LINUX + id)?.let { app.surface.agents.use(it) }
        listeners.forEach { it() }
    }

    fun finish() {
        prefs.edit().putBoolean(KEY_FINISHED, true).apply()
        model.defaultAgent?.let { setDefault(it) }
        connectInNote(model.installedAgents.map { it.id })
    }

    // ----------------------------------------------------------------------------------------- helpers

    /** Opens an address an agent's login printed, in the browser, on the person's click. Only https. */
    fun openUrl(url: String) {
        if (!SetupModel.safeUrl(url)) {
            Log.w(TAG, "setup: refused to open a non-https address")
            return
        }
        app.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url.trim())).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    fun copy(label: String, text: String) {
        app.getSystemService(ClipboardManager::class.java)?.setPrimaryClip(ClipData.newPlainText(label, text))
    }

    fun openTerminal() {
        app.packageManager.getLaunchIntentForPackage(Connectors.LinuxEnvironment.TERMINAL)?.let {
            app.startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }

    /**
     * The guest's quired matches the one this image carries (docs/quire-setup.md §4.4): when it is older, the admin
     * worker installs this one in a unit of its own, and Quire reconnects. A guest without a worker (0.3.0) stays as
     * it is; the wizard says so (Env.OLD_HELPER).
     */
    private fun keepQuiredCurrent(h: AgentHost) {
        if (updateTried) return
        val deb = File(QUIRED_DEB)
        val shipped = runCatching { File(QUIRED_VERSION).readText().trim() }.getOrDefault("")
        val running = h.quiredVersion
        if (!deb.isFile || shipped.isEmpty() || running.isEmpty() || compareVersions(running, shipped) >= 0) return
        updateTried = true
        work("quired-update") {
            val bytes = deb.readBytes()
            val sha = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            Log.i(TAG, "setup: updating quired $running -> $shipped")
            AdminClient.open(app).use { admin ->
                val id = admin.quiredUpdate(bytes, sha)
                val deadline = SystemClock.elapsedRealtime() + UPDATE_MS
                while (SystemClock.elapsedRealtime() < deadline) {
                    SystemClock.sleep(1500)
                    val j = runCatching { AdminClient.open(app).use { it.job(id) } }.getOrNull() ?: continue
                    when (j.optString("state")) {
                        "done" -> { Log.i(TAG, "setup: quired updated to ${j.optString("version")}"); break }
                        "failed" -> { Log.w(TAG, "setup: quired update failed: ${j.optString("error")}"); return@work }
                    }
                }
            }
            app.agents.disconnect()
            catalog(QUIRED_WAIT_MS)
        }
    }

    private fun notifyLinux(ok: Boolean) {
        val nm = app.getSystemService(NotificationManager::class.java) ?: return
        nm.createNotificationChannel(NotificationChannel(CHANNEL, app.getString(R.string.setup_channel),
            NotificationManager.IMPORTANCE_DEFAULT))
        val open = PendingIntent.getActivity(app, 0, Intent(app, SetupActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE)
        nm.notify(NOTIFICATION_ID, Notification.Builder(app, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(app.getString(if (ok) R.string.setup_ready_title else R.string.setup_failed_title))
            .setContentText(app.getString(if (ok) R.string.setup_ready_text else R.string.setup_failed_text))
            .setContentIntent(open)
            .setAutoCancel(true)
            .build())
    }

    companion object {
        private const val INVALID_REQUEST = -32600
        private const val KEY_FINISHED = "finished"
        private const val KEY_DEFAULT = "default"
        private const val CHANNEL = "setup"
        private const val NOTIFICATION_ID = 393
        private const val POLL_MS = 700L
        private const val RESTART_MS = 12_000L
        private const val ERROR_GRACE_MS = 20_000L
        private const val LINUX_TIMEOUT_MS = 30 * 60_000L
        private const val QUIRED_WAIT_MS = 60_000L
        private const val CALL_MS = 30_000L
        private const val SIGNIN_MS = 60_000L
        private const val INSTALL_MS = 20 * 60_000L
        private const val LOGIN_MS = 15 * 60_000L
        private const val UPDATE_MS = 3 * 60_000L

        /** The quired package this image carries, and its version (device/anybook/common/quire/Android.bp). */
        const val QUIRED_DEB = "/system_ext/etc/quire/quired.deb"
        const val QUIRED_VERSION = "/system_ext/etc/quire/quired.version"

        /** Dotted numeric versions: negative when [a] is older than [b]. */
        fun compareVersions(a: String, b: String): Int {
            val x = a.trim().removePrefix("v").split('.', '-', '+').map { it.toIntOrNull() ?: 0 }
            val y = b.trim().removePrefix("v").split('.', '-', '+').map { it.toIntOrNull() ?: 0 }
            for (i in 0 until maxOf(x.size, y.size)) {
                val c = (x.getOrElse(i) { 0 }).compareTo(y.getOrElse(i) { 0 })
                if (c != 0) return c
            }
            return 0
        }
    }
}
