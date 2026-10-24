// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.openbook.update.system.PayloadServer
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.random.Random

/** The loopback server update_engine reads the laptop's payload from. */
@RunWith(AndroidJUnit4::class)
class PayloadServerTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private fun request(url: String, method: String = "GET", range: String? = null): Triple<Int, Map<String, String>, ByteArray> {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = method
        range?.let { c.setRequestProperty("Range", it) }
        val code = c.responseCode
        val body = runCatching { (if (code < 400) c.inputStream else c.errorStream)?.readBytes() }.getOrNull() ?: ByteArray(0)
        val headers = c.headerFields.filterKeys { it != null }.mapValues { it.value.first() }.mapKeys { it.key.lowercase() }
        c.disconnect()
        return Triple(code, headers, body)
    }

    @Test fun servesTheFileWholeAndInRanges() {
        val data = Random(7).nextBytes(3 * 1024 * 1024 + 17)
        val file = File(context.cacheDir, "payload.bin").apply { writeBytes(data) }
        PayloadServer(file).use { server ->
            assertTrue(server.url.startsWith("http://127.0.0.1:"))
            val (code, headers, body) = request(server.url)
            assertEquals(200, code)
            assertEquals(data.size.toString(), headers["content-length"])
            assertArrayEquals(data, body)
            val (c2, h2, b2) = request(server.url, range = "bytes=1000-1999")
            assertEquals(206, c2)
            assertEquals("bytes 1000-1999/${data.size}", h2["content-range"])
            assertArrayEquals(data.copyOfRange(1000, 2000), b2)
            val (c3, _, b3) = request(server.url, range = "bytes=${data.size - 5}-")
            assertEquals(206, c3)
            assertArrayEquals(data.copyOfRange(data.size - 5, data.size), b3)
            assertEquals(416, request(server.url, range = "bytes=${data.size}-").first)
            assertEquals(200, request(server.url, method = "HEAD").first)
        }
    }

    @Test fun answersNothingElse() {
        val file = File(context.cacheDir, "payload2.bin").apply { writeBytes(ByteArray(10)) }
        PayloadServer(file).use { server ->
            val other = server.url.replaceAfterLast("/", "other.bin")
            assertEquals(404, request(other).first)
            val guess = server.url.substringBefore("127.0.0.1:") + "127.0.0.1:" + server.url.substringAfter("127.0.0.1:").substringBefore("/") + "/payload.bin"
            assertEquals(404, request(guess).first)
            assertEquals(405, request(server.url, method = "DELETE").first)
        }
    }
}
