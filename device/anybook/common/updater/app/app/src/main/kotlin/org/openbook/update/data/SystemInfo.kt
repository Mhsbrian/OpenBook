// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.data

import android.os.Build
import java.util.concurrent.TimeUnit

/** The running system: Google's build, its security patch and the A/B slot it booted from. */
data class SystemInfo(
    val buildId: String,
    val incremental: String,
    val securityPatch: String,
    val fingerprint: String,
    val slot: String?,
) {
    val mark get() = SystemMark(fingerprint, incremental, buildId, slot)

    companion object {
        /** Spawns getprop: call off the main thread. */
        fun read() = basic().copy(slot = slot())

        /** Without the slot, from the build constants only (no process). */
        fun basic() = SystemInfo(Build.ID, Build.VERSION.INCREMENTAL, Build.VERSION.SECURITY_PATCH, Build.FINGERPRINT, null)

        /** ro.boot.slot_suffix ("_a"/"_b"; readable by every domain), null on a non-A/B device or on failure. */
        private fun slot(): String? = runCatching {
            val p = ProcessBuilder("/system/bin/getprop", "ro.boot.slot_suffix").redirectErrorStream(true).start()
            if (!p.waitFor(5, TimeUnit.SECONDS)) {
                p.destroyForcibly()
                return null
            }
            p.inputStream.bufferedReader().readText().trim().takeIf { it == "_a" || it == "_b" }
        }.getOrNull()
    }
}

/** What identifies the installed system across a restart. */
data class SystemMark(val fingerprint: String, val incremental: String, val buildId: String, val slot: String?)
