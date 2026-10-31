// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.util.Log
import java.io.File
import java.math.BigInteger
import org.json.JSONObject

/**
 * A Google apps package the user brought at install time (ANAL-211). The install engine writes its manifest into the
 * new system's product partition, so its presence says the package is installed. Google Play needs an uncertified
 * device's Google Services Framework (GSF) Android ID registered at google.com/android/uncertified; this reads the ID
 * the way device-ID tools do, from GSF's gservices provider, and the registration screen shows it.
 */
object GappsInfo {
    private const val TAG = "OpenBookInstaller"
    const val MANIFEST = "/product/etc/openbook/gapps-manifest.json"
    const val GSF_PACKAGE = "com.google.android.gsf"
    private val GSERVICES: Uri = Uri.parse("content://com.google.android.gsf.gservices")

    data class Installed(val name: String, val apps: Int, val hasGsf: Boolean)

    fun installed(): Installed? = try {
        val f = File(MANIFEST)
        if (!f.isFile) {
            null
        } else {
            val m = JSONObject(f.readText())
            val pkg = m.optJSONObject("package")
            val apps = m.optJSONArray("apps")
            val n = apps?.length() ?: 0
            val gsf = (0 until n).any { apps!!.optJSONObject(it)?.optString("package") == GSF_PACKAGE }
            val name = pkg?.optString("name")?.takeIf { it.isNotBlank() && it != "null" } ?: pkg?.optString("file").orEmpty()
            Installed(name, n, gsf)
        }
    } catch (e: Exception) {
        Log.w(TAG, "cannot read $MANIFEST: ${e.message}")
        null
    }

    /** The GSF Android ID in decimal, as google.com/android/uncertified asks for it; null until GSF has created one. */
    fun gsfId(ctx: Context): String? = try {
        ctx.contentResolver.query(GSERVICES, null, null, arrayOf("android_id"), null)?.use { c ->
            if (c.moveToFirst() && c.columnCount >= 2) c.getString(1)?.trim()?.takeIf { it.matches(Regex("-?[0-9]+")) } else null
        }
    } catch (e: SecurityException) {
        Log.w(TAG, "gservices: ${e.message}")
        null
    } catch (e: IllegalArgumentException) {
        null
    }

    fun hex(id: String): String = try {
        var v = BigInteger(id)
        if (v.signum() < 0) v = v.add(BigInteger.ONE.shiftLeft(64))  // a negative long, as an unsigned 64-bit value
        v.toString(16)
    } catch (e: NumberFormatException) {
        ""
    }

    /** The Settings › About entry exists only on a system with a package. */
    fun setSettingsEntryEnabled(ctx: Context, on: Boolean) {
        ctx.packageManager.setComponentEnabledSetting(
            ComponentName(ctx, GappsRegistrationActivity::class.java),
            if (on) PackageManager.COMPONENT_ENABLED_STATE_ENABLED else PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP,
        )
    }
}
