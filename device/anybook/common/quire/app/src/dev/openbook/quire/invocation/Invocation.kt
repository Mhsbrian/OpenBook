// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.invocation

import android.app.contextualsearch.CallbackToken
import android.app.contextualsearch.ContextualSearchManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.media.projection.MediaProjectionManager
import android.util.Log
import dev.openbook.quire.Quire
import dev.openbook.quire.Quire.TAG
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

/** What ContextualSearchManagerService handed Quire for one invocation (docs/quire.md §2.3). */
data class Invocation(
    val time: Long,
    /** What the person did: the assistant session's [Quire.EXTRA_TRIGGER], else named after the entry point. */
    val trigger: String,
    val entrypoint: Int,
    /** Null when the system withheld them (assist data not allowed). */
    val visiblePackages: List<String>?,
    /** Null when there was no screenshot at all. */
    val flagSecureFound: Boolean?,
    val screenshot: Bitmap?,
    val audioPlaying: Boolean?,
    val managedProfileVisible: Boolean,
    val hasToken: Boolean,
    val callingPackage: String?,
    /** ContextualSearchManagerService also offers a MediaProjection. Quire never uses it. */
    val mediaProjectionOffered: Boolean,
) {
    val entrypointName: String
        get() = entrypointName(entrypoint)

    fun summary(): String =
        "trigger=$trigger entrypoint=$entrypoint($entrypointName) " +
            "visible=${visiblePackages ?: "withheld"} flagSecureFound=${flagSecureFound ?: "n/a"} " +
            "screenshot=${screenshot?.let { "${it.width}x${it.height}" } ?: "none"}"

    companion object {
        fun from(intent: Intent): Invocation {
            val entrypoint = intent.getIntExtra(ContextualSearchManager.EXTRA_ENTRYPOINT, -1)
            return Invocation(
                time = System.currentTimeMillis(),
                trigger = intent.getStringExtra(Quire.EXTRA_TRIGGER) ?: triggerOf(entrypoint),
                entrypoint = entrypoint,
                visiblePackages =
                    intent.getStringArrayListExtra(ContextualSearchManager.EXTRA_VISIBLE_PACKAGE_NAMES),
                flagSecureFound =
                    if (intent.hasExtra(ContextualSearchManager.EXTRA_FLAG_SECURE_FOUND)) {
                        intent.getBooleanExtra(ContextualSearchManager.EXTRA_FLAG_SECURE_FOUND, false)
                    } else {
                        null
                    },
                screenshot =
                    intent.getParcelableExtra(ContextualSearchManager.EXTRA_SCREENSHOT, Bitmap::class.java),
                audioPlaying =
                    if (intent.hasExtra(ContextualSearchManager.EXTRA_IS_AUDIO_PLAYING)) {
                        intent.getBooleanExtra(ContextualSearchManager.EXTRA_IS_AUDIO_PLAYING, false)
                    } else {
                        null
                    },
                managedProfileVisible =
                    intent.getBooleanExtra(ContextualSearchManager.EXTRA_IS_MANAGED_PROFILE_VISIBLE, false),
                hasToken =
                    intent.getParcelableExtra(ContextualSearchManager.EXTRA_TOKEN, CallbackToken::class.java) != null,
                callingPackage = intent.getStringExtra(Intent.EXTRA_CALLING_PACKAGE),
                mediaProjectionOffered = intent.hasExtra(MediaProjectionManager.EXTRA_MEDIA_PROJECTION),
            )
        }

        /** Contextual search started by SystemUI or Launcher3 carries only the platform's entry point. */
        private fun triggerOf(entrypoint: Int): String =
            when (entrypoint) {
                // SystemUI's contextual cursor: the pointer shake (and Launcher3's "search screen" system action).
                ContextualSearchManager.ENTRYPOINT_SYSTEM_ACTION -> "system_action"
                // Meta+A (contextual search) and Meta+G (contextual cursor), both through Launcher3.
                ContextualSearchManager.ENTRYPOINT_KEYBOARD_SHORTCUT -> "keyboard_shortcut"
                else -> "entrypoint_$entrypoint"
            }

        fun entrypointName(entrypoint: Int): String =
            when (entrypoint) {
                ContextualSearchManager.ENTRYPOINT_LONG_PRESS_NAV_HANDLE -> "LONG_PRESS_NAV_HANDLE"
                ContextualSearchManager.ENTRYPOINT_LONG_PRESS_HOME -> "LONG_PRESS_HOME"
                ContextualSearchManager.ENTRYPOINT_LONG_PRESS_OVERVIEW -> "LONG_PRESS_OVERVIEW"
                ContextualSearchManager.ENTRYPOINT_OVERVIEW_ACTION -> "OVERVIEW_ACTION"
                ContextualSearchManager.ENTRYPOINT_OVERVIEW_MENU -> "OVERVIEW_MENU"
                ContextualSearchManager.ENTRYPOINT_SYSTEM_ACTION -> "SYSTEM_ACTION"
                ContextualSearchManager.ENTRYPOINT_LONG_PRESS_META -> "LONG_PRESS_META"
                ContextualSearchManager.ENTRYPOINT_KEYBOARD_SHORTCUT -> "KEYBOARD_SHORTCUT"
                else -> "UNKNOWN"
            }
    }
}

/** Logs invocations and, on debuggable builds, keeps the last few on disk (Quire's files/invocations/). */
object Invocations {
    private const val PREFS = "invocations"
    private const val KEY_LAST = "last"

    /** Records [invocation]: logs it at once, then saves it off the main thread. */
    fun record(context: Context, invocation: Invocation, io: java.util.concurrent.Executor) {
        Log.i(TAG, "invocation: ${invocation.summary()} token=${invocation.hasToken} " +
            "audioPlaying=${invocation.audioPlaying ?: "n/a"} " +
            "managedProfileVisible=${invocation.managedProfileVisible} " +
            "caller=${invocation.callingPackage} mediaProjectionOffered=${invocation.mediaProjectionOffered}")
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_LAST, "${invocation.trigger} (${invocation.entrypointName})").apply()
        if (!Quire.keepsEvidence) return
        io.execute {
            val saved = runCatching { save(context, invocation) }
                .onFailure { Log.e(TAG, "invocation: could not save", it) }
                .getOrNull()
            if (saved != null) Log.i(TAG, "invocation: saved ${saved.path}")
        }
    }

    fun last(context: Context): String? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_LAST, null)

    private fun save(context: Context, invocation: Invocation): File {
        val dir = File(context.filesDir, "invocations").apply { mkdirs() }
        val base = "${stamp(invocation.time)}-${invocation.trigger}"
        val json = JSONObject()
            .put("time", invocation.time)
            .put("trigger", invocation.trigger)
            .put("entrypoint", invocation.entrypoint)
            .put("entrypointName", invocation.entrypointName)
            .put("visiblePackages", invocation.visiblePackages?.let { JSONArray(it) } ?: JSONObject.NULL)
            .put("flagSecureFound", invocation.flagSecureFound ?: JSONObject.NULL)
            .put("audioPlaying", invocation.audioPlaying ?: JSONObject.NULL)
            .put("managedProfileVisible", invocation.managedProfileVisible)
            .put("token", invocation.hasToken)
            .put("callingPackage", invocation.callingPackage ?: JSONObject.NULL)
            .put("mediaProjectionOffered", invocation.mediaProjectionOffered)
        invocation.screenshot?.let { shot ->
            // The screenshot arrives as a hardware bitmap; PNG needs a software copy.
            val copy = shot.copy(Bitmap.Config.ARGB_8888, false)
            File(dir, "$base.png").outputStream().use { copy.compress(Bitmap.CompressFormat.PNG, 100, it) }
            json.put("screenshot", "$base.png").put("width", shot.width).put("height", shot.height)
        }
        val record = File(dir, "$base.json").apply { writeText(json.toString(2)) }
        prune(dir, "json")
        prune(dir, "png")
        return record
    }

    internal fun prune(dir: File, extension: String) {
        dir.listFiles { f -> f.extension == extension }
            ?.sortedByDescending { it.name }
            ?.drop(Quire.EVIDENCE_KEPT)
            ?.forEach { it.delete() }
    }

    internal fun stamp(time: Long): String =
        SimpleDateFormat("yyyyMMdd-HHmmss-SSS", Locale.ROOT).format(Date(time))
}
