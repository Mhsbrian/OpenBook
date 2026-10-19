// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// tools/connector-test.sh: just enough of the Android classes agents/Connectors.kt uses, so the real file runs on the
// host JVM against a scripted agent bridge (after the Checker's probe in the ANAL-217 review of PR #113 at dcaa459).

package android.content

import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.os.PowerExemptionManager

class Context {
    val packageManager = PackageManager()
    val contentResolver = ContentResolver()
    val exemptions = mutableListOf<String>()
    fun getString(id: Int) = "message-$id"
    fun <T> getSystemService(cls: Class<T>): T? = cls.cast(PowerExemptionManager(this))
}

/** The agent bridge: status answers come from [states] (the last one repeats); start answers [startReply]. */
class ContentResolver {
    val states = ArrayDeque<String>()
    var startReply = "starting"
    var startMessage: String? = null
    var starts = 0
    var statusCalls = 0
    fun call(authority: String, method: String, arg: String?, extras: Bundle?): Bundle {
        if (method == "start") {
            starts++
            return Bundle(startReply, startMessage)
        }
        statusCalls++
        return Bundle(if (states.size > 1) states.removeFirst() else states.first())
    }
    fun openFileDescriptor(uri: Uri, mode: String): ParcelFileDescriptor? = null
}
