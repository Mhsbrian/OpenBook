// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

/**
 * Which task owns an ACP session. A session ID is the agent's own name for it and means nothing outside that agent's
 * connection: two agents can both answer `session/new` with "session-1". So a route is the connection the session was
 * opened on plus its ID, and an update, a permission request, a cancel, a release or a disconnect reaches only the
 * owner on that connection (docs/quire.md §5.1). Connections are compared by identity.
 *
 * No Android types, so it is tested on the host (tests/unit/SessionRoutesTest.kt). Main thread only.
 */
class SessionRoutes<C : Any, O : Any> {
    private class Key<C : Any>(val connection: C, val sessionId: String) {
        override fun equals(other: Any?) =
            other is Key<*> && other.connection === connection && other.sessionId == sessionId

        override fun hashCode() = System.identityHashCode(connection) * 31 + sessionId.hashCode()
    }

    private val owners = LinkedHashMap<Key<C>, O>()

    fun own(connection: C, sessionId: String, owner: O) {
        owners[Key(connection, sessionId)] = owner
    }

    /** Releases the route only if [owner] still holds it, so a stale release never drops a newer owner. */
    fun release(connection: C, sessionId: String, owner: O) {
        val key = Key(connection, sessionId)
        if (owners[key] === owner) owners.remove(key)
    }

    fun owner(connection: C, sessionId: String): O? = owners[Key(connection, sessionId)]

    /** The connection closed: removes its routes and returns their owners. Other connections' routes stay. */
    fun drop(connection: C): List<O> {
        val gone = owners.entries.filter { it.key.connection === connection }
        gone.forEach { owners.remove(it.key) }
        return gone.map { it.value }
    }

    val size: Int
        get() = owners.size
}
