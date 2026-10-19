// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.invocation

/**
 * What Quire may take in from a call (docs/quire-design.md §2, §5.3: Observe is disclosure). The intake chip says
 * "the window under the pointer", so Quire takes in a window only when SystemUI said which one: the pointer, the
 * window's bounds and package, read moments before the screenshot (frameworks/base 0008). The screenshot is cropped to
 * those bounds and labelled with that package. Anything less, and Quire takes in nothing: it never sends the whole
 * display, and never one window's pixels under another's name.
 *
 * No Android types, so it is tested on the host (tests/unit/IntakePolicyTest.kt).
 */
object IntakePolicy {
    /** How old the bounds may be when the call reaches Quire (ms). SystemUI reads them as it starts the call. */
    const val MAX_SOURCE_AGE_MS = 3000L

    /**
     * Not windows of their own: the desktop (its home task spans the display, so its "window" is every window on it),
     * the system UI and Quire. A call over them takes in nothing.
     */
    val NOT_A_WINDOW = setOf("com.android.launcher3", "com.android.systemui", "dev.openbook.quire")

    data class Box(val left: Int, val top: Int, val right: Int, val bottom: Int) {
        val width: Int
            get() = right - left
        val height: Int
            get() = bottom - top
        val isEmpty: Boolean
            get() = width <= 0 || height <= 0

        fun contains(x: Float, y: Float) = x >= left && x < right && y >= top && y < bottom

        fun intersect(o: Box) = Box(maxOf(left, o.left), maxOf(top, o.top), minOf(right, o.right), minOf(bottom, o.bottom))

        override fun toString() = "[$left,$top][$right,$bottom]"
    }

    /** Why nothing was taken in, as the log and the checks name it. */
    enum class Refusal(val tag: String) {
        NO_SCREENSHOT("no-screenshot"),
        NO_POINTER("no-pointer"),
        NO_BOUNDS("no-bounds"),
        EMPTY_BOUNDS("empty-bounds"),
        POINTER_OUTSIDE("pointer-outside-bounds"),
        OFF_SCREEN("bounds-off-screen"),
        NO_SOURCE("no-source-package"),
        NO_TIME("no-source-time"),
        STALE("stale-bounds"),
        NOT_VISIBLE("source-not-visible"),
        DESKTOP("desktop"),
    }

    sealed class Decision {
        /** Take in [crop] of the screenshot, labelled with [pkg]'s name. */
        data class Window(val crop: Box, val pkg: String) : Decision()

        /** Take in nothing; [secure] when the screenshot left a secure window out (the chip says so). */
        data class Nothing(val why: Refusal, val secure: Boolean) : Decision()
    }

    /**
     * [shotWidth]/[shotHeight]: the screenshot's size (0 when there is none). [pointer]: where the pointer was, in
     * display pixels. [bounds], [pkg] and [ageMs]: the window SystemUI found under it, and how long ago it read them.
     * [visible]: the packages the screenshot shows, from the platform (null when withheld).
     */
    fun decide(
        shotWidth: Int,
        shotHeight: Int,
        pointer: Pair<Float, Float>?,
        bounds: Box?,
        pkg: String?,
        ageMs: Long?,
        visible: List<String>?,
        flagSecure: Boolean,
    ): Decision {
        fun no(why: Refusal) = Decision.Nothing(why, flagSecure)
        if (shotWidth <= 0 || shotHeight <= 0) return Decision.Nothing(Refusal.NO_SCREENSHOT, false)
        if (pointer == null) return no(Refusal.NO_POINTER)
        if (bounds == null) return no(Refusal.NO_BOUNDS)
        if (bounds.isEmpty) return no(Refusal.EMPTY_BOUNDS)
        if (!bounds.contains(pointer.first, pointer.second)) return no(Refusal.POINTER_OUTSIDE)
        val crop = bounds.intersect(Box(0, 0, shotWidth, shotHeight))
        if (crop.isEmpty) return no(Refusal.OFF_SCREEN)
        if (pkg.isNullOrEmpty()) return no(Refusal.NO_SOURCE)
        if (pkg in NOT_A_WINDOW) return no(Refusal.DESKTOP)
        if (ageMs == null) return no(Refusal.NO_TIME)
        if (ageMs < 0 || ageMs > MAX_SOURCE_AGE_MS) return no(Refusal.STALE)
        if (visible == null || pkg !in visible) return no(Refusal.NOT_VISIBLE)
        return Decision.Window(crop, pkg)
    }
}
