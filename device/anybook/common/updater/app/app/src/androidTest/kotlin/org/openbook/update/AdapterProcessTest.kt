// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.TimeUnit
import kotlin.random.Random

/**
 * openbook-adapt (a static Go binary) as a child of an app process: Android's app seccomp filter and the
 * app sandbox apply, as they do to the engine. It hashes, writes and signs with its worker threads here.
 * Needs /system/bin/openbook-adapt (emulator-test.sh pushes it when ADAPT_BIN is set); skipped otherwise.
 */
@RunWith(AndroidJUnit4::class)
class AdapterProcessTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val adapter = File("/system/bin/openbook-adapt")

    private fun run(vararg args: String): Pair<Int, String> {
        val p = ProcessBuilder(listOf(adapter.path) + args).redirectErrorStream(true).start()
        val out = p.inputStream.bufferedReader().readText()
        check(p.waitFor(120, TimeUnit.SECONDS)) { "openbook-adapt did not finish" }
        return p.exitValue() to out
    }

    @Test fun runsInTheAppSandbox() {
        assumeTrue("no /system/bin/openbook-adapt on this device", adapter.canExecute())
        val img = File(context.cacheDir, "system.img").apply { writeBytes(Random(3).nextBytes(8 * 1024 * 1024)) }
        val salt = "ab".repeat(32)
        val (rc, out) = run("hashtree-footer", "--image", img.path, "--partition-size", (16L * 1024 * 1024).toString(),
                            "--name", "system", "--salt", salt)
        assertEquals(out, 0, rc)
        assertEquals(16L * 1024 * 1024, img.length())
        // A usage error is reported, not a crash (a seccomp kill would be signal 31: exit 159).
        assertEquals(2, run("no-such-command").first)
    }
}
