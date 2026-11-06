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
            Triple(Env.OLD_HELPER, Remedy.OLD_HELPER, listOf(Row.DONE, Row.DONE, Row.DONE, Row.DONE, Row.FAILED)),
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
