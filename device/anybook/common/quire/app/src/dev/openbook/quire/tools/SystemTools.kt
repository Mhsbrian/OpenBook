// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.app.Notification
import android.app.NotificationManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.media.AudioManager
import android.media.MediaMetadata
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.os.SystemClock
import android.service.notification.NotificationListenerService
import android.util.Log
import android.view.KeyEvent
import dev.openbook.quire.Quire.TAG
import org.json.JSONObject

/**
 * Quire's notification listener: how the `notifications_list` and `notification_dismiss` tools see and clear the
 * person's notifications, through the platform's own API for it. Access shows in Settings › Notifications › Device &
 * app notifications, and the person can turn it off; Quire then can't read them.
 */
class QuireNotificationListener : NotificationListenerService() {
    override fun onListenerConnected() {
        instance = this
        Log.i(TAG, "tools: notification listener connected")
    }

    override fun onListenerDisconnected() {
        if (instance === this) instance = null
    }

    companion object {
        @Volatile var instance: QuireNotificationListener? = null
            private set

        fun component(c: Context) = ComponentName(c, QuireNotificationListener::class.java)

        /**
         * The listener, connected. OpenBook's image grants Quire notification access by default
         * (config_defaultListenerAccessPackages); an install that predates it is granted once here, as that default
         * would have. A person who turned it off since is respected: Quire never grants it again.
         */
        fun connected(c: Context): QuireNotificationListener {
            instance?.let { return it }
            val nm = c.getSystemService(NotificationManager::class.java)
            val prefs = c.getSharedPreferences("tools", Context.MODE_PRIVATE)
            if (!nm.isNotificationListenerAccessGranted(component(c))) {
                if (prefs.getBoolean("listener_granted", false)) {
                    throw ToolError("The person turned off Quire's notification access (Settings › Notifications › " +
                        "Device & app notifications), so Quire can't see notifications.")
                }
                nm.setNotificationListenerAccessGranted(component(c), true, false)
                prefs.edit().putBoolean("listener_granted", true).apply()
                Log.i(TAG, "tools: granted Quire's notification listener its default access")
            } else {
                prefs.edit().putBoolean("listener_granted", true).apply()
            }
            val deadline = SystemClock.elapsedRealtime() + 5000
            while (SystemClock.elapsedRealtime() < deadline) {
                instance?.let { return it }
                requestRebind(component(c))
                SystemClock.sleep(250)
            }
            throw ToolError("Quire's notification access isn't connected yet; try again in a moment.")
        }
    }
}

object SystemTools {
    private val clipboardRead = object : Tool("clipboard_read", Tier.OBSERVE, "read") {
        override val description = "Read the text on the laptop's clipboard (what the person copied)."
        override val schema = Schema.obj()
        override fun title(c: Context, args: JSONObject) = "Reading the clipboard"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val clip = c.getSystemService(ClipboardManager::class.java).primaryClip
                ?: return ToolResult.text("The clipboard is empty.")
            if (clip.description.extras?.getBoolean("android.content.extra.IS_SENSITIVE") == true) {
                throw ToolError("The clipboard holds something marked sensitive (a password, for example); Quire doesn't read it.")
            }
            val text = (0 until clip.itemCount).mapNotNull { clip.getItemAt(it).coerceToText(c)?.toString() }
                .joinToString("\n").ifEmpty { return ToolResult.text("The clipboard holds no text.") }
            return ToolResult.text(text.take(50_000))
        }
    }

    private val clipboardWrite = object : Tool("clipboard_write", Tier.ACT, "edit") {
        override val description = "Put text on the laptop's clipboard, for the person to paste."
        override val schema = Schema.obj("text" to Schema.str("The text."), required = listOf("text"))
        override fun title(c: Context, args: JSONObject) = "Copying to the clipboard"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            c.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("Quire", args.optString("text")))
            return ToolResult.text("Copied to the clipboard.")
        }
    }

    private val notificationsList = object : Tool("notifications_list", Tier.OBSERVE, "read") {
        override val description = "List the notifications on the laptop: app, title and text, and a key for " +
            "notification_dismiss. Notifications an app marked secret are left out."
        override val schema = Schema.obj()
        override fun title(c: Context, args: JSONObject) = "Reading notifications"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val l = QuireNotificationListener.connected(c)
            val list = l.activeNotifications.orEmpty().filter {
                it.notification.visibility != Notification.VISIBILITY_SECRET &&
                    it.notification.flags and Notification.FLAG_GROUP_SUMMARY == 0 && it.packageName != c.packageName
            }
            if (list.isEmpty()) return ToolResult.text("There are no notifications.")
            return ToolResult.text(list.sortedByDescending { it.postTime }.joinToString("\n") { sbn ->
                val e = sbn.notification.extras
                val title = e.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
                val text = (e.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: e.getCharSequence(Notification.EXTRA_TEXT))
                    ?.toString().orEmpty()
                "- ${Apps.label(c, sbn.packageName)}: $title" + (if (text.isNotEmpty()) " — ${text.take(300)}" else "") +
                    (if (!sbn.isClearable) " (can't be dismissed)" else "") + " [key: ${sbn.key}]"
            })
        }
    }

    private val notificationDismiss = object : Tool("notification_dismiss", Tier.ACT, "app") {
        override val description = "Dismiss notifications, as swiping them away does: one by its key, every one of an " +
            "app, or all that can be dismissed."
        override val schema = Schema.obj("key" to Schema.str("The notification's key from notifications_list (optional)."),
            "app" to Schema.str("Dismiss all of this app's notifications (optional)."),
            "all" to Schema.bool("Dismiss every notification that can be dismissed (optional)."))
        override fun title(c: Context, args: JSONObject) = "Dismissing notifications"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val l = QuireNotificationListener.connected(c)
            val active = l.activeNotifications.orEmpty().filter { it.isClearable }
            val pick = when {
                args.str("key") != null -> active.filter { it.key == args.req("key") }
                args.str("app") != null -> {
                    val pkg = Apps.find(c, args.req("app")).pkg
                    active.filter { it.packageName == pkg }
                }
                args.optBoolean("all") -> active
                else -> throw ToolError("Say which: a key, an app, or all.")
            }
            if (pick.isEmpty()) return ToolResult.text("No notification matched (or it can't be dismissed).")
            l.cancelNotifications(pick.map { it.key }.toTypedArray())
            return ToolResult.text("Dismissed ${pick.size} notification" + if (pick.size == 1) "." else "s.")
        }
    }

    private val ACTIONS = mapOf("play_pause" to KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, "play" to KeyEvent.KEYCODE_MEDIA_PLAY,
        "pause" to KeyEvent.KEYCODE_MEDIA_PAUSE, "next" to KeyEvent.KEYCODE_MEDIA_NEXT,
        "previous" to KeyEvent.KEYCODE_MEDIA_PREVIOUS, "stop" to KeyEvent.KEYCODE_MEDIA_STOP)

    private val mediaControl = object : Tool("media_control", Tier.ACT, "app") {
        override val description = "Control what is playing (music, video): play, pause, next, previous, stop; " +
            "\"status\" only says what is playing."
        override val schema = Schema.obj("action" to Schema.str("What to do.", ACTIONS.keys.toList() + "status"),
            required = listOf("action"))
        override fun title(c: Context, args: JSONObject) = when (args.optString("action")) {
            "status" -> "Checking what's playing"
            else -> "Media: ${args.optString("action").replace('_', '/')}"
        }
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val action = args.req("action").lowercase()
            if (action != "status") {
                val code = ACTIONS[action] ?: throw ToolError("Actions: ${ACTIONS.keys.joinToString(", ")}, status.")
                val am = c.getSystemService(AudioManager::class.java)
                am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, code))
                am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_UP, code))
                SystemClock.sleep(400)
            }
            return ToolResult.text((if (action == "status") "" else "Sent $action. ") + playing(c))
        }
    }

    private fun playing(c: Context): String {
        val sessions = runCatching {
            c.getSystemService(MediaSessionManager::class.java).getActiveSessions(null)
        }.getOrDefault(emptyList())
        if (sessions.isEmpty()) return "Nothing is playing."
        return sessions.take(3).joinToString(" ") { s ->
            val m = s.metadata
            val what = listOfNotNull(m?.getString(MediaMetadata.METADATA_KEY_TITLE),
                m?.getString(MediaMetadata.METADATA_KEY_ARTIST)).joinToString(" — ").ifEmpty { "something" }
            val state = when (s.playbackState?.state) {
                PlaybackState.STATE_PLAYING -> "playing"
                PlaybackState.STATE_PAUSED -> "paused"
                PlaybackState.STATE_STOPPED -> "stopped"
                else -> "idle"
            }
            "${Apps.label(c, s.packageName)}: $what ($state)."
        }
    }

    val all: List<Tool> = listOf(clipboardRead, clipboardWrite, notificationsList, notificationDismiss, mediaControl)
}
