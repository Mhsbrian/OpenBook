// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.data

/** The laptop's graphics, as the firmware's switches set them (openbook-gfx-mode, docs/nvidia-graphics-modes.md §2). */
enum class Mode(val wire: String) {
    ECO("eco"), HYBRID("hybrid"), ULTIMATE("ultimate"), INVALID("invalid"), UNKNOWN("unknown");

    companion object {
        fun of(wire: String): Mode? = entries.firstOrNull { it.wire == wire }
    }
}

/** Where a switch stands (the switcher's state machine, §5). */
enum class Phase(val wire: String) {
    IDLE("idle"), PENDING("pending"), TRIAL("trial"), BOOTED("booted"), ROLLBACK("rollback"), FAILED("failed");

    companion object {
        fun of(wire: String): Phase? = entries.firstOrNull { it.wire == wire }
    }
}

/**
 * What this image says about Ultimate: OFFERED (the app may offer it), VERIFIED (this image can drive it but the
 * update interlock does not allow it yet), DEVELOPMENT (a dev image, through the lab only), UNVERIFIED, and
 * UNSUPPORTED (no MUX OpenBook switches on this laptop: nothing can be switched).
 */
enum class Ultimate(val wire: String) {
    OFFERED("offered"), VERIFIED("verified"), DEVELOPMENT("development"), UNVERIFIED("unverified"),
    UNSUPPORTED("unsupported");

    companion object {
        fun of(wire: String): Ultimate? = entries.firstOrNull { it.wire == wire }
    }
}

/** The switcher's answer to a request: SEQ:CODE (codes in openbook-gfx-mode's SetResult). */
data class Answer(val seq: String, val code: String) {
    companion object {
        fun of(wire: String): Answer? {
            val i = wire.indexOf(':')
            return if (i <= 0 || i == wire.length - 1) null else Answer(wire.substring(0, i), wire.substring(i + 1))
        }
    }
}

/**
 * The switcher's state, from vendor.openbook.gfx.summary ("1 MODE PHASE TARGET LOCK WRITES ULTIMATE RESULT"),
 * vendor.openbook.gfx.last_failure and vendor.openbook.gfx.event.
 */
data class GfxState(
    val mode: Mode,
    val phase: Phase,
    val target: Mode,
    val locked: Mode?,
    val writesOn: Boolean,
    val ultimate: Ultimate,
    val answer: Answer?,
    val lastFailure: String? = null,
    val event: String? = null,
) {
    /** The laptop has a MUX the switcher handles. */
    val switchable get() = ultimate != Ultimate.UNSUPPORTED
    /** The last boot came back from a failed Ultimate by itself. */
    val rolledBack get() = phase == Phase.IDLE && event?.startsWith("rolled back to ") == true

    companion object {
        /** Null when the summary is missing (an image without the switcher) or from another version. */
        fun parse(summary: String?, lastFailure: String? = null, event: String? = null): GfxState? {
            val w = summary?.trim()?.split(" ") ?: return null
            if (w.size != 8 || w[0] != "1") return null
            val mode = Mode.of(w[1]) ?: return null
            val phase = Phase.of(w[2]) ?: return null
            val target = Mode.of(w[3]) ?: return null
            val locked = if (w[4] == "none") null else Mode.of(w[4]) ?: return null
            val writes = when (w[5]) {
                "on" -> true
                "off" -> false
                else -> return null
            }
            val ultimate = Ultimate.of(w[6]) ?: return null
            val answer = if (w[7] == "-") null else Answer.of(w[7])
            return GfxState(mode, phase, target, locked, writes, ultimate, answer,
                            lastFailure?.takeIf { it.isNotBlank() && it != "none" },
                            event?.takeIf { it.isNotBlank() })
        }

        /** `getprop` output: "[name]: [value]" lines. Only the properties this app may read are listed. */
        fun fromGetprop(text: String): GfxState? {
            val props = HashMap<String, String>()
            for (line in text.lineSequence()) {
                val m = PROP.matchEntire(line.trim()) ?: continue
                props[m.groupValues[1]] = m.groupValues[2]
            }
            return parse(props["vendor.openbook.gfx.summary"], props["vendor.openbook.gfx.last_failure"],
                         props["vendor.openbook.gfx.event"])
        }

        private val PROP = Regex("""\[([^\]]+)\]: \[(.*)\]""")
    }
}
