// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.invocation

import dev.openbook.quire.invocation.IntakePolicy.Box
import dev.openbook.quire.invocation.IntakePolicy.Decision
import dev.openbook.quire.invocation.IntakePolicy.Refusal
import dev.openbook.quire.test.Check

/**
 * ANAL-219, the Checker's finding 3: Quire takes in a window only when SystemUI said which one, recently, and never the
 * whole display under a window's name (invocation/IntakePolicy.kt). Run by tools/unit-test.sh.
 */
object IntakePolicyTest {
    private const val SETTINGS = "com.android.settings"
    private val visible = listOf("com.android.documentsui", SETTINGS, "com.android.launcher3")
    private val window = Box(269, 107, 1651, 884)

    private fun decide(
        pointer: Pair<Float, Float>? = 566f to 233f,
        bounds: Box? = window,
        pkg: String? = SETTINGS,
        age: Long? = 120L,
        visiblePackages: List<String>? = visible,
        secure: Boolean = false,
        w: Int = 1920,
        h: Int = 1080,
    ) = IntakePolicy.decide(w, h, pointer, bounds, pkg, age, visiblePackages, secure)

    private fun refusal(d: Decision) = (d as? Decision.Nothing)?.why

    fun run(c: Check) {
        c.eq("the shake over Settings takes in Settings' window", decide(), Decision.Window(window, SETTINGS))
        c.eq("a window partly off the display is cropped to what shows",
            decide(bounds = Box(1500, 100, 2300, 700), pointer = 1600f to 300f),
            Decision.Window(Box(1500, 100, 1920, 700), SETTINGS))
        c.eq("a full-screen window is the whole display, named as that window",
            decide(bounds = Box(0, 0, 1920, 1080)), Decision.Window(Box(0, 0, 1920, 1080), SETTINGS))

        c.eq("no screenshot: nothing", refusal(decide(w = 0, h = 0)), Refusal.NO_SCREENSHOT)
        c.eq("the stale pointer (Meta+Space after 10 s still): nothing", refusal(decide(pointer = null, bounds = null,
            pkg = null, age = null)), Refusal.NO_POINTER)
        c.eq("a pointer over the desktop, no window: nothing", refusal(decide(bounds = null, pkg = null, age = null)),
            Refusal.NO_BOUNDS)
        c.eq("bounds without a pointer: nothing", refusal(decide(pointer = null)), Refusal.NO_POINTER)
        c.eq("empty bounds: nothing", refusal(decide(bounds = Box(600, 300, 600, 500))), Refusal.EMPTY_BOUNDS)
        c.eq("inverted bounds: nothing", refusal(decide(bounds = Box(900, 800, 300, 200))), Refusal.EMPTY_BOUNDS)
        c.eq("the pointer outside the bounds: nothing", refusal(decide(pointer = 100f to 1000f)),
            Refusal.POINTER_OUTSIDE)
        c.eq("bounds off the display: nothing", refusal(decide(bounds = Box(2000, 100, 2600, 600),
            pointer = 2100f to 200f)), Refusal.OFF_SCREEN)
        c.eq("no package: nothing", refusal(decide(pkg = null)), Refusal.NO_SOURCE)
        c.eq("no time: nothing", refusal(decide(age = null)), Refusal.NO_TIME)
        c.eq("bounds read 3.5 s ago: nothing", refusal(decide(age = 3500L)), Refusal.STALE)
        c.eq("bounds from the future: nothing", refusal(decide(age = -5L)), Refusal.STALE)
        c.eq("at the limit: still the window", decide(age = IntakePolicy.MAX_SOURCE_AGE_MS),
            Decision.Window(window, SETTINGS))
        c.eq("a package the screenshot does not show: nothing", refusal(decide(pkg = "com.example.elsewhere")),
            Refusal.NOT_VISIBLE)
        c.eq("visible packages withheld: nothing", refusal(decide(visiblePackages = null)), Refusal.NOT_VISIBLE)
        c.eq("the desktop's home task (it spans every window): nothing", refusal(decide(bounds = Box(0, 0, 1920, 1080),
            pkg = "com.android.launcher3", visiblePackages = visible)), Refusal.DESKTOP)
        c.eq("the system UI: nothing", refusal(decide(pkg = "com.android.systemui",
            visiblePackages = visible + "com.android.systemui")), Refusal.DESKTOP)
        c.eq("Quire itself: nothing", refusal(decide(pkg = "dev.openbook.quire",
            visiblePackages = visible + "dev.openbook.quire")), Refusal.DESKTOP)
        c.eq("a secure window and no bounds: nothing, said as secure",
            decide(bounds = null, pkg = null, age = null, secure = true), Decision.Nothing(Refusal.NO_BOUNDS, true))
        c.eq("a secure window elsewhere does not stop the window under the pointer",
            decide(secure = true), Decision.Window(window, SETTINGS))
        c.eq("no screenshot is never said as secure", decide(w = 0, h = 0, secure = true),
            Decision.Nothing(Refusal.NO_SCREENSHOT, false))
    }
}
