// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.system

import android.util.Log
import java.io.BufferedInputStream
import java.io.Closeable
import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.io.RandomAccessFile
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException
import java.security.SecureRandom
import java.util.concurrent.Executors

/**
 * Serves one payload file to update_engine over HTTP on the loopback interface, the way OpenBook's host
 * tooling serves it over adb (update_engine streams payloads from an http:// URL). Only GET and HEAD of an
 * unguessable path, with single byte ranges; nothing else is answered. Lives while an install runs.
 */
class PayloadServer(private val file: File) : Closeable {
    // IPv4 loopback, the address in [url] (Android's getLoopbackAddress() is ::1).
    private val socket = ServerSocket(0, 8, InetAddress.getByAddress(byteArrayOf(127, 0, 0, 1)))
    private val token = ByteArray(16).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
    private val pool = Executors.newFixedThreadPool(4)
    private val path = "/$token/payload.bin"
    val url: String get() = "http://127.0.0.1:${socket.localPort}$path"

    init {
        pool.execute { acceptLoop() }
    }

    private fun acceptLoop() {
        while (!socket.isClosed) {
            val client = try { socket.accept() } catch (e: SocketException) { return }
            pool.execute { runCatching { client.use(::serve) }.onFailure { Log.d(TAG, "payload request ended: $it") } }
        }
    }

    private fun readLine(input: InputStream): String? {
        val sb = StringBuilder()
        while (true) {
            val c = input.read()
            if (c < 0) return if (sb.isEmpty()) null else sb.toString()
            if (c == '\n'.code) return sb.toString().trimEnd('\r')
            if (sb.length > 8192) return null
            sb.append(c.toChar())
        }
    }

    private fun serve(client: Socket) {
        client.soTimeout = 60_000
        val input = BufferedInputStream(client.getInputStream())
        val out = client.getOutputStream()
        while (true) { // keep-alive: update_engine may reuse the connection
            val request = readLine(input) ?: return
            val headers = generateSequence { readLine(input)?.takeIf { it.isNotEmpty() } }.toList()
            val (method, target) = request.split(' ').let { if (it.size >= 2) it[0] to it[1] else return }
            if (method != "GET" && method != "HEAD") return status(out, 405, "Method Not Allowed")
            if (target != path) return status(out, 404, "Not Found")
            val size = file.length()
            val range = headers.firstOrNull { it.startsWith("range:", ignoreCase = true) }?.substringAfter(':')?.trim()
            var start = 0L
            var end = size - 1
            var partial = false
            if (range != null) {
                val m = Regex("""bytes=(\d*)-(\d*)""").matchEntire(range) ?: return status(out, 416, "Range Not Satisfiable")
                val (a, b) = m.destructured
                when {
                    a.isNotEmpty() -> { start = a.toLong(); if (b.isNotEmpty()) end = minOf(b.toLong(), size - 1) }
                    b.isNotEmpty() -> start = maxOf(size - b.toLong(), 0)
                    else -> return status(out, 416, "Range Not Satisfiable")
                }
                if (start > end || start >= size) return status(out, 416, "Range Not Satisfiable")
                partial = true
            }
            val length = end - start + 1
            val head = buildString {
                append(if (partial) "HTTP/1.1 206 Partial Content\r\n" else "HTTP/1.1 200 OK\r\n")
                append("Content-Type: application/octet-stream\r\nAccept-Ranges: bytes\r\n")
                append("Content-Length: $length\r\n")
                if (partial) append("Content-Range: bytes $start-$end/$size\r\n")
                append("\r\n")
            }
            out.write(head.toByteArray(Charsets.US_ASCII))
            if (method == "GET") copy(start, length, out)
            out.flush()
        }
    }

    private fun copy(start: Long, length: Long, out: OutputStream) {
        RandomAccessFile(file, "r").use { f ->
            f.seek(start)
            val buf = ByteArray(1 shl 20)
            var left = length
            while (left > 0) {
                val n = f.read(buf, 0, minOf(buf.size.toLong(), left).toInt())
                if (n < 0) break
                out.write(buf, 0, n)
                left -= n
            }
        }
    }

    private fun status(out: OutputStream, code: Int, text: String) {
        out.write("HTTP/1.1 $code $text\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".toByteArray(Charsets.US_ASCII))
        out.flush()
    }

    override fun close() {
        runCatching { socket.close() }
        pool.shutdownNow()
    }

    companion object {
        private const val TAG = "OpenBookUpdate"
    }
}
