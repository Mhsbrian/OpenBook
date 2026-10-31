// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.note

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Log
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.QuireApplication
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong

/**
 * "Save as a file" (docs/quire-design.md §3.2 Long output and Code) through the Storage Access Framework: the person
 * picks where in DocumentsUI's own picker, so Quire needs no storage permission and writes only the file they chose.
 * The note is a window, not an activity, so this invisible activity carries the picker's result.
 */
object Saver {
    class Job(val name: String, val mime: String, val text: String, val done: (Result<String>) -> Unit)

    private val jobs = ConcurrentHashMap<Long, Job>()
    private val ids = AtomicLong(1)

    fun save(context: Context, job: Job) {
        val id = ids.getAndIncrement()
        jobs[id] = job
        context.startActivity(Intent(context, SaveActivity::class.java)
            .putExtra(EXTRA_JOB, id)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION))
    }

    internal fun take(id: Long): Job? = jobs.remove(id)

    internal const val EXTRA_JOB = "dev.openbook.quire.extra.SAVE_JOB"
}

class SaveActivity : Activity() {
    private var job: Saver.Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        job = Saver.take(intent.getLongExtra(Saver.EXTRA_JOB, -1))
        val j = job
        if (j == null) {
            finish()
            return
        }
        if (savedInstanceState == null) {
            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType(j.mime)
                .putExtra(Intent.EXTRA_TITLE, j.name), REQUEST)
        }
    }

    @Deprecated("Activity result API; this activity exists only to carry the picker's result")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val j = job ?: return finish()
        val uri = data?.data
        if (resultCode != RESULT_OK || uri == null) {
            Log.i(TAG, "note: save cancelled")
            j.done(Result.failure(CancelledException()))
            finish()
            return
        }
        val app = application as QuireApplication
        val resolver = contentResolver
        app.io.execute {
            val r = runCatching {
                resolver.openOutputStream(uri, "wt")!!.use { it.write(j.text.toByteArray(Charsets.UTF_8)) }
                displayName(uri) ?: j.name
            }
            r.onSuccess { Log.i(TAG, "note: saved ${j.text.length} chars as $it") }
            r.onFailure { Log.w(TAG, "note: save failed: ${it.javaClass.simpleName}") }
            mainExecutor.execute { j.done(r) }
        }
        finish()
    }

    private fun displayName(uri: Uri): String? =
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }

    class CancelledException : Exception("cancelled")

    companion object {
        private const val REQUEST = 1
    }
}
