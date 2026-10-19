// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire

import android.app.Application
import dev.openbook.quire.control.ComputerControl
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class QuireApplication : Application() {
    /** The one computer-control session Quire may hold (the platform allows one at a time). */
    lateinit var computerControl: ComputerControl
        private set

    /** Disk work: screenshots and invocation records. */
    val io: ExecutorService = Executors.newSingleThreadExecutor()

    override fun onCreate() {
        super.onCreate()
        computerControl = ComputerControl(this)
    }
}
