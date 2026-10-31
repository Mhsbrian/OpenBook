// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.openbook.graphics.data.Answer
import org.openbook.graphics.data.Choice
import org.openbook.graphics.data.GfxBackend
import org.openbook.graphics.data.GfxState
import org.openbook.graphics.data.Mode
import org.openbook.graphics.data.Outcome
import org.openbook.graphics.data.Phase
import org.openbook.graphics.data.Rules
import org.openbook.graphics.data.Switcher
import org.openbook.graphics.data.Ultimate

class GfxStateTest {
    @Test
    fun parsesTheSummary() {
        val s = GfxState.parse("1 hybrid idle hybrid none on unverified 12345:restart")!!
        assertEquals(Mode.HYBRID, s.mode)
        assertEquals(Phase.IDLE, s.phase)
        assertNull(s.locked)
        assertTrue(s.writesOn)
        assertEquals(Ultimate.UNVERIFIED, s.ultimate)
        assertEquals(Answer("12345", "restart"), s.answer)
        assertTrue(s.switchable)
        val e = GfxState.parse("1 eco pending ultimate eco off offered -")!!
        assertEquals(Mode.ULTIMATE, e.target)
        assertEquals(Mode.ECO, e.locked)
        assertFalse(e.writesOn)
        assertNull(e.answer)
        assertEquals(Ultimate.OFFERED, e.ultimate)
    }

    @Test
    fun refusesOtherVersionsAndGarbage() {
        for (bad in listOf(null, "", "2 hybrid idle hybrid none on unverified -", "1 hybrid idle hybrid none on unverified",
                           "1 turbo idle hybrid none on unverified -", "1 hybrid sleeping hybrid none on unverified -",
                           "1 hybrid idle hybrid none maybe unverified -", "1 hybrid idle hybrid none on sometimes -",
                           "1 hybrid idle hybrid nobody on unverified -")) {
            assertNull(bad, GfxState.parse(bad))
        }
        assertNull(GfxState.parse("1 hybrid idle hybrid none on unverified 12345")!!.answer)  // no code
    }

    @Test
    fun readsGetpropOutput() {
        val out = """
            [ro.boot.slot_suffix]: [_b]
            [vendor.openbook.gfx.event]: [rolled back to hybrid (2 ultimate boots without a healthy display)]
            [vendor.openbook.gfx.last_failure]: [2 ultimate boots without a healthy display]
            [vendor.openbook.gfx.summary]: [1 hybrid idle hybrid none on development adb:restart]
        """.trimIndent()
        val s = GfxState.fromGetprop(out)!!
        assertEquals(Mode.HYBRID, s.mode)
        assertTrue(s.rolledBack)
        assertEquals("2 ultimate boots without a healthy display", s.lastFailure)
        assertEquals(Answer("adb", "restart"), s.answer)
        assertNull(GfxState.fromGetprop("[ro.boot.slot_suffix]: [_a]\n"))  // an image without the switcher
    }
}

class RulesTest {
    private fun s(summary: String) = GfxState.parse(summary)!!

    @Test
    fun choices() {
        val hybrid = s("1 hybrid idle hybrid none on unverified -")
        assertEquals(Choice.AVAILABLE, Rules.choice(hybrid, Mode.ECO, owner = true))
        assertEquals(Choice.CURRENT, Rules.choice(hybrid, Mode.HYBRID, owner = true))
        assertEquals(Choice.NOT_AVAILABLE, Rules.choice(hybrid, Mode.ULTIMATE, owner = true))
        assertEquals(Choice.NOT_OWNER, Rules.choice(hybrid, Mode.ECO, owner = false))
        assertEquals(Choice.WRITES_OFF, Rules.choice(s("1 hybrid idle hybrid none off unverified -"), Mode.ECO, true))
        assertEquals(Choice.LOCKED, Rules.choice(s("1 hybrid idle hybrid hybrid on unverified -"), Mode.ECO, true))
        assertEquals(Choice.BUSY, Rules.choice(s("1 hybrid pending eco none on unverified -"), Mode.ECO, true))
        assertEquals(Choice.UNSUPPORTED, Rules.choice(s("1 unknown idle hybrid none off unsupported -"), Mode.ECO, true))
        // Offered by the release: Ultimate is a choice like the others.
        assertEquals(Choice.AVAILABLE, Rules.choice(s("1 hybrid idle hybrid none on offered -"), Mode.ULTIMATE, true))
        // After failed rollbacks the iGPU modes may still be asked for; Ultimate not.
        val failed = s("1 ultimate failed hybrid none on offered -")
        assertEquals(Choice.AVAILABLE, Rules.choice(failed, Mode.HYBRID, true))
        assertEquals(Choice.BUSY, Rules.choice(failed, Mode.ULTIMATE, true))
    }

    @Test
    fun restartsAndKeep() {
        assertTrue(Rules.needsRestart(Mode.HYBRID, Mode.ULTIMATE))
        assertTrue(Rules.needsRestart(Mode.ULTIMATE, Mode.HYBRID))
        assertTrue(Rules.needsRestart(Mode.ECO, Mode.HYBRID))
        assertFalse(Rules.needsRestart(Mode.HYBRID, Mode.ECO))
        assertTrue(Rules.asksToKeep(s("1 ultimate booted ultimate none on offered -")))
        assertFalse(Rules.asksToKeep(s("1 ultimate trial ultimate none on offered -")))
        assertTrue(Rules.canLock(s("1 eco idle eco none on unverified -"), owner = true))
        assertFalse(Rules.canLock(s("1 eco pending hybrid none on unverified -"), owner = true))
        assertFalse(Rules.canLock(s("1 eco idle eco none on unverified -"), owner = false))
    }
}

/** A switcher that answers the way openbook-gfx-mode does, after a few polls. */
private class FakeBackend(var answerAfterPolls: Int = 2, var code: String = "done", var accept: Boolean = true) : GfxBackend {
    var clock = 1_792_000_000_000L
    val sent = mutableListOf<String>()
    private var polls = 0
    private var answer = "-"

    override fun read(): GfxState? {
        if (sent.isNotEmpty() && ++polls >= answerAfterPolls) answer = sent.last().substringAfter('@') + ":" + code
        return GfxState.parse("1 hybrid idle hybrid none on unverified $answer")
    }

    override fun send(value: String): Boolean {
        if (accept) {
            sent += value
            polls = 0
        }
        return accept
    }

    override fun now() = clock

    override fun sleep(millis: Long) {
        clock += millis
    }
}

class SwitcherTest {
    @Test
    fun sendsOneRequestAndWaitsForItsAnswer() {
        val b = FakeBackend(code = "restart")
        assertEquals(Outcome.RestartNeeded, Switcher(b).request(Switcher.Verb.SWITCH, Mode.ECO))
        assertEquals(1, b.sent.size)
        assertTrue(b.sent[0], Regex("switch:eco@[0-9]{1,9}").matches(b.sent[0]))
        val u = FakeBackend()
        Switcher(u).request(Switcher.Verb.UNLOCK)
        assertTrue(u.sent[0], Regex("unlock@[0-9]{1,9}").matches(u.sent[0]))
    }

    @Test
    fun everyRequestGetsANewSequenceNumber() {
        val b = FakeBackend()
        val sw = Switcher(b)
        repeat(5) { sw.request(Switcher.Verb.LOCK) }
        assertEquals(5, b.sent.map { it.substringAfter('@') }.toSet().size)
    }

    @Test
    fun mapsTheSwitchersCodes() {
        val cases = mapOf("done" to Outcome.Done, "already" to Outcome.Already, "dry-run" to Outcome.WritesOff,
                          "refused-locked" to Outcome.Refused("locked"), "failed-firmware" to Outcome.Failed("firmware"),
                          "bad-request" to Outcome.Failed("bad-request"))
        for ((code, want) in cases) assertEquals(code, want, Switcher(FakeBackend(code = code)).request(Switcher.Verb.KEEP))
    }

    @Test
    fun givesUpWithoutAnAnswer() {
        val b = FakeBackend(answerAfterPolls = Int.MAX_VALUE)
        val start = b.clock
        assertEquals(Outcome.NoAnswer, Switcher(b).request(Switcher.Verb.SWITCH, Mode.HYBRID, timeoutMillis = 3_000))
        assertTrue(b.clock - start in 3_000..3_000 + Switcher.POLL_MILLIS)
        assertEquals(Outcome.NoAnswer, Switcher(FakeBackend(accept = false)).request(Switcher.Verb.SWITCH, Mode.ECO))
    }
}
