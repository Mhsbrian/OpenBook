// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.openbook.update.engine.EngineExit
import org.openbook.update.engine.EngineState
import org.openbook.update.engine.Release
import org.openbook.update.engine.ReleaseKind

class EngineStateTest {
    @Test fun parsesKeyValueLinesKeepingEqualsInValues() {
        val s = EngineState.parse("result=error:3\ndetail=cannot fetch https://x/?a=b\nempty=\n\njunk\n")
        assertEquals(3, s.errorCode)
        assertEquals("cannot fetch https://x/?a=b", s.detail)
        assertNull(s["empty"])
        assertNull(s["junk"])
    }

    @Test fun releaseNeedsANumber() {
        assertNull(Release.of(EngineState.parse("latest=garbage\n")))
        val r = Release.of(EngineState.parse("number=16658739\n"))!!
        assertEquals(16658739L, r.number)
        assertEquals("", r.buildId)
        assertEquals("16658739", r.identifier)
        assertEquals(ReleaseKind.UNKNOWN, r.kind) // no kind recorded: treated as held
        assertEquals("16999999_CL3B.260722.140",
                     Release.of(EngineState.parse("number=16999999\nlatest_id=CL3B.260722.140\n"))!!.identifier)
    }

    @Test fun neverRun() = assertEquals("never-run", EngineState.EMPTY.result)

    @Test fun kindsAndExits() {
        assertEquals(listOf(false, true, true), ReleaseKind.entries.map { it.held })
        assertEquals(ReleaseKind.QUARTERLY, ReleaseKind.of("quarterly"))
        assertEquals(ReleaseKind.UNKNOWN, ReleaseKind.of("future-kind"))
        assertEquals(EngineExit.STOPPED, EngineExit.of(130))
        assertEquals(EngineExit.LISTING_REFUSED, EngineExit.of(9))
        assertEquals(EngineExit.UNKNOWN, EngineExit.of(77))
    }
}
