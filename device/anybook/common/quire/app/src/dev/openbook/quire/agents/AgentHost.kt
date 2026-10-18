// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.agents

import android.os.ParcelFileDescriptor
import android.system.ErrnoException
import android.system.Os
import android.system.OsConstants
import android.util.Log
import dev.openbook.quire.Quire.TAG
import java.io.Closeable
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import org.json.JSONArray
import org.json.JSONObject

/**
 * Quire core as the ACP client of one `quired serve` (docs/quire.md §4, §6): the agents installed where quired runs,
 * their sign-in methods, sessions and prompt turns. quired routes each session to the agent named in session/new's
 * `_meta.quire.agent` and offers `_quire/agents` and `_quire/describe` (quire/quired/internal/serve).
 */
class AgentHost private constructor(private val pfd: ParcelFileDescriptor, private val listener: Listener) : Closeable {
    interface Listener {
        /** A session/update from the agent (message chunks, tool calls, plans), in order. */
        fun onUpdate(sessionId: String, update: JSONObject)

        /**
         * The agent asks before a tool call. Return the chosen option's id, or null to cancel. Blocks the asking
         * thread, not Quire's: a person may take their time. Anything that goes wrong means no.
         */
        fun onPermission(sessionId: String, toolCall: JSONObject, options: JSONArray): String?
    }

    data class Agent(val id: String, val name: String, val version: String, val supported: Boolean, val note: String)

    data class Session(val id: String, val agent: String, val folder: String)

    private val connection: AcpConnection
    // Guarded by itself: updates for sessions whose session/new reply hasn't been handled yet.
    private val early = HashMap<String, MutableList<JSONObject>>()
    private var known = setOf<String>()

    lateinit var serverInfo: JSONObject
        private set

    init {
        connection = AcpConnection(
            FileInputStream(pfd.fileDescriptor),
            FileOutputStream(pfd.fileDescriptor),
            object : AcpConnection.Handler {
                override fun onNotification(method: String, params: JSONObject) {
                    if (method != "session/update") return
                    val sid = params.optString("sessionId")
                    val update = params.optJSONObject("update") ?: return
                    // quired may relay an update a session announced before session/new's reply arrived.
                    synchronized(early) {
                        if (sid !in known) {
                            early.getOrPut(sid) { mutableListOf() }.let { if (it.size < 256) it.add(update) }
                            return
                        }
                        listener.onUpdate(sid, update)
                    }
                }

                override fun onRequest(method: String, params: JSONObject): Any? {
                    if (method != "session/request_permission") {
                        throw AcpError(AcpError.METHOD_NOT_FOUND, "Quire does not offer $method")
                    }
                    val options = params.optJSONArray("options") ?: JSONArray()
                    val chosen = try {
                        listener.onPermission(params.optString("sessionId"), params.optJSONObject("toolCall") ?: JSONObject(), options)
                    } catch (e: Exception) {
                        Log.w(TAG, "agents: permission handler failed, refusing", e)
                        null
                    }
                    val outcome = if (chosen != null) {
                        JSONObject().put("outcome", "selected").put("optionId", chosen)
                    } else {
                        JSONObject().put("outcome", "cancelled")
                    }
                    return JSONObject().put("outcome", outcome)
                }

                override fun onClosed(cause: Throwable?) {
                    Log.i(TAG, "agents: connection to quired closed" + (cause?.let { ": $it" } ?: ""))
                }
            },
            // quired sees EOF and stops the agents it started for this connection.
            Closeable {
                try {
                    Os.shutdown(pfd.fileDescriptor, OsConstants.SHUT_RDWR)
                } catch (_: ErrnoException) {
                }
                pfd.close()
            })
    }

    val isClosed: Boolean
        get() = connection.isClosed

    private fun initialize() {
        val req = JSONObject()
            .put("protocolVersion", 1)
            .put("clientCapabilities", JSONObject().put("fs", JSONObject().put("readTextFile", false).put("writeTextFile", false)).put("terminal", false))
            .put("clientInfo", JSONObject().put("name", "quire").put("title", "Quire (OpenBook)").put("version", "0.2"))
        serverInfo = connection.call("initialize", req, INIT_MS)
        val version = serverInfo.optInt("protocolVersion", -1)
        if (version != 1) throw IOException("quired chose ACP protocol version $version; Quire speaks 1")
    }

    fun agents(): List<Agent> {
        val list = connection.call("_quire/agents", JSONObject(), CALL_MS).optJSONArray("agents") ?: JSONArray()
        return (0 until list.length()).map {
            val a = list.getJSONObject(it)
            Agent(a.optString("id"), a.optString("name"), a.optString("version"), a.optBoolean("supported"), a.optString("note"))
        }
    }

    /** The agent's own initialize response: capabilities and `authMethods`. Starts the agent; costs no model call. */
    fun describe(agent: String): JSONObject = connection.call("_quire/describe", JSONObject().put("agent", agent), START_MS)

    fun authenticate(agent: String, methodId: String) {
        connection.call("authenticate", JSONObject().put("methodId", methodId).put("_meta", meta(agent)), AUTH_MS)
    }

    /** A new session; quired makes its folder unless [folder] names one in its root. */
    fun newSession(agent: String, folder: String? = null): Session {
        val req = JSONObject().put("cwd", folder ?: "").put("mcpServers", JSONArray()).put("_meta", meta(agent))
        val res = connection.call("session/new", req, START_MS)
        val sid = res.getString("sessionId")
        val got = res.optJSONObject("_meta")?.optJSONObject("quire")?.optString("cwd") ?: ""
        synchronized(early) {
            known = known + sid
            early.remove(sid)?.forEach { listener.onUpdate(sid, it) }
        }
        return Session(sid, agent, got)
    }

    /** Runs one turn and returns its stop reason. */
    fun prompt(sessionId: String, text: String, timeoutMs: Long = TURN_MS): String {
        val blocks = JSONArray().put(JSONObject().put("type", "text").put("text", text))
        return connection.call("session/prompt", JSONObject().put("sessionId", sessionId).put("prompt", blocks), timeoutMs)
            .optString("stopReason")
    }

    fun cancel(sessionId: String) = connection.notify("session/cancel", JSONObject().put("sessionId", sessionId))

    override fun close() = connection.close()

    private fun meta(agent: String) = JSONObject().put("quire", JSONObject().put("agent", agent))

    companion object {
        private const val INIT_MS = 15_000L
        private const val CALL_MS = 30_000L
        private const val START_MS = 120_000L
        private const val AUTH_MS = 300_000L
        private const val TURN_MS = 30 * 60_000L

        /** Speaks ACP over [pfd] (a stream to quired serve) and initializes. Takes ownership of [pfd]. */
        fun open(pfd: ParcelFileDescriptor, listener: Listener): AgentHost {
            val host = AgentHost(pfd, listener)
            try {
                host.initialize()
            } catch (e: Exception) {
                host.close()
                throw e
            }
            return host
        }
    }
}
