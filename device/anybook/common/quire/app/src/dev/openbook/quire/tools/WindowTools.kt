// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.app.ActivityManager
import android.app.ActivityTaskManager
import android.app.WindowConfiguration
import android.content.Context
import android.graphics.Rect
import android.hardware.display.DisplayManager
import android.view.Display
import android.view.WindowInsets
import android.view.WindowManager
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import org.json.JSONObject

/** The windows on the person's screen, and the short context block each prompt opens with (ANAL-220). */
object LiveContext {
    class Win(val taskId: Int, val pkg: String, val app: String, val bounds: Rect, val visible: Boolean,
        val focused: Boolean, val freeform: Boolean) {
        fun describe(): String = "$app (window $taskId" + (if (focused) ", focused" else "") +
            (if (!visible) ", minimized" else "") +
            (if (freeform) ", at ${bounds.left},${bounds.top} size ${bounds.width()}×${bounds.height()}" else ", full screen") + ")"
    }

    private val HIDDEN = setOf("com.android.systemui", "dev.openbook.quire")

    /** The app windows on the person's display, front first; [all] includes minimized ones. */
    fun windows(c: Context, all: Boolean = false): List<Win> {
        val tasks = ActivityTaskManager.getInstance().getTasks(64, false, false, Display.DEFAULT_DISPLAY)
        return tasks.filter { t ->
            val type = t.configuration.windowConfiguration.activityType
            type == WindowConfiguration.ACTIVITY_TYPE_STANDARD || type == WindowConfiguration.ACTIVITY_TYPE_UNDEFINED
        }.mapNotNull { t ->
            val pkg = (t.topActivity ?: t.baseActivity)?.packageName ?: return@mapNotNull null
            if (pkg in HIDDEN) return@mapNotNull null
            Win(t.taskId, pkg, Apps.label(c, pkg), Rect(t.configuration.windowConfiguration.bounds), t.isVisible,
                t.isFocused, t.configuration.windowConfiguration.windowingMode == WindowConfiguration.WINDOWING_MODE_FREEFORM)
        }.filter { all || it.visible }
    }

    /**
     * The context block a prompt opens with: who the agent is (first prompt only), the time, the person's language, and
     * the apps on screen by name. Window titles are left out: they can hold a message's subject or a document's name.
     */
    fun block(c: Context, first: Boolean): String = buildString {
        append("[Quire context, from Quire, not from the person]\n")
        if (first) append(Skill.PREFACE).append('\n')
        val now = Date()
        val tz = TimeZone.getDefault()
        append("Time: ").append(SimpleDateFormat("EEEE d MMMM yyyy, HH:mm", Locale.ENGLISH).format(now))
            .append(' ').append(tz.getDisplayName(tz.inDaylightTime(now), TimeZone.SHORT, Locale.ENGLISH))
            .append(" (").append(tz.id).append(")\n")
        val locale = c.resources.configuration.locales[0]
        append("The person's language: ").append(locale.getDisplayName(Locale.ENGLISH)).append('\n')
        val wins = runCatching { windows(c) }.getOrDefault(emptyList())
        append("On screen: ")
        append(if (wins.isEmpty()) "the desktop, no app windows" else wins.joinToString(", ") {
            it.app + if (it.focused) " (focused)" else "" })
        append('\n')
    }

    /** The display's area for windows: the whole display less the taskbar and other system bars. */
    fun workArea(c: Context): Rect {
        val display = c.getSystemService(DisplayManager::class.java).getDisplay(Display.DEFAULT_DISPLAY)
        val wm = c.createDisplayContext(display).getSystemService(WindowManager::class.java)
        val m = wm.maximumWindowMetrics
        val insets = m.windowInsets.getInsetsIgnoringVisibility(WindowInsets.Type.systemBars() or
            WindowInsets.Type.displayCutout())
        val b = m.bounds
        return Rect(b.left + insets.left, b.top + insets.top, b.right - insets.right, b.bottom - insets.bottom)
    }
}

object WindowTools {
    private fun find(c: Context, which: String): LiveContext.Win {
        val wins = LiveContext.windows(c, all = true)
        which.toIntOrNull()?.let { id -> wins.firstOrNull { it.taskId == id }?.let { return it } }
        val app = runCatching { Apps.find(c, which, wins.map { Apps.App(it.app, it.pkg,
            android.content.ComponentName(it.pkg, "")) }) }.getOrNull()
        return app?.let { a -> wins.firstOrNull { it.pkg == a.pkg } }
            ?: throw ToolError("No window \"$which\". Windows: " + wins.joinToString("; ") { it.describe() }.ifEmpty { "none" })
    }

    private val windowArg = "window" to Schema.str("The window: its app's name, or its number from list_windows.")

    private val listWindows = object : Tool("list_windows", Tier.OBSERVE, "read") {
        override val description = "List the app windows on the laptop's screen, front first, with their numbers, " +
            "positions and sizes, and the screen's work area."
        override val schema = Schema.obj()
        override fun title(c: Context, args: JSONObject) = "Looking at the windows"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val wins = LiveContext.windows(c, all = true)
            val area = LiveContext.workArea(c)
            return ToolResult.text("Work area: ${area.left},${area.top} to ${area.right},${area.bottom}\n" +
                wins.joinToString("\n") { "- " + it.describe() }.ifEmpty { "No app windows are open." })
        }
    }

    private val focusWindow = object : Tool("focus_window", Tier.ACT, "window") {
        override val description = "Bring a window to the front, or switch to an app that is already open."
        override val schema = Schema.obj(windowArg, required = listOf("window"))
        override fun title(c: Context, args: JSONObject) = "Switching to ${args.optString("window")}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val w = find(c, args.req("window"))
            note.retitle("Switching to ${w.app}")
            c.getSystemService(ActivityManager::class.java).moveTaskToFront(w.taskId, 0)
            return ToolResult.text("${w.app} is in front.")
        }
    }

    private val moveWindow = object : Tool("move_window", Tier.ACT, "window") {
        override val description = "Move or resize a window: give a new position (x, y), a new size (width, height), " +
            "or both, in screen pixels (list_windows shows the work area)."
        override val schema = Schema.obj(windowArg, "x" to Schema.int("Left edge (optional)."),
            "y" to Schema.int("Top edge (optional)."), "width" to Schema.int("Width (optional)."),
            "height" to Schema.int("Height (optional)."), required = listOf("window"))
        override fun title(c: Context, args: JSONObject) = "Moving ${args.optString("window")}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val w = find(c, args.req("window"))
            if (!w.freeform) throw ToolError("${w.app} fills the screen; it can't be moved. Use maximize_window to " +
                "toggle it, or ask the person to make it a window.")
            val area = LiveContext.workArea(c)
            val width = if (args.has("width")) args.getInt("width") else w.bounds.width()
            val height = if (args.has("height")) args.getInt("height") else w.bounds.height()
            val x = if (args.has("x")) args.getInt("x") else w.bounds.left
            val y = if (args.has("y")) args.getInt("y") else w.bounds.top
            val r = Rect(x, y, x + width.coerceIn(320, area.width()), y + height.coerceIn(240, area.height()))
            r.offset((area.left - r.left).coerceAtLeast(0) - (r.right - area.right).coerceAtLeast(0),
                (area.top - r.top).coerceAtLeast(0) - (r.bottom - area.bottom).coerceAtLeast(0))
            note.retitle(if (args.has("width") || args.has("height")) "Resizing ${w.app}" else "Moving ${w.app}")
            ActivityTaskManager.getInstance().resizeTask(w.taskId, r)
            return ToolResult.text("${w.app} is at ${r.left},${r.top}, ${r.width()}×${r.height()}.")
        }
    }

    private val maximizeWindow = object : Tool("maximize_window", Tier.ACT, "window") {
        override val description = "Make a window fill the screen's work area (above the taskbar)."
        override val schema = Schema.obj(windowArg, required = listOf("window"))
        override fun title(c: Context, args: JSONObject) = "Maximizing ${args.optString("window")}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val w = find(c, args.req("window"))
            note.retitle("Maximizing ${w.app}")
            if (!w.freeform) return ToolResult.text("${w.app} already fills the screen.")
            ActivityTaskManager.getInstance().resizeTask(w.taskId, LiveContext.workArea(c))
            c.getSystemService(ActivityManager::class.java).moveTaskToFront(w.taskId, 0)
            return ToolResult.text("${w.app} fills the screen.")
        }
    }

    private val closeWindow = object : Tool("close_window", Tier.ACT, "window") {
        override val description = "Close a window, as its close button does."
        override val schema = Schema.obj(windowArg, required = listOf("window"))
        override fun title(c: Context, args: JSONObject) = "Closing ${args.optString("window")}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val w = find(c, args.req("window"))
            note.retitle("Closing ${w.app}")
            if (!ActivityTaskManager.getInstance().removeTask(w.taskId)) throw ToolError("${w.app} didn't close.")
            return ToolResult.text("Closed ${w.app}.")
        }
    }

    val all: List<Tool> = listOf(listWindows, focusWindow, moveWindow, maximizeWindow, closeWindow)
}
