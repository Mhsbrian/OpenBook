// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.engine

/**
 * What kind of Google release an update is, as the engine classifies it from the two build IDs' release
 * trains (year letter, product letter, quarter). Only the running train's own updates are taken by the
 * laptop itself; a new train may be a new Android version.
 */
enum class ReleaseKind(val wire: String, val held: Boolean) {
    MONTHLY("monthly", false),
    QUARTERLY("quarterly", true),
    UNKNOWN("unknown", true);

    companion object {
        fun of(value: String?) = entries.firstOrNull { it.wire == value } ?: UNKNOWN
    }
}

/** A release in Google's listing: the build number, its Android build ID and listing date. */
data class Release(val number: Long, val buildId: String, val date: String, val kind: ReleaseKind) {
    val identifier get() = if (buildId.isNotEmpty()) "${number}_$buildId" else number.toString()

    companion object {
        /** From the engine's release record ("number", "latest_id", "latest_date", "kind"). */
        fun of(record: EngineState): Release? {
            val number = record["number"]?.toLongOrNull() ?: record["latest"]?.substringBefore('_')?.toLongOrNull() ?: return null
            return Release(number, record["latest_id"].orEmpty(), record["latest_date"].orEmpty(), ReleaseKind.of(record["kind"]))
        }
    }
}

/** One of the engine's key=value files: `state` (its last run) or `release` (its last successful check). */
data class EngineState(val values: Map<String, String>) {
    operator fun get(key: String): String? = values[key]?.takeIf { it.isNotEmpty() }

    /** "result": never-run, up-to-date, update-available, downloading, verifying, downloaded, held, stopped, error:N. */
    val result: String get() = this["result"] ?: "never-run"
    val errorCode: Int? get() = result.removePrefix("error:").takeIf { result.startsWith("error:") }?.toIntOrNull()
    val bytes: Long? get() = this["bytes"]?.toLongOrNull()?.takeIf { it > 0 }
    val build: String? get() = this["build"]
    val detail: String? get() = this["detail"]

    companion object {
        val EMPTY = EngineState(emptyMap())

        fun parse(text: String): EngineState = EngineState(
            text.lineSequence().mapNotNull { line ->
                val i = line.indexOf('=')
                if (i <= 0) null else line.substring(0, i) to line.substring(i + 1)
            }.toMap(),
        )
    }
}

/** What is on disk for a release: a verified download (the engine's MD5 marker) or a partial one. */
data class DownloadFacts(val verified: Boolean = false, val partBytes: Long = 0) {
    companion object { val NONE = DownloadFacts() }
}
