// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.agents

import android.content.Context
import android.os.SystemClock
import android.util.Log
import dev.openbook.quire.Quire.TAG
import java.util.concurrent.CopyOnWriteArrayList
import org.json.JSONArray
import org.json.JSONObject

/**
 * Quire core's agents (Q4, docs/quire.md §4): picks the first connector that can be used, keeps one ACP connection to
 * its quired, and runs prompt turns. Every line the Q4 checks read is logged under [TAG] as "agents: ...". Q5 puts the
 * note on top of this.
 */
class Agents(private val context: Context) {
    /** How a permission request is answered: by asking the person, or by a fixed policy (the scripted checks). */
    enum class Approve { ASK, READ, ALL, NONE }

    /** Shows the agent's question to the person and returns the chosen option id, or null. */
    fun interface Asker {
        fun ask(title: String, kind: String, options: JSONArray): String?
    }

    interface Listener {
        fun onAgentsChanged(summary: String)
    }

    data class Answer(val sessionId: String, val stopReason: String, val text: String, val millis: Long)

    class Unavailable(message: String) : Exception(message)

    private val listeners = CopyOnWriteArrayList<Listener>()

    @Volatile
    var asker: Asker? = null

    @Volatile
    var summary: String = ""
        private set

    private var host: AgentHost? = null
    private var connector: String? = null
    private val turns = HashMap<String, Turn>()

    private class Turn(val approve: Approve) {
        val text = StringBuilder()
        val titles = HashMap<String, String>()
        val kinds = HashMap<String, String>()
    }

    fun addListener(l: Listener) = listeners.add(l)

    fun removeListener(l: Listener) = listeners.remove(l)

    private fun publish(text: String) {
        summary = text
        listeners.forEach { it.onAgentsChanged(text) }
    }

    /** Every connector's status, logged. */
    fun statuses(): List<Connectors.Status> {
        val all = Connectors.statuses(context)
        Log.i(TAG, "agents: status " + all.joinToString(" ") { "${it.connector}=${it.state}" + (it.detail?.let { d -> "($d)" } ?: "") })
        return all
    }

    /** The connection to quired, opened through the first usable connector. Throws [Unavailable] saying why not. */
    @Synchronized
    fun connect(): AgentHost {
        host?.let { if (!it.isClosed) return it }
        host = null
        val all = statuses()
        val ready = all.firstOrNull { it.state == Connectors.State.READY }
        if (ready == null) {
            // Say what is missing, in order: the Linux environment, then a paired computer.
            val why = all.joinToString(" ") { it.describe(context) }
            Log.w(TAG, "agents: unavailable: $why")
            publish(why)
            throw Unavailable(why)
        }
        val t0 = SystemClock.elapsedRealtime()
        val pfd = when (ready.connector) {
            Connectors.LinuxEnvironment.NAME -> Connectors.LinuxEnvironment.connect(context)
            else -> throw Unavailable(ready.describe(context))
        }
        val h = try {
            AgentHost.open(pfd, hostListener)
        } catch (e: Exception) {
            val why = Connectors.Status(ready.connector, Connectors.State.ERROR, "quired: ${e.message}").describe(context)
            Log.w(TAG, "agents: unavailable: $why", e)
            publish(why)
            throw Unavailable(why)
        }
        val info = h.serverInfo.optJSONObject("agentInfo")
        Log.i(TAG, "agents: connected via ${ready.connector} in ${SystemClock.elapsedRealtime() - t0} ms; " +
            "${info?.optString("name")} ${info?.optString("version")}")
        host = h
        connector = ready.connector
        return h
    }

    fun agents(): List<AgentHost.Agent> {
        val list = connect().agents()
        list.forEach { Log.i(TAG, "agents: agent ${it.id} version=\"${it.version}\" supported=${it.supported}" + if (it.supported) "" else " note=\"${it.note}\"") }
        publish(context.getString(dev.openbook.quire.R.string.agents_list, Connectors.label(context, connector ?: ""),
            list.filter { it.supported }.joinToString(", ") { it.name }.ifEmpty { "-" }))
        return list
    }

    /** The agent's sign-in methods (ACP authMethods), from its own initialize. No model call. */
    fun describe(agent: String): JSONObject {
        val info = connect().describe(agent)
        val methods = info.optJSONArray("authMethods") ?: JSONArray()
        Log.i(TAG, "agents: auth $agent " + (0 until methods.length()).joinToString(" ", "[", "]") {
            val m = methods.getJSONObject(it)
            m.optString("id") + ":" + m.optString("type", "agent") + ":\"" + m.optString("name") + "\""
        })
        return info
    }

    fun authenticate(agent: String, methodId: String) {
        connect().authenticate(agent, methodId)
        Log.i(TAG, "agents: authenticated $agent with $methodId")
    }

    /** One prompt turn in a new session; the answer streams into the summary. */
    fun prompt(agent: String, text: String, approve: Approve): Answer {
        val h = connect()
        val session = try {
            h.newSession(agent)
        } catch (e: AcpError) {
            if (e.code == AcpError.AUTH_REQUIRED) {
                // quired attaches the agent's sign-in methods (authMethods) to the error.
                Log.w(TAG, "agents: $agent needs sign-in: ${e.data}")
            }
            throw e
        }
        Log.i(TAG, "agents: session ${session.id} agent=$agent folder=${session.folder}")
        val turn = Turn(approve)
        synchronized(turns) { turns[session.id] = turn }
        val t0 = SystemClock.elapsedRealtime()
        try {
            val stop = h.prompt(session.id, text)
            val ms = SystemClock.elapsedRealtime() - t0
            val answer = synchronized(turn) { turn.text.toString() }
            Log.i(TAG, "agents: answer ${session.id} stop=$stop ms=$ms text=" + JSONObject.quote(answer.take(600)))
            publish(answer.ifEmpty { stop })
            return Answer(session.id, stop, answer, ms)
        } finally {
            synchronized(turns) { turns.remove(session.id) }
        }
    }

    @Synchronized
    fun disconnect() {
        host?.close()
        host = null
    }

    private val hostListener = object : AgentHost.Listener {
        override fun onUpdate(sessionId: String, update: JSONObject) {
            val turn = synchronized(turns) { turns[sessionId] } ?: return
            val id = update.optString("toolCallId")
            when (update.optString("sessionUpdate")) {
                "agent_message_chunk" -> {
                    val chunk = update.optJSONObject("content")?.optString("text") ?: ""
                    val now = synchronized(turn) { turn.text.append(chunk).toString() }
                    publish(now)
                }
                "tool_call" -> synchronized(turn) {
                    turn.titles[id] = update.optString("title")
                    turn.kinds[id] = update.optString("kind")
                    Log.i(TAG, "agents: tool ${turn.titles[id]} (${turn.kinds[id]}) ${update.optString("status")}")
                }
                "tool_call_update" -> {
                    val status = update.optString("status")
                    if (status == "completed" || status == "failed") {
                        Log.i(TAG, "agents: tool ${synchronized(turn) { turn.titles[id] }} $status")
                    }
                }
            }
        }

        override fun onPermission(sessionId: String, toolCall: JSONObject, options: JSONArray): String? {
            val turn = synchronized(turns) { turns[sessionId] }
            val id = toolCall.optString("toolCallId")
            val title = toolCall.optString("title").ifEmpty { turn?.let { synchronized(it) { it.titles[id] } } ?: id }
            val kind = toolCall.optString("kind").ifEmpty { turn?.let { synchronized(it) { it.kinds[id] } } ?: "" }
            fun pick(vararg kinds: String): String? {
                for (k in kinds) for (i in 0 until options.length()) {
                    val o = options.getJSONObject(i)
                    if (o.optString("kind") == k) return o.optString("optionId")
                }
                return null
            }
            val chosen = when (turn?.approve ?: Approve.NONE) {
                Approve.ALL -> pick("allow_once", "allow_always")
                Approve.NONE -> pick("reject_once", "reject_always")
                Approve.READ -> if (kind in setOf("read", "search", "think")) pick("allow_once", "allow_always")
                    else pick("reject_once", "reject_always")
                // Nobody to ask means no.
                Approve.ASK -> asker?.ask(title, kind, options) ?: pick("reject_once", "reject_always")
            }
            val name = (0 until options.length()).map { options.getJSONObject(it) }
                .firstOrNull { it.optString("optionId") == chosen }?.optString("name") ?: "cancelled"
            Log.i(TAG, "agents: permission \"$title\" ($kind) -> $name")
            return chosen
        }
    }
}
