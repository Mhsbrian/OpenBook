// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.setup

import android.app.Activity
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.ScrollView
import android.widget.TextView
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.R
import dev.openbook.quire.note.Icons
import dev.openbook.quire.setup.SetupModel.Kind
import dev.openbook.quire.setup.SetupModel.Page
import dev.openbook.quire.setup.SetupModel.Remedy
import dev.openbook.quire.setup.SetupModel.Row
import dev.openbook.quire.setup.SetupModel.SignState
import dev.openbook.quire.ui.Avatar
import dev.openbook.quire.ui.Icon
import dev.openbook.quire.ui.IconButton
import dev.openbook.quire.ui.Leaf
import dev.openbook.quire.ui.Palette
import dev.openbook.quire.ui.QButton
import dev.openbook.quire.ui.TextRole
import dev.openbook.quire.ui.Type
import dev.openbook.quire.ui.dp
import dev.openbook.quire.ui.dpi
import dev.openbook.quire.ui.kbd
import dev.openbook.quire.ui.role
import dev.openbook.quire.ui.rounded

/**
 * Quire setup (docs/quire-setup.md §2): one window, four steps, one main button per page, and the agents page after
 * setup. Every page is drawn from [SetupModel]; [SetupController] does the work. The prototype is
 * docs/quire-setup-design/index.html.
 */
class SetupActivity : Activity() {
    private lateinit var setup: SetupController
    private val model get() = setup.model
    private lateinit var p: Palette
    private lateinit var type: Type
    private lateinit var header: LinearLayout
    private lateinit var body: FrameLayout
    private lateinit var footer: LinearLayout
    private lateinit var sheetLayer: FrameLayout
    private var shownPage: Page? = null
    private var helloAsked: String? = null
    private val listener: () -> Unit = { render() }

    // Fields keep what the person typed across redraws; their text is never stored anywhere else.
    private val pasteField by lazy { field(R.string.setup_paste_hint, secret = true) }

    // Kept across redraws, so progress moves on from where it was instead of starting over on every poll.
    private val linuxRing by lazy { ProgressRing(this, p, 196f, 6f, 56f) }
    private val keyField by lazy { field(R.string.setup_key_hint, secret = true) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setup = (application as QuireApplication).setup
        p = Palette.of(this)
        type = Type.of(this)

        header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dpi(28f), 0, dpi(20f), 0)
        }
        body = FrameLayout(this)
        footer = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dpi(56f), 0, dpi(28f), 0)
        }
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(header, LinearLayout.LayoutParams(-1, dpi(64f)))
            addView(ScrollView(this@SetupActivity).apply {
                isFillViewport = true
                addView(body, FrameLayout.LayoutParams(-1, -2))
            }, LinearLayout.LayoutParams(-1, 0, 1f))
            addView(footer, LinearLayout.LayoutParams(-1, dpi(84f)))
        }
        sheetLayer = FrameLayout(this).apply {
            visibility = View.GONE
            setBackgroundColor(p.scrim)
            isClickable = true
        }
        val root = FrameLayout(this).apply {
            background = GlassBackground(this@SetupActivity, p, 0f)
            addView(column, FrameLayout.LayoutParams(-1, -1))
            addView(sheetLayer, FrameLayout.LayoutParams(-1, -1))
        }
        setContentView(root)
        setup.addListener(listener)
        setup.refresh()
        render()
    }

    override fun onMultiWindowModeChanged(isInMultiWindowMode: Boolean, newConfig: android.content.res.Configuration) {
        super.onMultiWindowModeChanged(isInMultiWindowMode, newConfig)
        render()
    }

    override fun onResume() {
        super.onResume()
        setup.visible = true
    }

    override fun onPause() {
        setup.visible = false
        super.onPause()
    }

    override fun onDestroy() {
        setup.removeListener(listener)
        super.onDestroy()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_ESCAPE) {
            if (sheetLayer.visibility == View.VISIBLE) closeSheet() else finish()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    private fun closeSheet() {
        if (model.prompt != null) setup.cancelSignIn()
        model.showWhatRuns = false
        pasteField.text.clear()
        keyField.text.clear()
        render()
    }

    // ------------------------------------------------------------------------------------------------ frame

    private fun render() {
        if (isDestroyed) return
        val focused = currentFocus?.tag as? String
        val page = model.page
        if (page != shownPage) {
            shownPage = page
            body.alpha = 0f
            body.animate().alpha(1f).setDuration(if (dev.openbook.quire.ui.Motion.enabled) 160 else 0).start()
        }
        renderHeader()
        body.removeAllViews()
        footer.removeAllViews()
        when (page) {
            Page.WELCOME -> welcome()
            Page.LINUX -> linux()
            Page.AGENTS -> agents(installing = false)
            Page.INSTALLING -> agents(installing = true)
            Page.SIGNIN -> signIn()
            Page.TRY -> tryIt()
            Page.MANAGE -> manage()
        }
        renderSheet()
        val target = focused?.let { window.decorView.findViewWithTag<View>(it) }
            ?: window.decorView.findViewWithTag<View>(DEFAULT_FOCUS)
        target?.requestFocus()
    }

    private fun renderHeader() {
        header.removeAllViews()
        val manage = model.page == Page.MANAGE || model.page == Page.WELCOME
        header.addView(Leaf(this, 22f), LinearLayout.LayoutParams(dpi(22f), dpi(22f)).apply { marginEnd = dpi(12f) })
        header.addView(text(TextRole.LABEL_MEDIUM, p.onSurface, getString(if (manage) R.string.setup_app else R.string.setup_title)))
        header.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        val at = SetupModel.stepIndex(model.page)
        if (at >= 0) {
            val steps = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                contentDescription = getString(R.string.setup_steps)
            }
            val names = intArrayOf(R.string.setup_step_linux, R.string.setup_step_agents, R.string.setup_step_signin,
                R.string.setup_step_try)
            names.forEachIndexed { i, res ->
                if (i > 0) steps.addView(View(this).apply {
                    background = rounded(context, p.outlineVariant, 1f)
                }, LinearLayout.LayoutParams(dpi(14f), dpi(1.5f)).apply { marginStart = dpi(6f); marginEnd = dpi(6f) })
                val name = getString(res)
                val pill = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(dpi(6f), dpi(5f), dpi(10f), dpi(5f))
                    if (i == at) background = rounded(context, p.card, 999f, p.cardOutline, 1f)
                    contentDescription = when {
                        i < at -> getString(R.string.setup_step_done, name)
                        i == at -> getString(R.string.setup_step_now, name)
                        else -> name
                    }
                }
                val dot = TextView(this).apply {
                    role(TextRole.META_BOLD, if (i == at) p.onPrimary else if (i < at) p.onSuccessContainer else p.onSurfaceVariant, type)
                    gravity = Gravity.CENTER
                    text = if (i < at) "" else "${i + 1}"
                    background = when {
                        i == at -> GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(p.primary) }
                        i < at -> GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(p.successContainer) }
                        else -> GradientDrawable().apply { shape = GradientDrawable.OVAL; setStroke(dpi(1.5f), p.outlineVariant) }
                    }
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                }
                val dotFrame = FrameLayout(this).apply {
                    addView(dot, FrameLayout.LayoutParams(-1, -1))
                    if (i < at) addView(Icon(context, Icons.CHECK, 13f, p.onSuccessContainer), FrameLayout.LayoutParams(-1, -1))
                }
                pill.addView(dotFrame, LinearLayout.LayoutParams(dpi(18f), dpi(18f)).apply { marginEnd = dpi(6f) })
                pill.addView(text(TextRole.META, if (i == at) p.onSurface else p.onSurfaceVariant, name).apply {
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                })
                steps.addView(pill)
            }
            header.addView(steps, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dpi(12f) })
        }
        // A desktop window has the system's caption with its own close; the window's × is for a full-screen one.
        if (!isInMultiWindowMode) header.addView(IconButton(this, p, Icons.CLOSE, getString(R.string.setup_close)).apply {
            tag = "close"
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(dpi(36f), dpi(36f)))
    }

    private fun pageColumn(title: CharSequence, lead: CharSequence?): LinearLayout {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dpi(56f), dpi(18f), dpi(56f), dpi(12f))
        }
        col.addView(text(TITLE, p.onSurface, title).apply { isFocusable = false; isAccessibilityHeading = true })
        if (lead != null) col.addView(text(TextRole.BODY, p.onSurfaceVariant, lead).apply { maxWidth = dpi(640f) },
            LinearLayout.LayoutParams(-2, -2).apply { topMargin = dpi(8f) })
        body.addView(col, FrameLayout.LayoutParams(-1, -2))
        return col
    }

    /** The footer's left side: a line of help, or nothing. A bare View here would take the whole height. */
    private fun hint(view: View?) {
        footer.addView(FrameLayout(this).apply {
            if (view != null) addView(view, FrameLayout.LayoutParams(-2, -2, Gravity.START or Gravity.CENTER_VERTICAL))
        }, LinearLayout.LayoutParams(0, -2, 1f))
    }

    private fun hintText(s: CharSequence) = text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, s)

    private fun button(label: CharSequence, style: QButton.Style, tag: String? = null, enabled: Boolean = true,
        glyph: String? = null, onClick: () -> Unit): QButton = QButton(this, p, label, style, glyph).apply {
        this.tag = tag
        isEnabled = enabled
        alpha = if (enabled) 1f else 0.45f
        minHeight = dpi(if (style == QButton.Style.FILLED && footer.childCount >= 0) 44f else 36f)
        setOnClickListener { if (isEnabled) onClick() }
    }

    private fun action(label: CharSequence, style: QButton.Style, tag: String? = null, enabled: Boolean = true,
        onClick: () -> Unit) {
        footer.addView(button(label, style, tag, enabled, onClick = onClick),
            LinearLayout.LayoutParams(-2, dpi(44f)).apply { marginStart = dpi(8f) })
    }

    // ------------------------------------------------------------------------------------------------ pages

    private fun welcome() {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dpi(56f), dpi(36f), dpi(56f), dpi(12f))
        }
        val hero = FrameLayout(this)
        hero.addView(ProgressRing(this, p, 220f, 3f, 0f).apply { fraction = 1f },
            FrameLayout.LayoutParams(-2, -2, Gravity.CENTER))
        hero.addView(FrameLayout(this).apply {
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(p.card); setStroke(dpi(1f), p.cardOutline) }
            addView(Leaf(this@SetupActivity, 76f).apply { breathing = true }, FrameLayout.LayoutParams(dpi(76f), dpi(76f), Gravity.CENTER))
        }, FrameLayout.LayoutParams(dpi(156f), dpi(156f), Gravity.CENTER))
        row.addView(hero, LinearLayout.LayoutParams(dpi(260f), dpi(260f)).apply { marginEnd = dpi(40f) })
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(text(TITLE, p.onSurface, getString(R.string.setup_welcome_title)).apply { isAccessibilityHeading = true })
        col.addView(text(TextRole.BODY, p.onSurfaceVariant, getString(R.string.setup_welcome_lead)),
            LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(8f) })
        val points = listOf(
            Triple(Icons.COMPUTER, R.string.setup_point1_title, R.string.setup_point1),
            Triple(Icons.PSYCHOLOGY, R.string.setup_point2_title, R.string.setup_point2),
            Triple(Icons.SHIELD, R.string.setup_point3_title, R.string.setup_point3),
        )
        for ((glyph, t, s) in points) col.addView(point(glyph, getString(t), getString(s)),
            LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(18f) })
        row.addView(col, LinearLayout.LayoutParams(0, -2, 1f))
        body.addView(row, FrameLayout.LayoutParams(-1, -2))
        hint(hintText(getString(R.string.setup_welcome_hint)))
        action(getString(R.string.setup_not_now), QButton.Style.TEXT) { finish() }
        action(getString(R.string.setup_get_started), QButton.Style.FILLED, DEFAULT_FOCUS) {
            if (model.env == SetupModel.Env.READY && model.quired.isNotEmpty()) model.next().also { render() }
            else setup.startLinux()
        }
    }

    private fun point(glyph: String, title: String, sub: String) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        addView(tile(glyph, 40f, 12f), LinearLayout.LayoutParams(dpi(40f), dpi(40f)).apply { marginEnd = dpi(14f) })
        addView(LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            addView(text(TextRole.PROMPT, p.onSurface, title))
            addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, sub))
        }, LinearLayout.LayoutParams(0, -2, 1f))
    }

    private fun tile(glyph: String, sizeDp: Float, radiusDp: Float) = FrameLayout(this).apply {
        background = rounded(context, p.secondaryContainer, radiusDp)
        addView(Icon(context, glyph, sizeDp * 0.5f, p.onSecondaryContainer), FrameLayout.LayoutParams(-1, -1))
    }

    private fun linux() {
        val m = model
        val failed = m.remedy != Remedy.NONE && m.remedy != Remedy.START
        if (failed && !m.linuxDone) return problem()
        val done = m.linuxDone || (m.env == SetupModel.Env.READY && m.quired.isNotEmpty())
        val col = pageColumn(getString(if (done) R.string.setup_linux_title_done else R.string.setup_linux_title),
            getString(if (done) R.string.setup_linux_lead_done else R.string.setup_linux_lead))
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dpi(32f), 0, 0)
        }
        val ringCol = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            (linuxRing.parent as? ViewGroup)?.removeView(linuxRing)
            addView(linuxRing.apply { fraction = m.linuxFraction })
            addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant,
                if (done) getString(R.string.setup_done) else getString(R.string.setup_percent, (m.linuxFraction * 100).toInt())),
                LinearLayout.LayoutParams(-2, -2).apply { topMargin = dpi(6f) })
        }
        row.addView(ringCol, LinearLayout.LayoutParams(dpi(260f), -2).apply { marginEnd = dpi(48f) })
        val rows = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        val states = m.linuxRows()
        val mb = m.megabytes
        val titles = intArrayOf(R.string.setup_row_check, R.string.setup_row_download, R.string.setup_row_unpack,
            R.string.setup_row_start, R.string.setup_row_connect)
        for (i in 0 until 5) {
            val st = states[i]
            val sub = when {
                i == 0 && st == Row.DONE -> getString(R.string.setup_row_check_sub)
                i == 1 && st == Row.NOW && mb != null -> getString(R.string.setup_row_download_sub, mb.first, mb.second)
                i == 1 && st == Row.DONE -> getString(R.string.setup_row_download_done)
                i == 2 -> getString(R.string.setup_row_unpack_sub)
                i == 4 && st == Row.DONE -> getString(R.string.setup_row_connect_done)
                else -> ""
            }
            rows.addView(checkRow(st, getString(titles[i]), sub))
        }
        row.addView(rows, LinearLayout.LayoutParams(0, -2, 1f))
        col.addView(row)
        hint(if (done) null else hintText(getString(R.string.setup_linux_hint)))
        if (!done && m.remedy == Remedy.START) {
            action(getString(R.string.setup_set_up), QButton.Style.FILLED, DEFAULT_FOCUS) { setup.startLinux() }
        } else {
            action(getString(R.string.setup_next), QButton.Style.FILLED, DEFAULT_FOCUS, enabled = done) { m.next(); render() }
        }
    }

    private fun checkRow(st: Row, title: String, sub: String) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        minimumHeight = dpi(52f)
        setPadding(dpi(12f), dpi(6f), dpi(16f), dpi(6f))
        if (st == Row.NOW) background = rounded(context, p.card, 14f, p.cardOutline, 1f)
        addView(Mark(context, p).apply { state = st }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dpi(12f) })
        addView(LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            addView(text(if (st == Row.WAIT) TextRole.LABEL else TextRole.LABEL_MEDIUM,
                if (st == Row.WAIT) p.onSurfaceVariant else p.onSurface, title))
            if (sub.isNotEmpty()) addView(text(TextRole.META, p.onSurfaceVariant, sub))
        }, LinearLayout.LayoutParams(0, -2, 1f))
    }

    private fun problem() {
        val m = model
        val (t, l) = when (m.remedy) {
            Remedy.FIRMWARE -> R.string.setup_nokvm_title to R.string.setup_nokvm_lead
            Remedy.NO_IMAGE -> R.string.setup_noimage_title to R.string.setup_noimage_lead
            Remedy.NO_AVF -> R.string.setup_noavf_title to R.string.setup_noavf_lead
            Remedy.OLD_HELPER -> R.string.setup_old_title to R.string.setup_old_lead
            else -> R.string.setup_error_title to R.string.setup_error_lead
        }
        val col = pageColumn(getString(t), getString(l))
        if (m.remedy == Remedy.FIRMWARE) {
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(dpi(24f), dpi(22f), dpi(24f), dpi(22f))
                background = rounded(context, p.card, 16f, p.cardOutline, 1f)
                addView(tile(Icons.SETTINGS, 48f, 14f), LinearLayout.LayoutParams(dpi(48f), dpi(48f)).apply { marginEnd = dpi(18f) })
                addView(LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(text(TextRole.PROMPT, p.onSurface, getString(R.string.setup_nokvm_heading)))
                    listOf(R.string.setup_nokvm_1, R.string.setup_nokvm_2, R.string.setup_nokvm_3).forEachIndexed { i, s ->
                        addView(text(TextRole.LABEL, p.onSurface, "${i + 1}.  ${getString(s)}"),
                            LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(6f) })
                    }
                    addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, getString(R.string.setup_nokvm_why)),
                        LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(10f) })
                }, LinearLayout.LayoutParams(0, -2, 1f))
            }
            col.addView(card, LinearLayout.LayoutParams(dpi(700f), -2).apply { topMargin = dpi(26f) })
        } else if (m.envDetail.isNotEmpty() && m.remedy == Remedy.RETRY) {
            col.addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, m.envDetail),
                LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(14f) })
        }
        hint(null)
        if (m.remedy == Remedy.OLD_HELPER || m.remedy == Remedy.RETRY) {
            action(getString(R.string.setup_open_terminal), QButton.Style.TEXT) { setup.openTerminal() }
        } else {
            action(getString(R.string.setup_close), QButton.Style.TEXT) { finish() }
        }
        val again = if (m.remedy == Remedy.RETRY) R.string.setup_try_again else R.string.setup_check_again
        action(getString(again), QButton.Style.FILLED, DEFAULT_FOCUS) {
            if (m.remedy == Remedy.RETRY) setup.startLinux() else setup.refresh()
        }
    }

    private fun agents(installing: Boolean) {
        val m = model
        val running = m.installing
        val col = pageColumn(getString(when {
            !installing -> R.string.setup_agents_title
            running -> R.string.setup_installing_title
            else -> R.string.setup_installed_title
        }), getString(when {
            !installing -> R.string.setup_agents_lead
            running -> R.string.setup_installing_lead
            else -> R.string.setup_installed_lead
        }))
        val grid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        m.offered.chunked(2).forEach { pair ->
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            pair.forEachIndexed { i, a ->
                line.addView(agentCard(a, installing), LinearLayout.LayoutParams(0, -2, 1f).apply {
                    if (i == 0) marginEnd = dpi(5f) else marginStart = dpi(5f)
                })
            }
            if (pair.size == 1) line.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f).apply { marginStart = dpi(5f) })
            grid.addView(line, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dpi(10f) })
        }
        col.addView(grid, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(22f) })
        if (!installing && m.comingSoon.isNotEmpty()) {
            val soon = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            soon.addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, getString(R.string.setup_coming)))
            m.comingSoon.forEach {
                soon.addView(text(TextRole.META, p.onSurfaceVariant, it.name).apply {
                    setPadding(dpi(10f), dpi(4f), dpi(10f), dpi(4f))
                    background = rounded(context, Palette.withAlpha(p.outline, 0.14f), 999f)
                }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dpi(8f) })
            }
            soon.addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, "· " + getString(R.string.setup_coming_acp)),
                LinearLayout.LayoutParams(-2, -2).apply { marginStart = dpi(8f) })
            col.addView(soon, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(6f) })
        }
        if (installing && m.showDetails) col.addView(code(detailsText()), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(8f) })

        if (!installing) {
            val n = m.selected.size
            hint(if (n == 0) hintText(getString(R.string.setup_select_hint)) else LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                addView(hintText(getString(R.string.setup_selected, n, m.selectedMegabytes())))
                addView(button(getString(R.string.setup_what_runs), QButton.Style.TEXT, "whatruns") {
                    m.showWhatRuns = true
                    render()
                })
            })
            action(getString(R.string.setup_skip), QButton.Style.TEXT) { m.next(); render() }
            action(installLabel(), QButton.Style.FILLED, DEFAULT_FOCUS, enabled = n > 0) { setup.install() }
        } else {
            val jobs = m.jobs.values.toList()
            val doneN = jobs.count { it.state == SetupModel.JobState.DONE || it.state == SetupModel.JobState.FAILED }
            hint(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                if (running) addView(hintText(getString(R.string.setup_installing_hint, (doneN + 1).coerceAtMost(jobs.size), jobs.size)))
                addView(button(getString(if (m.showDetails) R.string.setup_hide_details else R.string.setup_show_details),
                    QButton.Style.TEXT, "details") { m.showDetails = !m.showDetails; render() })
            })
            action(getString(R.string.setup_next), QButton.Style.FILLED, DEFAULT_FOCUS, enabled = !running) { m.next(); render() }
        }
    }

    private fun installLabel(): String {
        val sel = model.selected.toList()
        return when (sel.size) {
            0 -> getString(R.string.setup_install)
            1 -> getString(R.string.setup_install_one, model.agent(sel[0])?.name ?: "")
            else -> getString(R.string.setup_install_n, sel.size)
        }
    }

    private fun agentCard(a: SetupModel.Agent, installing: Boolean): View {
        val m = model
        val job = if (installing) m.jobs[a.id] else null
        val selected = !installing && a.id in m.selected
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dpi(64f)
            setPadding(dpi(14f), dpi(12f), dpi(14f), dpi(12f))
            background = if (selected) rounded(context, p.card, 16f, p.primary, 2f) else rounded(context, p.card, 16f, p.cardOutline, 1f)
            tag = "agent:${a.id}"
            isFocusable = true
        }
        card.addView(avatar(a, 40f), LinearLayout.LayoutParams(dpi(40f), dpi(40f)).apply { marginEnd = dpi(14f) })
        val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val nameRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        nameRow.addView(text(TextRole.LABEL_MEDIUM, p.onSurface, a.name))
        if (a.id == "opencode" && !a.installed && job == null) nameRow.addView(text(TextRole.META_MEDIUM, p.onPrimaryContainer,
            getString(R.string.setup_first_pick)).apply {
            setPadding(dpi(8f), dpi(1f), dpi(8f), dpi(1f))
            background = rounded(context, p.primaryContainer, 999f)
        }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dpi(6f) })
        texts.addView(nameRow)
        when {
            job != null && (job.state == SetupModel.JobState.RUNNING || job.state == SetupModel.JobState.QUEUED) -> {
                texts.addView(text(TextRole.META, p.onSurfaceVariant,
                    job.title.ifEmpty { getString(R.string.setup_waiting) }).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END })
                texts.addView(InkBar(this, p).apply { fraction = job.fraction }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(6f) })
            }
            job != null && job.state == SetupModel.JobState.FAILED ->
                texts.addView(text(TextRole.META, p.error, job.error.ifEmpty { getString(R.string.setup_not_installed) }).apply { maxLines = 2 })
            a.installed -> texts.addView(text(TextRole.META, p.onSurfaceVariant, "${a.maker} · ${shortVersion(a)}"))
            else -> texts.addView(text(TextRole.META, p.onSurfaceVariant, "${a.maker} · ${a.needs}"))
        }
        card.addView(texts, LinearLayout.LayoutParams(0, -2, 1f))
        val right: View = when {
            a.installed || job?.state == SetupModel.JobState.DONE -> chip(getString(R.string.setup_installed), ok = true)
            job?.state == SetupModel.JobState.FAILED -> button(getString(R.string.setup_try_again), QButton.Style.PAPER) { setup.retry(a.id) }
            job != null -> text(TextRole.META_MEDIUM, p.onSurfaceVariant, "${(job.fraction * 100).toInt()} %")
            installing -> View(this).apply { visibility = View.GONE }
            else -> FrameLayout(this).apply {
                background = if (selected) GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(p.primary) }
                    else GradientDrawable().apply { shape = GradientDrawable.OVAL; setStroke(dpi(1.5f), p.outline) }
                if (selected) addView(Icon(context, Icons.CHECK, 15f, p.onPrimary), FrameLayout.LayoutParams(-1, -1))
            }
        }
        card.addView(right, if (right is FrameLayout) LinearLayout.LayoutParams(dpi(24f), dpi(24f)) else LinearLayout.LayoutParams(-2, -2))
        card.contentDescription = getString(R.string.setup_card, a.name, a.maker, a.needs)
        if (!installing && !a.installed) {
            card.stateDescription = getString(if (selected) R.string.setup_selected_state else R.string.setup_unselected_state)
            card.setOnClickListener { m.toggle(a.id); render() }
        }
        return card
    }

    private fun detailsText(): String = buildString {
        for ((id, job) in model.jobs) {
            val a = model.agent(id) ?: continue
            appendLine(getString(R.string.setup_what_runs_from, a.name, a.steps.firstOrNull()?.source?.let(::hostOf) ?: a.maker))
            if (a.debian.isNotEmpty()) appendLine(getString(R.string.setup_what_runs_debian, a.debian.joinToString(" ")))
            a.steps.forEach { appendLine(it.command) }
            if (job.line.isNotEmpty()) appendLine(job.line)
            if (job.output.isNotEmpty()) appendLine(job.output)
        }
    }.trimEnd()

    private fun whatRunsText(): String = buildString {
        for (id in model.selected) {
            val a = model.agent(id) ?: continue
            appendLine(getString(R.string.setup_what_runs_from, a.name, a.steps.firstOrNull()?.source?.let(::hostOf) ?: a.maker))
            if (a.debian.isNotEmpty()) appendLine(getString(R.string.setup_what_runs_debian, a.debian.joinToString(" ")))
            a.steps.forEach { appendLine(it.command) }
            appendLine()
        }
    }.trimEnd()

    /** "opencode v2.2.5" reads "v2.2.5" under the agent's own name. */
    private fun shortVersion(a: SetupModel.Agent) =
        a.version.removePrefix(a.name).removePrefix(a.id).trim().ifEmpty { a.version }

    private fun hostOf(url: String) = url.removePrefix("https://").removePrefix("http://").substringBefore('/')

    private fun signIn() {
        val m = model
        val col = pageColumn(getString(R.string.setup_signin_title), getString(R.string.setup_signin_lead))
        val rows = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        for ((a, st) in m.signInRows()) {
            val row = paperRow()
            row.addView(avatar(a, 40f), LinearLayout.LayoutParams(dpi(40f), dpi(40f)).apply { marginEnd = dpi(14f) })
            row.addView(LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                addView(text(TextRole.LABEL_MEDIUM, p.onSurface, a.name))
                addView(text(TextRole.META, p.onSurfaceVariant, when (st) {
                    SignState.IN -> getString(R.string.setup_signed_in)
                    SignState.NOT_NEEDED -> getString(R.string.setup_no_account)
                    else -> a.needs
                }))
            }, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(when (st) {
                SignState.IN -> chip(getString(R.string.setup_signed_in), ok = true)
                SignState.NOT_NEEDED -> chip(getString(R.string.setup_ready), ok = true)
                else -> button(getString(R.string.setup_signin_button), QButton.Style.TONAL, "signin:${a.id}") {
                    a.firstMethod?.let { setup.signIn(a.id, it) }
                }
            })
            rows.addView(row, LinearLayout.LayoutParams(dpi(760f), -2).apply { bottomMargin = dpi(10f) })
        }
        col.addView(rows, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dpi(22f) })
        val pending = m.pendingSignIns
        hint(hintText(if (pending > 0) getString(R.string.setup_signin_pending, pending) else getString(R.string.setup_all_set)))
        if (pending > 0) action(getString(R.string.setup_later), QButton.Style.TEXT) { m.next(); render() }
        action(getString(R.string.setup_next), QButton.Style.FILLED, if (pending > 0) null else DEFAULT_FOCUS) { m.next(); render() }
    }

    private fun tryIt() {
        val m = model
        val col = pageColumn(getString(R.string.setup_try_title), getString(R.string.setup_try_lead))
        val agent = m.defaultAgent?.let { m.agent(it) }
        if (agent != null && helloAsked != agent.id) {
            helloAsked = agent.id
            body.post { setup.sayHello() }
        }
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val mini = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dpi(20f), dpi(18f), dpi(20f), dpi(14f))
            background = rounded(context, p.card, 22f, p.cardOutline, 1f)
            minimumHeight = dpi(300f)
        }
        mini.addView(text(TextRole.PROMPT, p.onSurface, getString(R.string.setup_hello_prompt)))
        mini.addView(View(this).apply { background = rounded(context, p.primary, 1f) },
            LinearLayout.LayoutParams(-1, dpi(1.5f)).apply { topMargin = dpi(8f); bottomMargin = dpi(12f) })
        val answer = when {
            agent == null -> getString(R.string.setup_no_agent_yet)
            m.helloFailed.isNotEmpty() -> getString(R.string.setup_hello_failed, agent.name, m.helloFailed)
            else -> m.helloText
        }
        mini.addView(text(TextRole.BODY, if (m.helloFailed.isNotEmpty()) p.error else p.onSurface, answer).apply {
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }, LinearLayout.LayoutParams(-1, 0, 1f))
        if (agent != null) {
            val quiet = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            val chipAgent = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dpi(3f), dpi(3f), dpi(10f), dpi(3f))
                background = rounded(context, p.card, 999f, p.cardOutline, 1f)
                addView(avatar(agent, 20f), LinearLayout.LayoutParams(dpi(20f), dpi(20f)).apply { marginEnd = dpi(6f) })
                addView(text(TextRole.META_MEDIUM, p.onSurface, agent.name))
                isFocusable = true
                tag = "agentchip"
                contentDescription = getString(R.string.setup_default) + ": " + agent.name
                setOnClickListener { cycleDefault() }
            }
            quiet.addView(chipAgent)
            quiet.addView(text(TextRole.META, p.onSurfaceVariant,
                getString(if (m.helloDone) R.string.setup_default_agent else R.string.setup_answering)),
                LinearLayout.LayoutParams(-2, -2).apply { marginStart = dpi(8f) })
            mini.addView(quiet, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(12f) })
        }
        row.addView(mini, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dpi(24f) })
        val callout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dpi(20f), dpi(20f), dpi(20f), dpi(20f))
            background = rounded(context, p.card, 22f, p.cardOutline, 1f)
            addView(text(TextRole.PROMPT, p.onSurface, getString(R.string.setup_call_title)))
            addView(FrameLayout(context).apply {
                background = rounded(context, Palette.withAlpha(p.outline, 0.08f), 14f)
                addView(Leaf(context, 40f).apply { breathing = true }, FrameLayout.LayoutParams(dpi(40f), dpi(40f), Gravity.CENTER))
            }, LinearLayout.LayoutParams(-1, dpi(172f)).apply { topMargin = dpi(14f) })
            addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, getString(R.string.setup_call_shake)),
                LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(14f) })
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, getString(R.string.setup_call_or)))
                addView(kbd(context, p, "Meta"), LinearLayout.LayoutParams(-2, -2).apply { marginStart = dpi(6f) })
                addView(kbd(context, p, "Space"), LinearLayout.LayoutParams(-2, -2).apply { marginStart = dpi(6f) })
            }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(8f) })
        }
        row.addView(callout, LinearLayout.LayoutParams(dpi(300f), -2))
        col.addView(row, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(24f) })
        hint(if (m.helloDone && m.helloFailed.isEmpty()) hintText(getString(R.string.setup_is_set_up)) else null)
        if (agent == null) action(getString(R.string.setup_add_agents), QButton.Style.TONAL) { m.go(Page.AGENTS); render() }
        action(getString(R.string.setup_done), QButton.Style.FILLED, DEFAULT_FOCUS, enabled = agent == null || m.helloDone) {
            setup.finish()
            m.next()
            render()
        }
    }

    private fun cycleDefault() {
        val ready = model.installedAgents.filter {
            model.signIns[it.id] == SignState.IN || model.signIns[it.id] == SignState.NOT_NEEDED
        }.ifEmpty { model.installedAgents }
        if (ready.size < 2) return
        val i = ready.indexOfFirst { it.id == model.defaultAgent }
        setup.setDefault(ready[(i + 1) % ready.size].id)
        render()
    }

    private fun manage() {
        val m = model
        val col = pageColumn(getString(R.string.setup_manage_title), getString(R.string.setup_manage_lead))
        col.addView(sectionTitle(getString(R.string.setup_env_heading)), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(18f) })
        val running = m.env == SetupModel.Env.READY
        val env = paperRow().apply {
            addView(tile(Icons.TERMINAL, 40f, 12f), LinearLayout.LayoutParams(dpi(40f), dpi(40f)).apply { marginEnd = dpi(14f) })
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                addView(text(TextRole.LABEL_MEDIUM, p.onSurface, getString(if (running) R.string.setup_env_running else R.string.setup_env_stopped)))
                addView(text(TextRole.META, p.onSurfaceVariant, getString(R.string.setup_env_sub, m.quired.ifEmpty { "—" })))
            }, LinearLayout.LayoutParams(0, -2, 1f))
            addView(button(getString(if (running) R.string.setup_stop else R.string.setup_start), QButton.Style.PAPER, "envbutton") {
                if (running) setup.stopLinux() else setup.startLinux()
            })
        }
        col.addView(env, LinearLayout.LayoutParams(-1, -2))
        col.addView(sectionTitle(getString(R.string.setup_agents_heading)), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(22f) })
        val list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(context, p.card, 16f, p.cardOutline, 1f)
        }
        val installed = m.installedAgents
        if (installed.isEmpty()) list.addView(text(TextRole.LABEL, p.onSurfaceVariant, getString(R.string.setup_none_installed)).apply {
            setPadding(dpi(16f), dpi(18f), dpi(16f), dpi(18f))
        })
        installed.forEachIndexed { i, a ->
            if (i > 0) list.addView(View(this).apply { setBackgroundColor(p.cardOutline) }, LinearLayout.LayoutParams(-1, dpi(1f)))
            val st = m.signIns[a.id] ?: SignState.UNKNOWN
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                minimumHeight = dpi(60f)
                setPadding(dpi(14f), dpi(10f), dpi(10f), dpi(10f))
            }
            row.addView(avatar(a, 40f), LinearLayout.LayoutParams(dpi(40f), dpi(40f)).apply { marginEnd = dpi(14f) })
            row.addView(LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                addView(text(TextRole.LABEL_MEDIUM, p.onSurface, a.name))
                addView(text(TextRole.META, p.onSurfaceVariant, getString(when (st) {
                    SignState.IN -> R.string.setup_manage_signed_in
                    SignState.NOT_NEEDED -> R.string.setup_manage_no_account
                    else -> R.string.setup_manage_signed_out
                }, shortVersion(a))))
            }, LinearLayout.LayoutParams(0, -2, 1f))
            val isDefault = m.defaultAgent == a.id
            row.addView(IconButton(this, p, Icons.CHECK_CIRCLE, if (isDefault) getString(R.string.setup_default)
                else getString(R.string.setup_make_default, a.name)).apply {
                icon.setGlyph(Icons.CHECK_CIRCLE, isDefault)
                icon.setTextColor(if (isDefault) p.primary else p.onSurfaceVariant)
                tag = "default:${a.id}"
                setOnClickListener { setup.setDefault(a.id); render() }
            }, LinearLayout.LayoutParams(dpi(36f), dpi(36f)))
            row.addView(IconButton(this, p, Icons.MORE_VERT, getString(R.string.setup_more, a.name)).apply {
                tag = "more:${a.id}"
                setOnClickListener { v -> more(v, a, st) }
            }, LinearLayout.LayoutParams(dpi(36f), dpi(36f)))
            list.addView(row)
        }
        col.addView(list, LinearLayout.LayoutParams(-1, -2))
        hint(button(getString(R.string.setup_open_terminal), QButton.Style.TEXT, glyph = Icons.TERMINAL) { setup.openTerminal() })
        action(getString(R.string.setup_add_agents), QButton.Style.TONAL, DEFAULT_FOCUS) { m.go(Page.AGENTS); render() }
    }

    private fun more(anchor: View, a: SetupModel.Agent, st: SignState) {
        PopupMenu(this, anchor).apply {
            menu.add(0, 1, 0, R.string.setup_update)
            if (st != SignState.NOT_NEEDED) {
                menu.add(0, 2, 1, R.string.setup_sign_in_again)
                if (st == SignState.IN) menu.add(0, 3, 2, R.string.setup_sign_out)
            }
            menu.add(0, 4, 3, R.string.setup_remove)
            menu.add(0, 5, 4, R.string.setup_remove_settings)
            setOnMenuItemClickListener {
                when (it.itemId) {
                    1 -> setup.update(a.id)
                    2 -> a.firstMethod?.let { m -> setup.signIn(a.id, m) }
                    3 -> setup.signOut(a.id)
                    4 -> setup.remove(a.id, settings = false)
                    5 -> setup.remove(a.id, settings = true)
                }
                true
            }
            show()
        }
    }

    // ------------------------------------------------------------------------------------------------ sheets

    private fun renderSheet() {
        sheetLayer.removeAllViews()
        val m = model
        val prompt = m.prompt
        val content: View? = when {
            m.page == Page.AGENTS && m.showWhatRuns && m.selected.isNotEmpty() -> whatRunsSheet()
            prompt != null -> signInSheet(prompt)
            else -> null
        }
        // A code or a key is typed in these sheets: keep the window out of screenshots and the recents thumbnail
        // only while one is open (docs/quire-setup.md §6).
        val secret = prompt != null && (prompt.method.kind == Kind.KEY || prompt.method.kind == Kind.PASTE)
        if (secret) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
        if (content == null) {
            sheetLayer.visibility = View.GONE
            return
        }
        sheetLayer.visibility = View.VISIBLE
        sheetLayer.addView(content, FrameLayout.LayoutParams(dpi(560f), -2, Gravity.CENTER))
    }

    private fun sheet(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dpi(30f), dpi(28f), dpi(30f), dpi(22f))
        background = rounded(context, Palette.withAlpha(if (p.dark) p.surfaceContainer else p.surface, 0.97f), 24f, p.cardOutline, 1f)
        elevation = dp(12f)
        isClickable = true
    }

    private fun whatRunsSheet() = sheet().apply {
        addView(text(TextRole(22f, 28f, 400), p.onSurface, getString(R.string.setup_what_runs)).apply { isAccessibilityHeading = true })
        addView(text(TextRole.LABEL, p.onSurfaceVariant, getString(R.string.setup_what_runs_lead)),
            LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(4f) })
        addView(code(whatRunsText()), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(14f) })
        addView(sheetActions(hintText(getString(R.string.setup_what_runs_fine)),
            button(getString(R.string.setup_back), QButton.Style.TEXT, "back") { model.showWhatRuns = false; render() },
            button(installLabel(), QButton.Style.FILLED, DEFAULT_FOCUS) { setup.install() }))
    }

    private fun signInSheet(pr: SetupModel.Prompt): View {
        val a = model.agent(pr.agent)
        val name = a?.name ?: pr.agent
        val s = sheet()
        if (a != null) s.addView(avatar(a, 36f), LinearLayout.LayoutParams(dpi(36f), dpi(36f)))
        when (pr.method.kind) {
            Kind.KEY -> {
                s.addView(sheetTitle(getString(R.string.setup_key_title, name)))
                s.addView(sheetLead(getString(R.string.setup_key_lead)))
                val key = a?.keys?.firstOrNull()
                if (key != null) s.addView(text(TextRole.META_MEDIUM, p.onSurfaceVariant, key.label.ifEmpty { key.name }),
                    LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(16f) })
                s.addView(fieldRow(keyField, getString(R.string.setup_key_save)) {
                    val v = keyField.text.toString()
                    keyField.text.clear()
                    if (v.isNotBlank() && key != null) setup.saveKey(pr.agent, key.name, v)
                })
                failed(s, pr)
                s.addView(sheetActions(null, button(getString(R.string.setup_cancel), QButton.Style.TEXT, "cancel") { closeSheet() }))
                s.addView(fine(getString(R.string.setup_key_fine)))
            }
            Kind.DEVICE -> {
                s.addView(sheetTitle(getString(R.string.setup_signin_to, name)))
                s.addView(sheetLead(getString(R.string.setup_device_lead, a?.maker ?: name)))
                if (pr.code.isEmpty() && pr.url.isEmpty()) {
                    s.addView(waiting(getString(R.string.setup_waiting_agent, name)))
                } else {
                    s.addView(numbered(1, getString(R.string.setup_device_copy), LinearLayout(this).apply {
                        orientation = LinearLayout.HORIZONTAL
                        gravity = Gravity.CENTER_VERTICAL
                        addView(TextView(context).apply {
                            text = pr.code
                            setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 28f)
                            typeface = Typeface.create(type.code, 500, false)
                            letterSpacing = 0.12f
                            setTextColor(p.onSurface)
                            setPadding(dpi(18f), dpi(10f), dpi(18f), dpi(10f))
                            background = rounded(context, p.card, 14f, p.cardOutline, 1f)
                            setTextIsSelectable(true)
                        })
                        addView(button(getString(R.string.setup_copy), QButton.Style.PAPER, "copy", glyph = Icons.CONTENT_COPY) {
                            setup.copy(name, pr.code)
                        }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dpi(12f) })
                    }))
                    s.addView(numbered(2, getString(R.string.setup_device_enter),
                        button(getString(R.string.setup_open_page), QButton.Style.FILLED, DEFAULT_FOCUS, enabled = pr.url.isNotEmpty(),
                            glyph = Icons.OPEN_IN_NEW) { setup.openUrl(pr.url) }))
                    s.addView(waiting(getString(R.string.setup_waiting_browser)))
                }
                failed(s, pr)
                s.addView(sheetActions(hintText(getString(R.string.setup_device_fine)),
                    button(getString(R.string.setup_cancel), QButton.Style.TEXT, "cancel") { closeSheet() }))
            }
            Kind.ACP -> {
                s.addView(sheetTitle(getString(R.string.setup_signin_to, name)))
                s.addView(sheetLead(getString(R.string.setup_link_lead)))
                if (pr.url.isNotEmpty()) s.addView(numbered(1, getString(R.string.setup_open_page),
                    button(getString(R.string.setup_open_page), QButton.Style.FILLED, DEFAULT_FOCUS, glyph = Icons.OPEN_IN_NEW) {
                        setup.openUrl(pr.url)
                    }))
                if (pr.failed.isEmpty()) s.addView(waiting(getString(R.string.setup_waiting_agent, name)))
                failed(s, pr)
                val keyMethod = a?.methods?.firstOrNull { it.kind == Kind.KEY }
                s.addView(sheetActions(null,
                    keyMethod?.let { km -> button(getString(R.string.setup_use_key), QButton.Style.TEXT, "usekey", glyph = Icons.KEY) {
                        setup.signIn(pr.agent, km) } },
                    if (pr.failed.isNotEmpty()) button(getString(R.string.setup_open_terminal), QButton.Style.TEXT) { setup.openTerminal() } else null,
                    button(getString(R.string.setup_cancel), QButton.Style.TEXT, "cancel") { closeSheet() }))
            }
            Kind.LINK -> {
                s.addView(sheetTitle(getString(R.string.setup_signin_to, name)))
                s.addView(sheetLead(getString(R.string.setup_link_lead)))
                s.addView(numbered(1, getString(R.string.setup_open_page),
                    button(getString(R.string.setup_open_page), QButton.Style.FILLED, DEFAULT_FOCUS, enabled = pr.url.isNotEmpty(),
                        glyph = Icons.OPEN_IN_NEW) { setup.openUrl(pr.url) }))
                s.addView(waiting(getString(if (pr.url.isEmpty()) R.string.setup_waiting_agent else R.string.setup_waiting_browser, name)))
                failed(s, pr)
                s.addView(sheetActions(null, button(getString(R.string.setup_cancel), QButton.Style.TEXT, "cancel") { closeSheet() }))
            }
            else -> {
                s.addView(sheetTitle(getString(R.string.setup_signin_to, name)))
                s.addView(sheetLead(getString(R.string.setup_paste_lead)))
                s.addView(numbered(1, getString(R.string.setup_paste_open),
                    button(getString(R.string.setup_open_page), QButton.Style.FILLED, DEFAULT_FOCUS, enabled = pr.url.isNotEmpty(),
                        glyph = Icons.OPEN_IN_NEW) { setup.openUrl(pr.url) }))
                s.addView(numbered(2, getString(R.string.setup_paste_code), fieldRow(pasteField, getString(R.string.setup_signin_button)) {
                    val v = pasteField.text.toString()
                    pasteField.text.clear()
                    if (v.isNotBlank()) setup.paste(v)
                }))
                if (pr.url.isEmpty()) s.addView(waiting(getString(R.string.setup_waiting_agent, name)))
                failed(s, pr)
                val keyMethod = a?.methods?.firstOrNull { it.kind == Kind.KEY }
                s.addView(sheetActions(null,
                    keyMethod?.let { km ->
                        button(getString(R.string.setup_use_key), QButton.Style.TEXT, "usekey", glyph = Icons.KEY) {
                            setup.signIn(pr.agent, km)
                        }
                    },
                    button(getString(R.string.setup_cancel), QButton.Style.TEXT, "cancel") { closeSheet() }))
                s.addView(fine(getString(R.string.setup_paste_fine, name)))
            }
        }
        return s
    }

    private fun failed(s: LinearLayout, pr: SetupModel.Prompt) {
        if (pr.failed.isNotEmpty()) s.addView(text(TextRole.LABEL, p.error, pr.failed),
            LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(12f) })
    }

    private fun sheetTitle(t: String) = text(TextRole(22f, 28f, 400), p.onSurface, t).apply {
        isAccessibilityHeading = true
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(12f) }
    }

    private fun sheetLead(t: String) = text(TextRole.LABEL, p.onSurfaceVariant, t).apply {
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(4f) }
    }

    private fun fine(t: String) = text(TextRole.META, p.onSurfaceVariant, t).apply {
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(12f) }
    }

    private fun waiting(t: String) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        addView(Mark(context, p).apply { state = Row.NOW })
        addView(text(TextRole.CHIP_REGULAR, p.onSurfaceVariant, t), LinearLayout.LayoutParams(-2, -2).apply { marginStart = dpi(6f) })
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(18f) }
        accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
    }

    private fun numbered(n: Int, title: String, content: View) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        addView(TextView(context).apply {
            role(TextRole.CHIP, p.onSecondaryContainer, type)
            gravity = Gravity.CENTER
            text = "$n"
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(p.secondaryContainer) }
        }, LinearLayout.LayoutParams(dpi(26f), dpi(26f)).apply { marginEnd = dpi(12f) })
        addView(LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            addView(text(TextRole.PROMPT, p.onSurface, title).apply { minHeight = dpi(26f); gravity = Gravity.CENTER_VERTICAL })
            addView(content, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dpi(8f) })
        }, LinearLayout.LayoutParams(0, -2, 1f))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(18f) }
    }

    private fun fieldRow(field: EditText, action: String, onAction: () -> Unit): View {
        (field.parent as? ViewGroup)?.removeView(field)
        field.setOnEditorActionListener { _, id, _ ->
            if (id == EditorInfo.IME_ACTION_DONE) { onAction(); true } else false
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(field, LinearLayout.LayoutParams(0, dpi(44f), 1f))
            addView(button(action, QButton.Style.FILLED, "fieldaction") { onAction() },
                LinearLayout.LayoutParams(-2, dpi(40f)).apply { marginStart = dpi(10f) })
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(10f) }
        }
    }

    private fun sheetActions(lead: View?, vararg buttons: View?) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        addView(lead ?: View(context), LinearLayout.LayoutParams(0, if (lead == null) 1 else -2, 1f))
        buttons.filterNotNull().forEach { addView(it, LinearLayout.LayoutParams(-2, dpi(40f)).apply { marginStart = dpi(8f) }) }
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dpi(22f) }
    }

    // ------------------------------------------------------------------------------------------------ pieces

    private fun text(r: TextRole, color: Int, s: CharSequence) = TextView(this).apply {
        role(r, color, type)
        text = s
    }

    private fun sectionTitle(s: String) = text(TextRole.HEADING, p.onSurfaceVariant, s.uppercase()).apply {
        letterSpacing = 0.04f
        setPadding(dpi(4f), 0, 0, dpi(8f))
        isAccessibilityHeading = true
    }

    private fun chip(label: String, ok: Boolean) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dpi(8f), dpi(3f), dpi(10f), dpi(3f))
        background = rounded(context, if (ok) p.successContainer else p.secondaryContainer, 999f)
        if (ok) addView(Icon(context, Icons.CHECK, 15f, p.onSuccessContainer), LinearLayout.LayoutParams(dpi(16f), dpi(16f)).apply { marginEnd = dpi(4f) })
        addView(text(TextRole.META_MEDIUM, if (ok) p.onSuccessContainer else p.onSecondaryContainer, label))
    }

    private fun paperRow() = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        minimumHeight = dpi(64f)
        setPadding(dpi(14f), dpi(12f), dpi(14f), dpi(12f))
        background = rounded(context, p.card, 16f, p.cardOutline, 1f)
    }

    private fun avatar(a: SetupModel.Agent, sizeDp: Float) = Avatar(this, sizeDp, if (sizeDp >= 36f) 13f else 9f).apply {
        val (initials, color) = AVATARS[a.id] ?: (a.name.split(' ').filter { it.isNotEmpty() }.take(2)
            .joinToString("") { it.take(1) }.uppercase() to 0xFF5E5E68.toInt())
        set(initials, color)
    }

    private fun code(s: String) = TextView(this).apply {
        role(TextRole.CODE, if (p.dark) p.onSurface else p.inverseOnSurface, type)
        typeface = type.code
        text = s
        setPadding(dpi(14f), dpi(12f), dpi(14f), dpi(12f))
        background = rounded(context, if (p.dark) Palette.withAlpha(0xFF000000.toInt(), 0.55f) else p.inverseSurface, 14f)
        setTextIsSelectable(true)
    }

    private fun field(hintRes: Int, secret: Boolean) = EditText(this).apply {
        role(TextRole.FIELD, p.onSurface, type)
        hint = getString(hintRes)
        setHintTextColor(p.onSurfaceVariant)
        isSingleLine = true
        imeOptions = EditorInfo.IME_ACTION_DONE
        if (secret) {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            // Never in saved state, never offered to autofill (docs/quire-setup.md §6).
            isSaveEnabled = false
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        }
        setPadding(dpi(18f), 0, dpi(18f), 0)
        background = rounded(context, p.field, 22f, p.cardOutline, 1f)
        tag = "field:$hintRes"
    }

    companion object {
        private const val DEFAULT_FOCUS = "main"
        private val TITLE = TextRole(30f, 38f, 400)

        /** The note's avatars (note/Agents.kt), by catalog id. Initials only: no makers' logos. */
        private val AVATARS = mapOf(
            "claude" to ("CC" to 0xFF5B5D72.toInt()), "opencode" to ("oc" to 0xFF72557B.toInt()),
            "copilot" to ("Cp" to 0xFF4F5065.toInt()), "antigravity" to ("Ag" to 0xFF5A6190.toInt()),
            "gemini" to ("G" to 0xFF565B8C.toInt()), "cursor" to ("Cu" to 0xFF5E5E68.toInt()),
            "kimi" to ("Ki" to 0xFF6A5E7E.toInt()), "grok" to ("Gk" to 0xFF54586A.toInt()),
            "hermes" to ("He" to 0xFF5A6378.toInt()), "omp" to ("Pi" to 0xFF65597A.toInt()),
            "codex" to ("Cx" to 0xFF7A7A84.toInt()),
        )
    }
}
