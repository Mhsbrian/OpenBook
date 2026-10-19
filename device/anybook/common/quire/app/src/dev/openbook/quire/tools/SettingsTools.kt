// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.app.UiModeManager
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.hardware.display.ColorDisplayManager
import android.hardware.display.DisplayManager
import android.location.LocationManager
import android.media.AudioManager
import android.net.ConnectivityManager
import android.net.wifi.WifiManager
import android.os.PowerManager
import android.os.Process
import android.provider.Settings
import android.view.Display
import dev.openbook.quire.note.Change
import org.json.JSONObject
import kotlin.math.roundToInt

/**
 * A setting people change, read and written through the platform's own API for it (the one Settings uses), so a
 * change by Quire is the same as the person's own. Values are kept as raw strings, for the change log's undo.
 */
abstract class Setting(val key: String, val name: String, val where: String, val choices: String) {
    /** The current value, raw. */
    abstract fun get(c: Context): String

    abstract fun set(c: Context, raw: String)

    /** The raw value [input] means, given [current] ("bigger" depends on it). Throws a [ToolError] naming the choices. */
    abstract fun parse(c: Context, input: String, current: String): String

    /** The value as people read it. */
    open fun label(raw: String): String = raw

    open fun available(c: Context): Boolean = true

    /** Settings that weaken the laptop's protection: the person allows each change first. */
    open val sensitive: Boolean = false

    protected fun bad(input: String): Nothing = throw ToolError("\"$input\" is not a value for $name. Choices: $choices.")
}

private val ON = setOf("on", "true", "yes", "1", "enable", "enabled", "activate", "start")
private val OFF = setOf("off", "false", "no", "0", "disable", "disabled", "deactivate", "stop")

private fun word(s: String) = s.trim().lowercase().removePrefix("turn ").trim()

/** An on/off setting. */
private abstract class Switch(key: String, name: String, where: String) : Setting(key, name, where, "on, off") {
    abstract fun isOn(c: Context): Boolean
    abstract fun turn(c: Context, on: Boolean)
    override fun get(c: Context) = if (isOn(c)) "on" else "off"
    override fun set(c: Context, raw: String) = turn(c, raw == "on")
    override fun parse(c: Context, input: String, current: String): String = when (word(input)) {
        in ON -> "on"
        in OFF -> "off"
        "toggle", "switch" -> if (current == "on") "off" else "on"
        else -> bad(input)
    }
    override fun label(raw: String) = if (raw == "on") "On" else "Off"
}

/** A percentage, 0 to 100; "up", "more", "max" and their opposites move it. */
private abstract class Percent(key: String, name: String, where: String, val step: Int = 10) :
    Setting(key, name, where, "0 to 100 (%), or up, down, max, min") {
    override fun parse(c: Context, input: String, current: String): String {
        val w = word(input)
        val now = current.toIntOrNull() ?: 50
        val n = Regex("^(-?\\d+(?:\\.\\d+)?)\\s*%?$").find(w)?.groupValues?.get(1)?.toDoubleOrNull()
        return when {
            n != null -> (if (n <= 1.0 && w.contains('.')) n * 100 else n).roundToInt().coerceIn(0, 100).toString()
            w in setOf("up", "more", "higher", "brighter", "louder", "increase", "raise") -> (now + step).coerceAtMost(100).toString()
            w in setOf("down", "less", "lower", "dimmer", "darker", "quieter", "softer", "decrease", "reduce") -> (now - step).coerceAtLeast(0).toString()
            w in setOf("max", "maximum", "full", "highest", "brightest", "loudest") -> "100"
            w in setOf("min", "minimum", "lowest", "mute", "silent", "zero") -> "0"
            w in setOf("half", "medium", "middle") -> "50"
            else -> bad(input)
        }
    }
    override fun label(raw: String) = "$raw%"
}

private fun cr(c: Context) = c.contentResolver

object SettingsCatalog {
    private val darkTheme = object : Setting("dark_theme", "Dark theme", "Display › Dark theme", "on, off, auto") {
        private fun ui(c: Context) = c.getSystemService(UiModeManager::class.java)
        override fun get(c: Context) = when (ui(c).nightMode) {
            UiModeManager.MODE_NIGHT_YES -> "on"
            UiModeManager.MODE_NIGHT_NO -> "off"
            UiModeManager.MODE_NIGHT_CUSTOM -> "custom"
            else -> "auto"
        }
        override fun set(c: Context, raw: String) = ui(c).setNightMode(when (raw) {
            "on" -> UiModeManager.MODE_NIGHT_YES
            "off" -> UiModeManager.MODE_NIGHT_NO
            "custom" -> UiModeManager.MODE_NIGHT_CUSTOM
            else -> UiModeManager.MODE_NIGHT_AUTO
        })
        override fun parse(c: Context, input: String, current: String) = when (val w = word(input)) {
            in ON, "dark", "night" -> "on"
            in OFF, "light", "day" -> "off"
            "auto", "automatic", "sunset", "schedule" -> "auto"
            "toggle" -> if (current == "on") "off" else "on"
            else -> bad(w)
        }
        override fun label(raw: String) = when (raw) {
            "on" -> "On"
            "off" -> "Off"
            "custom" -> "On a schedule"
            else -> "Automatic"
        }
    }

    /** Android's own font sizes (Settings' slider). */
    private val SCALES = listOf(0.85f, 1.0f, 1.15f, 1.3f, 1.5f, 1.8f, 2.0f)

    private val fontSize = object : Setting("text_size", "Text size", "Display › Display size and text › Font size",
        "a scale from 0.85 to 2.0 (1.0 is the default), or bigger, smaller, default, largest") {
        override fun get(c: Context) = Settings.System.getFloat(cr(c), Settings.System.FONT_SCALE, 1.0f).toString()
        override fun set(c: Context, raw: String) {
            Settings.System.putFloat(cr(c), Settings.System.FONT_SCALE, raw.toFloat())
        }
        override fun parse(c: Context, input: String, current: String): String {
            val w = word(input)
            val now = current.toFloatOrNull() ?: 1.0f
            val n = Regex("^(\\d+(?:\\.\\d+)?)\\s*(%|x|×)?$").find(w)?.groupValues
            return when {
                n != null -> {
                    var v = n[1].toFloat()
                    if (n[2] == "%" || v > 4f) v /= 100f
                    v.coerceIn(SCALES.first(), SCALES.last()).toString()
                }
                w in setOf("bigger", "larger", "large", "up", "increase", "more") ->
                    (SCALES.firstOrNull { it > now + 0.01f } ?: SCALES.last()).toString()
                w in setOf("smaller", "small", "down", "decrease", "less") ->
                    (SCALES.lastOrNull { it < now - 0.01f } ?: SCALES.first()).toString()
                w in setOf("default", "normal", "reset", "standard") -> "1.0"
                w in setOf("largest", "biggest", "max", "maximum", "huge") -> SCALES.last().toString()
                w in setOf("smallest", "min", "minimum") -> SCALES.first().toString()
                else -> bad(input)
            }
        }
        override fun label(raw: String): String {
            val v = raw.toFloatOrNull() ?: return raw
            val pct = (v * 100).roundToInt()
            return if (pct == 100) "Default (100%)" else "$pct%"
        }
    }

    private val boldText = object : Switch("bold_text", "Bold text", "Display › Display size and text › Bold text") {
        override fun isOn(c: Context) = Settings.Secure.getInt(cr(c), Settings.Secure.FONT_WEIGHT_ADJUSTMENT, 0) > 0
        override fun turn(c: Context, on: Boolean) {
            Settings.Secure.putInt(cr(c), Settings.Secure.FONT_WEIGHT_ADJUSTMENT, if (on) 300 else 0)
        }
    }

    private val batterySaver = object : Switch("battery_saver", "Battery Saver", "Battery › Battery Saver") {
        override fun isOn(c: Context) = c.getSystemService(PowerManager::class.java).isPowerSaveMode
        override fun turn(c: Context, on: Boolean) {
            if (!c.getSystemService(PowerManager::class.java).setPowerSaveModeEnabled(on)) {
                val plugged = c.registerReceiver(null, android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED))
                    ?.getIntExtra(android.os.BatteryManager.EXTRA_PLUGGED, 0) ?: 0
                throw ToolError(if (plugged != 0) "Battery Saver can't be turned on while the laptop is plugged in: " +
                    "Android allows it only on battery (Settings shows the same). It can turn on by itself once " +
                    "unplugged: Settings › Battery › Battery Saver › Set a schedule." else
                    "Battery Saver can't be changed on this laptop now.")
            }
        }
    }

    private val brightness = object : Percent("brightness", "Brightness", "Display › Brightness level") {
        private fun dm(c: Context) = c.getSystemService(DisplayManager::class.java)
        override fun get(c: Context) =
            dm(c).getBrightness(Display.DEFAULT_DISPLAY, DisplayManager.BRIGHTNESS_UNIT_PERCENTAGE).roundToInt().toString()
        override fun set(c: Context, raw: String) =
            dm(c).setBrightness(Display.DEFAULT_DISPLAY, raw.toFloat(), DisplayManager.BRIGHTNESS_UNIT_PERCENTAGE)
    }

    private val autoBrightness = object : Switch("adaptive_brightness", "Adaptive brightness",
        "Display › Adaptive brightness") {
        override fun available(c: Context) =
            c.resources.getBoolean(com.android.internal.R.bool.config_automatic_brightness_available)
        override fun isOn(c: Context) = Settings.System.getInt(cr(c), Settings.System.SCREEN_BRIGHTNESS_MODE, 0) ==
            Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC
        override fun turn(c: Context, on: Boolean) {
            Settings.System.putInt(cr(c), Settings.System.SCREEN_BRIGHTNESS_MODE,
                if (on) Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC else Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL)
        }
    }

    private class Volume(key: String, name: String, val stream: Int) : Percent(key, name, "Sound & vibration › $name") {
        private fun am(c: Context) = c.getSystemService(AudioManager::class.java)
        override fun get(c: Context): String {
            val a = am(c)
            val min = a.getStreamMinVolume(stream)
            val max = a.getStreamMaxVolume(stream)
            return ((a.getStreamVolume(stream) - min) * 100.0 / (max - min).coerceAtLeast(1)).roundToInt().toString()
        }
        override fun set(c: Context, raw: String) {
            val a = am(c)
            val min = a.getStreamMinVolume(stream)
            val max = a.getStreamMaxVolume(stream)
            a.setStreamVolume(stream, min + ((max - min) * raw.toInt() / 100.0).roundToInt(), AudioManager.FLAG_SHOW_UI)
        }
    }

    private val bluetooth = object : Switch("bluetooth", "Bluetooth", "Connected devices › Bluetooth") {
        private fun adapter(c: Context) = c.getSystemService(BluetoothManager::class.java)?.adapter
        override fun available(c: Context) = adapter(c) != null
        override fun isOn(c: Context) = adapter(c)?.isEnabled == true
        @Suppress("DEPRECATION")
        override fun turn(c: Context, on: Boolean) {
            val a = adapter(c) ?: throw ToolError("This laptop has no Bluetooth.")
            val ok = if (on) a.enable() else a.disable()
            if (!ok) throw ToolError("Bluetooth didn't change.")
        }
    }

    private val wifi = object : Switch("wifi", "Wi-Fi", "Network & internet › Internet › Wi-Fi") {
        private fun wm(c: Context) = c.getSystemService(WifiManager::class.java)
        override fun available(c: Context) = wm(c) != null
        override fun isOn(c: Context) = wm(c)?.isWifiEnabled == true
        @Suppress("DEPRECATION")
        override fun turn(c: Context, on: Boolean) {
            if (wm(c)?.setWifiEnabled(on) != true) throw ToolError("Wi-Fi didn't change.")
        }
    }

    private val airplane = object : Switch("airplane_mode", "Airplane mode", "Network & internet › Airplane mode") {
        override fun isOn(c: Context) = Settings.Global.getInt(cr(c), Settings.Global.AIRPLANE_MODE_ON, 0) == 1
        override fun turn(c: Context, on: Boolean) = c.getSystemService(ConnectivityManager::class.java).setAirplaneMode(on)
    }

    private val nightLight = object : Switch("night_light", "Night Light", "Display › Night Light") {
        override fun available(c: Context) = ColorDisplayManager.isNightDisplayAvailable(c)
        override fun isOn(c: Context) = c.getSystemService(ColorDisplayManager::class.java).isNightDisplayActivated
        override fun turn(c: Context, on: Boolean) {
            c.getSystemService(ColorDisplayManager::class.java).setNightDisplayActivated(on)
        }
    }

    private val TIMEOUTS = listOf(15_000, 30_000, 60_000, 120_000, 300_000, 600_000, 1_800_000)

    private val screenTimeout = object : Setting("screen_timeout", "Screen timeout", "Display › Screen timeout",
        "15 seconds, 30 seconds, 1, 2, 5, 10 or 30 minutes") {
        override fun get(c: Context) = Settings.System.getInt(cr(c), Settings.System.SCREEN_OFF_TIMEOUT, 60_000).toString()
        override fun set(c: Context, raw: String) {
            Settings.System.putInt(cr(c), Settings.System.SCREEN_OFF_TIMEOUT, raw.toInt())
        }
        override fun parse(c: Context, input: String, current: String): String {
            val m = Regex("^(\\d+(?:\\.\\d+)?)\\s*(s|sec|secs|seconds?|m|min|mins|minutes?|h|hours?)?$").find(word(input))
                ?: bad(input)
            val n = m.groupValues[1].toDouble()
            val unit = m.groupValues[2]
            val ms = when {
                unit.startsWith("s") -> n * 1000
                unit.startsWith("h") -> n * 3_600_000
                else -> n * 60_000
            }.toInt()
            return TIMEOUTS.minBy { kotlin.math.abs(it - ms) }.toString()
        }
        override fun label(raw: String): String {
            val ms = raw.toIntOrNull() ?: return raw
            return if (ms < 60_000) "${ms / 1000} seconds" else "${ms / 60_000} minute" + if (ms == 60_000) "" else "s"
        }
    }

    private val location = object : Switch("location", "Location", "Location › Use location") {
        private fun lm(c: Context) = c.getSystemService(LocationManager::class.java)
        override fun isOn(c: Context) = lm(c).isLocationEnabled
        override fun turn(c: Context, on: Boolean) = lm(c).setLocationEnabledForUser(on, Process.myUserHandle())
    }

    private class SecureSwitch(key: String, name: String, where: String, val setting: String) : Switch(key, name, where) {
        override fun isOn(c: Context) = Settings.Secure.getInt(cr(c), setting, 0) == 1
        override fun turn(c: Context, on: Boolean) {
            Settings.Secure.putInt(cr(c), setting, if (on) 1 else 0)
        }
    }

    private val ANIMATIONS = listOf(Settings.Global.ANIMATOR_DURATION_SCALE, Settings.Global.TRANSITION_ANIMATION_SCALE,
        Settings.Global.WINDOW_ANIMATION_SCALE)

    /** Accessibility's "Remove animations": the three animation scales at 0. The raw value keeps all three. */
    private val removeAnimations = object : Setting("remove_animations", "Remove animations",
        "Accessibility › Color and motion › Remove animations", "on, off") {
        override fun get(c: Context) = ANIMATIONS.joinToString(",") { Settings.Global.getFloat(cr(c), it, 1f).toString() }
        override fun set(c: Context, raw: String) {
            val v = raw.split(",").map { it.toFloatOrNull() ?: 1f }
            ANIMATIONS.forEachIndexed { i, k -> Settings.Global.putFloat(cr(c), k, v.getOrElse(i) { v.last() }) }
        }
        override fun parse(c: Context, input: String, current: String) = when (word(input)) {
            in ON -> "0.0,0.0,0.0"
            in OFF -> "1.0,1.0,1.0"
            else -> bad(input)
        }
        override fun label(raw: String) = if (raw.split(",").all { (it.toFloatOrNull() ?: 1f) == 0f }) "On" else "Off"
    }

    private class GlobalSwitch(key: String, name: String, where: String, val setting: String,
        override val sensitive: Boolean) : Switch(key, name, where) {
        override fun isOn(c: Context) = Settings.Global.getInt(cr(c), setting, 0) == 1
        override fun turn(c: Context, on: Boolean) {
            Settings.Global.putInt(cr(c), setting, if (on) 1 else 0)
        }
    }

    val all: List<Setting> = listOf(
        darkTheme, fontSize, boldText, batterySaver, brightness, autoBrightness,
        Volume("media_volume", "Media volume", AudioManager.STREAM_MUSIC),
        Volume("ring_volume", "Ring and notification volume", AudioManager.STREAM_RING),
        Volume("alarm_volume", "Alarm volume", AudioManager.STREAM_ALARM),
        bluetooth, wifi, airplane, nightLight, screenTimeout, location,
        SecureSwitch("color_inversion", "Color inversion", "Accessibility › Color and motion › Color inversion",
            Settings.Secure.ACCESSIBILITY_DISPLAY_INVERSION_ENABLED),
        SecureSwitch("high_contrast_text", "High contrast text", "Accessibility › Display size and text › " +
            "High contrast text", Settings.Secure.ACCESSIBILITY_HIGH_TEXT_CONTRAST_ENABLED),
        removeAnimations,
        GlobalSwitch("developer_options", "Developer options", "System › Developer options",
            Settings.Global.DEVELOPMENT_SETTINGS_ENABLED, sensitive = true),
        GlobalSwitch("usb_debugging", "USB debugging (adb)", "System › Developer options › USB debugging",
            Settings.Global.ADB_ENABLED, sensitive = true),
        GlobalSwitch("wireless_debugging", "Wireless debugging (adb)", "System › Developer options › Wireless debugging",
            Settings.Global.ADB_WIFI_ENABLED, sensitive = true),
    )

    /** The setting [name] means: its key, or its name ("Dark theme", "font size", "volume"). */
    fun find(c: Context, name: String): Setting {
        val n = name.trim().lowercase().replace(Regex("[^a-z0-9]+"), "_").trim('_')
        val aliases = mapOf("theme" to "dark_theme", "dark_mode" to "dark_theme", "night_mode" to "dark_theme",
            "font_size" to "text_size", "font_scale" to "text_size", "text" to "text_size", "font" to "text_size",
            "power_saver" to "battery_saver", "battery_saver_mode" to "battery_saver", "low_power_mode" to "battery_saver",
            "volume" to "media_volume", "sound" to "media_volume", "screen_brightness" to "brightness",
            "auto_brightness" to "adaptive_brightness", "wi_fi" to "wifi", "airplane" to "airplane_mode",
            "flight_mode" to "airplane_mode", "invert_colors" to "color_inversion", "animations" to "remove_animations",
            "adb" to "usb_debugging", "adb_enabled" to "usb_debugging", "development_settings" to "developer_options",
            "screen_off_timeout" to "screen_timeout", "sleep" to "screen_timeout", "eye_comfort" to "night_light")
        val key = aliases[n] ?: n
        return all.firstOrNull { it.key == key } ?: all.firstOrNull { it.name.lowercase().replace(Regex("[^a-z0-9]+"), "_")
            .trim('_') == n } ?: throw ToolError("OpenBook has no setting called \"$name\". Settings: " +
            all.filter { it.available(c) }.joinToString(", ") { it.key } + ". For anything else, use open_settings " +
            "and computer control in Settings.")
    }

    fun byKey(key: String): Setting? = all.firstOrNull { it.key == key }
}

object SettingsTools {
    private val listSettings = object : Tool("list_settings", Tier.OBSERVE, "read") {
        override val description = "List the laptop's settings Quire can change, with their current values and " +
            "choices: dark theme, text size, Battery Saver, brightness, volumes, Bluetooth, Wi-Fi and more."
        override val schema = Schema.obj("name" to Schema.str("Only this setting (optional)."))
        override fun title(c: Context, args: JSONObject) = "Reading settings"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val only = args.str("name")?.let { listOf(SettingsCatalog.find(c, it)) } ?: SettingsCatalog.all
            return ToolResult.text(only.filter { it.available(c) }.joinToString("\n") { s ->
                val now = runCatching { s.label(s.get(c)) }.getOrElse { "unavailable" }
                "${s.key}: ${s.name} = $now (choices: ${s.choices})" + if (s.sensitive) " [asks the person first]" else ""
            })
        }
    }

    private val changeSetting = object : Tool("change_setting", Tier.ACT, "setting") {
        override val description = "Change one of the laptop's settings (list_settings names them): \"dark_theme\" " +
            "on, \"text_size\" bigger, \"battery_saver\" on, \"brightness\" 70, \"media_volume\" 30, \"bluetooth\" off. " +
            "The note shows the change with an undo. Developer options and adb ask the person first."
        override val schema = Schema.obj(
            "name" to Schema.str("The setting, e.g. dark_theme, text_size, battery_saver, brightness, media_volume, " +
                "bluetooth, wifi."),
            "value" to Schema.str("The new value, e.g. on, off, bigger, 1.3, 70, up, down."),
            required = listOf("name", "value"))
        override fun title(c: Context, args: JSONObject) = "Changing ${args.optString("name").replace('_', ' ')}"

        override fun ask(c: Context, args: JSONObject): Ask? {
            val s = SettingsCatalog.find(c, args.req("name"))
            if (!s.sensitive) return null
            val old = s.get(c)
            val new = s.parse(c, args.req("value"), old)
            return Ask("Change ${s.name}?", listOf(Change(s.name, s.where, s.label(old), s.label(new))),
                why = "This changes how the laptop can be reached or debugged. It can be changed back in Settings.",
                verb = "Change it", keep = "Leave it")
        }

        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val s = SettingsCatalog.find(c, args.req("name"))
            if (!s.available(c)) throw ToolError("${s.name} isn't available on this laptop.")
            val old = s.get(c)
            val new = s.parse(c, args.req("value"), old)
            note.retitle("${s.name}: ${s.label(new)}")
            if (new == old) return ToolResult.text("${s.name} is already ${s.label(new)}.")
            s.set(c, new)
            val now = runCatching { s.get(c) }.getOrDefault(new)
            val e = ChangeLog.get(c).record(s.key, s.name, s.where, old, new, s.label(old), s.label(new))
            note.changed(listOf(e))
            return ToolResult.text("${s.name}: ${s.label(old)} → ${s.label(new)}" +
                (if (now != new && s.key != "brightness") " (it reads ${s.label(now)} now)" else "") +
                ". The person can undo it from the note (change id ${e.id}).")
        }
    }

    private val undoChange = object : Tool("undo_change", Tier.ACT, "setting") {
        override val description = "Undo a setting change Quire made in the last 24 hours: the last one, the last " +
            "one of a setting (\"name\"), or one by its change id."
        override val schema = Schema.obj("name" to Schema.str("The setting whose last change to undo (optional)."),
            "id" to Schema.int("The change id change_setting gave (optional)."))
        override fun title(c: Context, args: JSONObject) = "Undoing a change"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val log = ChangeLog.get(c)
            val e = when {
                args.has("id") -> log.find(args.optLong("id"))
                args.str("name") != null -> log.last(SettingsCatalog.find(c, args.req("name")).key)
                else -> log.last()
            } ?: throw ToolError("There is no change of Quire's to undo.")
            if (e.undone) throw ToolError("That change was already undone.")
            // Resolve and authorize this exact entry, rather than looking up "last" again after confirmation.
            // The person's Undo button calls undo directly; an agent must ask before restoring sensitive settings.
            val s = SettingsCatalog.byKey(e.key) ?: throw ToolError("Quire can't undo ${e.name} any more.")
            if (s.sensitive && !note.confirm(Ask("Undo ${s.name}?",
                    listOf(Change(s.name, s.where, s.label(s.get(c)), s.label(e.old))),
                    why = "This changes how the laptop can be reached or debugged. It can be changed back in Settings.",
                    verb = "Undo it", keep = "Leave it"))) {
                return ToolResult.error(Broker.DENIED)
            }
            note.retitle("Undoing ${e.name}")
            val undone = undo(c, e)
            note.changed(listOf(undone))
            return ToolResult.text("${e.name} is back to ${e.oldLabel}.")
        }
    }

    /** Puts [e]'s setting back and logs that as a change too. Worker thread. */
    fun undo(c: Context, e: ChangeLog.Entry): ChangeLog.Entry {
        val s = SettingsCatalog.byKey(e.key) ?: throw ToolError("Quire can't undo ${e.name} any more.")
        val now = s.get(c)
        s.set(c, e.old)
        val log = ChangeLog.get(c)
        log.markUndone(e.id)
        return log.record(s.key, s.name, s.where, now, e.old, s.label(now), s.label(e.old))
    }

    private val PAGES = linkedMapOf(
        "settings" to Settings.ACTION_SETTINGS, "wifi" to Settings.ACTION_WIFI_SETTINGS,
        "network" to Settings.ACTION_WIRELESS_SETTINGS, "bluetooth" to Settings.ACTION_BLUETOOTH_SETTINGS,
        "display" to Settings.ACTION_DISPLAY_SETTINGS, "sound" to Settings.ACTION_SOUND_SETTINGS,
        "battery" to Intent.ACTION_POWER_USAGE_SUMMARY, "apps" to Settings.ACTION_APPLICATION_SETTINGS,
        "notifications" to Settings.ACTION_ALL_APPS_NOTIFICATION_SETTINGS, "storage" to Settings.ACTION_INTERNAL_STORAGE_SETTINGS,
        "security" to Settings.ACTION_SECURITY_SETTINGS, "privacy" to Settings.ACTION_PRIVACY_SETTINGS,
        "location" to Settings.ACTION_LOCATION_SOURCE_SETTINGS, "accessibility" to Settings.ACTION_ACCESSIBILITY_SETTINGS,
        "date_time" to Settings.ACTION_DATE_SETTINGS, "language" to Settings.ACTION_LOCALE_SETTINGS,
        "keyboard" to Settings.ACTION_HARD_KEYBOARD_SETTINGS, "accounts" to Settings.ACTION_SYNC_SETTINGS,
        "about" to Settings.ACTION_DEVICE_INFO_SETTINGS, "developer" to Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS,
        "night_light" to Settings.ACTION_NIGHT_DISPLAY_SETTINGS, "dark_theme" to Settings.ACTION_DARK_THEME_SETTINGS,
        "wallpaper" to Intent.ACTION_SET_WALLPAPER, "users" to Settings.ACTION_USER_SETTINGS,
        "system_update" to "android.settings.SYSTEM_UPDATE_SETTINGS", "reset" to "android.settings.RESET_SETTINGS",
    )

    private val openSettings = object : Tool("open_settings", Tier.ACT, "app") {
        override val description = "Open a page of the Settings app on the laptop's screen, for the person to see or " +
            "use: ${PAGES.keys.joinToString(", ")}."
        override val schema = Schema.obj("page" to Schema.str("The page.", PAGES.keys.toList()), required = listOf("page"))
        override fun title(c: Context, args: JSONObject) = "Opening ${args.optString("page").replace('_', ' ')} settings"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val page = args.req("page").lowercase().replace(Regex("[^a-z]+"), "_")
            val action = PAGES[page] ?: throw ToolError("No settings page \"$page\". Pages: ${PAGES.keys.joinToString(", ")}.")
            Apps.start(c, Intent(action))
            return ToolResult.text("Opened Settings at ${page.replace('_', ' ')}.")
        }
    }

    val all: List<Tool> = listOf(listSettings, changeSetting, undoChange, openSettings)
}
