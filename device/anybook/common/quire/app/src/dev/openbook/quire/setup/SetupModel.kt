// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.setup

/**
 * The wizard's state (docs/quire-setup.md §2): which page shows, what the Linux environment is doing, the agents
 * `quired` lists, the jobs that install them and their sign-in. No Android types, so the host tests drive it
 * (tests/unit/SetupModelTest.kt). [SetupController] feeds it; [SetupActivity] draws it. It never holds a secret: a
 * pasted code or a key goes straight from its field to `quired` and is not stored here.
 */
class SetupModel {
    enum class Page { WELCOME, LINUX, AGENTS, INSTALLING, SIGNIN, TRY, MANAGE }

    /** The Linux environment, as the wizard words it. Mirrors agents/Connectors.State, plus what quired adds. */
    enum class Env {
        UNKNOWN, READY, NO_AVF, NO_KVM, OFF, NOT_INSTALLED, NO_IMAGE, INSTALLING, STOPPED, STARTING, ERROR,
        /** Running, but its quired predates setup (0.3.0) and can't install agents or update itself. */
        OLD_HELPER,
    }

    /** What the person can do about an [Env] on the Linux page (§2, page 1′). */
    enum class Remedy { NONE, START, FIRMWARE, NO_IMAGE, RETRY, OLD_HELPER, NO_AVF }

    enum class Row { WAIT, NOW, DONE, FAILED }

    /** How an agent signs in: its own login (device code, paste-back, a link), a key, ACP's authenticate, or nothing. */
    enum class Kind { DEVICE, PASTE, LINK, KEY, ACP, NONE }

    data class Method(val id: String, val kind: Kind, val label: String)

    data class Key(val name: String, val label: String)

    data class Step(val title: String, val command: String, val source: String)

    data class Agent(
        val id: String,
        val name: String,
        val maker: String,
        val needs: String,
        val supported: Boolean,
        val installed: Boolean,
        val version: String,
        val methods: List<Method>,
        val keys: List<Key>,
        val hasKey: Boolean,
        val debian: List<String>,
        val steps: List<Step>,
    ) {
        /** Needs no account: its only method is NONE, or it has none and no keys. */
        val needsNoAccount: Boolean
            get() = methods.all { it.kind == Kind.NONE } && keys.isEmpty()

        /** The method the wizard offers first: a code-based one before a key. */
        val firstMethod: Method?
            get() = methods.firstOrNull { it.kind == Kind.DEVICE || it.kind == Kind.PASTE || it.kind == Kind.LINK }
                ?: methods.firstOrNull { it.kind == Kind.ACP }
                ?: methods.firstOrNull { it.kind == Kind.KEY }
    }

    enum class JobState { QUEUED, RUNNING, DONE, FAILED, CANCELLED }

    data class Job(val agent: String, var state: JobState = JobState.QUEUED, var step: Int = 0, var steps: Int = 0,
        var title: String = "", var line: String = "", var error: String = "", var output: String = "") {
        val fraction: Float
            get() = when {
                state == JobState.DONE -> 1f
                steps <= 0 -> 0.05f
                else -> ((step - 1).coerceAtLeast(0) + 0.5f) / steps
            }
    }

    enum class SignState { NOT_NEEDED, OUT, IN, UNKNOWN }

    /** A sign-in in progress: what the agent's own login asked for (§4.2 `_quire/login/prompt`). */
    data class Prompt(val agent: String, val method: Method, var url: String = "", var code: String = "",
        var paste: Boolean = false, var failed: String = "")

    var page = Page.WELCOME
        private set
    var env = Env.UNKNOWN
        private set
    var envDetail = ""
        private set
    var phase = ""
        private set
    var bytes = -1L
        private set
    var total = -1L
        private set

    /** Set once the Linux environment answered while the person watched step 1, so its rows read as done. */
    var linuxDone = false
        private set
    var quired = ""
        private set
    var agents: List<Agent> = emptyList()
        private set
    val selected = linkedSetOf<String>()
    val jobs = LinkedHashMap<String, Job>()
    val signIns = LinkedHashMap<String, SignState>()
    var prompt: Prompt? = null

    /**
     * What a sign-out did, when it couldn't sign the account itself out (docs/quire-setup.md §6): Quire's own key is
     * gone, but the maker's login stays until the person does what [manual] says, in the files [cleanup] names.
     */
    data class SignOutNote(val agent: String, val ran: String, val removed: List<String>, val manual: List<String>,
        val cleanup: List<String>)

    var signOutNote: SignOutNote? = null
    var showWhatRuns = false
    var showDetails = false
    var defaultAgent: String? = null
    var helloAgent: String? = null
    var helloText = ""
    var helloDone = false
    var helloFailed = ""

    /** Setup was finished once; the Quire app then opens on the agents page. */
    var finished = false
        private set

    fun agent(id: String) = agents.firstOrNull { it.id == id }

    val installedAgents: List<Agent>
        get() = agents.filter { it.installed && it.supported }

    /** The agents shown in the grid: those quired can run. The rest are named under it ("Coming to Quire"). */
    val offered: List<Agent>
        get() = agents.filter { it.supported }

    val comingSoon: List<Agent>
        get() = agents.filter { !it.supported }

    // ------------------------------------------------------------------------------------------------ inputs

    /** Where the window opens: the agents page once setup is finished, else the first unfinished step. */
    fun open(finished: Boolean) {
        this.finished = finished
        page = if (finished) Page.MANAGE else Page.WELCOME
    }

    fun onEnv(env: Env, detail: String = "", phase: String = "", bytes: Long = -1, total: Long = -1) {
        this.env = env
        envDetail = detail
        this.phase = phase
        this.bytes = bytes
        this.total = total
        if (env == Env.READY && page == Page.LINUX) linuxDone = quired.isNotEmpty()
    }

    fun onCatalog(quired: String, agents: List<Agent>) {
        this.quired = quired
        this.agents = agents
        selected.retainAll(agents.filter { it.supported && !it.installed }.map { it.id }.toSet())
        for (a in installedAgents) if (a.id !in signIns || signIns[a.id] == SignState.UNKNOWN) {
            signIns[a.id] = if (a.needsNoAccount) SignState.NOT_NEEDED else signIns[a.id] ?: SignState.UNKNOWN
        }
        if (defaultAgent == null || installedAgents.none { it.id == defaultAgent }) {
            defaultAgent = installedAgents.firstOrNull { signIns[it.id] == SignState.IN || signIns[it.id] == SignState.NOT_NEEDED }?.id
                ?: installedAgents.firstOrNull()?.id
        }
        if (env == Env.READY && page == Page.LINUX) linuxDone = true
    }

    fun onSignIn(agent: String, state: SignState) {
        signIns[agent] = state
    }

    fun go(to: Page) {
        page = to
        if (to != Page.AGENTS) showWhatRuns = false
        if (to != Page.SIGNIN) prompt = null
        signOutNote = null
    }

    /** Get started, and Next on each page: the first step that isn't done yet (§2: done steps are skipped). */
    fun next(): Page {
        val to = when (page) {
            Page.WELCOME -> if (env == Env.READY && quired.isNotEmpty()) afterLinux() else Page.LINUX
            Page.LINUX -> afterLinux()
            Page.AGENTS, Page.INSTALLING -> afterAgents()
            Page.SIGNIN -> Page.TRY
            Page.TRY -> Page.MANAGE.also { finished = true }
            Page.MANAGE -> Page.MANAGE
        }
        go(to)
        return to
    }

    private fun afterLinux() = if (installedAgents.isEmpty()) Page.AGENTS else afterAgents()

    private fun afterAgents() =
        if (installedAgents.any { signIns[it.id] == SignState.OUT || signIns[it.id] == SignState.UNKNOWN }) Page.SIGNIN
        else Page.TRY

    fun toggle(id: String) {
        val a = agent(id) ?: return
        if (!a.supported || a.installed) return
        if (!selected.add(id)) selected.remove(id)
    }

    /** Install: one job per selected agent, run in order. */
    fun startInstall(): List<String> {
        val ids = selected.toList()
        jobs.clear()
        ids.forEach { jobs[it] = Job(it) }
        selected.clear()
        showWhatRuns = false
        go(Page.INSTALLING)
        return ids
    }

    val installing: Boolean
        get() = jobs.values.any { it.state == JobState.QUEUED || it.state == JobState.RUNNING }

    // ------------------------------------------------------------------------------------------------ derived

    /** What the person can do about the environment now. */
    val remedy: Remedy
        get() = when (env) {
            Env.NO_AVF -> Remedy.NO_AVF
            Env.NO_KVM -> Remedy.FIRMWARE
            Env.NO_IMAGE -> Remedy.NO_IMAGE
            Env.ERROR -> Remedy.RETRY
            Env.OLD_HELPER -> Remedy.OLD_HELPER
            Env.OFF, Env.NOT_INSTALLED, Env.STOPPED, Env.UNKNOWN -> Remedy.START
            Env.INSTALLING, Env.STARTING, Env.READY -> Remedy.NONE
        }

    /**
     * The five rows of the Linux page (§2): this laptop can run it, downloading, unpacking, starting Linux,
     * connecting Quire.
     */
    fun linuxRows(): List<Row> {
        if (linuxDone || (env == Env.READY && quired.isNotEmpty())) return List(5) { Row.DONE }
        val failed = remedy != Remedy.NONE && remedy != Remedy.START
        val at = when (env) {
            Env.NO_KVM, Env.NO_AVF -> 0
            Env.NO_IMAGE -> 1
            Env.INSTALLING -> if (phase == "unpack" || phase == "verify") 2 else 1
            Env.STARTING, Env.STOPPED -> 3
            Env.READY, Env.ERROR, Env.OLD_HELPER -> 4
            else -> 0
        }
        return List(5) { i ->
            when {
                i < at -> Row.DONE
                i == at && failed -> Row.FAILED
                i == at && remedy == Remedy.START && env != Env.STOPPED -> Row.WAIT
                i == at -> Row.NOW
                else -> Row.WAIT
            }
        }
    }

    /** The ring on the Linux page, 0 to 1. */
    val linuxFraction: Float
        get() {
            if (linuxDone || (env == Env.READY && quired.isNotEmpty())) return 1f
            val dl = if (total > 0 && bytes >= 0) (bytes.toFloat() / total).coerceIn(0f, 1f) else 0f
            return when (env) {
                Env.INSTALLING -> when (phase) {
                    "verify" -> 0.62f
                    "unpack" -> 0.62f + 0.18f * dl
                    else -> 0.08f + 0.52f * dl
                }
                Env.STARTING, Env.STOPPED -> 0.85f
                Env.READY -> 0.95f
                else -> 0.04f
            }
        }

    /** Megabytes done and in total, for "412 of 788 MB"; null when not downloading. */
    val megabytes: Pair<Long, Long>?
        get() = if (env == Env.INSTALLING && phase != "unpack" && phase != "verify" && total > 0)
            (bytes.coerceAtLeast(0) / MB) to (total / MB) else null

    /** Rough size of the selected agents' downloads, for the count under the grid. */
    fun selectedMegabytes(): Int = selected.sumOf { SIZE_MB[it] ?: 80 }

    /** The Debian packages the selected (or given) agents need first, once each. */
    fun debianFor(ids: Collection<String>): List<String> =
        ids.mapNotNull { agent(it) }.flatMap { it.debian }.distinct()

    /** The rows the Sign in page lists: every installed agent Quire can run. */
    fun signInRows(): List<Pair<Agent, SignState>> =
        installedAgents.map { it to (signIns[it.id] ?: if (it.needsNoAccount) SignState.NOT_NEEDED else SignState.UNKNOWN) }

    val pendingSignIns: Int
        get() = signInRows().count { it.second == SignState.OUT || it.second == SignState.UNKNOWN }

    /**
     * The sign-in state after `_quire/signout` (quired's answer): signed out only when the maker's own logout ran, or
     * the agent's only sign-in was a key Quire kept. Removing Quire's key file alone never counts as signing the
     * account out.
     */
    fun afterSignOut(agent: String, accountSignedOut: Boolean?, ran: String, removed: List<String>,
        manual: List<String>, cleanup: List<String>): SignState {
        if (accountSignedOut == true) {
            signIns[agent] = SignState.OUT
            signOutNote = null
            return SignState.OUT
        }
        // The maker's login is still there, so the account is as signed in as it was; the note says what is left.
        signOutNote = SignOutNote(agent, ran, removed, manual, cleanup)
        return signIns[agent] ?: SignState.UNKNOWN
    }

    companion object {
        private const val MB = 1_000_000L

        /** Approximate downloads (docs/quire-setup.md §5), only for the hint under the grid. */
        private val SIZE_MB = mapOf("claude" to 70, "opencode" to 60, "copilot" to 110, "antigravity" to 90,
            "gemini" to 90, "cursor" to 120, "kimi" to 80, "grok" to 90, "hermes" to 150, "omp" to 60)

        /** The order of the steps row in the header: Linux · Agents · Sign in · Try it. */
        fun stepIndex(page: Page): Int = when (page) {
            Page.WELCOME, Page.MANAGE -> -1
            Page.LINUX -> 0
            Page.AGENTS, Page.INSTALLING -> 1
            Page.SIGNIN -> 2
            Page.TRY -> 3
        }

        fun kind(s: String): Kind = when (s) {
            "device" -> Kind.DEVICE
            "paste" -> Kind.PASTE
            "link" -> Kind.LINK
            "key" -> Kind.KEY
            "acp" -> Kind.ACP
            else -> Kind.NONE
        }

        /** Only an https address an agent's own login printed is opened, and only on the person's click. */
        fun safeUrl(url: String): Boolean {
            val u = url.trim()
            if (!u.startsWith("https://") || u.length > 2048) return false
            val host = u.removePrefix("https://").substringBefore('/').substringBefore('?').substringBefore('#')
            return host.isNotEmpty() && '@' !in host && host.all { it.isLetterOrDigit() || it == '.' || it == '-' || it == ':' }
        }
    }
}
