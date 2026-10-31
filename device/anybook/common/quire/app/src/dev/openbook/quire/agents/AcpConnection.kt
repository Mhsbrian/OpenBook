// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.agents

import java.io.BufferedReader
import java.io.Closeable
import java.io.IOException
import java.io.InputStream
import java.io.InputStreamReader
import java.io.OutputStream
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import java.util.concurrent.atomic.AtomicLong
import kotlin.concurrent.thread
import org.json.JSONObject

/** A JSON-RPC error from the peer, or one a handler returns to it. */
class AcpError(val code: Int, message: String, val data: Any? = null) : Exception(message) {
    companion object {
        const val METHOD_NOT_FOUND = -32601
        const val INVALID_PARAMS = -32602
        const val INTERNAL = -32603
        const val AUTH_REQUIRED = -32000
    }
}

/**
 * One JSON-RPC 2.0 connection framed as newline-delimited JSON, which is how ACP travels on a stream. This is the
 * Kotlin side of quired's `internal/acp` (quire/quired): notifications are handled on the read thread, in order;
 * requests from the peer each get a thread, because answering one may wait for a person.
 */
class AcpConnection(
    input: InputStream,
    private val output: OutputStream,
    private val handler: Handler,
    /** Ends the transport on [close]: it must make the read side see EOF (shut a socket down, close a pipe). */
    private val transport: Closeable,
) : Closeable {
    interface Handler {
        fun onNotification(method: String, params: JSONObject)

        /** Answers a request from the peer; may block. Throw [AcpError] to choose the error the peer sees. */
        fun onRequest(method: String, params: JSONObject): Any?

        /** The peer went away, or [close] was called. */
        fun onClosed(cause: Throwable?) {}
    }

    private val pending = ConcurrentHashMap<Long, CompletableFuture<JSONObject>>()
    private val nextId = AtomicLong()
    private val writeLock = Any()
    private val requests = Executors.newCachedThreadPool { r -> Thread(r, "acp-request") }

    @Volatile
    var isClosed = false
        private set

    init {
        thread(name = "acp-read", isDaemon = true) { readLoop(input) }
    }

    /** Sends a request and waits up to [timeoutMs] for its result (an ACP result is always an object). */
    fun call(method: String, params: JSONObject, timeoutMs: Long): JSONObject {
        val id = nextId.incrementAndGet()
        val reply = CompletableFuture<JSONObject>()
        pending[id] = reply
        try {
            send(JSONObject().put("jsonrpc", "2.0").put("id", id).put("method", method).put("params", params))
            return reply.get(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (e: ExecutionException) {
            throw e.cause ?: e
        } catch (e: TimeoutException) {
            throw IOException("$method: no answer in $timeoutMs ms")
        } finally {
            pending.remove(id)
        }
    }

    fun notify(method: String, params: JSONObject) {
        send(JSONObject().put("jsonrpc", "2.0").put("method", method).put("params", params))
    }

    private fun send(message: JSONObject) {
        if (isClosed) throw IOException("the connection is closed")
        val bytes = (message.toString() + "\n").toByteArray(Charsets.UTF_8)
        synchronized(writeLock) {
            output.write(bytes)
            output.flush()
        }
    }

    private fun readLoop(input: InputStream) {
        var cause: Throwable? = null
        try {
            val reader = BufferedReader(InputStreamReader(input, Charsets.UTF_8), 1 shl 16)
            while (true) {
                val line = reader.readLine() ?: break // no line limit: answers can be long
                val trimmed = line.trim()
                if (!trimmed.startsWith("{")) continue
                val m = try { JSONObject(trimmed) } catch (e: Exception) { continue }
                dispatch(m)
            }
        } catch (e: Throwable) {
            cause = e
        }
        end(cause)
    }

    private fun dispatch(m: JSONObject) {
        val method = m.optString("method", "")
        val hasId = m.has("id") && !m.isNull("id")
        when {
            method.isNotEmpty() && !hasId -> handler.onNotification(method, m.optJSONObject("params") ?: JSONObject())
            method.isNotEmpty() -> requests.execute { answer(m.get("id"), method, m.optJSONObject("params") ?: JSONObject()) }
            hasId -> {
                val id = m.optLong("id", -1)
                val reply = pending[id] ?: return
                val error = m.optJSONObject("error")
                if (error != null) {
                    reply.completeExceptionally(
                        AcpError(error.optInt("code"), error.optString("message"), error.opt("data")))
                } else {
                    reply.complete(m.optJSONObject("result") ?: JSONObject())
                }
            }
        }
    }

    private fun answer(id: Any, method: String, params: JSONObject) {
        val reply = JSONObject().put("jsonrpc", "2.0").put("id", id)
        try {
            reply.put("result", handler.onRequest(method, params) ?: JSONObject.NULL)
        } catch (e: AcpError) {
            reply.put("error", JSONObject().put("code", e.code).put("message", e.message ?: "").putOpt("data", e.data))
        } catch (e: Exception) {
            reply.put("error", JSONObject().put("code", AcpError.INTERNAL).put("message", e.toString()))
        }
        try {
            send(reply)
        } catch (_: IOException) {
            // The peer has gone; it can't be told anything.
        }
    }

    private fun end(cause: Throwable?) {
        if (isClosed) return
        isClosed = true
        val closed = IOException("the connection closed", cause)
        pending.values.forEach { it.completeExceptionally(closed) }
        requests.shutdownNow()
        handler.onClosed(cause)
    }

    override fun close() {
        try {
            transport.close()
        } catch (_: IOException) {
        }
        end(null)
    }
}
