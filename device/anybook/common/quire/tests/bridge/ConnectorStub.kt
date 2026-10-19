// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.agents

import android.content.Context
import android.os.ParcelFileDescriptor

// tools/bridge-test.sh: only the platform boundary (the Terminal app's status and its descriptor) is substituted; the
// client and directory under test are the app's own sources.
object Connectors {
    enum class State { READY, STOPPED }
    class Status(val state: State) { fun describe(context: Context) = "Linux environment stopped" }
    object LinuxEnvironment {
        var ready = true
        var opens = 0
        lateinit var next: ParcelFileDescriptor
        fun status(context: Context) = Status(if (ready) State.READY else State.STOPPED)
        fun connect(context: Context): ParcelFileDescriptor { opens++; return next }
    }
}
