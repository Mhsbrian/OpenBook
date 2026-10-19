// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.acp

import android.content.Context
import android.system.ErrnoException
import android.system.Os
import android.system.OsConstants
import android.util.Log
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.agents.Connectors
import java.io.Closeable
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.Executor
import java.util.concurrent.Executors
import org.json.JSONArray
import org.json.JSONObject

/** An open byte stream to an ACP agent. */
class Link(val input: InputStream, val output: OutputStream, private val onClose: Closeable) : Closeable {
    override fun close() = onClose.close()
}

/**
 * Where an agent is reached. `linux:<agent>` is an agent in the laptop's Linux environment: `quired serve` in the
 * Debian guest, over vsock through the Terminal app's agent bridge (agents/Connectors.kt, ANAL-218), with the agent
 * named in [quiredAgent]. `tcp:<host>:<port>` is a loopback address, which debuggable builds use to reach an agent on
 * the host through `adb reverse` (scripts/quire/q5-acp-agent.py, or a real ACP agent behind socat). Pairing adds an
 * authenticated LAN link.
 */
data class Endpoint(
    val id: String,
    /** The agent's name until `initialize` reports its own. */
    val name: String,
    /** Shown after the name: "on this laptop", or the paired computer's name. */
    val where: String,
    val address: String,
    /** The working directory sent in `session/new`, in the agent's own file system. */
    val cwd: String,
    /** False for a paired computer: unreachable means offline, not broken. */
    val local: Boolean,
) {
    /**
     * The agent `quired serve` routes this endpoint's sessions to (its `_meta.quire.agent`), or null for an endpoint
     * that is the agent itself.
     */
    val quiredAgent: String?
        get() = address.removePrefix(LINUX).takeIf { address.startsWith(LINUX) && it.isNotEmpty() }

    /** Opens the link. Blocks; call off the main thread. */
    fun open(context: Context): Link {
        if (quiredAgent != null) return openLinux(context)
        val parts = address.split(":")
        require(parts.size == 3 && parts[0] == "tcp") { "unsupported address $address" }
        val host = InetAddress.getByName(parts[1])
        // Only loopback: the host side is adb's reverse forward. Nothing on the network can be reached this way.
        require(host.isLoopbackAddress) { "only loopback addresses are allowed: $address" }
        val socket = Socket()
        socket.connect(InetSocketAddress(host, parts[2].toInt()), CONNECT_TIMEOUT_MS)
        socket.tcpNoDelay = true
        return Link(socket.getInputStream(), socket.getOutputStream(), socket)
    }

    /** A stream to quired in the Linux environment; when it can't be used, the error says why (Connectors). */
    private fun openLinux(context: Context): Link {
        val status = Connectors.LinuxEnvironment.status(context)
        if (status.state != Connectors.State.READY) throw IOException(status.describe(context))
        val pfd = Connectors.LinuxEnvironment.connect(context)
        return Link(FileInputStream(pfd.fileDescriptor), FileOutputStream(pfd.fileDescriptor), Closeable {
            // quired sees EOF and stops the agent it started for this connection (agents/AgentHost.kt).
            try {
                Os.shutdown(pfd.fileDescriptor, OsConstants.SHUT_RDWR)
            } catch (_: ErrnoException) {
            }
            pfd.close()
        })
    }

    companion object {
        const val CONNECT_TIMEOUT_MS = 3000
        const val LINUX = "linux:"
    }
}

/** What `initialize` told us about the agent. */
data class AgentInfo(
    val name: String,
    val title: String?,
    val version: String?,
    val authMethods: List<AuthMethod>,
    val images: Boolean,
)

data class AuthMethod(val id: String, val name: String, val description: String?)

/**
 * Quire core's side of one ACP agent (docs/quire.md §4: the core is an ACP client). Calls are asynchronous; every
 * callback runs on [main]. Quire offers the agent no file system and no terminal: an agent uses its own tools, and asks
 * the person through `session/request_permission` when its policy says to.
 */
class AcpAgent(
    private val context: Context,
    val endpoint: Endpoint,
    private val listener: Listener,
    private val main: Executor,
) {
    interface Listener {
        fun onUpdate(agent: AcpAgent, sessionId: String, update: JSONObject)

        /** [answer] takes ACP's `outcome` object; call it once. */
        fun onPermission(agent: AcpAgent, sessionId: String, request: JSONObject, answer: (JSONObject) -> Unit)

        fun onClosed(agent: AcpAgent, error: Throwable?)
    }

    private val io = Executors.newSingleThreadExecutor { r -> Thread(r, "acp-open-${endpoint.id}") }
    private var link: Link? = null
    private var connection: AcpConnection? = null

    @Volatile var info: AgentInfo? = null
        private set

    val connected: Boolean
        get() = connection != null

    /** Opens the link and runs `initialize`. */
    fun connect(done: (Result<AgentInfo>) -> Unit) {
        io.execute {
            val opened = try {
                endpoint.open(context)
            } catch (e: Exception) {
                Log.w(TAG, "acp[${endpoint.id}]: cannot reach ${endpoint.address}: ${e.javaClass.simpleName}")
                main.execute { done(Result.failure(e)) }
                return@execute
            }
            val c = AcpConnection(opened.input, opened.output, handler, endpoint.id)
            link = opened
            connection = c
            c.start()
            val params = JSONObject()
                .put("protocolVersion", PROTOCOL_VERSION)
                .put("clientCapabilities", JSONObject()
                    .put("fs", JSONObject().put("readTextFile", false).put("writeTextFile", false))
                    .put("terminal", false))
                .put("clientInfo", JSONObject().put("name", "quire").put("title", "Quire").put("version", VERSION))
            c.request("initialize", params) { r ->
                val routed = endpoint.quiredAgent
                if (routed == null || r.isFailure) {
                    finishConnect(r, done)
                    return@request
                }
                val version = (r.getOrNull() as? JSONObject)?.optInt("protocolVersion", -1) ?: -1
                if (version != PROTOCOL_VERSION) {
                    finishConnect(Result.failure(IOException("quired chose ACP version $version")), done)
                    return@request
                }
                // quired answered for itself; the name, sign-in methods and image support that matter are the
                // agent's own initialize response, which _quire/describe returns (it starts the agent, no model call).
                c.request("_quire/describe", JSONObject().put("agent", routed)) { d -> finishConnect(d, done) }
            }
        }
    }

    private fun finishConnect(r: Result<Any?>, done: (Result<AgentInfo>) -> Unit) {
        val result = r.mapCatching { parseInfo(it as? JSONObject ?: throw IOException("bad initialize")) }
        result.onSuccess { info = it }
        result.onFailure { close() }
        main.execute { done(result) }
    }

    private fun parseInfo(o: JSONObject): AgentInfo {
        val version = o.optInt("protocolVersion", -1)
        if (version != PROTOCOL_VERSION) throw IOException("unsupported ACP version $version")
        val agentInfo = o.optJSONObject("agentInfo")
        val methods = o.optJSONArray("authMethods") ?: JSONArray()
        return AgentInfo(
            name = agentInfo?.optString("name")?.takeIf { it.isNotEmpty() } ?: endpoint.name,
            title = agentInfo?.optString("title")?.takeIf { it.isNotEmpty() },
            version = agentInfo?.optString("version")?.takeIf { it.isNotEmpty() },
            authMethods = (0 until methods.length()).mapNotNull { i ->
                methods.optJSONObject(i)?.let {
                    AuthMethod(it.optString("id"), it.optString("name"), it.optString("description").ifEmpty { null })
                }
            },
            images = o.optJSONObject("agentCapabilities")?.optJSONObject("promptCapabilities")
                ?.optBoolean("image", false) ?: false,
        )
    }

    fun newSession(done: (Result<String>) -> Unit) {
        call("session/new", routed(JSONObject().put("cwd", endpoint.cwd).put("mcpServers", JSONArray()))) { r ->
            done(r.mapCatching { (it as JSONObject).getString("sessionId") })
        }
    }

    fun authenticate(methodId: String, done: (Result<Unit>) -> Unit) {
        call("authenticate", routed(JSONObject().put("methodId", methodId))) { r -> done(r.map { }) }
    }

    /** Names the agent for quired serve, which routes session/new and authenticate by `_meta.quire.agent`. */
    private fun routed(params: JSONObject): JSONObject {
        val agent = endpoint.quiredAgent ?: return params
        return params.put("_meta", JSONObject().put("quire", JSONObject().put("agent", agent)))
    }

    /** Runs one turn; [done] gets the stop reason. */
    fun prompt(sessionId: String, prompt: JSONArray, done: (Result<String>) -> Unit) {
        call("session/prompt", JSONObject().put("sessionId", sessionId).put("prompt", prompt)) { r ->
            done(r.mapCatching { (it as JSONObject).getString("stopReason") })
        }
    }

    fun cancel(sessionId: String) {
        connection?.notify("session/cancel", JSONObject().put("sessionId", sessionId))
    }

    private fun call(method: String, params: JSONObject, done: (Result<Any?>) -> Unit) {
        val c = connection ?: return main.execute { done(Result.failure(IOException("not connected"))) }
        c.request(method, params) { r -> main.execute { done(r) } }
    }

    fun close() {
        connection?.close()
        connection = null
        try {
            link?.close()
        } catch (e: IOException) {
            // Already gone.
        }
        link = null
    }

    private val handler = object : AcpConnection.Handler {
        override fun onNotification(method: String, params: JSONObject) {
            if (method != "session/update") return
            val sessionId = params.optString("sessionId")
            val update = params.optJSONObject("update") ?: return
            main.execute { listener.onUpdate(this@AcpAgent, sessionId, update) }
        }

        override fun onRequest(method: String, params: JSONObject, reply: AcpConnection.Reply) {
            when (method) {
                "session/request_permission" -> main.execute {
                    listener.onPermission(this@AcpAgent, params.optString("sessionId"), params) { outcome ->
                        reply.result(JSONObject().put("outcome", outcome))
                    }
                }
                // Quire advertises no file system and no terminal (clientCapabilities above).
                else -> reply.error(AcpConnection.METHOD_NOT_FOUND, "Quire does not offer $method")
            }
        }

        override fun onClosed(error: Throwable?) {
            connection = null
            main.execute { listener.onClosed(this@AcpAgent, error) }
        }
    }

    companion object {
        const val PROTOCOL_VERSION = 1
        const val VERSION = "0.5"

        fun selected(optionId: String): JSONObject = JSONObject().put("outcome", "selected").put("optionId", optionId)
        fun cancelled(): JSONObject = JSONObject().put("outcome", "cancelled")
    }
}
