// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.test

/** A minimal check runner for Quire's host tests (tools/unit-test.sh): no JUnit, no Android. */
class Check {
    var passed = 0
        private set
    val failed = mutableListOf<String>()

    fun eq(name: String, actual: Any?, expected: Any?) {
        if (actual == expected) {
            passed++
            println("PASS $name")
        } else {
            failed += name
            println("FAIL $name: expected $expected, got $actual")
        }
    }
}

fun main() {
    val c = Check()
    println("== SessionRoutes")
    dev.openbook.quire.note.SessionRoutesTest.run(c)
    println("== IntakePolicy")
    dev.openbook.quire.invocation.IntakePolicyTest.run(c)
    println("${c.passed} passed, ${c.failed.size} failed")
    if (c.failed.isNotEmpty()) kotlin.system.exitProcess(1)
}
