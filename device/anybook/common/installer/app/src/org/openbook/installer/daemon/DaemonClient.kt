// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.daemon

import android.net.LocalSocket
import android.net.LocalSocketAddress
import android.util.Log
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.Closeable
import java.io.EOFException
import java.io.IOException
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.nio.charset.StandardCharsets
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONException
import org.json.JSONObject

/**
 * Client for openbook-installd (PROTOCOL.md): newline-delimited JSON over the reserved UNIX socket
 * `/dev/socket/openbook_installd`.
 *
 * One connection is kept open and requests are serialised on it (the daemon answers them in order and serves one
 * connection at a time). All I/O runs on [Dispatchers.IO]. A dropped connection is reopened on the next request;
 * [stream] callers handle [IOException] themselves (the install keeps running in the daemon; see `attach`).
 */
class DaemonClient(private val socketName: String = SOCKET_NAME) : Closeable {
    private val ids = AtomicInteger(1)
    private val lock = Mutex()

    @Volatile private var socket: LocalSocket? = null
    private var reader: BufferedReader? = null
    private var writer: BufferedWriter? = null

    /** Sends [cmd] and returns its final `"ok": true` message; throws [DaemonException] or [IOException]. */
    suspend fun request(
        cmd: String,
        timeoutMs: Int = DEFAULT_TIMEOUT_MS,
        retryOnce: Boolean = true,
        args: JSONObject.() -> Unit = {},
    ): JSONObject = withContext(Dispatchers.IO) {
        lock.withLock {
            try {
                exchange(cmd, timeoutMs, args)
            } catch (e: IOException) {
                closeLocked()
                if (!retryOnce) throw e
                Log.w(TAG, "$cmd: ${e.message}; reconnecting once")
                try {
                    exchange(cmd, timeoutMs, args)
                } catch (e2: IOException) {
                    closeLocked()
                    throw e2
                }
            }
        }
    }

    private fun exchange(cmd: String, timeoutMs: Int, args: JSONObject.() -> Unit): JSONObject {
        val id = send(cmd, args)
        socket?.soTimeout = timeoutMs
        while (true) {
            val msg = readMessage() ?: throw EOFException("openbook-installd closed the connection")
            if (msg.optInt("id", -1) != id || msg.has("event")) continue
            if (!msg.optBoolean("ok", false)) {
                throw DaemonException(msg.text("code").ifEmpty { "internal" }, msg.text("error"), msg)
            }
            return msg
        }
    }

    /**
     * Sends a streaming command (`apply` or `attach`) and emits every message for it: events, then the final message
     * (as [InstallEvent.Final]), after which the flow completes. Throws [IOException] if the connection drops.
     */
    fun stream(cmd: String, args: JSONObject.() -> Unit = {}): Flow<InstallEvent> = flow {
        lock.withLock {
            try {
                val id = send(cmd, args)
                socket?.soTimeout = STREAM_IDLE_TIMEOUT_MS
                while (true) {
                    val msg = readMessage() ?: throw EOFException("openbook-installd closed the connection")
                    if (msg.optInt("id", -1) != id) continue
                    val event = Parse.event(msg) ?: continue
                    emit(event)
                    if (event is InstallEvent.Final) break
                }
            } catch (e: IOException) {
                closeLocked()
                throw e
            }
        }
    }.flowOn(Dispatchers.IO)

    private fun connectLocked() {
        if (socket != null) return
        val s = LocalSocket(LocalSocket.SOCKET_STREAM)
        try {
            s.connect(LocalSocketAddress(socketName, LocalSocketAddress.Namespace.RESERVED))
        } catch (e: IOException) {
            try { s.close() } catch (_: IOException) {}
            throw e
        }
        socket = s
        reader = BufferedReader(InputStreamReader(s.inputStream, StandardCharsets.UTF_8))
        writer = BufferedWriter(OutputStreamWriter(s.outputStream, StandardCharsets.UTF_8))
    }

    private fun send(cmd: String, args: JSONObject.() -> Unit): Int {
        connectLocked()
        val id = ids.getAndIncrement()
        val msg = JSONObject().put("id", id).put("cmd", cmd).apply(args)
        val w = writer ?: throw IOException("not connected")
        w.write(msg.toString())
        w.write("\n")
        w.flush()
        return id
    }

    private fun readMessage(): JSONObject? {
        val r = reader ?: throw IOException("not connected")
        while (true) {
            val line = r.readLine() ?: return null
            if (line.isBlank()) continue
            try {
                return JSONObject(line)
            } catch (e: JSONException) {
                Log.w(TAG, "ignoring a line that is not JSON: ${line.take(200)}")
            }
        }
    }

    private fun closeLocked() {
        val s = socket
        socket = null
        reader = null
        writer = null
        try { s?.close() } catch (_: IOException) {}
    }

    /** Closes the connection; a blocked read in another thread fails with an [IOException]. */
    override fun close() {
        val s = socket
        try { s?.shutdownInput() } catch (_: IOException) {}
        try { s?.close() } catch (_: IOException) {}
    }

    companion object {
        private const val TAG = "OpenBookInstaller"
        const val SOCKET_NAME = "openbook_installd"
        const val DEFAULT_TIMEOUT_MS = 60_000

        /** `plan` hashes and checks the target; give it longer. */
        const val PLAN_TIMEOUT_MS = 180_000

        /** No message at all for this long during an install counts as a dropped connection (then: attach). */
        const val STREAM_IDLE_TIMEOUT_MS = 300_000
    }
}
