// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import dev.openbook.quire.test.Check

/**
 * ANAL-219, the Checker's finding 2: two agents that both call their session "session-1" must never see each other's
 * updates, permission requests, cancels or disconnects (note/SessionRoutes.kt). Run by tools/unit-test.sh.
 */
object SessionRoutesTest {
    private class Connection(val name: String) {
        override fun toString() = name
    }

    fun run(c: Check) {
        val a = Connection("agent A")
        val b = Connection("agent B")
        val routes = SessionRoutes<Connection, String>()
        routes.own(a, "session-1", "task A")
        routes.own(b, "session-1", "task B")
        c.eq("A's session-1 routes to task A", routes.owner(a, "session-1"), "task A")
        c.eq("B's session-1 routes to task B", routes.owner(b, "session-1"), "task B")
        c.eq("two routes for the colliding ID", routes.size, 2)
        c.eq("an unknown session on A has no owner", routes.owner(a, "session-2"), null)
        c.eq("a look-alike connection is another connection", routes.owner(Connection("agent A"), "session-1"), null)

        routes.release(b, "session-1", "task A")
        c.eq("task A cannot release B's session-1", routes.owner(b, "session-1"), "task B")
        routes.release(a, "session-1", "task A")
        c.eq("task A releases its own", routes.owner(a, "session-1"), null)
        c.eq("B's route survives A's release", routes.owner(b, "session-1"), "task B")

        routes.own(a, "session-1", "task A")
        routes.own(a, "session-2", "task A2")
        val dropped = routes.drop(a)
        c.eq("A's disconnect reaches A's tasks only", dropped.sorted(), listOf("task A", "task A2"))
        c.eq("B still routes after A disconnects", routes.owner(b, "session-1"), "task B")
        c.eq("A has no routes left", routes.owner(a, "session-1"), null)
        c.eq("a second drop of A finds nothing", routes.drop(a), emptyList<String>())

        routes.own(b, "session-1", "task C")
        routes.release(b, "session-1", "task B")
        c.eq("a stale release keeps the newer owner", routes.owner(b, "session-1"), "task C")
    }
}
