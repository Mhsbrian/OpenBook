// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.data

import android.util.Log
import java.util.concurrent.TimeUnit

/**
 * The system's getprop and setprop, run in this app's own SELinux domain (openbook_graphics_app): it may read the
 * switcher's state (vendor.openbook.gfx.*, which the vendor policy lets system apps read) and set only
 * openbook.gfx.request (the OpenBook layer's platform policy). No hidden API is used.
 */
object SystemBackend : GfxBackend {
    private const val TAG = "OpenBookGraphics"

    override fun read(): GfxState? = run("/system/bin/getprop")?.let { GfxState.fromGetprop(it) }

    override fun send(value: String): Boolean {
        val ok = run("/system/bin/setprop", "openbook.gfx.request", value) != null
        if (!ok) Log.w(TAG, "could not set openbook.gfx.request=$value")
        return ok
    }

    override fun now(): Long = System.currentTimeMillis()

    override fun sleep(millis: Long) = Thread.sleep(millis)

    /** The command's output, or null if it failed or took longer than five seconds. */
    private fun run(vararg cmd: String): String? = runCatching {
        val p = ProcessBuilder(*cmd).redirectErrorStream(true).start()
        val out = p.inputStream.bufferedReader().use { it.readText() }
        if (!p.waitFor(5, TimeUnit.SECONDS)) {
            p.destroyForcibly()
            return null
        }
        if (p.exitValue() == 0) out else null
    }.getOrNull()
}
