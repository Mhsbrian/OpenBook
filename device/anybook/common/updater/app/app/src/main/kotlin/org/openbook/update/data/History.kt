// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** One line of the update history. The text is rendered from [type] when shown (localizable). */
data class HistoryEntry(val timeMillis: Long, val type: Type, val build: String = "", val detail: String = "") {
    enum class Type { FOUND, HELD, DOWNLOADED, VERIFICATION_FAILED, INSTALLED, WENT_BACK, SYSTEM_CHANGED, RESTART_REQUESTED }
}

/** The update history: newest first, at most [limit] entries, in the app's private files (JSON). */
class History(private val file: File, private val limit: Int = 200) {
    private val _entries = MutableStateFlow(load())
    val entries: StateFlow<List<HistoryEntry>> = _entries.asStateFlow()

    /** Adds an entry; a history that cannot be saved (storage full) never stops the update work. */
    @Synchronized
    fun add(entry: HistoryEntry) {
        val updated = (listOf(entry) + _entries.value).take(limit)
        _entries.value = updated
        runCatching {
            val tmp = File(file.path + ".tmp")
            tmp.writeText(encode(updated))
            check(tmp.renameTo(file))
        }.onFailure { android.util.Log.w("OpenBookUpdate", "cannot save the update history: $it") }
    }

    private fun load(): List<HistoryEntry> = runCatching { decode(file.readText()) }.getOrDefault(emptyList())

    companion object {
        fun encode(entries: List<HistoryEntry>): String = JSONArray().apply {
            entries.forEach { e ->
                put(JSONObject().put("time", e.timeMillis).put("type", e.type.name).put("build", e.build).put("detail", e.detail))
            }
        }.toString()

        fun decode(text: String): List<HistoryEntry> {
            val array = JSONArray(text)
            return (0 until array.length()).mapNotNull { i ->
                val o = array.getJSONObject(i)
                val type = runCatching { HistoryEntry.Type.valueOf(o.getString("type")) }.getOrNull() ?: return@mapNotNull null
                HistoryEntry(o.getLong("time"), type, o.optString("build"), o.optString("detail"))
            }
        }
    }
}
