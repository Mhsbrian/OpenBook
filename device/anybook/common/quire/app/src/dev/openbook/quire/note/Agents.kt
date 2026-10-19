// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.Context
import android.util.Log
import dev.openbook.quire.Quire
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.acp.AcpAgent
import dev.openbook.quire.acp.AgentInfo
import dev.openbook.quire.acp.Endpoint
import java.util.concurrent.Executor
import org.json.JSONArray
import org.json.JSONObject

/** One agent Quire can reach, and whether the person has connected it (docs/quire.md §5.3: opt-in). */
class AgentEntry(val endpoint: Endpoint) {
    enum class State { IDLE, CONNECTING, READY, UNREACHABLE }

    var agent: AcpAgent? = null
    var info: AgentInfo? = null
    var state = State.IDLE

    /** False until the person connects it: nothing is sent to an agent before that. */
    var connected = false

    /** The agent answered `session/new` with "authentication required" and hasn't been signed in since. */
    var needsSignIn = false

    val name: String
        get() = info?.title ?: info?.name?.let { pretty(it) } ?: endpoint.name

    val where: String
        get() = endpoint.where

    val initials: String
        get() = KNOWN[key()]?.first ?: name.split(' ', '-').filter { it.isNotEmpty() }.let { words ->
            if (words.size >= 2) "${words[0][0]}${words[1][0]}".uppercase() else name.take(2)
        }

    val color: Int
        get() = KNOWN[key()]?.second ?: AVATARS[Math.floorMod(name.hashCode(), AVATARS.size)]

    private fun key() = name.lowercase().substringBefore(' ')

    private fun pretty(n: String) = KNOWN_NAMES[n.lowercase()] ?: n

    companion object {
        // The prototype's avatars (docs/quire-design/quire.js, AGENTS).
        private val KNOWN = mapOf(
            "claude" to ("CC" to 0xFF5B5D72.toInt()),
            "opencode" to ("oc" to 0xFF72557B.toInt()),
            "copilot" to ("Cp" to 0xFF4F5065.toInt()),
            "cursor" to ("Cu" to 0xFF5E5E68.toInt()),
            "gemini" to ("G" to 0xFF565B8C.toInt()),
            "codex" to ("Cx" to 0xFF7A7A84.toInt()),
        )
        private val KNOWN_NAMES = mapOf("claude-code" to "Claude Code", "claude" to "Claude Code")
        private val AVATARS = intArrayOf(0xFF5B5D72.toInt(), 0xFF72557B.toInt(), 0xFF4F5065.toInt(),
            0xFF565B8C.toInt(), 0xFF5E5E68.toInt())
    }
}

/**
 * The agents Quire knows and their ACP connections. Updates and permission requests are routed to the task that owns
 * the session on the connection they came from ([SessionRoutes]: two agents may use the same session ID). Today the
 * list holds the endpoints a debuggable build was given by its lab commands; Q4 fills it from `quired agents` in the
 * Linux environment.
 */
class AgentDirectory(context: Context, private val main: Executor) : AcpAgent.Listener {
    interface SessionOwner {
        fun onUpdate(update: JSONObject)
        fun onPermission(request: JSONObject, answer: (JSONObject) -> Unit)
        fun onAgentClosed(error: Throwable?)
    }

    private val prefs = context.getSharedPreferences("agents", Context.MODE_PRIVATE)
    val entries = mutableListOf<AgentEntry>()
    private val owners = SessionRoutes<AcpAgent, SessionOwner>()
    var lastUsed: String? = prefs.getString(KEY_LAST, null)
        private set

    init {
        if (Quire.keepsEvidence) load()
    }

    fun find(id: String) = entries.firstOrNull { it.endpoint.id == id }

    /** The agent a new note starts with: the last one used, else the first connected one. */
    fun default(): AgentEntry? =
        entries.firstOrNull { it.connected && it.endpoint.id == lastUsed } ?: entries.firstOrNull { it.connected }

    fun use(entry: AgentEntry) {
        lastUsed = entry.endpoint.id
        prefs.edit().putString(KEY_LAST, lastUsed).apply()
    }

    fun put(endpoint: Endpoint, connected: Boolean) {
        val old = find(endpoint.id)
        if (old != null) {
            old.agent?.close()
            entries.remove(old)
        }
        entries += AgentEntry(endpoint).also { it.connected = connected }
        save()
    }

    fun remove(id: String) {
        find(id)?.let {
            it.agent?.close()
            entries.remove(it)
        }
        save()
    }

    fun setConnected(entry: AgentEntry, connected: Boolean) {
        entry.connected = connected
        save()
    }

    /** Connects [entry] if needed; [done] runs on the main thread. */
    fun ensure(entry: AgentEntry, done: (Result<AcpAgent>) -> Unit) {
        val existing = entry.agent
        if (existing != null && existing.connected && existing.info != null) {
            done(Result.success(existing))
            return
        }
        val agent = AcpAgent(entry.endpoint, this, main)
        entry.agent = agent
        entry.state = AgentEntry.State.CONNECTING
        agent.connect { r ->
            r.onSuccess {
                entry.info = it
                entry.state = AgentEntry.State.READY
                Log.i(TAG, "acp: connected to ${entry.endpoint.id}: ${it.name} ${it.version ?: ""} " +
                    "auth=${it.authMethods.map { m -> m.id }} images=${it.images}")
            }
            r.onFailure {
                entry.agent = null
                entry.state = AgentEntry.State.UNREACHABLE
            }
            done(r.map { agent })
        }
    }

    /** [owner] owns [sessionId] on [agent]'s connection, the one that answered `session/new`. */
    fun own(agent: AcpAgent, sessionId: String, owner: SessionOwner) {
        owners.own(agent, sessionId, owner)
    }

    fun release(agent: AcpAgent, sessionId: String, owner: SessionOwner) {
        owners.release(agent, sessionId, owner)
    }

    override fun onUpdate(agent: AcpAgent, sessionId: String, update: JSONObject) {
        owners.owner(agent, sessionId)?.onUpdate(update)
    }

    override fun onPermission(agent: AcpAgent, sessionId: String, request: JSONObject,
        answer: (JSONObject) -> Unit) {
        val owner = owners.owner(agent, sessionId)
        if (owner == null) {
            // No note owns this session on this connection: nobody can be asked, so the answer is no
            // (docs/quire.md §5.1).
            Log.i(TAG, "acp[${agent.endpoint.id}]: permission for a session no task owns: cancelled")
            answer(AcpAgent.cancelled())
            return
        }
        owner.onPermission(request, answer)
    }

    /** A connection closed: only the tasks with a session on it hear of it; other agents' tasks run on. */
    override fun onClosed(agent: AcpAgent, error: Throwable?) {
        val owned = owners.drop(agent)
        entries.firstOrNull { it.agent === agent }?.let {
            it.agent = null
            it.state = AgentEntry.State.IDLE
        }
        Log.i(TAG, "acp: ${agent.endpoint.id} closed${error?.let { ": ${it.javaClass.simpleName}" } ?: ""}, " +
            "${owned.size} session(s)")
        owned.forEach { it.onAgentClosed(error) }
    }

    private fun save() {
        if (!Quire.keepsEvidence) return
        val list = JSONArray()
        entries.forEach {
            val e = it.endpoint
            list.put(JSONObject().put("id", e.id).put("name", e.name).put("where", e.where).put("address", e.address)
                .put("cwd", e.cwd).put("local", e.local).put("connected", it.connected))
        }
        prefs.edit().putString(KEY_ENDPOINTS, list.toString()).apply()
    }

    private fun load() {
        val list = runCatching { JSONArray(prefs.getString(KEY_ENDPOINTS, "[]")) }.getOrNull() ?: return
        for (i in 0 until list.length()) {
            val o = list.optJSONObject(i) ?: continue
            val e = Endpoint(o.optString("id"), o.optString("name"), o.optString("where"), o.optString("address"),
                o.optString("cwd", "/"), o.optBoolean("local", true))
            entries += AgentEntry(e).also { it.connected = o.optBoolean("connected", false) }
        }
    }

    companion object {
        private const val KEY_LAST = "last"
        private const val KEY_ENDPOINTS = "endpoints"
    }
}
