// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

/**
 * Line diffs for the consent card (§3.2 "Consent, command or file"): what an agent's file edit adds and removes, with a
 * little context. Longest common subsequence on lines, which is plenty for the edits a card shows; larger inputs fall
 * back to "removed, then added".
 */
object Diff {
    private const val MAX_CELLS = 250_000
    private const val CONTEXT = 1

    fun lines(old: String?, new: String, maxLines: Int = 14): List<DiffLine> {
        val b = split(new)
        if (old == null) return cap(b.map { DiffLine(DiffLine.Kind.ADD, it) }, maxLines)
        val a = split(old)
        val raw = if (a.size.toLong() * b.size > MAX_CELLS) {
            a.map { DiffLine(DiffLine.Kind.DEL, it) } + b.map { DiffLine(DiffLine.Kind.ADD, it) }
        } else {
            lcs(a, b)
        }
        return cap(withContext(raw), maxLines)
    }

    private fun split(s: String): List<String> = if (s.isEmpty()) emptyList() else s.removeSuffix("\n").split("\n")

    private fun lcs(a: List<String>, b: List<String>): List<DiffLine> {
        val n = a.size
        val m = b.size
        val t = Array(n + 1) { IntArray(m + 1) }
        for (i in n - 1 downTo 0) for (j in m - 1 downTo 0) {
            t[i][j] = if (a[i] == b[j]) t[i + 1][j + 1] + 1 else maxOf(t[i + 1][j], t[i][j + 1])
        }
        val out = ArrayList<DiffLine>()
        var i = 0
        var j = 0
        while (i < n && j < m) {
            when {
                a[i] == b[j] -> { out += DiffLine(DiffLine.Kind.SAME, a[i]); i++; j++ }
                t[i + 1][j] >= t[i][j + 1] -> { out += DiffLine(DiffLine.Kind.DEL, a[i]); i++ }
                else -> { out += DiffLine(DiffLine.Kind.ADD, b[j]); j++ }
            }
        }
        while (i < n) out += DiffLine(DiffLine.Kind.DEL, a[i++])
        while (j < m) out += DiffLine(DiffLine.Kind.ADD, b[j++])
        return out
    }

    /** Keeps changed lines and [CONTEXT] lines around them; runs of unchanged lines become one SKIP line. */
    private fun withContext(lines: List<DiffLine>): List<DiffLine> {
        val keep = BooleanArray(lines.size)
        lines.forEachIndexed { i, l ->
            if (l.kind != DiffLine.Kind.SAME) {
                for (k in (i - CONTEXT).coerceAtLeast(0)..(i + CONTEXT).coerceAtMost(lines.size - 1)) keep[k] = true
            }
        }
        val out = ArrayList<DiffLine>()
        var skipped = 0
        lines.forEachIndexed { i, l ->
            if (keep[i]) {
                if (skipped > 0) out += DiffLine(DiffLine.Kind.SKIP, "$skipped unchanged")
                skipped = 0
                out += l
            } else {
                skipped++
            }
        }
        if (skipped > 0 && out.isNotEmpty()) out += DiffLine(DiffLine.Kind.SKIP, "$skipped unchanged")
        return out
    }

    private fun cap(lines: List<DiffLine>, max: Int): List<DiffLine> {
        if (lines.size <= max) return lines
        val more = lines.size - (max - 1)
        return lines.take(max - 1) + DiffLine(DiffLine.Kind.SKIP, "$more more lines")
    }

    fun counts(lines: List<DiffLine>): Pair<Int, Int> =
        lines.count { it.kind == DiffLine.Kind.ADD } to lines.count { it.kind == DiffLine.Kind.DEL }
}
