// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.data

/** What a restart did, judged at boot from the slot and build the laptop came up with. */
sealed interface RestartOutcome {
    /** The installed update started: the laptop runs from the other slot now. */
    data class Updated(val from: SystemMark, val to: SystemMark) : RestartOutcome

    /** An update was waiting, but the laptop came back on the same slot (both slots known): the new version
     *  did not start (three failed boots return to the previous slot) or the switch never happened. */
    data class WentBack(val current: SystemMark) : RestartOutcome

    /** The system changed while the app was not watching (for example an update installed from a computer). */
    data class Changed(val from: SystemMark, val to: SystemMark) : RestartOutcome

    data object None : RestartOutcome
}

object AfterRestart {
    /**
     * [pending]: the system as it was when an installed update was waiting for a restart (recorded when
     * the app saw update_engine report it, or when the owner confirmed the restart). [lastSeen]: the
     * system at the previous boot.
     */
    fun evaluate(current: SystemMark, pending: SystemMark?, lastSeen: SystemMark?, confirmedByOwner: Boolean = true): RestartOutcome = when {
        pending != null -> when {
            // Same slot: after the owner's own restart from the app, the new version did not start. Without
            // it, the waiting update may have been withdrawn meanwhile: nothing is claimed.
            current.slot != null && pending.slot != null -> when {
                current.slot != pending.slot -> RestartOutcome.Updated(pending, current)
                confirmedByOwner -> RestartOutcome.WentBack(current)
                else -> RestartOutcome.None
            }
            // Without both slots only a changed build tells; the same build cannot be judged either way.
            changedBuild(pending, current) -> RestartOutcome.Updated(pending, current)
            else -> RestartOutcome.None
        }
        lastSeen != null && (changedBuild(lastSeen, current) ||
            (lastSeen.slot != null && current.slot != null && lastSeen.slot != current.slot)) ->
            RestartOutcome.Changed(lastSeen, current)
        else -> RestartOutcome.None
    }

    private fun changedBuild(a: SystemMark, b: SystemMark) =
        a.fingerprint != b.fingerprint || a.incremental != b.incremental || a.buildId != b.buildId
}
