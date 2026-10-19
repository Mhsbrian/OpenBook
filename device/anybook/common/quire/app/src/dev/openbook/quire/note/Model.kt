// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.graphics.Bitmap
import android.graphics.PointF
import android.graphics.Rect
import dev.openbook.quire.ui.QButton

/**
 * The note's content (docs/quire-design.md §3.2): one card whose body is a list of blocks. Each block has a stable [id]
 * and a [version] that goes up when it changes, so the view updates only what changed and keyboard focus stays put.
 */
sealed class Block {
    val id: Int = nextId++
    var version = 0
        private set

    fun changed() {
        version++
    }

    /** A follow-up the person sent, drawn like the first prompt. */
    class Prompt(val text: String) : Block()

    /** Thought chunks collapse to this one line until the answer starts (§3.2 Streaming). */
    class Thinking : Block()

    /** Message chunks, as markdown; [streaming] draws the caret. */
    class Answer : Block() {
        val text = StringBuilder()
        var streaming = true
    }

    /** One line per tool call (§3.2 Steps); folded into a chip when the run ends. */
    class Steps : Block() {
        val items = mutableListOf<Step>()
        var folded = false
        var expanded = false
    }

    /** An ACP `plan` (§3.2 Plan), updated in place. */
    class Plan : Block() {
        var entries: List<PlanEntry> = emptyList()
    }

    /** Inline consent (§3.3). */
    class Consent(
        val source: Source,
        val title: String,
        val meta: String?,
        val rows: List<Change>,
        val command: String?,
        val diff: List<DiffLine>?,
        val why: String?,
        val options: List<Option>,
        val toolCallId: String?,
        /** Answers the request; the note calls it once, with an option id or null for cancelled. */
        val answer: (String?) -> Unit,
    ) : Block() {
        enum class Source { AGENT, BROKER }

        var answered = false
    }

    /**
     * "Changed 3 settings" with per-row undo (§3.2 Settings help). Q6's broker adds a row for each setting it changes;
     * [onUndo] undoes row i, which then shows as undone ([undone]).
     */
    class Changes(var title: String, val meta: String?, rows: List<Change>, val undo: Boolean,
        val onUndo: ((Int) -> Unit)? = null) : Block() {
        val rows: MutableList<Change> = rows.toMutableList()
        val undone = mutableSetOf<Int>()
    }

    /** A one-line result with an icon (Done, Stopped, Waiting for your permission, Offline). */
    class Result(val icon: String, val tone: Tone, var message: String, var sub: String?) : Block()

    class Error(val title: String, val meta: String?, val message: String, val details: String?) : Block() {
        var showDetails = false
    }

    class Auth(val title: String, val message: String, val methods: List<Row>) : Block()

    /** The agents Quire found, for the no-agent state. */
    class Agents(val title: String, val message: String, val agents: List<Row>) : Block()

    class Image(val bitmap: Bitmap, val caption: String) : Block() {
        var expanded = false
    }

    class Buttons(val actions: List<Action>, val end: Boolean = false) : Block()

    companion object {
        private var nextId = 1
    }
}

enum class Tone { SUCCESS, WARN, ERROR }

enum class StepStatus { PENDING, RUNNING, DONE, FAILED, INTERRUPTED }

class Step(val id: String, var title: String, var kind: String, var status: StepStatus) {
    /** Q6: a call of Quire's own tools. The broker names the line, so the agent's later updates don't rename it. */
    var broker = false

    /** The broker's tool for this line, and the agent's tool call id once matched (the agent may announce it late). */
    var toolName: String? = null
    var agentId: String? = null
    var startedAt = 0L

    /** File and command details, for the consent card. */
    var rawInput: org.json.JSONObject? = null
    var diff: List<DiffLine>? = null
    var diffPath: String? = null
    var newFile = false

    /** True for kinds that change something (§3.3 rule 6 counts them). */
    val changes: Boolean
        get() = kind in setOf("edit", "delete", "move", "execute", "setting", "app", "window")
}

data class PlanEntry(val content: String, val priority: String?, val status: String)

data class Change(val name: String, val where: String, val old: String, val new: String)

data class DiffLine(val kind: Kind, val text: String) {
    enum class Kind { SAME, ADD, DEL, SKIP }
}

/** A permission option as the agent sent it (§3.3 rule 2): the agent's own name and opaque id; kind only styles. */
data class Option(val id: String, val name: String, val kind: String) {
    val order: Int
        get() = when (kind) {
            "reject_always" -> 0
            "reject_once" -> 1
            "allow_always" -> 2
            "allow_once" -> 3
            else -> 4
        }

    val style: QButton.Style
        get() = when (kind) {
            "allow_once" -> QButton.Style.FILLED
            "allow_always" -> QButton.Style.TONAL
            else -> QButton.Style.TEXT
        }
}

data class Row(val glyph: String?, val title: String, val sub: String?, val initials: String? = null,
    val color: Int = 0, val onClick: (() -> Unit)? = null)

data class Action(val label: String, val glyph: String?, val style: QButton.Style, val run: () -> Unit)

/** What Quire took in when it was called (§2), shown in the intake chip and sent with the prompt. */
sealed class Intake {
    /** A window: its app's name and the screenshot cropped to it. */
    class Window(val name: String, val shot: Bitmap?) : Intake()

    /** A pointer region, cropped to the region (§3.2 Images). */
    class Region(val name: String, val shot: Bitmap) : Intake()

    class Selection(val text: String, val from: String?) : Intake()

    /** A secure window was under the pointer: nothing is taken in. */
    object Secure : Intake()

    /** Nothing yet (the taskbar button): the chip offers to add what's on screen. */
    object None : Intake()
}

/** Where the note opens (§3.1 Placement). */
sealed class Anchor {
    /** At the pointer's hotspot, in display pixels. Once the note has flipped to the hotspot's left, it stays there. */
    class Pointer(val at: PointF) : Anchor() {
        var flipped = false
    }

    /** Above the taskbar's Quire button. [button] is the button's bounds when Launcher3 reports them. */
    class Taskbar(val button: Rect?) : Anchor()
}

/** The mirror's state (§3.4), owned by the task that drives a computer-control session. */
class Mirror(val app: String) {
    var title: String = app
    var paused = false
    var blockedReason: String? = null

    /** Shown instead of the step count while blocked (§3.4: "Settings is showing a protected screen"). */
    var status: String = ""

    /** Steps in the run, for "Step 2 of 4". */
    var total = 0
    var pausedAt = 0L

    /** The control the agent acts on, in session display pixels: the view zooms 2× on it. */
    var target: Rect? = null

    /** Where the agent's pointer is, in session display pixels; [tapAt] is the last tap's time. */
    var pointer: PointF? = null
    var tapAt = 0L
    val steps = Block.Steps()
}
