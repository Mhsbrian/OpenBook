// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire

import android.app.Application
import dev.openbook.quire.agents.Agents
import dev.openbook.quire.control.ComputerControl
import dev.openbook.quire.note.QuireSurface
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class QuireApplication : Application() {
    /** The one computer-control session Quire may hold (the platform allows one at a time). */
    lateinit var computerControl: ComputerControl
        private set

    /** The agents Quire reaches: in the Linux environment, or on a paired computer (ANAL-218). */
    lateinit var agents: Agents
        private set

    /** The note and its tasks (docs/quire-design.md). */
    lateinit var surface: QuireSurface
        private set

    /** Disk work: screenshots and invocation records. */
    val io: ExecutorService = Executors.newSingleThreadExecutor()

    /** Agent work: connecting to quired and prompt turns, which can take minutes. */
    val agentWork: ExecutorService = Executors.newCachedThreadPool()

    override fun onCreate() {
        super.onCreate()
        computerControl = ComputerControl(this)
        agents = Agents(this)
        surface = QuireSurface(this)
    }
}
