// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
@file:Suppress("UNUSED_PARAMETER")
package dev.openbook.quire.tools
import android.content.Context
import android.graphics.Bitmap
import org.json.JSONObject
enum class Tier { OBSERVE, ACT, CONFIRM }
class ToolError(message: String): Exception(message)
data class Change(val name: String, val where: String, val old: String, val new: String)
data class Ask(val title: String, val rows: List<Change> = emptyList(), val detail: String? = null, val why: String, val verb: String = "Allow", val keep: String = "Keep it")
class ToolResult(val text: String, val error: Boolean = false) {
    companion object {
        fun text(s: String) = ToolResult(s)
        fun error(s: String) = ToolResult(s, true)
        fun image(s: String, bitmap: Bitmap) = ToolResult(s)
    }
}
interface CallNote {
    fun retitle(title: String)
    fun confirm(ask: Ask): Boolean
    fun changed(entries: List<ChangeLog.Entry>)
    val control: AgentControl
}
abstract class Tool(val name: String, val tier: Tier, val kind: String) {
    abstract val description: String
    abstract val schema: JSONObject
    abstract fun title(c: Context, args: JSONObject): String
    open fun ask(c: Context, args: JSONObject): Ask? = null
    abstract fun run(c: Context, args: JSONObject, note: CallNote): ToolResult
}
object Schema {
    fun obj(vararg props: Pair<String, JSONObject>, required: List<String> = emptyList()) = JSONObject()
    fun str(description: String, enum: List<String>? = null) = JSONObject()
    fun int(description: String) = JSONObject()
    fun bool(description: String) = JSONObject()
}
fun JSONObject.req(k: String): String = optString(k).trim().ifEmpty { throw ToolError("Missing $k") }
fun JSONObject.str(k: String): String? = optString(k).trim().ifEmpty { null }
object Broker { const val DENIED = "Denied" }
object Apps {
    data class App(val label: String)
    fun find(c: Context, name: String) = App(name)
}
class Setting(var key: String, var sensitive: Boolean) {
    val name = key
    val where = "System / Developer options"
    var value = "off"
    var writes = 0
    fun get(c: Context) = value
    fun set(c: Context, raw: String) { writes++; value = raw }
    fun label(raw: String) = raw
    fun available(c: Context) = true
    fun parse(c: Context, input: String, current: String) = input
}
object SettingsCatalog {
    val setting = Setting("usb_debugging", true)
    fun find(c: Context, name: String): Setting = setting
    fun byKey(key: String): Setting? = setting.takeIf { it.key == key }
}
class ChangeLog {
    data class Entry(val id: Long, val key: String, val name: String, val where: String,
        val old: String, val new: String, val oldLabel: String, val newLabel: String, var undone: Boolean = false)
    var entry = Entry(1, "usb_debugging", "USB debugging", "Developer options", "on", "off", "On", "Off")
    fun find(id: Long) = entry.takeIf { it.id == id }
    fun last(key: String? = null) = entry.takeIf { key == null || it.key == key }
    fun markUndone(id: Long) { entry.undone = true }
    fun record(key: String, name: String, where: String, old: String, new: String, oldLabel: String, newLabel: String) =
        Entry(2, key, name, where, old, new, oldLabel, newLabel)
    companion object { val log = ChangeLog(); fun get(c: Context) = log }
}

object LiveContext {
    data class Window(val taskId: Int, val pkg: String)
    fun windows(c: Context, all: Boolean): List<Window> = emptyList()
}
