// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package android.os

class Bundle(private val state: String?, private val message: String? = null) {
    fun getString(key: String) = if (key == "state") state else message
}

class ParcelFileDescriptor

/** A clock that only moves when Connectors sleeps, so the waits are exact and instant. */
object SystemClock {
    var now = 1_000L
    fun elapsedRealtime() = now
    fun sleep(ms: Long) { now += ms }
}

object SystemProperties {
    fun getBoolean(key: String, def: Boolean) = true
}

class PowerExemptionManager(private val context: android.content.Context) {
    fun addToTemporaryAllowList(pkg: String, reason: Int, why: String, ms: Long) {
        context.exemptions += "$pkg:$ms"
    }
    companion object {
        const val REASON_OTHER = 1
    }
}
