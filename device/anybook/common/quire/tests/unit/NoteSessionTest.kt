// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import dev.openbook.quire.test.Check

/**
 * ANAL-393, the Checker's Hold on PR #15: quired ends an agent's sessions when its credentials change
 * (`_quire/agent/stopped`). The notes that own them must forget them and open new ones; other notes run on.
 * Run by tools/unit-test.sh.
 */
object NoteSessionTest {
    private class Conn(val name: String)
    private class Note(val name: String) {
        var stopped = 0
    }

    fun run(c: Check) {
        val claude = Conn("claude")
        val copilot = Conn("copilot")

        // An idle note: its session is forgotten, the next message opens a new one with context and intake again.
        val idle = NoteSession<Conn>()
        idle.opened(claude, "s1")
        idle.contextSent = true
        idle.intakeSent = true
        c.eq("idle: reuses its session before the stop", idle.reusableOn(claude), "s1")
        idle.stopped()
        c.eq("idle: no session after the stop", idle.reusableOn(claude), null)
        c.eq("idle: context goes again", idle.contextSent, false)
        c.eq("idle: intake goes again", idle.intakeSent, false)
        idle.opened(claude, "s2")
        c.eq("idle: the next message uses the new session", idle.reusableOn(claude), "s2")

        // A session is only reused on the connection it was opened on.
        val moved = NoteSession<Conn>()
        moved.opened(claude, "s1")
        c.eq("another connection never reuses it", moved.reusableOn(copilot), null)
        moved.contextSent = true
        moved.clear()
        c.eq("choosing another agent forgets the session", moved.id, null)
        c.eq("…and keeps what was sent", moved.contextSent, true)

        // The routes: the stopped sessions' owners, a running and an idle note, hear of it; nothing else does.
        val routes = SessionRoutes<Conn, Note>()
        val running = Note("running")
        val idleNote = Note("idle")
        val other = Note("other agent")
        val sameIdOther = Note("same id, other connection")
        routes.own(claude, "s1", running)
        routes.own(claude, "s2", idleNote)
        routes.own(claude, "s3", Note("unrelated session"))
        routes.own(copilot, "c1", other)
        routes.own(copilot, "s1", sameIdOther)
        val gone = routes.dropSessions(claude, listOf("s1", "s2", "s9"))
        c.eq("both owners of the stopped sessions hear of it", gone.map { it.name }, listOf("running", "idle"))
        c.eq("a session the stop didn't name keeps its route", routes.owner(claude, "s3")?.name, "unrelated session")
        c.eq("another agent's note keeps its route", routes.owner(copilot, "c1"), other)
        c.eq("the same ID on another connection keeps its route", routes.owner(copilot, "s1"), sameIdOther)
        c.eq("the stopped routes are gone", routes.owner(claude, "s1"), null)
        c.eq("routes left", routes.size, 3)
    }
}
