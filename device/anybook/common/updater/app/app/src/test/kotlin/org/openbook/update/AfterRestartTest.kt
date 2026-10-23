// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import org.junit.Assert.assertEquals
import org.junit.Test
import org.openbook.update.data.AfterRestart.evaluate
import org.openbook.update.data.History
import org.openbook.update.data.HistoryEntry
import org.openbook.update.data.RestartOutcome
import org.openbook.update.data.SystemMark

class AfterRestartTest {
    private val a = SystemMark("fp-old", "16658739", "CL3B.260622.276.R4", "_a")
    private val bNew = SystemMark("fp-new", "16999999", "CL3B.260722.140", "_b")

    @Test fun switchedSlotIsAnUpdate() = assertEquals(RestartOutcome.Updated(a, bNew), evaluate(bNew, a, a))

    @Test fun sameBuildIntoTheOtherSlotIsStillAnUpdate() {
        val bSame = a.copy(slot = "_b")
        assertEquals(RestartOutcome.Updated(a, bSame), evaluate(bSame, a, a))
    }

    @Test fun sameSlotAfterTheOwnersRestartWentBack() {
        assertEquals(RestartOutcome.WentBack(a), evaluate(a, a, a, confirmedByOwner = true))
        // Not restarted from the app: the waiting update may have been withdrawn; nothing is claimed.
        assertEquals(RestartOutcome.None, evaluate(a, a, a, confirmedByOwner = false))
        assertEquals(RestartOutcome.Updated(a, bNew), evaluate(bNew, a, a, confirmedByOwner = false))
    }

    @Test fun withoutBothSlotsOnlyAChangedBuildCounts() {
        val old = a.copy(slot = null)
        // The same build on an unknown slot cannot be judged: no "went back" without both slots.
        assertEquals(RestartOutcome.None, evaluate(old, old, null))
        assertEquals(RestartOutcome.None, evaluate(old, a, null))
        assertEquals(RestartOutcome.Updated(old, bNew.copy(slot = null)), evaluate(bNew.copy(slot = null), old, null))
    }

    @Test fun unwatchedChangeAndNothing() {
        assertEquals(RestartOutcome.Changed(a, bNew), evaluate(bNew, null, a))
        assertEquals(RestartOutcome.None, evaluate(a, null, a))
        assertEquals(RestartOutcome.None, evaluate(a, null, null)) // first boot with the app
        // An unreadable slot is no change.
        assertEquals(RestartOutcome.None, evaluate(a.copy(slot = null), null, a))
        assertEquals(RestartOutcome.Changed(a, a.copy(slot = "_b")), evaluate(a.copy(slot = "_b"), null, a))
    }

    @Test fun historyRoundTripsAndSkipsUnknownTypes() {
        val entries = listOf(HistoryEntry(2, HistoryEntry.Type.INSTALLED, "CL3B.260722.140 (16999999)"),
                             HistoryEntry(1, HistoryEntry.Type.FOUND, "x", "detail"))
        assertEquals(entries, History.decode(History.encode(entries)))
        val withFuture = History.encode(entries).replace("\"FOUND\"", "\"FROM_A_LATER_VERSION\"")
        assertEquals(entries.take(1), History.decode(withFuture))
    }
}
