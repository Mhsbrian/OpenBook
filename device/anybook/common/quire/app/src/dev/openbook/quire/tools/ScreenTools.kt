// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.app.assist.AssistStructure
import android.content.Context
import android.graphics.Bitmap
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.service.voice.VoiceInteractionSession
import android.util.Log
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.assist.QuireVoiceInteractionService
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import org.json.JSONObject

/**
 * Reads the person's screen the way the platform lets its assistant: Quire, the assistant role holder, shows a session
 * without UI asking for the assist structure (the text and controls of every visible activity) and, when asked, the
 * assist screenshot. The platform decides what Quire may see: no structure from a window marked secure, none when the
 * person turned off "Use text from screen" or "Use screenshot", none from a private profile or under a policy that
 * disallows assist content; the screenshot leaves secure layers black.
 */
object ScreenReader {
    const val EXTRA_READ = "dev.openbook.quire.extra.READ_SCREEN"

    class Window(val app: String, val title: String?, val text: String)

    class Reading {
        val windows = ArrayList<Window>()
        var expected = -1
        var screenshot: Bitmap? = null
        var screenshotDone = false
        var wantScreenshot = false
        val done = CompletableFuture<Reading>()

        fun check() {
            if (expected >= 0 && windows.size >= expected && (!wantScreenshot || screenshotDone)) done.complete(this)
        }
    }

    private val main = Handler(Looper.getMainLooper())

    @Volatile private var pending: Reading? = null

    /** Reads the screen. Worker thread; at most [timeoutMs]. */
    fun read(c: Context, screenshot: Boolean, timeoutMs: Long = 6000): Reading {
        val r = Reading().apply { wantScreenshot = screenshot }
        synchronized(this) {
            if (pending != null) throw ToolError("Quire is already reading the screen; try again in a moment.")
            pending = r
        }
        try {
            val started = CompletableFuture<Boolean>()
            main.post {
                val vis = QuireVoiceInteractionService.instance
                if (vis == null) {
                    started.complete(false)
                    return@post
                }
                vis.allowScreenContext(true)
                val flags = VoiceInteractionSession.SHOW_WITH_ASSIST or
                    VoiceInteractionSession.SHOW_WITH_ASSIST_STRUCTURE_SCREEN_CONTENT or
                    if (screenshot) VoiceInteractionSession.SHOW_WITH_SCREENSHOT else 0
                vis.showSession(Bundle().apply { putBoolean(EXTRA_READ, true) }, flags)
                started.complete(true)
            }
            if (!started.get(2, TimeUnit.SECONDS)) throw ToolError("Quire isn't the laptop's assistant, so it can't read the screen.")
            return try {
                r.done.get(timeoutMs, TimeUnit.MILLISECONDS)
            } catch (e: java.util.concurrent.TimeoutException) {
                Log.i(TAG, "tools: screen read timed out with ${r.windows.size}/${r.expected} windows, " +
                    "screenshot=${r.screenshot != null}")
                r
            }
        } finally {
            r.done.complete(r)
            synchronized(this) { pending = null }
            main.post { QuireVoiceInteractionService.instance?.allowScreenContext(false) }
        }
    }

    /** Runs [action] once the current read is complete or given up. */
    fun whenDone(action: () -> Unit) {
        val r = pending ?: return action()
        r.done.whenComplete { _, _ -> action() }
    }

    /** QuireSession, for a read: the activities' structures, one by one. */
    fun onAssist(state: VoiceInteractionSession.AssistState) {
        val r = pending ?: return
        synchronized(r) {
            r.expected = state.count
            val s = state.assistStructure
            if (s != null) r.windows += Window(s.activityComponent?.packageName ?: "", null, outline(s))
            else r.windows += Window(state.assistContent?.intent?.`package` ?: "", null, "")
            r.check()
        }
    }

    fun onScreenshot(b: Bitmap?) {
        val r = pending ?: return
        synchronized(r) {
            r.screenshot = b
            r.screenshotDone = true
            r.check()
        }
    }

    /** No assist data will come (the platform withheld it). */
    fun onNoAssist() {
        val r = pending ?: return
        synchronized(r) {
            if (r.expected < 0) r.expected = 0
            r.check()
        }
    }

    private const val MAX_WINDOW = 12_000

    /** A compact outline of [s]: one line per node that says something, indented by depth. */
    fun outline(s: AssistStructure): String = buildString {
        for (i in 0 until s.windowNodeCount) {
            val w = s.getWindowNodeAt(i)
            w.title?.takeIf { it.isNotBlank() }?.let { append("window: ").append(it).append('\n') }
            w.rootViewNode?.let { node(it, 0, this) }
        }
    }.let { if (it.length > MAX_WINDOW) it.take(MAX_WINDOW) + "\n…(cut)" else it }

    private fun node(n: AssistStructure.ViewNode, depth: Int, out: StringBuilder) {
        // Password text never reaches assist (TextView leaves it out); a node blocked from assist is skipped whole.
        if (out.length > MAX_WINDOW || n.visibility != android.view.View.VISIBLE || n.isAssistBlocked) return
        val text = n.text?.toString()?.trim()?.takeIf { it.isNotEmpty() }
        val desc = n.contentDescription?.toString()?.trim()?.takeIf { it.isNotEmpty() }
        val hint = n.hint?.trim()?.takeIf { it.isNotEmpty() }
        val label = text ?: desc ?: hint
        var d = depth
        if (label != null || n.isCheckable) {
            val kind = n.className?.substringAfterLast('.')?.let {
                when {
                    it.contains("Button") -> "button"
                    it.contains("EditText") || it.contains("TextField") -> "field"
                    it.contains("Switch") || it.contains("Toggle") -> "switch"
                    it.contains("CheckBox") -> "checkbox"
                    it.contains("Image") -> "image"
                    else -> null
                }
            }
            out.append("  ".repeat(depth.coerceAtMost(12)))
            if (kind != null) out.append('[').append(kind).append("] ")
            out.append(label?.take(400) ?: "")
            if (text != null && desc != null && desc != text) out.append(" — ").append(desc.take(200))
            if (n.isCheckable) out.append(if (n.isChecked) " (on)" else " (off)")
            if (n.isSelected) out.append(" (selected)")
            if (n.isFocused) out.append(" (focused)")
            if (hint != null && text != null) out.append(" (hint: ").append(hint.take(100)).append(')')
            out.append('\n')
            d++
        }
        for (i in 0 until n.childCount) node(n.getChildAt(i), d, out)
    }
}

object ScreenTools {
    private val readScreen = object : Tool("read_screen", Tier.OBSERVE, "read") {
        override val description = "Read what is on the laptop's screen now: each visible window's app and its text " +
            "and controls (buttons, fields, switches). Use it for \"what's on my screen?\" and before acting on what " +
            "the person is looking at. Protected windows are never read."
        override val schema = Schema.obj()
        override fun title(c: Context, args: JSONObject) = "Reading the screen"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val windows = LiveContext.windows(c)
            ScreenConsentActivity.ensure(c, note)
            note.retitle("Reading the screen")
            val r = ScreenReader.read(c, screenshot = false)
            val out = StringBuilder()
            out.append("Windows on screen, front first:\n")
            windows.forEach { out.append("- ").append(it.describe()).append('\n') }
            if (windows.isEmpty()) out.append("- (none: the desktop)\n")
            val read = r.windows.filter { it.text.isNotBlank() }
            if (read.isEmpty()) {
                out.append("\nThe windows' text isn't available now: a protected window may be showing, or Quire's " +
                    "note isn't on screen (the laptop lets its assistant read the screen only while the assistant " +
                    "shows). take_screenshot may still work.")
            }
            for (w in read) {
                out.append("\n## ").append(Apps.label(c, w.app)).append('\n').append(w.text)
            }
            return ToolResult.text(out.toString().trim())
        }
    }

    private val screenshot = object : Tool("take_screenshot", Tier.OBSERVE, "read") {
        override val description = "Take a picture of the laptop's screen, for when you need to see it (images, " +
            "layout). Protected windows come out black. Prefer read_screen for text."
        override val schema = Schema.obj()
        override fun title(c: Context, args: JSONObject) = "Looking at the screen"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            ScreenConsentActivity.ensure(c, note)
            note.retitle("Looking at the screen")
            val r = ScreenReader.read(c, screenshot = true)
            val b = r.screenshot ?: throw ToolError("The laptop gave no screenshot: the person may have turned off " +
                "\"Use screenshot\" for Quire, or a protected window is showing.")
            return ToolResult.image("The laptop's screen, ${b.width}×${b.height}:", b)
        }
    }

    val all: List<Tool> = listOf(readScreen, screenshot)
}
