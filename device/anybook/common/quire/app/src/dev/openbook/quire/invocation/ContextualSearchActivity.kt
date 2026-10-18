// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.invocation

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.PointF
import android.graphics.Rect
import android.os.Bundle
import android.util.Log
import dev.openbook.quire.Quire
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
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

    private fun handle(intent: Intent) {
        val app = application as QuireApplication
        val invocation = Invocation.from(intent)
        Invocations.record(this, invocation, app.io)
        val pointer = pointer(intent)
        val bounds = intent.sourceBounds
        val anchor = if (pointer != null) Anchor.Pointer(pointer) else Anchor.Taskbar(null)
        val intake = intake(invocation, bounds)
        Log.i(TAG, "note: invocation anchor=${if (pointer != null) "pointer ${pointer.x},${pointer.y}" else "taskbar"} " +
            "bounds=$bounds intake=${intake.javaClass.simpleName}")
        app.surface.invoke(invocation.trigger, anchor, intake)
    }

    /** SystemUI puts the pointer's position in the contextual search extras (§2 rules); absent, the taskbar anchors. */
    private fun pointer(intent: Intent): PointF? {
        if (!intent.hasExtra(Quire.EXTRA_POINTER_X) || !intent.hasExtra(Quire.EXTRA_POINTER_Y)) return null
        return PointF(intent.getFloatExtra(Quire.EXTRA_POINTER_X, 0f), intent.getFloatExtra(Quire.EXTRA_POINTER_Y, 0f))
    }

    /**
     * What Quire takes in (§2): the window under the pointer, cropped to the bounds SystemUI reports. When the screenshot
     * left a secure window out and no bounds say which window the person meant, Quire takes in nothing and says so,
     * rather than guess (§5.3: Observe is disclosure).
     */
    private fun intake(invocation: Invocation, bounds: Rect?): Intake {
        val shot = invocation.screenshot ?: return Intake.None
        if (invocation.flagSecureFound == true && bounds == null) return Intake.Secure
        val soft = shot.copy(Bitmap.Config.ARGB_8888, false)
        val crop = bounds?.let { b ->
            val r = Rect(b)
            if (!r.intersect(0, 0, soft.width, soft.height) || r.isEmpty) null
            else Bitmap.createBitmap(soft, r.left, r.top, r.width(), r.height())
        } ?: soft
        Invocations.lastShot = crop
        return Intake.Window(windowName(invocation), crop)
    }

    /** The app the person was looking at: the first visible package that isn't Quire or the desktop itself. */
    private fun windowName(invocation: Invocation): String {
        val pkg = invocation.visiblePackages?.firstOrNull { it !in IGNORED } ?: return getString(android.R.string.untitled)
        return try {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, 0)).toString()
        } catch (e: PackageManager.NameNotFoundException) {
            pkg
        }
    }

    companion object {
        private val IGNORED = setOf("dev.openbook.quire", "com.android.launcher3", "com.android.systemui")
    }
}
