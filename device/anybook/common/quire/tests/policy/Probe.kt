// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
package dev.openbook.quire.tools
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Rect
import org.json.JSONObject
class FakeControl: AgentControl {
    override val app = "Chat"
    override val pageTitles = listOf("Chat")
    var target = AgentControl.Target(10, 20, "Send", null)
    var taps = 0
    var types = 0
    var submissions = 0
    override fun open(app: Apps.App): String? = null
    override fun read() = "Chat composer"
    override fun locate(text: String?, node: Int?, x: Int?, y: Int?) = target
    override fun tap(t: AgentControl.Target, title: String): String? { taps++; return null }
    override fun type(text: String, replace: Boolean, submit: Boolean, title: String): String? {
        types++; if (submit) submissions++; return null
    }
    override fun scroll(down: Boolean, title: String): String? = null
    override fun back(title: String): String? = null
    override fun screenshot(): Bitmap? = null
    override fun end(handOver: Boolean) = "done"
}
class DenyingNote(override val control: FakeControl = FakeControl(), val allow: Boolean = false): CallNote {
    val asks = mutableListOf<Ask>()
    var confirms = 0
    override fun retitle(title: String) {}
    override fun confirm(ask: Ask): Boolean { confirms++; asks.add(ask); return allow }
    override fun changed(entries: List<ChangeLog.Entry>) {}
}
val context = Context()
fun call(tool: Tool, args: JSONObject, note: DenyingNote): ToolResult {
    // Same ask-before-run contract as Broker.run; note is live and not cancelled.
    val ask = tool.ask(context, args)
    check(tool.tier != Tier.CONFIRM || ask != null)
    if (ask != null && !note.confirm(ask)) return ToolResult.error(Broker.DENIED)
    return tool.run(context, args, note)
}
fun main() {
    val tap = ControlTools.all.single { it.name == "control_tap" }
    val type = ControlTools.all.single { it.name == "control_type" }
    var failures = 0
    var total = 0
    fun result(name: String, safe: Boolean, evidence: String) {
        total++
        println("${if (safe) "PASS" else "FAIL"}: $name; $evidence")
        if (!safe) failures++
    }
    DenyingNote().let { n ->
        call(tap, JSONObject().put("text", "Send"), n)
        result("labelled Send tap denied", n.confirms == 1 && n.control.taps == 0,
            "confirmations=${n.confirms} taps=${n.control.taps}")
    }
    DenyingNote().let { n ->
        call(type, JSONObject().put("text", "message").put("submit", true), n)
        result("submission cannot bypass confirmation", n.control.submissions == 0,
            "confirmations=${n.confirms} submissions=${n.control.submissions}")
    }
    DenyingNote().let { n ->
        n.control.target = AgentControl.Target(10, 20, "the point 10,20", null)
        call(tap, JSONObject().put("x", 10).put("y", 20), n)
        result("unclassified coordinate tap requires confirmation", n.control.taps == 0,
            "confirmations=${n.confirms} taps=${n.control.taps}")
    }
    DenyingNote().let { n ->
        call(type, JSONObject().put("text", "draft").put("submit", false), n)
        result("ordinary draft typing stays automatic", n.confirms == 0 && n.control.types == 1,
            "confirmations=${n.confirms} types=${n.control.types}")
    }
    DenyingNote().let { n ->
        call(SettingsTools.changeSetting, JSONObject().put("name", "usb_debugging").put("value", "on"), n)
        result("direct adb change denied", n.confirms == 1 && SettingsCatalog.setting.writes == 0,
            "confirmations=${n.confirms} writes=${SettingsCatalog.setting.writes}")
    }
    DenyingNote().let { n ->
        call(SettingsTools.undoChange, JSONObject().put("name", "usb_debugging"), n)
        result("agent adb undo cannot bypass confirmation", SettingsCatalog.setting.writes == 0,
            "confirmations=${n.confirms} writes=${SettingsCatalog.setting.writes} value=${SettingsCatalog.setting.value}")
    }
    DenyingNote(allow = true).let { n ->
        call(type, JSONObject().put("text", "message").put("submit", true), n)
        result("allowed submission dispatches once", n.confirms == 1 && n.control.submissions == 1,
            "confirmations=${n.confirms} submissions=${n.control.submissions}")
    }
    DenyingNote(allow = true).let { n ->
        n.control.target = AgentControl.Target(10, 20, "the point 10,20", null)
        call(tap, JSONObject().put("x", 10).put("y", 20), n)
        result("allowed unclassified tap dispatches once", n.confirms == 1 && n.control.taps == 1,
            "confirmations=${n.confirms} taps=${n.control.taps}")
    }
    DenyingNote().let { n ->
        n.control.target = AgentControl.Target(10, 20, "", Rect())
        call(tap, JSONObject().put("control", 1), n)
        result("unlabelled accessible target denied", n.confirms == 1 && n.control.taps == 0,
            "confirmations=${n.confirms} taps=${n.control.taps}")
    }
    DenyingNote().let { n ->
        n.control.target = AgentControl.Target(10, 20, "Bluetooth", Rect())
        call(tap, JSONObject().put("text", "Bluetooth"), n)
        result("ordinary labelled tap stays automatic", n.confirms == 0 && n.control.taps == 1,
            "confirmations=${n.confirms} taps=${n.control.taps}")
    }
    for (key in listOf("usb_debugging", "wireless_debugging", "developer_options")) {
        for (allow in listOf(false, true)) {
            val setting = SettingsCatalog.setting
            setting.key = key; setting.sensitive = true; setting.value = "off"; setting.writes = 0
            ChangeLog.log.entry = ChangeLog.Entry(1, key, key, "Developer options", "on", "off", "On", "Off")
            val n = DenyingNote(allow = allow)
            call(SettingsTools.undoChange, JSONObject().put("id", 1), n)
            result("sensitive undo $key allow=$allow", n.confirms == 1 &&
                setting.writes == (if (allow) 1 else 0) && setting.value == (if (allow) "on" else "off") &&
                ChangeLog.log.entry.undone == allow && n.asks.single().rows.single().new == "on",
                "confirmations=${n.confirms} writes=${setting.writes} value=${setting.value}")
        }
    }
    SettingsCatalog.setting.apply { key = "dark_theme"; sensitive = false; value = "off"; writes = 0 }
    ChangeLog.log.entry = ChangeLog.Entry(1, "dark_theme", "Dark theme", "Display", "on", "off", "On", "Off")
    DenyingNote().let { n ->
        call(SettingsTools.undoChange, JSONObject(), n)
        result("ordinary undo stays automatic", n.confirms == 0 && SettingsCatalog.setting.writes == 1,
            "confirmations=${n.confirms} writes=${SettingsCatalog.setting.writes}")
    }
    println("${total - failures} pass, $failures fail (policy expectations, not compilation errors)")
    if (failures > 0) kotlin.system.exitProcess(1)
}
