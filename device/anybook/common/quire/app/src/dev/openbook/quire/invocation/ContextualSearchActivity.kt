// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.invocation

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.PointF
import android.os.Bundle
import android.os.SystemClock
import android.util.Log
import dev.openbook.quire.Quire
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.invocation.IntakePolicy.Decision
import dev.openbook.quire.note.Anchor
import dev.openbook.quire.note.Intake

/**
 * Quire as the contextual search app (config_defaultContextualSearchPackageName). Every invocation ends here, whatever
 * started it: the pointer shake, Meta+A or Meta+G through Launcher3, or Meta+Space and the assist key through Quire's
 * assistant session. It records what arrived (Q2's checks read it), works out what Quire took in and where the note
 * opens (docs/quire-design.md §2), hands both to the note, and finishes without drawing anything.
 */
class ContextualSearchActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Recreated after a configuration change: the screenshot is still in the intent, but it is not a new call.
        if (savedInstanceState == null) handle(intent)
        finish()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
        finish()
    }

    private fun handle(intent: Intent) = Calls.handle(application as QuireApplication, intent)
}

/**
 * One call, whatever started it: records it, decides what Quire took in and where the note opens, and hands both to the
 * note. Debuggable builds' lab also feeds it made-up calls (note/LabReceiver.kt INVOKE), so the checks can reach the
 * cases SystemUI never sends.
 */
object Calls {
    fun handle(app: QuireApplication, intent: Intent) {
        val invocation = Invocation.from(intent)
        Invocations.record(app, invocation, app.io)
        val pointer = pointer(intent)
        val anchor = if (pointer != null) Anchor.Pointer(pointer) else Anchor.Taskbar(null)
        val (intake, why) = intake(app, invocation, intent, pointer)
        val crop = (intake as? Intake.Window)?.shot?.let { "${it.width}x${it.height}" } ?: "none"
        Log.i(TAG, "note: invocation anchor=${if (pointer != null) "pointer ${pointer.x},${pointer.y}" else "taskbar"} " +
            "bounds=${intent.sourceBounds} intake=${intake.javaClass.simpleName} $why crop=$crop")
        app.surface.invoke(invocation.trigger, anchor, intake)
    }

    /** SystemUI puts the pointer's position in the contextual search extras (§2 rules); absent, the taskbar anchors. */
    private fun pointer(intent: Intent): PointF? {
        if (!intent.hasExtra(Quire.EXTRA_POINTER_X) || !intent.hasExtra(Quire.EXTRA_POINTER_Y)) return null
        return PointF(intent.getFloatExtra(Quire.EXTRA_POINTER_X, 0f), intent.getFloatExtra(Quire.EXTRA_POINTER_Y, 0f))
    }

    /**
     * What Quire takes in (§2): the window under the pointer, cropped to the bounds SystemUI reports and named after the
     * package it reports, or nothing (IntakePolicy). Also returns the reason, for the log.
     */
    private fun intake(context: Context, invocation: Invocation, intent: Intent, pointer: PointF?): Pair<Intake, String> {
        val shot = invocation.screenshot
        val b = intent.sourceBounds
        val pkg = intent.getStringExtra(Quire.EXTRA_SOURCE_PACKAGE)
        val age = if (intent.hasExtra(Quire.EXTRA_SOURCE_TIME)) {
            SystemClock.elapsedRealtime() - intent.getLongExtra(Quire.EXTRA_SOURCE_TIME, 0L)
        } else {
            null
        }
        val decision = IntakePolicy.decide(shot?.width ?: 0, shot?.height ?: 0, pointer?.let { it.x to it.y },
            b?.let { IntakePolicy.Box(it.left, it.top, it.right, it.bottom) }, pkg, age, invocation.visiblePackages,
            invocation.flagSecureFound == true)
        val source = "source=$pkg age=${age?.let { "${it}ms" } ?: "none"}"
        return when (decision) {
            is Decision.Nothing -> (if (decision.secure) Intake.Secure else Intake.None) to
                "reason=${decision.why.tag} $source"
            is Decision.Window -> {
                val c = decision.crop
                val crop = Bitmap.createBitmap(shot!!.copy(Bitmap.Config.ARGB_8888, false), c.left, c.top, c.width,
                    c.height)
                Invocations.lastShot = crop
                Intake.Window(label(context, decision.pkg), crop) to "reason=window $source"
            }
        }
    }

    /** The name of the app whose window Quire cropped to. */
    private fun label(context: Context, pkg: String): String {
        val pm = context.packageManager
        return try {
            pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
        } catch (e: PackageManager.NameNotFoundException) {
            pkg
        }
    }
}
