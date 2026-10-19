// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.content.Context
import android.graphics.Bitmap
import android.util.Base64
import dev.openbook.quire.note.Change
import java.io.ByteArrayOutputStream
import org.json.JSONArray
import org.json.JSONObject

/**
 * How the broker treats a call (docs/quire.md §5.3). The never tier has no tier: what may never happen has no tool, and
 * a tool refuses the never-tier cases of its arguments itself (another app's private files, a secure window, a
 * password field).
 */
enum class Tier {
    /** Reads what the person can see or has. Runs at once; it discloses only to the agent the note names. */
    OBSERVE,

    /** Changes the person can see and undo. Runs at once, as a step in the note; settings keep an undo. */
    ACT,

    /** Destructive. The note asks first, saying exactly what will happen; only Allow runs it. */
    CONFIRM,
}

/** A refusal or failure the agent should read, as a tool result with `isError`. */
class ToolError(message: String) : Exception(message)

/** What the person is asked before a destructive call: the card's title, what changes, and what Quire can't undo. */
data class Ask(val title: String, val rows: List<Change> = emptyList(), val detail: String? = null,
    val why: String)

/** An MCP `CallToolResult`. */
class ToolResult private constructor(val content: JSONArray, val error: Boolean) {
    fun json(): JSONObject = JSONObject().put("content", content).apply { if (error) put("isError", true) }

    val text: String
        get() = (0 until content.length()).mapNotNull { content.optJSONObject(it)?.optString("text") }
            .joinToString("\n")

    companion object {
        fun text(s: String) = ToolResult(JSONArray().put(textBlock(s)), false)

        fun error(s: String) = ToolResult(JSONArray().put(textBlock(s)), true)

        /** [bitmap] as JPEG, longest side at most [max] px, after [caption]. */
        fun image(caption: String, bitmap: Bitmap, max: Int = 1280): ToolResult {
            val scale = minOf(1f, max / maxOf(bitmap.width, bitmap.height).toFloat())
            val scaled = if (scale >= 1f) bitmap else Bitmap.createScaledBitmap(bitmap,
                (bitmap.width * scale).toInt().coerceAtLeast(1), (bitmap.height * scale).toInt().coerceAtLeast(1), true)
            val bytes = ByteArrayOutputStream().also {
                scaled.copy(Bitmap.Config.ARGB_8888, false).compress(Bitmap.CompressFormat.JPEG, 85, it)
            }.toByteArray()
            return ToolResult(JSONArray().put(textBlock(caption)).put(JSONObject().put("type", "image")
                .put("mimeType", "image/jpeg").put("data", Base64.encodeToString(bytes, Base64.NO_WRAP))), false)
        }

        private fun textBlock(s: String) = JSONObject().put("type", "text").put("text", s)
    }
}

/**
 * The note's side of one call, given to the tool while it runs (on a worker thread). Each method may be called from
 * that thread; the note does its part on the main thread.
 */
interface CallNote {
    /** Renames the call's step, once the tool knows more ("Opening foxnews.com in Chrome"). */
    fun retitle(title: String)

    /**
     * Asks the person [ask] in the note and waits for the answer: true only for Allow. Stop, Esc, the end of the turn
     * and any failure mean no.
     */
    fun confirm(ask: Ask): Boolean

    /** Settings the call changed, shown in the note with an undo for each. */
    fun changed(entries: List<ChangeLog.Entry>)

    /** True once the call no longer matters: the person stopped the task, or the turn ended. */
    val cancelled: Boolean

    /** The note's computer-control run for this task, started on demand (ControlTools). */
    val control: AgentControl
}

/** One OS tool. Tools are stateless; everything a call needs comes in [run]'s arguments. */
abstract class Tool(val name: String, val tier: Tier, val kind: String) {
    /** For the model: what the tool does and when to use it. */
    abstract val description: String

    /** The arguments' JSON schema (MCP `inputSchema`). */
    abstract val schema: JSONObject

    /** The step's line in the note while it runs, from the arguments. Main thread; must not block. */
    abstract fun title(c: Context, args: JSONObject): String

    /**
     * What the person must allow first for these arguments, or null when the call needs no question. Tier CONFIRM
     * tools always return one; an ACT tool returns one for its destructive cases (overwriting a file, a developer
     * setting). Worker thread; may read state. Throws [ToolError] to refuse.
     */
    open fun ask(c: Context, args: JSONObject): Ask? = null

    /** Runs the call. Worker thread. Throws [ToolError] for a result the model should read as a failure. */
    abstract fun run(c: Context, args: JSONObject, note: CallNote): ToolResult

    fun spec(): JSONObject = JSONObject().put("name", name).put("description", description).put("inputSchema", schema)
}

/** Small builders for JSON schemas. */
object Schema {
    fun obj(vararg props: Pair<String, JSONObject>, required: List<String> = emptyList()): JSONObject {
        val p = JSONObject()
        props.forEach { (k, v) -> p.put(k, v) }
        return JSONObject().put("type", "object").put("properties", p).put("required", JSONArray(required))
            .put("additionalProperties", false)
    }

    fun str(description: String, enum: List<String>? = null): JSONObject =
        JSONObject().put("type", "string").put("description", description).apply { enum?.let { put("enum", JSONArray(it)) } }

    fun int(description: String): JSONObject = JSONObject().put("type", "integer").put("description", description)

    fun num(description: String): JSONObject = JSONObject().put("type", "number").put("description", description)

    fun bool(description: String): JSONObject = JSONObject().put("type", "boolean").put("description", description)
}

/** Argument readers that fail with a message the model can act on. */
fun JSONObject.req(key: String): String =
    optString(key).trim().ifEmpty { throw ToolError("Missing \"$key\".") }

fun JSONObject.str(key: String): String? = optString(key).trim().ifEmpty { null }
