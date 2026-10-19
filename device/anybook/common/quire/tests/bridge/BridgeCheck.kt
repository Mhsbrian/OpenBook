// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// The Linux-environment adapter (acp/AcpAgent.kt, acp/AcpConnection.kt, note/Agents.kt) on Android's own runtime, over a
// real socket pair standing in for the Terminal app's agent bridge: discovery without connecting, metadata from
// _quire/describe, routing by _meta.quire.agent, and the transport's lifetime (an idle close returns without the peer's
// help; end of stream and a rejected connect release the descriptor). Written by the Checker for the ANAL-217 review of
// PR #113; run with tools/bridge-test.sh.

package checker

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.os.ParcelFileDescriptor
import android.system.Os
import android.system.OsConstants
import dev.openbook.quire.acp.*
import dev.openbook.quire.agents.Connectors
import dev.openbook.quire.note.AgentDirectory
import java.io.*
import java.lang.reflect.Proxy
import java.util.concurrent.*
import org.json.*
import kotlin.concurrent.thread

private var passed = 0
private var failed = 0
private fun checkCase(name: String, ok: Boolean) {
    println("${if (ok) "PASS" else "FAIL"} $name")
    if (ok) passed++ else failed++
}
private val context = object : ContextWrapper(null) {
    override fun getApplicationContext(): Context = this
    override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
        Proxy.newProxyInstance(SharedPreferences::class.java.classLoader, arrayOf(SharedPreferences::class.java)) {
            _, method, args -> when (method.name) {
                "getString" -> args!![1]
                "edit" -> Proxy.newProxyInstance(SharedPreferences.Editor::class.java.classLoader,
                    arrayOf(SharedPreferences.Editor::class.java)) { proxy, m, _ ->
                        if (m.returnType == SharedPreferences.Editor::class.java) proxy else null
                    }
                else -> null
            }
        } as SharedPreferences
}
private val main = Executors.newSingleThreadExecutor { Thread(it, "checker-main") }
private fun <T> await(start: ((Result<T>) -> Unit) -> Unit): Result<T> {
    val f = CompletableFuture<Result<T>>()
    start { f.complete(it) }
    return f.get(5, TimeUnit.SECONDS)
}
private fun ep(name: String) = Endpoint("linux:$name", name, "in Linux", "linux:$name", "", true)
private class Peer(val version: Int = 1, val agentVersion: Int = 1, val describeError: Boolean = false) {
    val pair = ParcelFileDescriptor.createSocketPair()
    val calls = LinkedBlockingQueue<JSONObject>()
    val seen = CopyOnWriteArrayList<String>()
    val out = FileOutputStream(pair[1].fileDescriptor)
    val reader = BufferedReader(InputStreamReader(FileInputStream(pair[1].fileDescriptor)))
    val eof = CountDownLatch(1)
    fun send(o: JSONObject) { synchronized(out) { out.write((o.toString()+"\n").toByteArray()); out.flush() } }
    init {
        Connectors.LinuxEnvironment.next = pair[0]
        thread(name="checker-peer", isDaemon=true) {
            try {
                while (true) {
                    val line = reader.readLine() ?: break
                    val m = JSONObject(line)
                    calls.put(m)
                    val method = m.optString("method")
                    seen += method
                    if (!m.has("id") || method.isEmpty()) continue
                    val r = when(method) {
                        "initialize" -> JSONObject().put("protocolVersion", version).put("agentInfo", JSONObject().put("name", "quired"))
                        "_quire/describe" -> JSONObject().put("protocolVersion", agentVersion)
                            .put("agentInfo", JSONObject().put("name", "actual-agent").put("title", "Actual agent"))
                            .put("agentCapabilities", JSONObject().put("promptCapabilities", JSONObject().put("image", true)))
                            .put("authMethods", JSONArray().put(JSONObject().put("id", "login").put("name", "Sign in")))
                        "session/new" -> JSONObject().put("sessionId", "same-session")
                        "authenticate" -> JSONObject()
                        else -> continue
                    }
                    val reply = JSONObject().put("jsonrpc", "2.0").put("id", m.get("id"))
                    if (method == "_quire/describe" && describeError) {
                        reply.put("error", JSONObject().put("code", -32602).put("message", "agent removed"))
                    } else reply.put("result", r)
                    send(reply)
                }
            } catch (e: Exception) { println("peer ended: ${e.javaClass.simpleName}") }
            finally { eof.countDown() }
        }
    }
    fun request(method: String): JSONObject {
        while (true) {
            val c = calls.poll(5, TimeUnit.SECONDS) ?: error("missing $method")
            if (c.optString("method") == method) return c
        }
    }
    fun rescue() {
        for (p in pair) {
            try { Os.shutdown(p.fileDescriptor, OsConstants.SHUT_RDWR) } catch (_: Exception) {}
            try { p.close() } catch (_: Exception) {}
        }
    }
}
private val noListener = object : AcpAgent.Listener {
    override fun onUpdate(a: AcpAgent, s: String, u: JSONObject) {}
    override fun onPermission(a: AcpAgent, s: String, r: JSONObject, answer: (JSONObject)->Unit) { answer(AcpAgent.cancelled()) }
    override fun onClosed(a: AcpAgent, e: Throwable?) {}
}
fun main() {
    try {
        val dir = AgentDirectory(context, main)
        val a = ep("alpha")
        checkCase("discovery adds entry", dir.foundInLinux(listOf(a)))
        val entry = dir.find(a.id)!!
        checkCase("discovery does not connect or choose default", !entry.connected && entry.agent == null && dir.default() == null && Connectors.LinuxEnvironment.opens == 0)
        dir.setConnected(entry, true)
        dir.use(entry)
        checkCase("rediscovery preserves explicit choice and entry identity", !dir.foundInLinux(listOf(a)) && dir.find(a.id) === entry && dir.default() === entry)
        val peer = Peer()
        val result = await<AcpAgent> { dir.ensure(entry, it) }
        val client = result.getOrThrow()
        val info = entry.info!!
        checkCase("agent metadata comes from describe", info.name == "actual-agent" && info.images && info.authMethods.single().id == "login")
        val init = peer.request("initialize").getJSONObject("params")
        checkCase("no filesystem or terminal capability", !init.getJSONObject("clientCapabilities").getBoolean("terminal") && !init.getJSONObject("clientCapabilities").getJSONObject("fs").getBoolean("writeTextFile"))
        checkCase("describe names selected agent", peer.request("_quire/describe").getJSONObject("params").getString("agent") == "alpha")
        checkCase("no prompt or session before explicit request", peer.seen.toList() == listOf("initialize", "_quire/describe"))
        checkCase("newSession response decoded", await<String> { client.newSession(it) }.getOrThrow() == "same-session")
        val newp = peer.request("session/new").getJSONObject("params")
        checkCase("newSession routes alpha with server-created cwd", newp.getJSONObject("_meta").getJSONObject("quire").getString("agent") == "alpha" && newp.getString("cwd") == "")
        await<Unit> { client.authenticate("login", it) }.getOrThrow()
        val auth = peer.request("authenticate").getJSONObject("params")
        checkCase("authenticate routes alpha", auth.getJSONObject("_meta").getJSONObject("quire").getString("agent") == "alpha" && auth.getString("methodId") == "login")
        client.cancel("same-session")
        checkCase("cancel retains session id", peer.request("session/cancel").getJSONObject("params").getString("sessionId") == "same-session")
        Thread.sleep(100)
        val closed = CountDownLatch(1)
        val closer = thread(name="checker-explicit-close", isDaemon=true) { client.close(); closed.countDown() }
        val timely = closed.await(1500, TimeUnit.MILLISECONDS)
        checkCase("idle bridge close returns within 1.5 seconds", timely)
        if (!timely) {
            println("close thread state=${closer.state}")
            closer.stackTrace.forEach { println("  $it") }
            Thread.getAllStackTraces().filter { it.key.name.startsWith("acp-read-") }.forEach { (t, s) ->
                println("reader ${t.name} ${t.state}"); s.forEach { println("  $it") }
            }
        }
        peer.rescue()
        checkCase("shutdown releases blocked close", closed.await(2, TimeUnit.SECONDS))
        for ((label, p) in listOf("server version" to Peer(version=2), "agent version" to Peer(agentVersion=2), "describe error" to Peer(describeError=true))) {
            Connectors.LinuxEnvironment.next = p.pair[0]
            val c = AcpAgent(context, ep("alpha"), noListener, main)
            checkCase("rejects $label", await<AgentInfo> { c.connect(it) }.isFailure)
            if (label == "server version") checkCase("bad server version never starts agent", "_quire/describe" !in p.seen)
            Thread.sleep(200)
            checkCase("a rejected connect ($label) releases the bridge descriptor", !p.pair[0].fileDescriptor.valid())
            p.rescue()
        }
        val endingPeer = Peer()
        val ended = CountDownLatch(1)
        val endingClient = AcpAgent(context, ep("alpha"), object : AcpAgent.Listener by noListener {
            override fun onClosed(a: AcpAgent, e: Throwable?) { ended.countDown() }
        }, main)
        await<AgentInfo> { endingClient.connect(it) }.getOrThrow()
        Os.shutdown(endingPeer.pair[1].fileDescriptor, OsConstants.SHUT_RDWR)
        endingPeer.pair[1].close()
        checkCase("remote EOF notifies the client", ended.await(2, TimeUnit.SECONDS))
        Thread.sleep(100)
        checkCase("remote EOF closes the owned bridge descriptor", !endingPeer.pair[0].fileDescriptor.valid())
        endingPeer.rescue()
        // ANAL-225: a stopped environment (after a reboot) is started, then the connection opens.
        val startingPeer = Peer()
        Connectors.LinuxEnvironment.ready = false
        Connectors.LinuxEnvironment.startable = true
        val started = AcpAgent(context, ep("alpha"), noListener, main)
        val startedInfo = await<AgentInfo> { started.connect(it) }
        checkCase("a stopped environment is started, then connected",
            startedInfo.isSuccess && Connectors.LinuxEnvironment.starts == 1)
        started.close()
        startingPeer.rescue()
        Connectors.LinuxEnvironment.startable = false
        Connectors.LinuxEnvironment.ready = false
        val before = Connectors.LinuxEnvironment.opens
        val c = AcpAgent(context, ep("alpha"), noListener, main)
        val failure = await<AgentInfo> { c.connect(it) }.exceptionOrNull()
        checkCase("stopped environment fails before opening and explains why", Connectors.LinuxEnvironment.opens == before && failure?.message == "Linux environment stopped")
    } catch (e: Throwable) { failed++; e.printStackTrace() }
    println("RESULT $passed passed, $failed failed")
    kotlin.system.exitProcess(if (failed == 0) 0 else 1)
}
