// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.app.Activity
import android.app.ActivityOptions
import android.content.Context
import android.content.Intent
import android.content.IntentSender
import android.graphics.Rect
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.control.ComputerControl
import dev.openbook.quire.ui.Icon
import dev.openbook.quire.ui.Palette
import dev.openbook.quire.ui.TextRole
import dev.openbook.quire.ui.dp
import dev.openbook.quire.ui.dpi
import dev.openbook.quire.ui.role
import dev.openbook.quire.ui.rounded
import java.lang.ref.WeakReference

/**
 * Quire's window while it asks the platform for a computer-control session (docs/quire-design.md §3.3 rule 5).
 *
 * The platform creates a session only for an owner with a visible window: it checks when Quire asks, and again after
 * the person allows in its consent dialog. The note is an ordinary overlay, so it is hidden whenever a window on screen
 * hides overlays, and Settings and Files always do. So the request starts from this activity, which no overlay rule
 * hides, and the dialog is started from it: the dialog opens above it and stays above it, and nothing of Quire's ever
 * covers the dialog. The activity is inert (no touch, no focus) and transparent; while the dialog is up it shows a
 * still of the note at the note's place (header, intake, prompt, steps, the waiting row; no composer, no footer), on
 * the note's own surface, so the only change on screen is the dialog's scrim (§5.2). It is gone as soon as the
 * platform has answered (the session is created or refused) or the run stops.
 */
object ConsentWait : ComputerControl.ConsentHost {
    /** What the waiting card says, and where the note's card was (display pixels), to draw it in the same place. */
    class Card(val title: String, val sub: String, val at: Rect?)

    private class Pending(val card: Card, val ready: (Boolean) -> Unit)

    private var pending: Pending? = null
    private var card: Card? = null
    private var still: android.graphics.Bitmap? = null
    private var stillAt: Rect? = null
    private var activity: WeakReference<ConsentWaitActivity>? = null
    private var main: android.os.Handler? = null
    private val timeout = Runnable {
        pending?.let {
            Log.w(TAG, "consent: the waiting activity did not come up")
            pending = null
            it.ready(false)
        }
    }

    /** Starts the activity; [ready] runs once, true when its first frame is on screen and Quire may ask. */
    fun begin(context: Context, card: Card, ready: (Boolean) -> Unit) {
        close()
        val h = main ?: android.os.Handler(context.mainLooper).also { main = it }
        this.card = card
        pending = Pending(card, ready)
        Log.i(TAG, "consent: starting the waiting activity")
        try {
            context.startActivity(Intent(context, ConsentWaitActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION))
            h.postDelayed(timeout, START_TIMEOUT_MS)
        } catch (e: RuntimeException) {
            Log.w(TAG, "consent: could not start the waiting activity: ${e.javaClass.simpleName}: ${e.message}")
            pending = null
            ready(false)
        }
    }

    /** The note's still and where it is (display pixels), shown beneath the dialog instead of the plain card. */
    fun still(bitmap: android.graphics.Bitmap?, at: Rect?) {
        still = bitmap
        stillAt = at
    }

    /** The platform asks: the activity, already on screen, shows the still, then starts the dialog above itself. */
    override fun open(sender: IntentSender, opened: (Boolean) -> Unit) {
        val a = activity?.get()
        if (a == null || a.isFinishing) {
            Log.w(TAG, "consent: no waiting activity to open the dialog from")
            return opened(false)
        }
        val b = still
        val at = stillAt
        a.openDialog(sender, opened, if (b != null && at != null) b to at else null)
    }

    /** The platform answered or the run ended: the waiting activity goes. */
    override fun close() {
        main?.removeCallbacks(timeout)
        pending = null
        card = null
        still = null
        stillAt = null
        activity?.get()?.let {
            if (!it.isFinishing) {
                Log.i(TAG, "consent: waiting activity finished")
                it.finish()
            }
        }
        activity = null
    }

    internal fun attach(a: ConsentWaitActivity): Card? {
        val c = card ?: return null
        activity = WeakReference(a)
        return c
    }

    /** The activity's first frame is on screen. */
    internal fun shown() {
        main?.removeCallbacks(timeout)
        val p = pending ?: return
        pending = null
        Log.i(TAG, "consent: waiting activity on screen")
        p.ready(true)
    }

    internal fun detach(a: ConsentWaitActivity) {
        if (activity?.get() === a) activity = null
    }

    private const val START_TIMEOUT_MS = 3000L
}

class ConsentWaitActivity : Activity() {
    private var card: View? = null
    private var reported = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Inert: the person's clicks and keys are for the dialog above, never for this window.
        window.addFlags(WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE)
        val c = ConsentWait.attach(this)
        // Recreated, or started by nobody: there is nothing to wait for.
        if (c == null || savedInstanceState != null) {
            finish()
            return
        }
        setContentView(waitingCard(c))
        Log.i(TAG, "consent: waiting activity created")
    }

    override fun onResume() {
        super.onResume()
        if (reported || card == null) return
        reported = true
        // After this window's first frame, so the platform finds Quire on screen when it checks.
        window.decorView.viewTreeObserver.registerFrameCommitCallback {
            window.decorView.postDelayed({ if (!isFinishing) ConsentWait.shown() }, VISIBLE_SETTLE_MS)
        }
        window.decorView.invalidate()
    }

    /**
     * Shows the note's [still] (or, without one, the plain waiting card) and, once that frame is on screen, starts the
     * platform's dialog above this activity. The note steps aside as the dialog starts (ControlRun.onPending), so the
     * still takes its place without a blink and nothing of Quire's is ever over the dialog.
     */
    fun openDialog(sender: IntentSender, opened: (Boolean) -> Unit, still: Pair<android.graphics.Bitmap, Rect>?) {
        if (still != null) {
            card?.let { (it.parent as? ViewGroup)?.removeView(it) }
            val v = stillView(still.first, still.second)
            (window.decorView.findViewById<ViewGroup>(android.R.id.content).getChildAt(0) as ViewGroup).addView(v)
            card = v
            Log.i(TAG, "consent: the note's still at ${still.second.toShortString()}")
        }
        card?.visibility = View.VISIBLE
        val decor = window.decorView
        decor.viewTreeObserver.registerFrameCommitCallback { decor.post { startDialog(sender, opened) } }
        decor.invalidate()
    }

    private fun startDialog(sender: IntentSender, opened: (Boolean) -> Unit) {
        if (isFinishing) return opened(false)
        try {
            startIntentSender(sender, null, 0, 0, 0, ActivityOptions.makeBasic()
                .setPendingIntentBackgroundActivityStartMode(ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOW_IF_VISIBLE)
                .toBundle())
            Log.i(TAG, "consent: dialog started above the waiting activity")
            opened(true)
        } catch (e: Exception) {
            // SendIntentException, or ActivityNotFoundException when the image lacks the platform's consent app.
            Log.w(TAG, "consent: could not open the dialog: ${e.javaClass.simpleName}: ${e.message}")
            card?.visibility = View.INVISIBLE
            opened(false)
        }
    }

    override fun finish() {
        super.finish()
        overrideActivityTransition(OVERRIDE_TRANSITION_CLOSE, 0, 0)
    }

    override fun onDestroy() {
        ConsentWait.detach(this)
        super.onDestroy()
    }

    /**
     * The note's still on the note's surface (the blur at the note's radius under the 92 % note colour, the 1 dp
     * outline, the 12 dp shadow), at [at] in display pixels. An image: nothing in it can take focus.
     */
    private fun stillView(still: android.graphics.Bitmap, at: Rect): View {
        val p = Palette.of(this)
        val radius = dp(NoteCard.RADIUS_DP)
        val box = FrameLayout(this).apply {
            val blur = window.decorView.viewRootImpl?.createBackgroundBlurDrawable()?.apply {
                setColor(p.noteBackground)
                setBlurRadius(dpi(NoteCard.BLUR_DP))
                setCornerRadius(radius, radius, radius, radius)
            }
            background = blur ?: rounded(context, p.noteBackground, NoteCard.RADIUS_DP)
            foreground = rounded(context, 0, NoteCard.RADIUS_DP, p.noteOutline, 1f)
            elevation = dp(12f)
            outlineAmbientShadowColor = p.shadow
            outlineSpotShadowColor = p.shadow
            outlineProvider = object : android.view.ViewOutlineProvider() {
                override fun getOutline(view: View, outline: android.graphics.Outline) {
                    outline.setRoundRect(0, 0, view.width, view.height, radius)
                }
            }
            clipToOutline = true
            isFocusable = false
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
            addView(android.widget.ImageView(context).apply {
                setImageBitmap(still)
                scaleType = android.widget.ImageView.ScaleType.FIT_XY
            }, FrameLayout.LayoutParams(still.width, still.height))
        }
        box.layoutParams = FrameLayout.LayoutParams(still.width, still.height).apply { gravity = Gravity.TOP or Gravity.START }
        // At the note's place in display pixels, whatever this window's own offset.
        box.addOnLayoutChangeListener { v, _, _, _, _, _, _, _, _ ->
            val loc = IntArray(2)
            (v.parent as View).getLocationOnScreen(loc)
            v.translationX = (at.left - loc[0]).toFloat()
            v.translationY = (at.top - loc[1]).toFloat()
        }
        return box
    }

    /** The plain waiting card, for a run with no note to take a still of; inert, and beneath the dialog. */
    private fun waitingCard(c: ConsentWait.Card): View {
        val p = Palette.of(this)
        val frame = FrameLayout(this)
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.TOP
            background = rounded(context, if (p.dark) p.surfaceHigh else p.surfaceLowest, 20f)
            elevation = context.dp(12f)
            outlineAmbientShadowColor = p.shadow
            outlineSpotShadowColor = p.shadow
            setPadding(dpi(16f), dpi(14f), dpi(16f), dpi(14f))
            addView(Icon(context, Icons.SHIELD, 20f, p.tertiary, filled = true), LinearLayout.LayoutParams(dpi(20f), dpi(20f)))
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                addView(TextView(context).apply {
                    role(TextRole.LABEL_MEDIUM, p.onSurface)
                    text = c.title
                })
                addView(TextView(context).apply {
                    role(TextRole.SUB, p.onSurfaceVariant)
                    text = c.sub
                })
            }, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { marginStart = dpi(12f) })
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        }
        // Shown only while the dialog is up; before that the activity is fully transparent.
        card.visibility = View.INVISIBLE
        this.card = card
        val at = c.at
        val width = at?.width()?.takeIf { it > 0 } ?: dpi(400f)
        frame.addView(card, FrameLayout.LayoutParams(width, WRAP_CONTENT).apply {
            gravity = Gravity.TOP or Gravity.START
        })
        // The card goes where the note's card was, in display pixels, whatever this window's own offset.
        frame.addOnLayoutChangeListener { v, _, _, _, _, _, _, _, _ ->
            val loc = IntArray(2)
            v.getLocationOnScreen(loc)
            val x = (at?.left ?: ((v.width - width) / 2 + loc[0])) - loc[0]
            val y = (at?.top ?: (v.height - card.height - dpi(96f) + loc[1])) - loc[1]
            card.translationX = x.toFloat()
            card.translationY = y.toFloat()
        }
        return frame
    }

    companion object {
        /** After the first frame is committed, how long until WM has shown the surface. */
        private const val VISIBLE_SETTLE_MS = 150L
    }
}
