// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.content.Context
import android.graphics.Typeface
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.BackgroundColorSpan
import android.text.style.BulletSpan
import android.text.style.StyleSpan
import android.text.style.TypefaceSpan
import dev.openbook.quire.ui.Palette
import dev.openbook.quire.ui.Type
import dev.openbook.quire.ui.dpi

/**
 * The markdown agents write, as the note shows it (§3.2 Streaming, Long output, Code): paragraphs, headings as bold
 * lines, bullet and numbered lists, `code` runs, **bold** and *italic*, and fenced code as separate blocks. Text that
 * is still arriving is parsed as it stands; an unclosed fence is a code block in progress.
 */
object Markdown {
    sealed class Segment {
        class Text(val text: CharSequence) : Segment()
        class Code(val language: String, val source: String) : Segment()
    }

    fun parse(context: Context, palette: Palette, source: String): List<Segment> {
        val out = ArrayList<Segment>()
        val text = SpannableStringBuilder()
        fun flushText() {
            while (text.isNotEmpty() && text.last() == '\n') text.delete(text.length - 1, text.length)
            if (text.isNotEmpty()) out += Segment.Text(SpannableStringBuilder(text))
            text.clear()
            text.clearSpans()
        }
        val lines = source.split("\n")
        var i = 0
        while (i < lines.size) {
            val line = lines[i]
            val fence = FENCE.matchEntire(line.trimEnd())
            if (fence != null) {
                flushText()
                val lang = fence.groupValues[1]
                val code = StringBuilder()
                i++
                while (i < lines.size && !lines[i].trimStart().startsWith("```")) {
                    if (code.isNotEmpty()) code.append('\n')
                    code.append(lines[i])
                    i++
                }
                out += Segment.Code(lang, code.toString())
                i++
                continue
            }
            if (line.isBlank()) {
                // A blank line ends the paragraph; the next one is its own segment, 8 dp below.
                if (text.isNotEmpty()) flushText()
                i++
                continue
            }
            if (text.isNotEmpty()) text.append("\n")
            val heading = HEADING.matchEntire(line)
            val bullet = BULLET.matchEntire(line)
            val numbered = NUMBERED.matchEntire(line)
            when {
                heading != null -> {
                    val start = text.length
                    inline(context, palette, heading.groupValues[2], text)
                    text.setSpan(StyleSpan(Typeface.BOLD), start, text.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                }
                bullet != null -> {
                    val start = text.length
                    inline(context, palette, bullet.groupValues[2], text)
                    val indent = bullet.groupValues[1].length / 2
                    text.setSpan(BulletSpan(context.dpi(8f + 12f * indent), palette.onSurfaceVariant, context.dpi(2f)),
                        start, text.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                }
                numbered != null -> {
                    text.append(numbered.groupValues[2]).append(". ")
                    inline(context, palette, numbered.groupValues[3], text)
                }
                else -> inline(context, palette, line.trimEnd(), text)
            }
            i++
        }
        flushText()
        return out
    }

    /** **bold**, *italic* or _italic_, `code`, and [text](link) as its text. */
    private fun inline(context: Context, palette: Palette, s: String, out: SpannableStringBuilder) {
        var i = 0
        while (i < s.length) {
            val c = s[i]
            when {
                c == '`' -> {
                    val end = s.indexOf('`', i + 1)
                    if (end < 0) { out.append(s, i, s.length); return }
                    val start = out.length
                    out.append(s, i + 1, end)
                    out.setSpan(TypefaceSpan(Type.of(context).code), start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                    out.setSpan(BackgroundColorSpan(palette.surfaceHigh), start, out.length,
                        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                    i = end + 1
                }
                s.startsWith("**", i) -> {
                    val end = s.indexOf("**", i + 2)
                    if (end < 0) { out.append(s, i, s.length); return }
                    val start = out.length
                    inline(context, palette, s.substring(i + 2, end), out)
                    out.setSpan(StyleSpan(Typeface.BOLD), start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                    i = end + 2
                }
                (c == '*' || c == '_') && i + 1 < s.length && s[i + 1] != ' ' &&
                    (i == 0 || !s[i - 1].isLetterOrDigit()) -> {
                    val end = s.indexOf(c, i + 1)
                    if (end < 0) { out.append(c); i++; continue }
                    val start = out.length
                    out.append(s, i + 1, end)
                    out.setSpan(StyleSpan(Typeface.ITALIC), start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                    i = end + 1
                }
                c == '[' -> {
                    val m = LINK.find(s, i)
                    if (m != null && m.range.first == i) {
                        out.append(m.groupValues[1])
                        i = m.range.last + 1
                    } else {
                        out.append(c)
                        i++
                    }
                }
                else -> { out.append(c); i++ }
            }
        }
    }

    private val FENCE = Regex("^\\s*```\\s*([A-Za-z0-9_+.-]*)\\s*$")
    private val HEADING = Regex("^(#{1,6})\\s+(.*)$")
    private val BULLET = Regex("^(\\s*)[-*+]\\s+(.*)$")
    private val NUMBERED = Regex("^(\\s*)(\\d+)[.)]\\s+(.*)$")
    private val LINK = Regex("\\[([^\\]]*)]\\(([^)]*)\\)")
}
