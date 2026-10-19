// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire

import android.os.Build

/** Shared by Quire's parts. Every line scripts/quire/q2-cf-check.sh reads is logged under [TAG]. */
object Quire {
    const val TAG = "Quire"

    /**
     * Set by the assistant session on the contextual search it starts, so the note knows what the person pressed:
     * contextual search's own entry points have no value for the assist key.
     */
    const val EXTRA_TRIGGER = "dev.openbook.quire.extra.TRIGGER"

    /**
     * The pointer's position in display pixels when Quire was called, which SystemUI puts in the contextual search
     * extras with the window's bounds in `sourceBounds` (docs/quire-design.md §2). Without it the note opens at the
     * taskbar.
     */
    const val EXTRA_POINTER_X = "dev.openbook.quire.extra.POINTER_X"
    const val EXTRA_POINTER_Y = "dev.openbook.quire.extra.POINTER_Y"

    /** On the assistant path SystemUI passes the window's bounds in the session args under this key. */
    const val EXTRA_SOURCE_BOUNDS = "dev.openbook.quire.extra.SOURCE_BOUNDS"

    /**
     * With the bounds, SystemUI passes the package of the window they belong to and when it read them
     * (`SystemClock.elapsedRealtime()`, ms), so Quire names the window it crops to and refuses bounds too old to match
     * the screenshot (invocation/IntakePolicy.kt).
     */
    const val EXTRA_SOURCE_PACKAGE = "dev.openbook.quire.extra.SOURCE_PACKAGE"
    const val EXTRA_SOURCE_TIME = "dev.openbook.quire.extra.SOURCE_TIME"

    /**
     * Debuggable builds keep the last few invocations and session screenshots in Quire's private storage, as evidence
     * for the Q2 checks. User builds keep none. Q5 replaces this with the real surface.
     */
    val keepsEvidence: Boolean
        get() = Build.IS_DEBUGGABLE

    /** How many invocations, and how many session screenshots, a debuggable build keeps. */
    const val EVIDENCE_KEPT = 5
}
