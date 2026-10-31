// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// agents/Connectors.kt's start and wait against a scripted agent bridge (tools/connector-test.sh), ANAL-225. The first
// four cases are the Checker's (ANAL-217 review of PR #113 at dcaa459).

package dev.openbook.quire.test

import android.content.Context
import android.os.SystemClock
import dev.openbook.quire.agents.Connectors

private var passed = 0
private var failed = 0

private fun case(name: String, states: List<String>, expected: Connectors.State, reply: String = "starting",
    message: String? = null, enabled: Boolean = true, extra: (Context, Connectors.Status, Long) -> String? = { _, _, _ -> null }) {
    val ctx = Context()
    ctx.contentResolver.states.addAll(states)
    ctx.contentResolver.startReply = reply
    ctx.contentResolver.startMessage = message
    ctx.packageManager.terminalEnabled = enabled
    val t0 = SystemClock.now
    val s = Connectors.LinuxEnvironment.ensureRunning(ctx, 120_000L)
    val waited = SystemClock.now - t0
    val problem = if (s.state != expected) "got ${s.state}" else extra(ctx, s, waited)
    println("${if (problem == null) "PASS" else "FAIL"} $name: ${s.state}, waited $waited ms, starts=${ctx.contentResolver.starts}" +
        (s.detail?.let { ", detail=$it" } ?: "") + (problem?.let { " ($it)" } ?: ""))
    if (problem == null) passed++ else failed++
}

fun main() {
    case("normal start", listOf("stopped", "starting", "running"), Connectors.State.READY)
    case("start accepted before the Terminal app publishes starting", listOf("stopped", "stopped", "starting", "running"),
        Connectors.State.READY)
    case("a moment of error during the start", listOf("stopped", "starting", "error", "running"), Connectors.State.READY)
    case("a refused start keeps its reason", listOf("stopped", "stopped"), Connectors.State.ERROR, reply = "error",
        message = "precise start failure") { _, s, _ -> if (s.detail == "precise start failure") null else "lost the reason" }
    case("a start that never happens is given up after the publish lag", listOf("stopped", "stopped"),
        Connectors.State.STOPPED) { _, _, w -> if (w in 10_000L..20_000L) null else "waited $w ms" }
    case("an error that lasts is reported after the grace", listOf("stopped", "error"), Connectors.State.ERROR) { _, _, w ->
        if (w in 20_000L..30_000L) null else "waited $w ms"
    }
    case("not installed: installed, then started", listOf("not_installed", "installing", "installing", "starting", "running"),
        Connectors.State.READY, reply = "installing")
    case("the Terminal app gets its exemption before the start", listOf("stopped", "running"), Connectors.State.READY) { c, _, _ ->
        if (c.exemptions.size == 1 && c.contentResolver.starts == 1) null else "exemptions=${c.exemptions}"
    }
    case("running: no start", listOf("running"), Connectors.State.READY) { c, _, _ ->
        if (c.contentResolver.starts == 0) null else "started anyway"
    }
    case("off: not started (that is the note's Set up)", listOf("stopped"), Connectors.State.TERMINAL_OFF, enabled = false) { c, _, _ ->
        if (c.contentResolver.starts == 0) null else "started anyway"
    }
    println("RESULT $passed passed, $failed failed")
    kotlin.system.exitProcess(if (failed == 0) 0 else 1)
}
