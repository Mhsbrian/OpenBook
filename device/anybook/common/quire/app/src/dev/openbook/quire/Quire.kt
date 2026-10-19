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
     * Debuggable builds keep the last few invocations and session screenshots in Quire's private storage, as evidence
     * for the Q2 checks. User builds keep none. Q5 replaces this with the real surface.
     */
    val keepsEvidence: Boolean
        get() = Build.IS_DEBUGGABLE

    /** How many invocations, and how many session screenshots, a debuggable build keeps. */
    const val EVIDENCE_KEPT = 5
}
