// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.data

/** The system side, so the logic below runs in unit tests too. */
interface GfxBackend {
    /** The switcher's state; null on an image without it. Blocking: call off the main thread. */
    fun read(): GfxState?

    /** Sets openbook.gfx.request (init hands it to openbook-gfx-mode). False if the system refused it. */
    fun send(value: String): Boolean

    fun now(): Long

    fun sleep(millis: Long)
}

/** What became of a request. */
sealed interface Outcome {
    /** Done; nothing more to do. */
    data object Done : Outcome
    /** Done, and a restart finishes it. */
    data object RestartNeeded : Outcome
    /** Nothing to change. */
    data object Already : Outcome
    /** This image does not write the firmware: nothing changed. */
    data object WritesOff : Outcome
    data class Refused(val code: String) : Outcome
    data class Failed(val code: String) : Outcome
    /** The switcher did not answer in time (or this image has none). */
    data object NoAnswer : Outcome
}

/**
 * The OpenBook Graphics app's requests to openbook-gfx-mode: VERB[:MODE]@SEQ in openbook.gfx.request, one at a time,
 * each answered with SEQ:CODE in the summary (docs/nvidia-graphics-modes.md §4).
 */
class Switcher(private val backend: GfxBackend) {
    enum class Verb(val wire: String) { SWITCH("switch"), LOCK("lock"), UNLOCK("unlock"), KEEP("keep"), REVERT("revert"), SHOWN("shown") }

    private var lastSeq = -1L

    /** A sequence number the switcher has not seen from this app: tenths of a second, at most nine digits. */
    private fun nextSeq(): String {
        var seq = (backend.now() / 100) % 1_000_000_000L
        if (seq <= lastSeq && lastSeq - seq < 1_000_000L) seq = (lastSeq + 1) % 1_000_000_000L
        lastSeq = seq
        return seq.toString()
    }

    @Synchronized
    fun request(verb: Verb, mode: Mode? = null, timeoutMillis: Long = 20_000): Outcome {
        val seq = nextSeq()
        val value = verb.wire + (mode?.let { ":" + it.wire } ?: "") + "@" + seq
        if (!backend.send(value)) return Outcome.NoAnswer
        val deadline = backend.now() + timeoutMillis
        while (backend.now() < deadline) {
            val answer = backend.read()?.answer
            if (answer != null && answer.seq == seq) return outcome(answer.code)
            backend.sleep(POLL_MILLIS)
        }
        return Outcome.NoAnswer
    }

    companion object {
        const val POLL_MILLIS = 250L

        fun outcome(code: String): Outcome = when {
            code == "done" -> Outcome.Done
            code == "restart" -> Outcome.RestartNeeded
            code == "already" -> Outcome.Already
            code == "dry-run" -> Outcome.WritesOff
            code.startsWith("refused-") -> Outcome.Refused(code.removePrefix("refused-"))
            code.startsWith("failed-") -> Outcome.Failed(code.removePrefix("failed-"))
            else -> Outcome.Failed(code)
        }
    }
}
