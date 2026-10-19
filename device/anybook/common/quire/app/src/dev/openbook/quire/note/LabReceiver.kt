// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.app.contextualsearch.ContextualSearchManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.PointF
import android.graphics.Rect
import android.os.SystemClock
import android.util.Log
import dev.openbook.quire.Quire
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.acp.Endpoint
import dev.openbook.quire.invocation.Calls
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
 * · SEND (text) · ESC · HIDE · CLOSE · REOPEN (task id, else the last hidden) · PICKER · PICK (id) · CONTROL (prompt,
 * app, launch, taps: JSON [[text, title, done], ...]) · MIRROR (action pause|resume|takeover|stop) · TRAY · LISTEN
 * (final, partial) · LISTEN_RELEASE · BROKER (title, meta, rows: JSON [[name, where, old, new], ...], why, prompt,
 * steps: JSON [[title, kind], ...]) · PALETTE · DUMP
 *
 * INVOKE (px, py, bounds "l,t,r,b", source, age ms, visible "a,b", secure, w, h): a made-up contextual search call, as
 * if from SystemUI, through the same code as a real one (invocation/Calls), with a generated screenshot whose pixels
 * encode their own position (red = x, green = y, scaled to 255), so a check can tell from the image an agent received
 * which part of the display it is. Any extra left out is absent from the call.
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
            "REOPEN" -> {
                val id = intent.getStringExtra("task")?.toIntOrNull()
                (if (id != null) surface.tasks.firstOrNull { it.id == id } else surface.tasks.lastOrNull { it.hidden })
                    ?.let { surface.reopen(it) }
            }
            "INVOKE" -> Calls.handle(context.applicationContext as QuireApplication, invocation(intent))
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
                val steps = JSONArray(intent.getStringExtra("steps") ?: "[]")
                surface.window.task?.labBroker(intent.getStringExtra("title") ?: "", intent.getStringExtra("meta") ?: "",
                    (0 until rows.length()).map {
                        val r = rows.getJSONArray(it)
                        Change(r.getString(0), r.getString(1), r.getString(2), r.getString(3))
                    }, intent.getStringExtra("why") ?: "", intent.getStringExtra("prompt"),
                    (0 until steps.length()).map { steps.getJSONArray(it).let { s -> s.getString(0) to s.getString(1) } })
            }
            "DUMP" -> {
                surface.tasks.forEach {
                    Log.i(TAG, "lab: task ${it.id} phase=${it.phase} running=${it.running} hidden=${it.hidden} " +
                        "needsAnswer=${it.needsAnswer} agent=${it.agent?.endpoint?.id} session=${it.sessionId} " +
                        "shown=${surface.window.task === it} blocks=${it.blocks.map { b -> b.javaClass.simpleName }}")
                }
                surface.agents.entries.forEach {
                    Log.i(TAG, "lab: agent ${it.endpoint.id} ${it.endpoint.address} connected=${it.connected} " +
                        "state=${it.state} name=${it.name}")
                }
            }
            else -> Log.w(TAG, "lab: unknown note action $action")
        }
    }

    /** The launch intent ContextualSearchManagerService would send, for INVOKE. */
    private fun invocation(lab: Intent): Intent {
        val w = lab.getStringExtra("w")?.toIntOrNull() ?: 1920
        val h = lab.getStringExtra("h")?.toIntOrNull() ?: 1080
        val shot = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val row = IntArray(w)
        for (y in 0 until h) {
            for (x in 0 until w) row[x] = Color.rgb(x * 255 / (w - 1), y * 255 / (h - 1), 128)
            shot.setPixels(row, 0, w, 0, y, w, 1)
        }
        val i = Intent(ContextualSearchManager.ACTION_LAUNCH_CONTEXTUAL_SEARCH)
            .putExtra(ContextualSearchManager.EXTRA_ENTRYPOINT, ContextualSearchManager.ENTRYPOINT_SYSTEM_ACTION)
            .putExtra(Quire.EXTRA_TRIGGER, "lab_invoke")
            .putExtra(ContextualSearchManager.EXTRA_SCREENSHOT, shot)
            .putExtra(ContextualSearchManager.EXTRA_FLAG_SECURE_FOUND, lab.getStringExtra("secure") == "true")
            .putStringArrayListExtra(ContextualSearchManager.EXTRA_VISIBLE_PACKAGE_NAMES,
                ArrayList((lab.getStringExtra("visible") ?: "com.android.settings").split(',').filter { it.isNotEmpty() }))
        val px = lab.getStringExtra("px")?.toFloatOrNull()
        val py = lab.getStringExtra("py")?.toFloatOrNull()
        if (px != null && py != null) i.putExtra(Quire.EXTRA_POINTER_X, px).putExtra(Quire.EXTRA_POINTER_Y, py)
        lab.getStringExtra("bounds")?.split(',')?.mapNotNull { it.trim().toIntOrNull() }?.takeIf { it.size == 4 }?.let {
            i.sourceBounds = Rect(it[0], it[1], it[2], it[3])
        }
        lab.getStringExtra("source")?.let { i.putExtra(Quire.EXTRA_SOURCE_PACKAGE, it) }
        lab.getStringExtra("age")?.toLongOrNull()?.let {
            i.putExtra(Quire.EXTRA_SOURCE_TIME, SystemClock.elapsedRealtime() - it)
        }
        return i
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
