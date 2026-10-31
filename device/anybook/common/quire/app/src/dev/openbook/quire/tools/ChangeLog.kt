// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.content.Context
import android.util.Log
import dev.openbook.quire.Quire.TAG
import org.json.JSONArray
import org.json.JSONObject

/**
 * Every setting Quire changed, with the value before, so each can be undone (docs/quire.md §4: "keeps the audit log of
 * every change it made, with undo"). Kept for [KEEP_MS] in Quire's private storage; the note shows the change with its
 * undo, and agents can undo through `undo_change`.
 */
class ChangeLog private constructor(context: Context) {
    data class Entry(
        val id: Long,
        val key: String,
        val name: String,
        val where: String,
        val old: String,
        val new: String,
        val oldLabel: String,
        val newLabel: String,
        val at: Long,
        val undone: Boolean = false,
    ) {
        fun json(): JSONObject = JSONObject().put("id", id).put("key", key).put("name", name).put("where", where)
            .put("old", old).put("new", new).put("oldLabel", oldLabel).put("newLabel", newLabel).put("at", at)
            .put("undone", undone)

        companion object {
            fun of(o: JSONObject) = Entry(o.getLong("id"), o.getString("key"), o.optString("name"), o.optString("where"),
                o.getString("old"), o.getString("new"), o.optString("oldLabel"), o.optString("newLabel"),
                o.optLong("at"), o.optBoolean("undone"))
        }
    }

    private val prefs = context.applicationContext.getSharedPreferences("changes", Context.MODE_PRIVATE)
    private val entries = ArrayList<Entry>()

    init {
        val list = runCatching { JSONArray(prefs.getString(KEY, "[]")) }.getOrDefault(JSONArray())
        for (i in 0 until list.length()) runCatching { entries += Entry.of(list.getJSONObject(i)) }
        prune()
    }

    @Synchronized
    fun record(key: String, name: String, where: String, old: String, new: String, oldLabel: String,
        newLabel: String): Entry {
        val e = Entry(System.currentTimeMillis() * 10 + entries.size % 10, key, name, where, old, new, oldLabel,
            newLabel, System.currentTimeMillis())
        entries += e
        save()
        Log.i(TAG, "tools: change $key recorded (${entries.size} kept)")
        return e
    }

    @Synchronized
    fun find(id: Long): Entry? = entries.firstOrNull { it.id == id }

    /** The most recent change not yet undone, of [key] if given. */
    @Synchronized
    fun last(key: String? = null): Entry? = entries.lastOrNull { !it.undone && (key == null || it.key == key) }

    @Synchronized
    fun recent(): List<Entry> {
        prune()
        return entries.toList()
    }

    @Synchronized
    fun markUndone(id: Long) {
        val i = entries.indexOfFirst { it.id == id }
        if (i >= 0) {
            entries[i] = entries[i].copy(undone = true)
            save()
        }
    }

    private fun prune() {
        val cutoff = System.currentTimeMillis() - KEEP_MS
        entries.removeAll { it.at < cutoff }
        while (entries.size > MAX) entries.removeAt(0)
    }

    private fun save() {
        prune()
        prefs.edit().putString(KEY, JSONArray(entries.map { it.json() }).toString()).apply()
    }

    companion object {
        private const val KEY = "entries"
        private const val MAX = 200
        const val KEEP_MS = 24 * 60 * 60 * 1000L

        @Volatile private var instance: ChangeLog? = null

        fun get(context: Context): ChangeLog =
            instance ?: synchronized(this) { instance ?: ChangeLog(context).also { instance = it } }
    }
}
