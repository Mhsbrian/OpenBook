// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.display.DisplayManager
import android.hardware.input.InputManager
import android.os.BatteryManager
import android.view.Display
import android.view.InputDevice
import org.json.JSONObject
import org.openbook.installer.daemon.Component
import org.openbook.installer.daemon.Hello
import org.openbook.installer.daemon.HwInfo
import org.openbook.installer.daemon.Power

/**
 * What the app finds out through public Android APIs. openbook-installd runs in a system SELinux domain, which may
 * not read the battery's sysfs files (only the health HAL may), unlabeled sysfs attributes (DRM connectors) or
 * /proc/bus/input; the app fills in the display, the touchpad and the battery, and gives the engine the charger
 * state for the power rule (S8) with `apply`.
 */
object LocalFacts {
    fun power(context: Context): Power {
        val i = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val present = i?.getBooleanExtra(BatteryManager.EXTRA_PRESENT, false) ?: false
        val level = i?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = i?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val plugged = (i?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
        val pct = if (present && level >= 0 && scale > 0) level * 100 / scale else null
        return Power(ac = plugged, batteryPct = pct, ok = plugged || pct == null || pct >= 50)
    }

    fun powerJson(context: Context): JSONObject {
        val p = power(context)
        return JSONObject().put("ac", p.ac).put("battery_pct", p.batteryPct ?: JSONObject.NULL)
    }

    /** hello's power is null when the daemon could not read it. */
    fun withPower(context: Context, hello: Hello): Hello =
        if (hello.power.known) hello else hello.copy(power = power(context))

    private fun display(context: Context): Pair<Int, Int>? {
        val d = context.getSystemService(DisplayManager::class.java)?.getDisplay(Display.DEFAULT_DISPLAY) ?: return null
        val mode = d.mode
        return mode.physicalWidth to mode.physicalHeight
    }

    private fun touchpad(context: Context): String? {
        val im = context.getSystemService(InputManager::class.java) ?: return null
        for (id in im.inputDeviceIds) {
            val dev = im.getInputDevice(id) ?: continue
            if (!dev.isVirtual && dev.supportsSource(InputDevice.SOURCE_TOUCHPAD)) return dev.name
        }
        return null
    }

    private val ORDER = listOf("cpu", "gpu", "display", "wifi", "touchpad", "storage", "audio", "sleep", "dgpu", "battery")

    /** The daemon's hardware check, with the display, touchpad and battery from Android where it had none. */
    fun merge(context: Context, hw: HwInfo): HwInfo {
        val byId = LinkedHashMap<String, Component>()
        hw.components.forEach { byId[it.id] = it }
        fun weak(id: String) = byId[id].let { it == null || it.state == "missing" || it.state == "unknown" }
        if (weak("display")) {
            display(context)?.let { (w, h) -> byId["display"] = Component("display", "ready", "$w × $h", "") }
        }
        if (weak("touchpad")) {
            touchpad(context)?.let { byId["touchpad"] = Component("touchpad", "ready", it, "") }
        }
        if (byId["battery"] == null) {
            val p = power(context)
            p.batteryPct?.let {
                byId["battery"] = Component("battery", "ready", "$it %", if (p.ac) "charging" else "on_battery")
            }
        }
        val components = byId.values.sortedBy { ORDER.indexOf(it.id).let { i -> if (i < 0) ORDER.size else i } }
        val essential = components.filter { it.id != "dgpu" && it.id != "battery" }
        val verdict = when {
            components.none { it.id == "display" && it.state != "missing" } ||
                components.none { it.id == "storage" && it.state != "missing" } -> "unsupported"
            essential.any { it.state == "missing" || it.detail == "software_rendering" } -> "limited"
            else -> "ready"
        }
        return hw.copy(verdict = verdict, components = components)
    }
}
