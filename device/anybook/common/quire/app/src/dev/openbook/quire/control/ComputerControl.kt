// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.control

import android.app.ActivityOptions
import android.app.AppInteractionAttribution
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.companion.virtual.VirtualDeviceManager
import android.companion.virtual.computercontrol.ComputerControlSession
import android.companion.virtual.computercontrol.ComputerControlSessionParams
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentSender
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Rect
import android.media.Image
import android.os.OutcomeReceiver
import android.util.Log
import android.view.accessibility.AccessibilityNodeInfo
import dev.openbook.quire.Quire
import dev.openbook.quire.QuireApplication
import dev.openbook.quire.R
import dev.openbook.quire.invocation.Invocations
import java.io.File
import java.util.concurrent.CopyOnWriteArraySet

/**
 * Quire's computer-control session (docs/quire.md §2.4), through the @hide framework API. The platform decides
 * everything that matters for safety: whether Quire may own a session at all (the assistant role, ACCESS_COMPUTER_CONTROL,
 * its allowlist), the consent dialog, the lock screen, which apps the session may run, and when it blocks (secure
 * windows, disallowed launches, authentication prompts). Quire only asks, and reports what it was told.
 *
 * Every outcome is logged as "cc: ..." under [Quire.TAG]; scripts/quire/q2-cf-check.sh reads those lines.
 */
class ComputerControl(private val context: Context) {
    fun interface Listener {
        fun onChanged()
    }

    /** What happened to a request or a session, for the note (docs/quire-design.md §3.3 rule 5, §3.4). */
    interface Events {
        /** The platform asks for consent; the dialog opens once [proceed] runs (the note readies its waiting still). */
        fun beforeDialog(proceed: () -> Unit) = proceed()
        fun onPending(dialogShown: Boolean) {}
        fun onCreated(session: ComputerControlSession) {}
        fun onCreationFailed(errorCode: Int, dialogShown: Boolean) {}
        fun onRefused(reason: String) {}
        fun onActive() {}
        fun onBlocked(reason: Int, blockingPackage: String?) {}
        fun onClosed(reason: Int) {}
    }

    /**
     * Opens the platform's consent dialog for a caller that is not an activity (the note, a window): from an activity
     * of Quire's own, beneath the dialog, which keeps Quire visible while the dialog hides overlays
     * (note/ConsentWaitActivity.kt).
     */
    interface ConsentHost {
        /** Starts [sender]'s dialog; [opened] runs once, with whether it started. */
        fun open(sender: IntentSender, opened: (Boolean) -> Unit)

        /** The dialog was answered, or the request is over. */
        fun close()
    }

    /** The note's listener for the current request and session; null for Q2's window and the lab. */
    var events: Events? = null
    private var dialogShown = false
    private var consent: ConsentHost? = null

    private val main = context.mainExecutor
    private val listeners = CopyOnWriteArraySet<Listener>()
    private var pendingLaunch: String? = null

    /** The open session, if any. Main thread only. */
    var session: ComputerControlSession? = null
        private set

    /** One line for Quire's window. */
    var status: String = context.getString(R.string.control_idle)
        private set

    fun addListener(listener: Listener) {
        listeners += listener
    }

    fun removeListener(listener: Listener) {
        listeners -= listener
    }

    /**
     * Asks the platform for a session that may run [targets], then launches [launch] (a package or a flattened
     * component) on it. Quire must have a visible window while it asks (Q2's activity, or the note): the platform
     * requires the agent to be in the foreground, and checks again after consent. Quire starts the consent dialog from
     * [starter] when it is an activity, else through [host].
     */
    fun request(starter: Context, targets: List<String>, launch: String?, host: ConsentHost? = null) {
        if (session != null) {
            report("request refused by Quire: a session is already open")
            events?.onRefused("a session is already open")
            return
        }
        val vdm = context.getSystemService(VirtualDeviceManager::class.java)
        if (vdm == null) {
            report("request failed: no VirtualDeviceManager")
            events?.onRefused("no VirtualDeviceManager")
            return
        }
        dialogShown = false
        val name = "quire-${System.currentTimeMillis()}"
        val params = try {
            ComputerControlSessionParams.Builder()
                .setName(name)
                .setTargetPackageNames(targets)
                .setTargetComputerControlVersion(VirtualDeviceManager.COMPUTER_CONTROL_VERSION)
                .setAppInteractionAttribution(
                    AppInteractionAttribution.Builder(AppInteractionAttribution.INTERACTION_TYPE_USER_QUERY)
                        .build()
                )
                .setNotificationParams(
                    ComputerControlSessionParams.NotificationParams.Builder(notification(targets), NOTIFICATION_ID)
                        .build()
                )
                .build()
        } catch (e: IllegalArgumentException) {
            report("request failed: invalid parameters: ${e.message}")
            events?.onRefused("invalid parameters: ${e.message}")
            return
        }
        pendingLaunch = launch
        consent = host
        report("request name=$name targets=$targets version=${VirtualDeviceManager.COMPUTER_CONTROL_VERSION}")
        try {
            vdm.requestComputerControlSession(params, main, callback(starter))
        } catch (e: RuntimeException) {
            // SecurityException (not allowed to own a session), IllegalArgumentException (a target outside the
            // allowlist), IllegalStateException (computer control is off in this build), and so on.
            pendingLaunch = null
            report("request refused by the platform: ${e.javaClass.simpleName}: ${e.message}")
            events?.onRefused("${e.javaClass.simpleName}: ${e.message}")
        }
    }

    private fun callback(starter: Context) =
        object : ComputerControlSession.Callback {
            override fun onSessionPending(intentSender: IntentSender) {
                report("pending: the platform asks for consent")
                val host = consent
                if (host != null && starter !is android.app.Activity) {
                    val open = {
                        host.open(intentSender) { ok ->
                            if (ok) {
                                dialogShown = true
                                report("pending: the dialog is open, above Quire's waiting activity")
                                events?.onPending(true)
                            } else {
                                pendingLaunch = null
                                report("pending: could not open the consent dialog")
                                events?.onPending(false)
                            }
                        }
                    }
                    events?.beforeDialog(open) ?: open()
                    return
                }
                try {
                    starter.startIntentSender(
                        intentSender, null, 0, 0, 0,
                        ActivityOptions.makeBasic()
                            .setPendingIntentBackgroundActivityStartMode(
                                ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOW_IF_VISIBLE
                            )
                            .toBundle(),
                    )
                    dialogShown = true
                    events?.onPending(true)
                } catch (e: Exception) {
                    // SendIntentException, or ActivityNotFoundException when the image lacks the platform's
                    // consent app (VirtualDeviceManager, RELEASE_PACKAGE_COMPUTER_CONTROL).
                    pendingLaunch = null
                    report("pending: could not open the consent dialog: ${e.javaClass.simpleName}: ${e.message}")
                    events?.onPending(false)
                }
            }

            override fun onSessionCreated(created: ComputerControlSession) {
                session = created
                val size = created.displaySize
                report("created: display ${size.width}x${size.height}")
                created.setLifecycleCallback(main, lifecycle)
                events?.onCreated(created)
                // The platform has checked; the waiting activity can go now that the note is back.
                closeConsent()
                pendingLaunch?.let { launch(it) }
                pendingLaunch = null
            }

            override fun onSessionCreationFailed(errorCode: Int) {
                pendingLaunch = null
                report("creation failed: error=$errorCode(${errorName(errorCode)}) dialogShown=$dialogShown")
                events?.onCreationFailed(errorCode, dialogShown)
                closeConsent()
            }

            @Deprecated("The platform's own deprecation; LifecycleCallback.onClosed reports the reason.")
            override fun onSessionClosed() {
                closed()
            }
        }

    private fun closeConsent() {
        consent?.close()
        consent = null
    }

    private val lifecycle =
        object : ComputerControlSession.LifecycleCallback {
            override fun onActive() {
                report("lifecycle: active")
                events?.onActive()
            }

            override fun onBlocked(reason: Int, blockingPackage: String?) {
                report("lifecycle: blocked reason=$reason(${blockReasonName(reason)}) package=$blockingPackage")
                events?.onBlocked(reason, blockingPackage)
            }

            override fun onClosed(reason: Int) {
                report("lifecycle: closed reason=$reason(${closeReasonName(reason)})")
                closed()
                events?.onClosed(reason)
            }
        }

    private fun closed() {
        if (session == null) return
        session = null
        changed()
    }

    /** Launches a package, or a flattened component, on the session display. */
    fun launch(target: String) {
        val s = session ?: return report("launch refused by Quire: no session")
        try {
            val component = ComponentName.unflattenFromString(target)
            if (component != null) s.launchApplication(component) else s.launchApplication(target)
            report("launch: $target")
        } catch (e: RuntimeException) {
            report("launch failed: $target: ${e.javaClass.simpleName}: ${e.message}")
        }
    }

    /** Takes a screenshot of the session display; debuggable builds keep it in Quire's files/control/. */
    fun screenshot() {
        val s = session ?: return report("screenshot refused by Quire: no session")
        val io = (context.applicationContext as QuireApplication).io
        s.requestScreenshot(io, object : OutcomeReceiver<Image, ComputerControlSession.ScreenshotException> {
            override fun onResult(image: Image) {
                val bitmap = image.use { toBitmap(it) }
                val saved = if (Quire.keepsEvidence) save(bitmap) else null
                report("screenshot: ${bitmap.width}x${bitmap.height}" + (saved?.let { " saved ${it.path}" } ?: ""))
            }

            override fun onError(error: ComputerControlSession.ScreenshotException) {
                report("screenshot refused: error=${error.errorCode}")
            }
        }, null)
    }

    /** Taps the session display at ([x], [y]), in its own pixels. */
    fun tap(x: Int, y: Int) {
        val s = session ?: return report("tap refused by Quire: no session")
        try {
            s.tap(x, y)
            report("tap: $x,$y")
        } catch (e: RuntimeException) {
            report("tap failed: $x,$y: ${e.javaClass.simpleName}: ${e.message}")
        }
    }

    /**
     * Taps the centre of the first on-screen node whose text contains [text], found through the session's
     * accessibility windows, as an agent would.
     */
    fun tapText(text: String) {
        val s = session ?: return report("tap refused by Quire: no session")
        val node = s.accessibilityWindows.firstNotNullOfOrNull { window ->
            window.root?.findAccessibilityNodeInfosByText(text)?.firstOrNull()
        } ?: return report("tap refused by Quire: no node with text \"$text\" " +
            "(${s.accessibilityWindows.size} accessibility windows)")
        val target = clickableAncestor(node) ?: node
        val bounds = Rect().also { target.getBoundsInScreen(it) }
        report("tap target: \"$text\" checked=${checkedState(target)} bounds=$bounds")
        tap(bounds.centerX(), bounds.centerY())
    }

    /** Logs the session's accessibility windows and their texts, to find tap targets. */
    fun dumpWindows() {
        val s = session ?: return report("windows refused by Quire: no session")
        val windows = s.accessibilityWindows
        report("windows: ${windows.size}")
        windows.forEach { window ->
            Log.i(Quire.TAG, "cc: window \"${window.title}\" display=${window.displayId}")
            window.root?.let { dumpNode(it, 1) }
        }
    }

    private fun dumpNode(node: AccessibilityNodeInfo, depth: Int) {
        if (depth > 30) return
        val label = node.text ?: node.contentDescription
        if (label != null || node.isCheckable) {
            val bounds = Rect().also { node.getBoundsInScreen(it) }
            Log.i(Quire.TAG, "cc: ${"  ".repeat(depth)}\"$label\" ${node.className} " +
                "checkable=${node.isCheckable} checked=${checkedState(node)} bounds=$bounds")
        }
        for (i in 0 until node.childCount) node.getChild(i)?.let { dumpNode(it, depth + 1) }
    }

    private fun clickableAncestor(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var current: AccessibilityNodeInfo? = node
        while (current != null && !current.isClickable) current = current.parent
        return current
    }

    private fun checkedState(node: AccessibilityNodeInfo): String {
        if (node.isCheckable) return checked(node)
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            if (child.isCheckable) return checked(child)
        }
        return "n/a"
    }

    private fun checked(node: AccessibilityNodeInfo): String =
        (node.checked == AccessibilityNodeInfo.CHECKED_STATE_TRUE).toString()

    /**
     * Pause (docs/quire-design.md §3.4): the platform's own block. While blocked it drops agent input and lets the
     * person use the interactive mirror.
     */
    fun pause() {
        val s = session ?: return report("pause refused by Quire: no session")
        try {
            s.notifyBlocked()
            report("pause: notifyBlocked")
        } catch (e: RuntimeException) {
            report("pause failed: ${e.javaClass.simpleName}: ${e.message}")
        }
    }

    fun resume() {
        val s = session ?: return report("resume refused by Quire: no session")
        try {
            s.requestUnblock()
            report("resume: requestUnblock")
        } catch (e: RuntimeException) {
            report("resume failed: ${e.javaClass.simpleName}: ${e.message}")
        }
    }

    /** True when the last [find] failed because the platform returned no accessibility windows at all. */
    var windowsUnavailable = false
        private set

    /** The on-screen bounds of the first node whose text contains [text], and of its clickable ancestor. */
    fun find(text: String): Rect? {
        val s = session ?: return null
        // Prefer a node whose text is exactly [text] ("Dark theme" the row, not "Dark theme, font size" a summary).
        val windows = try {
            s.accessibilityWindows.also { windowsUnavailable = false }
        } catch (e: RuntimeException) {
            windowsUnavailable = true
            // AOSP: ProxyAccessibilityServiceConnection.getWindows() dereferences a null window list, so for a moment
            // after the session is unblocked the query throws from system_server. The caller retries.
            report("windows unavailable: ${e.javaClass.simpleName}: ${e.message}")
            return null
        }
        val matches = windows.flatMap { window ->
            window.root?.findAccessibilityNodeInfosByText(text)?.filter { it.isVisibleToUser }.orEmpty()
        }
        val node = matches.firstOrNull { it.text?.toString()?.equals(text, ignoreCase = true) == true }
            ?: matches.firstOrNull() ?: return null
        val target = clickableAncestor(node) ?: node
        return Rect().also { target.getBoundsInScreen(it) }
    }

    /** Moves the session's apps to the person's display; the platform then closes the session. */
    fun handOver() {
        val s = session ?: return report("hand over refused by Quire: no session")
        try {
            s.handOverApplications()
            report("hand over: done")
        } catch (e: RuntimeException) {
            report("hand over failed: ${e.javaClass.simpleName}: ${e.message}")
        }
    }

    fun close() {
        val s = session ?: return report("close refused by Quire: no session")
        s.close()
        report("close: requested")
    }

    private fun notification(targets: List<String>): Notification {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, context.getString(R.string.channel_automation),
                NotificationManager.IMPORTANCE_DEFAULT).apply { setSound(null, null) }
        )
        val names = targets.joinToString(", ") { label(it) }
        return Notification.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_quire)
            .setContentTitle(context.getString(R.string.notification_using, names))
            .setContentText(context.getString(R.string.notification_using_text))
            .setContentIntent(PendingIntent.getActivity(context, 0,
                Intent(context, ControlActivity::class.java), PendingIntent.FLAG_IMMUTABLE))
            // A computer-control notification must be promotable: ongoing, titled, requested as promoted.
            .setOngoing(true)
            .setRequestPromotedOngoing(true)
            .build()
    }

    private fun label(packageName: String): String =
        try {
            val pm = context.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(packageName, 0)).toString()
        } catch (e: PackageManager.NameNotFoundException) {
            packageName
        }

    private fun toBitmap(image: Image): Bitmap {
        val plane = image.planes[0]
        val rowPixels = plane.rowStride / plane.pixelStride
        val padded = Bitmap.createBitmap(rowPixels, image.height, Bitmap.Config.ARGB_8888)
        padded.copyPixelsFromBuffer(plane.buffer)
        return if (rowPixels == image.width) padded else Bitmap.createBitmap(padded, 0, 0, image.width, image.height)
    }

    private fun save(bitmap: Bitmap): File {
        val dir = File(context.filesDir, "control").apply { mkdirs() }
        val file = File(dir, "${Invocations.stamp(System.currentTimeMillis())}-session.png")
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        Invocations.prune(dir, "png")
        return file
    }

    private fun report(line: String) {
        Log.i(Quire.TAG, "cc: $line")
        main.execute {
            status = line
            changed()
        }
    }

    private fun changed() {
        listeners.forEach { it.onChanged() }
    }

    companion object {
        private const val CHANNEL = "automation"
        private const val NOTIFICATION_ID = 216

        fun errorName(code: Int): String =
            when (code) {
                ComputerControlSession.ERROR_SESSION_LIMIT_REACHED -> "SESSION_LIMIT_REACHED"
                ComputerControlSession.ERROR_DEVICE_LOCKED -> "DEVICE_LOCKED"
                ComputerControlSession.ERROR_PERMISSION_DENIED -> "PERMISSION_DENIED"
                else -> "UNKNOWN"
            }

        fun blockReasonName(reason: Int): String =
            when (reason) {
                ComputerControlSession.BLOCK_REASON_SECURE_CONTENT -> "SECURE_CONTENT"
                ComputerControlSession.BLOCK_REASON_DISALLOWED_ACTIVITY_LAUNCH -> "DISALLOWED_ACTIVITY_LAUNCH"
                ComputerControlSession.BLOCK_REASON_CALLER_INITIATED -> "CALLER_INITIATED"
                ComputerControlSession.BLOCK_REASON_AUTHENTICATION_PROMPT_REQUESTED -> "AUTHENTICATION_PROMPT"
                else -> "UNKNOWN"
            }

        fun closeReasonName(reason: Int): String =
            when (reason) {
                ComputerControlSession.CLOSE_REASON_CALLER_INITIATED -> "CALLER_INITIATED"
                ComputerControlSession.CLOSE_REASON_USER_INITIATED -> "USER_INITIATED"
                ComputerControlSession.CLOSE_REASON_SESSION_TIMED_OUT -> "TIMED_OUT"
                ComputerControlSession.CLOSE_REASON_SESSION_EMPTY -> "SESSION_EMPTY"
                else -> "UNKNOWN"
            }
    }
}
