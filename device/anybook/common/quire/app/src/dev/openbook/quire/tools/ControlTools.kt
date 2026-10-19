// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Rect
import org.json.JSONObject

/**
 * The note's computer-control run, as the tools drive it (implemented by note/TaskControl.kt on ControlRun). Every
 * method blocks the calling worker thread until the step is done; the run does its part on the main thread, in the
 * mirror the person watches, and holds a step while they have paused.
 */
interface AgentControl {
    /** The app being driven, or null when no run is live. */
    val app: String?

    /** Opens [app] on a computer-control display after the platform's consent. Null when it is open, else why not. */
    fun open(app: Apps.App): String?

    /** The display's text and controls, numbered (control_read). */
    fun read(): String

    /** What a tap on [text], control [node] or ([x], [y]) would hit, found within a few seconds; null if nothing. */
    fun locate(text: String?, node: Int?, x: Int?, y: Int?): Target?

    /** Titles of the session's windows (the page the app shows), from the last read or locate. */
    val pageTitles: List<String>

    fun tap(t: Target, title: String): String?
    fun type(text: String, replace: Boolean, submit: Boolean, title: String): String?
    fun scroll(down: Boolean, title: String): String?
    fun back(title: String): String?
    fun screenshot(): Bitmap?

    /** Ends the run: closes the app's session, or hands the app to the person's screen. */
    fun end(handOver: Boolean): String

    data class Target(val x: Int, val y: Int, val label: String, val bounds: Rect?)
}

object ControlTools {
    /**
     * Controls whose tap can't be taken back (§5.3: the never tier inside an automated app): the person allows each one
     * first. English labels, as OpenBook's apps are in English today; other languages are listed as an open point.
     */
    private val DESTRUCTIVE = Regex("\\b(delete|remove|uninstall|disable|deactivate|clear (storage|data|cache|all)|" +
        "erase|reset|factory|format|wipe|forget|unpair|revoke|send|post|publish|share|reply|pay|buy|purchase|" +
        "checkout|check out|place order|order now|subscribe|donate|transfer|sign out|log out|logout|turn off screen lock|" +
        "remove account|force stop|end call|call)\\b", RegexOption.IGNORE_CASE)

    /** Pages where every step asks first: the laptop's protection, accounts, developer settings, resets. */
    private val SENSITIVE_PAGES = Regex("(security|privacy|screen lock|lock screen|password|passkey|account|" +
        "developer|debugging|reset|encryption|credential|device admin|admin apps|biometric|fingerprint|face unlock|" +
        "unknown apps|install unknown|special app access|device & app notifications|permission manager)",
        RegexOption.IGNORE_CASE)

    private fun sensitivePage(control: AgentControl): String? = control.pageTitles.firstOrNull { SENSITIVE_PAGES.containsMatchIn(it) }

    private fun live(note: CallNote): AgentControl {
        val c = note.control
        if (c.app == null) throw ToolError("No app is being operated. Start with control_start.")
        return c
    }

    private val start = object : Tool("control_start", Tier.ACT, "app") {
        override val description = "Operate an app for the person with computer control: the app opens on a " +
            "separate screen that the person watches live in the note, and can pause or take over. The first time for " +
            "an app, the laptop asks the person to allow it. Then use control_read, control_tap, control_type, " +
            "control_scroll, control_back, and control_end when done. Use it when the person asks you to do " +
            "something in an app (\"in Settings, find Bluetooth and turn it off\")."
        override val schema = Schema.obj("app" to Schema.str("The app, e.g. \"Settings\"."), required = listOf("app"))
        override fun title(c: Context, args: JSONObject) = "Opening ${args.optString("app")} to work in it"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val app = Apps.find(c, args.req("app"))
            val control = note.control
            if (control.app == app.label) return ToolResult.text("${app.label} is already open for you. " + control.read())
            if (control.app != null) control.end(handOver = false)
            note.retitle("Opening ${app.label} to work in it")
            control.open(app)?.let { throw ToolError(it) }
            return ToolResult.text("${app.label} is open on the computer-control screen, which the person is " +
                "watching. Its screen now:\n" + control.read())
        }
    }

    private val read = object : Tool("control_read", Tier.OBSERVE, "read") {
        override val description = "Read the app on the computer-control screen: its text and its controls, " +
            "numbered [n] for control_tap. Read again after each step to see what changed."
        override val schema = Schema.obj()
        override fun title(c: Context, args: JSONObject) = "Reading the app"
        override fun run(c: Context, args: JSONObject, note: CallNote) = ToolResult.text(live(note).read())
    }

    private val tap = object : Tool("control_tap", Tier.ACT, "execute") {
        override val description = "Tap a control of the app on the computer-control screen: by its text (\"Bluetooth\"), " +
            "by its number from control_read, or at x,y. Taps that delete, send, pay or the like, and any step on " +
            "security, account or developer pages, ask the person first."
        override val schema = Schema.obj("text" to Schema.str("The control's text (optional)."),
            "control" to Schema.int("The control's number from control_read (optional)."),
            "x" to Schema.int("Screen x (optional, with y)."), "y" to Schema.int("Screen y (optional, with x)."))
        override fun title(c: Context, args: JSONObject) =
            "Tapping " + (args.str("text")?.let { "“$it”" } ?: args.str("control")?.let { "control $it" } ?: "the app")

        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val control = live(note)
            val t = control.locate(args.str("text"), if (args.has("control")) args.getInt("control") else null,
                if (args.has("x")) args.getInt("x") else null, if (args.has("y")) args.getInt("y") else null)
                ?: throw ToolError("Nothing like that is on ${control.app}'s screen now. Read it again (control_read).")
            val title = "Tapping “${t.label.take(60)}”"
            note.retitle(title)
            val page = sensitivePage(control)
            val destructive = DESTRUCTIVE.find(t.label)
            if (page != null || destructive != null) {
                val why = if (destructive != null) "“${t.label.take(80)}” may change something that can't be undone."
                    else "This page of ${control.app} (“$page”) protects the laptop or your accounts."
                if (!note.confirm(Ask("Tap “${t.label.take(60)}” in ${control.app}?", why = why +
                        " Quire can't undo it."))) {
                    return ToolResult.error(Broker.DENIED)
                }
            }
            control.tap(t, title)?.let { throw ToolError(it) }
            return ToolResult.text("Tapped “${t.label.take(80)}”. The screen now:\n" + control.read())
        }
    }

    private val type = object : Tool("control_type", Tier.ACT, "execute") {
        override val description = "Type text into the focused field of the app on the computer-control screen (tap " +
            "the field first). Never for passwords: the person types those."
        override val schema = Schema.obj("text" to Schema.str("The text."),
            "replace" to Schema.bool("Replace what the field holds (default false)."),
            "submit" to Schema.bool("Press Enter after it (default false)."), required = listOf("text"))
        override fun title(c: Context, args: JSONObject) = "Typing in the app"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val control = live(note)
            val page = sensitivePage(control)
            val submit = args.optBoolean("submit")
            if (page != null && !note.confirm(Ask("Type in ${control.app}?", why = "This page (“$page”) protects the " +
                    "laptop or your accounts."))) {
                return ToolResult.error(Broker.DENIED)
            }
            control.type(args.optString("text"), args.optBoolean("replace"), submit, "Typing “${args.optString("text")
                .take(40)}”")?.let { throw ToolError(it) }
            return ToolResult.text("Typed. The screen now:\n" + control.read())
        }
    }

    private val scroll = object : Tool("control_scroll", Tier.ACT, "execute") {
        override val description = "Scroll the app on the computer-control screen up or down, to find a control."
        override val schema = Schema.obj("direction" to Schema.str("Which way.", listOf("down", "up")),
            required = listOf("direction"))
        override fun title(c: Context, args: JSONObject) = "Scrolling ${args.optString("direction")}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val control = live(note)
            control.scroll(args.optString("direction") != "up", "Scrolling ${args.optString("direction")}")
                ?.let { throw ToolError(it) }
            return ToolResult.text("Scrolled. The screen now:\n" + control.read())
        }
    }

    private val back = object : Tool("control_back", Tier.ACT, "execute") {
        override val description = "Go back one screen in the app on the computer-control screen."
        override val schema = Schema.obj()
        override fun title(c: Context, args: JSONObject) = "Going back"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val control = live(note)
            control.back("Going back")?.let { throw ToolError(it) }
            return ToolResult.text("Went back. The screen now:\n" + control.read())
        }
    }

    private val shot = object : Tool("control_screenshot", Tier.OBSERVE, "read") {
        override val description = "See the app on the computer-control screen as a picture, for what its text " +
            "doesn't say."
        override val schema = Schema.obj()
        override fun title(c: Context, args: JSONObject) = "Looking at the app"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val control = live(note)
            val b = control.screenshot() ?: throw ToolError("No picture: the app may be showing a protected screen.")
            return ToolResult.image("${control.app}, ${b.width}×${b.height}:", b)
        }
    }

    private val end = object : Tool("control_end", Tier.ACT, "app") {
        override val description = "Finish operating the app: close it, or with hand_over put it on the person's own " +
            "screen to continue there. Call it when the task in the app is done."
        override val schema = Schema.obj("hand_over" to Schema.bool("Put the app on the person's screen (default false)."))
        override fun title(c: Context, args: JSONObject) = if (args.optBoolean("hand_over")) "Handing the app over" else
            "Closing the app"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val control = note.control
            if (control.app == null) return ToolResult.text("No app was being operated.")
            return ToolResult.text(control.end(args.optBoolean("hand_over")))
        }
    }

    val all: List<Tool> = listOf(start, read, tap, type, scroll, back, shot, end)
}
