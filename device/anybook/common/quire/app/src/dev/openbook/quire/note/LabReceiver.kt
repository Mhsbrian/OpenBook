// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.graphics.PointF
import android.util.Log
import dev.openbook.quire.Quire
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.acp.Endpoint
import dev.openbook.quire.invocation.Invocations
import org.json.JSONArray

/**
 * Commands for scripted checks (scripts/quire/q5-cf-check.py), on debuggable builds only. The receiver is not
 * exported, so only root and the system can reach it: no app can drive Quire or point it at an agent this way.
 *
 *   am broadcast -n dev.openbook.quire/.note.LabReceiver -a dev.openbook.quire.lab.<ACTION> [extras]
 *
 * ENDPOINT (id, name, where, address tcp:127.0.0.1:PORT, cwd, local, connected) · ENDPOINT_REMOVE (id) ·
 * OPEN (trigger, x and y for a pointer anchor else the taskbar, intake window|region|selection|secure|none, name, text)
 * · SEND (text) · ESC · HIDE · CLOSE · REOPEN · PICKER · PICK (id) · CONTROL (prompt, app, launch, taps: JSON
 * [[text, title, done], ...]) · MIRROR (action pause|resume|takeover|stop) · TRAY · LISTEN (final, partial) ·
 * LISTEN_RELEASE · BROKER (title, meta, rows: JSON [[name, where, old, new], ...], why) · PALETTE · DUMP
 */
class LabReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!Quire.keepsEvidence) return
        val surface = (context.applicationContext as QuireApplication).surface
        val action = intent.action?.removePrefix(PREFIX) ?: return
        Log.i(TAG, "lab: note $action")
        when (action) {
            "ENDPOINT" -> surface.agents.put(Endpoint(
                id = intent.getStringExtra("id") ?: "agent",
                name = intent.getStringExtra("name") ?: "Agent",
                where = intent.getStringExtra("where") ?: "on this laptop",
                address = intent.getStringExtra("address") ?: return,
                cwd = intent.getStringExtra("cwd") ?: "/",
                local = intent.getBooleanExtra("local", true),
            ), intent.getBooleanExtra("connected", true))
            "ENDPOINT_REMOVE" -> intent.getStringExtra("id")?.let { surface.agents.remove(it) }
            "OPEN" -> surface.invoke(intent.getStringExtra("trigger") ?: "lab", anchor(intent), intake(intent))
            "SEND" -> intent.getStringExtra("text")?.let { surface.send(it) }
            "ESC" -> surface.escape()
            "HIDE" -> surface.hide()
            "CLOSE" -> surface.close()
            "REOPEN" -> surface.tasks.lastOrNull { it.hidden }?.let { surface.reopen(it) }
            "PICKER" -> surface.window.card?.agentChip?.let { surface.openPicker(it) }
            "PICK" -> intent.getStringExtra("id")?.let { id -> surface.agents.find(id)?.let { surface.pickAgent(it) } }
            "CONTROL" -> {
                val taps = JSONArray(intent.getStringExtra("taps") ?: "[]")
                val plan = (0 until taps.length()).map {
                    val t = taps.getJSONArray(it)
                    ControlRun.Tap(t.getString(0), t.getString(1), t.getString(2))
                }
                surface.startControl(intent.getStringExtra("prompt") ?: "", intent.getStringExtra("app") ?: "Settings",
                    intent.getStringExtra("launch") ?: "com.android.settings", plan, anchor(intent),
                    intent.getStringExtra("aimMs")?.toLongOrNull() ?: 700L)
            }
            "MIRROR" -> surface.mirrorAction(when (intent.getStringExtra("action")) {
                "pause" -> MirrorPanel.Action.PAUSE
                "resume" -> MirrorPanel.Action.RESUME
                "takeover" -> MirrorPanel.Action.TAKE_OVER
                else -> MirrorPanel.Action.STOP
            })
            "TRAY" -> surface.showTray()
            "PALETTE" -> {
                // The system roles the note reads, for scripts/quire/q5-contrast.py --device.
                val p = dev.openbook.quire.ui.Palette.of(context)
                val roles = org.json.JSONObject()
                fun put(name: String, c: Int) = roles.put(name, String.format("#%06X", c and 0xFFFFFF))
                put("primary", p.primary); put("onPrimary", p.onPrimary); put("primaryContainer", p.primaryContainer)
                put("onPrimaryContainer", p.onPrimaryContainer); put("secondaryContainer", p.secondaryContainer)
                put("onSecondaryContainer", p.onSecondaryContainer); put("tertiary", p.tertiary)
                put("tertiaryContainer", p.tertiaryContainer); put("onTertiaryContainer", p.onTertiaryContainer)
                put("error", p.error); put("surface", p.surface); put("surfaceContainer", p.surfaceContainer)
                put("surfaceContainerHigh", p.surfaceHigh); put("surfaceContainerHighest", p.surfaceHighest)
                put("surfaceContainerLowest", p.surfaceLowest); put("onSurface", p.onSurface)
                put("onSurfaceVariant", p.onSurfaceVariant); put("inverseSurface", p.inverseSurface)
                put("inverseOnSurface", p.inverseOnSurface); put("outlineVariant", p.outlineVariant)
                Log.i(TAG, "note: palette ${if (p.dark) "dark" else "light"} $roles")
            }
            "LISTEN" -> surface.window.task?.listen(intent.getStringExtra("final") ?: "",
                intent.getStringExtra("partial") ?: "")
            "LISTEN_RELEASE" -> surface.window.task?.releaseListening()
            "BROKER" -> {
                val rows = JSONArray(intent.getStringExtra("rows") ?: "[]")
                surface.window.task?.labBroker(intent.getStringExtra("title") ?: "", intent.getStringExtra("meta") ?: "",
                    (0 until rows.length()).map {
                        val r = rows.getJSONArray(it)
                        Change(r.getString(0), r.getString(1), r.getString(2), r.getString(3))
                    }, intent.getStringExtra("why") ?: "")
            }
            "DUMP" -> {
                surface.tasks.forEach {
                    Log.i(TAG, "lab: task ${it.id} phase=${it.phase} running=${it.running} hidden=${it.hidden} " +
                        "needsAnswer=${it.needsAnswer} blocks=${it.blocks.map { b -> b.javaClass.simpleName }}")
                }
                surface.agents.entries.forEach {
                    Log.i(TAG, "lab: agent ${it.endpoint.id} ${it.endpoint.address} connected=${it.connected} " +
                        "state=${it.state} name=${it.name}")
                }
            }
            else -> Log.w(TAG, "lab: unknown note action $action")
        }
    }

    private fun anchor(intent: Intent): Anchor =
        if (intent.hasExtra("x") && intent.hasExtra("y")) {
            Anchor.Pointer(PointF(intent.getFloatExtra("x", 0f), intent.getFloatExtra("y", 0f)))
        } else {
            Anchor.Taskbar(null)
        }

    private fun intake(intent: Intent): Intake? {
        val name = intent.getStringExtra("name") ?: "Settings"
        return when (intent.getStringExtra("intake")) {
            "window" -> Intake.Window(name, Invocations.lastShot)
            "region" -> Invocations.lastShot?.let { Intake.Region(name, it) }
            "selection" -> Intake.Selection(intent.getStringExtra("text") ?: "", name)
            "secure" -> Intake.Secure
            "none" -> Intake.None
            else -> null
        }
    }

    companion object {
        private const val PREFIX = "dev.openbook.quire.lab."
    }
}
