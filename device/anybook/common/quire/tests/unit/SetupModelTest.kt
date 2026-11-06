// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.setup

import dev.openbook.quire.setup.SetupModel.Env
import dev.openbook.quire.setup.SetupModel.Kind
import dev.openbook.quire.setup.SetupModel.Page
import dev.openbook.quire.setup.SetupModel.Remedy
import dev.openbook.quire.setup.SetupModel.Row
import dev.openbook.quire.setup.SetupModel.SignState
import dev.openbook.quire.test.Check

/** ANAL-393: Quire setup's pages, skip rules, Linux rows and copy keys (setup/SetupModel.kt). Run by tools/unit-test.sh. */
object SetupModelTest {
    private fun mk(id: String, installed: Boolean = false, supported: Boolean = true,
        methods: List<SetupModel.Method> = listOf(SetupModel.Method("$id-login", Kind.DEVICE, "Sign in")),
        keys: List<SetupModel.Key> = emptyList(), debian: List<String> = emptyList()) =
        SetupModel.Agent(id, id.replaceFirstChar { it.uppercase() }, "Maker", "needs", supported, installed,
            if (installed) "1.0" else "", methods, keys, false, debian,
            listOf(SetupModel.Step("Install", "curl -fsSL https://example.org/$id | bash", "https://example.org/$id")))

    private val free = mk("opencode", installed = true, methods = listOf(SetupModel.Method("none", Kind.NONE, "")))

    fun run(c: Check) {
        // Opening: first time on the welcome page, after setup on the agents page.
        SetupModel().apply { open(false); c.eq("opens on welcome", page, Page.WELCOME) }
        SetupModel().apply { open(true); c.eq("finished opens on manage", page, Page.MANAGE) }

        // Get started with nothing set up goes to Linux; with Linux and an agent ready it skips to the next step.
        SetupModel().apply {
            open(false)
            c.eq("welcome -> linux", next(), Page.LINUX)
        }
        SetupModel().apply {
            open(false)
            onEnv(Env.READY)
            onCatalog("0.4.0", listOf(free, mk("claude")))
            c.eq("ready with a free agent skips to try", next(), Page.TRY)
        }
        SetupModel().apply {
            open(false)
            onEnv(Env.READY)
            onCatalog("0.4.0", listOf(mk("claude")))
            c.eq("ready with no agent goes to agents", next(), Page.AGENTS)
        }
        SetupModel().apply {
            open(false)
            onEnv(Env.READY)
            onCatalog("0.4.0", listOf(mk("claude", installed = true)))
            c.eq("an installed agent with unknown sign-in goes to sign in", next(), Page.SIGNIN)
            onSignIn("claude", SignState.IN)
            c.eq("sign in -> try", next(), Page.TRY)
            c.eq("try -> manage", next(), Page.MANAGE)
            c.eq("finished after try", finished, true)
            c.eq("default is the signed-in agent", defaultAgent, "claude")
        }

        // Selecting: unsupported and installed agents can't be picked; install moves the selection into jobs.
        SetupModel().apply {
            onCatalog("0.4.0", listOf(mk("claude"), mk("gemini", debian = listOf("nodejs", "npm")),
                mk("codex", supported = false), free))
            toggle("codex")
            toggle("opencode")
            c.eq("unsupported and installed not selectable", selected.toList(), emptyList<String>())
            toggle("claude"); toggle("gemini")
            c.eq("two selected", selected.toList(), listOf("claude", "gemini"))
            c.eq("debian for the selection", debianFor(selected), listOf("nodejs", "npm"))
            toggle("claude")
            c.eq("toggle off", selected.toList(), listOf("gemini"))
            toggle("claude")
            c.eq("offered excludes unsupported", offered.map { it.id }, listOf("claude", "gemini", "opencode"))
            c.eq("coming soon", comingSoon.map { it.id }, listOf("codex"))
            val ids = startInstall()
            c.eq("install order", ids, listOf("gemini", "claude"))
            c.eq("install page", page, Page.INSTALLING)
            c.eq("selection cleared", selected.isEmpty(), true)
            c.eq("installing while queued", installing, true)
            jobs.values.forEach { it.state = SetupModel.JobState.DONE }
            c.eq("not installing when done", installing, false)
        }

        // The Linux page's rows and remedies, for every state the bridge reports.
        val cases = listOf(
            Triple(Env.NO_KVM, Remedy.FIRMWARE, listOf(Row.FAILED, Row.WAIT, Row.WAIT, Row.WAIT, Row.WAIT)),
            Triple(Env.NO_AVF, Remedy.NO_AVF, listOf(Row.FAILED, Row.WAIT, Row.WAIT, Row.WAIT, Row.WAIT)),
            Triple(Env.NO_IMAGE, Remedy.NO_IMAGE, listOf(Row.DONE, Row.FAILED, Row.WAIT, Row.WAIT, Row.WAIT)),
            Triple(Env.STARTING, Remedy.NONE, listOf(Row.DONE, Row.DONE, Row.DONE, Row.NOW, Row.WAIT)),
            Triple(Env.ERROR, Remedy.RETRY, listOf(Row.DONE, Row.DONE, Row.DONE, Row.DONE, Row.FAILED)),
            Triple(Env.OLD_HELPER, Remedy.HELPER, listOf(Row.DONE, Row.DONE, Row.DONE, Row.DONE, Row.FAILED)),
            Triple(Env.NO_HELPER, Remedy.HELPER, listOf(Row.DONE, Row.DONE, Row.DONE, Row.DONE, Row.FAILED)),
            Triple(Env.OFF, Remedy.START, listOf(Row.WAIT, Row.WAIT, Row.WAIT, Row.WAIT, Row.WAIT)),
        )
        for ((env, remedy, rows) in cases) SetupModel().apply {
            onEnv(env)
            c.eq("remedy $env", this.remedy, remedy)
            c.eq("rows $env", linuxRows(), rows)
        }
        SetupModel().apply {
            onEnv(Env.INSTALLING, phase = "download", bytes = 412_000_000, total = 788_000_000)
            c.eq("download rows", linuxRows(), listOf(Row.DONE, Row.NOW, Row.WAIT, Row.WAIT, Row.WAIT))
            c.eq("megabytes", megabytes, 412L to 788L)
            c.eq("ring mid-download", (linuxFraction * 100).toInt(), 35)
            onEnv(Env.INSTALLING, phase = "unpack", bytes = 0, total = 0)
            c.eq("unpack rows", linuxRows(), listOf(Row.DONE, Row.DONE, Row.NOW, Row.WAIT, Row.WAIT))
            c.eq("no megabytes while unpacking", megabytes, null)
            go(Page.LINUX)
            onEnv(Env.READY)
            onCatalog("0.4.0", emptyList())
            c.eq("ready rows", linuxRows(), List(5) { Row.DONE })
            c.eq("ring full", linuxFraction, 1f)
        }
        // A restart in the middle of a download: a new model fed the same bridge state shows the same progress.
        SetupModel().apply {
            open(false)
            go(Page.LINUX)
            onEnv(Env.INSTALLING, phase = "download", bytes = 600_000_000, total = 788_000_000)
            c.eq("resumed rows", linuxRows(), listOf(Row.DONE, Row.NOW, Row.WAIT, Row.WAIT, Row.WAIT))
        }

        // ANAL-394: a Linux environment without Quire's helper. Google's image says so in its build_id.
        val google = "ferrochrome/x86_64/hourly-12499-Mon Oct 05 01:03:50 UTC 2026"
        val ours = "openbook_x86_64-26110612-Fri Nov 06 12:00:00 UTC 2026"
        c.eq("google's image isn't openbook's", SetupModel.isOpenBookImage(google), false)
        c.eq("openbook's image", SetupModel.isOpenBookImage(ours), true)
        SetupModel().apply {
            c.eq("no image reported: not foreign", foreignImage, false)
            onEnv(Env.READY, image = google)
            c.eq("google's image is foreign", foreignImage, true)
            onEnv(Env.READY)
            c.eq("no news keeps the image", image, google)
            onEnv(Env.NOT_INSTALLED, image = "")
            c.eq("reset: no image", image, "")
            c.eq("reset: not foreign", foreignImage, false)
            onEnv(Env.READY, image = ours)
            c.eq("openbook's image is not foreign", foreignImage, false)
        }
        // The page stays while the bridge keeps calling the VM running; a stop or a reset replaces it.
        SetupModel().apply {
            open(false)
            go(Page.LINUX)
            onEnv(Env.READY, image = google)
            onEnv(Env.NO_HELPER, "connection reset")
            c.eq("no helper: remedy", remedy, Remedy.HELPER)
            c.eq("no helper: missing", helperMissing, true)
            onEnv(Env.READY, image = google)
            c.eq("running again keeps the way out", env, Env.NO_HELPER)
            c.eq("running again keeps the remedy", remedy, Remedy.HELPER)
            onEnv(Env.NOT_INSTALLED, image = "")
            c.eq("reset in Recovery ends it", env, Env.NOT_INSTALLED)
            c.eq("reset: set up again", remedy, Remedy.START)
        }
        // Once the helper answers, the wizard carries on by itself from the Linux page.
        SetupModel().apply {
            open(false)
            go(Page.LINUX)
            onEnv(Env.READY, image = google)
            onEnv(Env.NO_HELPER)
            onEnv(Env.READY)
            onCatalog("0.4.1", listOf(mk("claude")))
            c.eq("helper answers: ready", env, Env.READY)
            c.eq("helper answers: linux done", linuxDone, true)
            c.eq("helper answers: on to agents", page, Page.AGENTS)
        }
        // Start clean: Recovery reset it, a new image is installed and started, and its quired answers.
        SetupModel().apply {
            open(false)
            go(Page.LINUX)
            onEnv(Env.READY, image = google)
            onEnv(Env.NO_HELPER)
            onEnv(Env.NOT_INSTALLED, image = "")
            onEnv(Env.INSTALLING, phase = "unpack")
            onEnv(Env.STARTING)
            onEnv(Env.READY, image = ours)
            c.eq("after a reset: the new image is ready", env, Env.READY)
            onCatalog("0.4.0", listOf(mk("claude")))
            c.eq("after a reset: on to agents", page, Page.AGENTS)
            go(Page.LINUX)
            onCatalog("0.4.1", listOf(mk("claude")))
            c.eq("carried on once: a later catalog doesn't move the page", page, Page.LINUX)
        }
        SetupModel().apply {
            open(false)
            go(Page.LINUX)
            onEnv(Env.OLD_HELPER)
            c.eq("old helper: remedy", remedy, Remedy.HELPER)
            onCatalog("0.4.1", listOf(free))
            c.eq("updated helper with a free agent: on to try", page, Page.TRY)
        }
        SetupModel().apply {
            open(true)
            onEnv(Env.NO_HELPER)
            onCatalog("0.4.1", listOf(free))
            c.eq("on the agents page it stays there", page, Page.MANAGE)
            c.eq("on the agents page: ready", env, Env.READY)
        }
        SetupModel().apply {
            open(false)
            go(Page.LINUX)
            onEnv(Env.READY)
            onCatalog("0.4.1", listOf(mk("claude")))
            c.eq("a first answer doesn't skip the done page", page, Page.LINUX)
        }
        // The one command: the package in Downloads, copied out and checked before dpkg installs it.
        val sha = "0123456789abcdef".repeat(4)
        c.eq("package name", SetupModel.helperDebName("0.4.1"), "quired_0.4.1_amd64.deb")
        SetupModel().apply {
            c.eq("no package yet: no command", helperCommand, "")
            onHelperDeb("quired_0.4.1_amd64.deb", sha)
            c.eq("command", helperCommand, "cp /mnt/shared/Download/quired_0.4.1_amd64.deb /tmp/ && " +
                "echo \"$sha  /tmp/quired_0.4.1_amd64.deb\" | sha256sum -c && sudo dpkg -i /tmp/quired_0.4.1_amd64.deb")
            c.eq("command: no problem", helperDebProblem, "")
            onHelperDeb("", "", "This build doesn't carry it")
            c.eq("no package: no command", helperCommand, "")
            c.eq("no package: why", helperDebProblem, "This build doesn't carry it")
        }
        for (bad in listOf("quired_0.4.1_amd64.deb; rm -rf ~", "../quired_0.4.1_amd64.deb", "quired_\$(id)_amd64.deb",
            "quired_0.4.1_amd64.deb\nsudo true", "other_0.4.1_amd64.deb", "quired__amd64.deb")) SetupModel().apply {
            onHelperDeb(bad, sha)
            c.eq("unsafe name refused: $bad", helperCommand, "")
        }
        SetupModel().apply {
            onHelperDeb("quired_0.4.1_amd64.deb", "\" ; true #")
            c.eq("bad sha refused", helperCommand, "")
        }

        // Sign-in rows and the first method: code-based before a key; no account for free agents.
        val keyed = mk("hermes", installed = true, methods = listOf(SetupModel.Method("key", Kind.KEY, "")),
            keys = listOf(SetupModel.Key("OPENROUTER_API_KEY", "OpenRouter key")))
        val claude = mk("claude", installed = true, methods = listOf(SetupModel.Method("key", Kind.KEY, ""),
            SetupModel.Method("login", Kind.PASTE, "")))
        SetupModel().apply {
            onCatalog("0.4.0", listOf(free, keyed, claude))
            c.eq("free needs no account", signInRows().first { it.first.id == "opencode" }.second, SignState.NOT_NEEDED)
            c.eq("pending sign-ins", pendingSignIns, 2)
            c.eq("paste before key", claude.firstMethod?.kind, Kind.PASTE)
            c.eq("key only", keyed.firstMethod?.kind, Kind.KEY)
            c.eq("default prefers a ready agent", defaultAgent, "opencode")
        }

        // Sign-out (the Checker's Hold 2): only the maker's own logout, or a key-only agent, counts as signed out.
        SetupModel().apply {
            onCatalog("0.4.0", listOf(mk("copilot", installed = true)))
            onSignIn("copilot", SignState.IN)
            val st = afterSignOut("copilot", null, "", listOf("~/.config/quire/keys/copilot.env"),
                listOf("Run copilot, then /logout"), listOf("~/.copilot"))
            c.eq("no logout command: still signed in", st, SignState.IN)
            c.eq("no logout command: the note says what is left", signOutNote?.cleanup, listOf("~/.copilot"))
            afterSignOut("copilot", false, "", emptyList(), listOf("x"), emptyList())
            c.eq("account not signed out: state kept", signIns["copilot"], SignState.IN)
            c.eq("maker's logout ran: signed out", afterSignOut("copilot", true, "copilot logout", emptyList(),
                emptyList(), emptyList()), SignState.OUT)
            c.eq("maker's logout ran: no note", signOutNote, null)
        }

        // Only https addresses an agent printed are opened.
        c.eq("https ok", SetupModel.safeUrl("https://github.com/login/device"), true)
        c.eq("http refused", SetupModel.safeUrl("http://github.com/login/device"), false)
        c.eq("file refused", SetupModel.safeUrl("file:///sdcard/x"), false)
        c.eq("userinfo refused", SetupModel.safeUrl("https://evil@github.com/"), false)
        c.eq("intent refused", SetupModel.safeUrl("intent://x#Intent;end"), false)
        c.eq("steps index", listOf(Page.LINUX, Page.AGENTS, Page.INSTALLING, Page.SIGNIN, Page.TRY).map { SetupModel.stepIndex(it) },
            listOf(0, 1, 1, 2, 3))
    }
}
