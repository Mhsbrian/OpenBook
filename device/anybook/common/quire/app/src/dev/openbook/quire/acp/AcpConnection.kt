// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.acp

import android.util.Log
import dev.openbook.quire.Quire.TAG
import java.io.BufferedReader
import java.io.Closeable
import java.io.IOException
import java.io.InputStream
import java.io.InputStreamReader
import java.io.OutputStream
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import org.json.JSONException
import org.json.JSONObject

/**
 * JSON-RPC 2.0 over newline-delimited JSON, the transport ACP uses (docs/quire.md §6, the same framing as `quired`'s
 * internal/acp). One reader thread delivers notifications in order and hands requests to [Handler.onRequest], which
 * may answer later from any thread, so a permission card can wait for the person. One writer thread does all the
 * writing. Lines that are not JSON are logged and skipped. Closing the stream fails every pending call.
 */
class AcpConnection(
    input: InputStream,
    private val output: OutputStream,
    private val handler: Handler,
    private val name: String,
    /** The stream's owner, when [input] and [output] don't end a blocked read by closing (Link). */
    private val transport: Link? = null,
) : Closeable {
    interface Handler {
        /** A notification from the peer, on the reader thread, in order. */
        fun onNotification(method: String, params: JSONObject)

        /** A request from the peer. Answer it once through [reply], from any thread. */
        fun onRequest(method: String, params: JSONObject, reply: Reply)

        /** The connection ended: [error] is null for a clean end of stream. */
        fun onClosed(error: Throwable?)
    }

    class RpcError(val code: Int, override val message: String, val data: Any? = null) : Exception(message) {
        override fun toString() = "RpcError($code, $message)"
    }

    /** The answer to one request from the peer. Only the first call counts. */
    inner class Reply internal constructor(private val id: Any) {
        private val sent = AtomicBoolean(false)

        fun result(result: Any) {
            if (sent.compareAndSet(false, true)) write(JSONObject().put("jsonrpc", "2.0").put("id", id).put("result", result))
        }

        fun error(code: Int, message: String) {
            if (sent.compareAndSet(false, true)) {
                write(JSONObject().put("jsonrpc", "2.0").put("id", id)
                    .put("error", JSONObject().put("code", code).put("message", message)))
            }
        }
    }

    private val reader = BufferedReader(InputStreamReader(input, Charsets.UTF_8))
    private val writer = Executors.newSingleThreadExecutor { r -> Thread(r, "acp-write-$name") }
    private val pending = ConcurrentHashMap<Long, (Result<Any?>) -> Unit>()
    private val nextId = AtomicLong(1)
    private val closed = AtomicBoolean(false)
    private val started = AtomicBoolean(false)

    fun start() {
        started.set(true)
        Thread({ readLoop() }, "acp-read-$name").start()
    }

    /** Calls [method] on the peer; [done] gets the result, or an [RpcError] or [IOException], on the reader thread. */
    fun request(method: String, params: JSONObject, done: (Result<Any?>) -> Unit) {
        if (closed.get()) {
            done(Result.failure(IOException("connection closed")))
            return
        }
        val id = nextId.getAndIncrement()
        pending[id] = done
        write(JSONObject().put("jsonrpc", "2.0").put("id", id).put("method", method).put("params", params))
    }

    fun notify(method: String, params: JSONObject) {
        write(JSONObject().put("jsonrpc", "2.0").put("method", method).put("params", params))
    }

    private fun write(message: JSONObject) {
        if (closed.get()) return
        val line = message.toString() + "\n"
        try {
            writer.execute {
                try {
                    output.write(line.toByteArray(Charsets.UTF_8))
                    output.flush()
                } catch (e: IOException) {
                    shutdown(e)
                }
            }
        } catch (e: java.util.concurrent.RejectedExecutionException) {
            // Closed meanwhile.
        }
    }

    private fun readLoop() {
        var error: Throwable? = null
        try {
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isBlank()) continue
                val message = try {
                    JSONObject(line)
                } catch (e: JSONException) {
                    Log.w(TAG, "acp[$name]: skipped a line that is not JSON (${line.length} chars)")
                    continue
                }
                dispatch(message)
            }
        } catch (e: IOException) {
            if (!closed.get()) error = e
        }
        shutdown(error)
        // The transport is released here, after the last read, on end of stream, an error or close(): never while a
        // read may still use its descriptor, whose number the system may give to the next file opened.
        transport?.close()
    }

    private fun dispatch(message: JSONObject) {
        val method = message.optString("method", "")
        val hasId = message.has("id") && !message.isNull("id")
        when {
            method.isNotEmpty() && hasId -> {
                val reply = Reply(message.get("id"))
                try {
                    handler.onRequest(method, message.optJSONObject("params") ?: JSONObject(), reply)
                } catch (e: RuntimeException) {
                    Log.e(TAG, "acp[$name]: request handler failed for $method", e)
                    reply.error(INTERNAL_ERROR, "internal error")
                }
            }
            method.isNotEmpty() -> handler.onNotification(method, message.optJSONObject("params") ?: JSONObject())
            hasId -> {
                val id = message.optLong("id", -1)
                val done = pending.remove(id) ?: return
                val err = message.optJSONObject("error")
                if (err != null) {
                    done(Result.failure(RpcError(err.optInt("code"), err.optString("message"), err.opt("data"))))
                } else {
                    done(Result.success(message.opt("result")))
                }
            }
        }
    }

    private fun shutdown(error: Throwable?) {
        if (!closed.compareAndSet(false, true)) return
        writer.shutdown()
        try {
            output.close()
        } catch (e: IOException) {
            // Already gone.
        }
        val failure = IOException("connection closed", error)
        pending.values.forEach { it(Result.failure(failure)) }
        pending.clear()
        handler.onClosed(error)
    }

    override fun close() {
        shutdown(null)
        // Before waiting for the reader: a read blocked on a stream that doesn't own its descriptor ends only when the
        // transport is shut down, and reader.close() waits for that read. The reader thread then releases it.
        transport?.shutdown()
        if (!started.get()) transport?.close()
        try {
            reader.close()
        } catch (e: IOException) {
            // Already gone.
        }
    }

    companion object {
        const val METHOD_NOT_FOUND = -32601
        const val INTERNAL_ERROR = -32603
        const val AUTH_REQUIRED = -32000
    }
}
