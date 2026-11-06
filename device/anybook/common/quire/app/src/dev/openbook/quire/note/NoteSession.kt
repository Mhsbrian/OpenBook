// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

/**
 * A note's ACP session: its ID, the connection it was opened on (an ID means something only there, SessionRoutes),
 * and whether the live context and the intake have gone with a prompt yet. No Android types, so it is tested on the
 * host (tests/unit/NoteSessionTest.kt).
 *
 * quired ends an agent's sessions when its credentials change (a key saved, a sign-in, a sign-out; ANAL-393), and tells
 * the client with `_quire/agent/stopped`. [stopped] then forgets the session, so the next message opens a new one,
 * and the agent, a fresh process that remembers nothing, gets the context and the intake again.
 */
class NoteSession<C : Any> {
    var id: String? = null
        private set
    var connection: C? = null
        private set
    var contextSent = false
    var intakeSent = false

    fun opened(connection: C, id: String) {
        this.connection = connection
        this.id = id
    }

    /** The session to prompt on [connection], or null when a new one must be opened there. */
    fun reusableOn(connection: C): String? = id?.takeIf { this.connection === connection }

    /** Forgets the session (another agent chosen, or its connection closed); what was sent stays sent. */
    fun clear() {
        id = null
        connection = null
    }

    /** quired ended the session: forget it, and send the context and the intake again with the next prompt. */
    fun stopped() {
        clear()
        contextSent = false
        intakeSent = false
    }
}
