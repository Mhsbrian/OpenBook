// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics.data

/** Whether a mode's card offers a switch, and if not, why (the card says so). */
enum class Choice {
    /** The laptop is in this mode now. */
    CURRENT,
    AVAILABLE,
    /** Only the owner (an admin user) switches; others see the mode. */
    NOT_OWNER,
    /** "Keep this mode" is on for another mode. */
    LOCKED,
    /** A switch is under way: it finishes, or goes back, after a restart. */
    BUSY,
    /** This version of OpenBook does not write the firmware yet. */
    WRITES_OFF,
    /** Ultimate is not offered on this version. */
    NOT_AVAILABLE,
    /** This laptop has no switch OpenBook can use. */
    UNSUPPORTED,
}

object Rules {
    /** The modes the app shows, in this order. */
    val MODES = listOf(Mode.ECO, Mode.HYBRID, Mode.ULTIMATE)

    fun choice(s: GfxState, mode: Mode, owner: Boolean): Choice = when {
        !s.switchable -> Choice.UNSUPPORTED
        mode == Mode.ULTIMATE && s.ultimate != Ultimate.OFFERED && s.mode != Mode.ULTIMATE -> Choice.NOT_AVAILABLE
        s.mode == mode && s.phase == Phase.IDLE -> Choice.CURRENT
        !owner -> Choice.NOT_OWNER
        s.phase != Phase.IDLE && !(s.phase == Phase.FAILED && mode != Mode.ULTIMATE) -> Choice.BUSY
        s.locked != null && s.locked != mode -> Choice.LOCKED
        !s.writesOn -> Choice.WRITES_OFF
        else -> Choice.AVAILABLE
    }

    /** The owner may lock or unlock the current mode while no switch is under way. */
    fun canLock(s: GfxState, owner: Boolean) = owner && s.switchable && s.phase == Phase.IDLE &&
        (s.mode == Mode.ECO || s.mode == Mode.HYBRID || s.mode == Mode.ULTIMATE)

    /** A switch to this mode needs a restart before it takes effect (the MUX is read at boot, §4). */
    fun needsRestart(from: Mode, to: Mode) = from == Mode.ULTIMATE || to == Mode.ULTIMATE ||
        (from == Mode.ECO && to == Mode.HYBRID)

    /** A new Ultimate that booted healthy waits for the owner's Keep (§5): the dialog. */
    fun asksToKeep(s: GfxState) = s.phase == Phase.BOOTED && s.mode == Mode.ULTIMATE
}
