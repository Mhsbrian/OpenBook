// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Environment
import android.provider.DocumentsContract
import android.text.format.Formatter
import android.webkit.MimeTypeMap
import dev.openbook.quire.note.Change
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import org.json.JSONObject

/**
 * The person's files: the laptop's shared storage (Download, Documents, Pictures…), through Quire's all-files access.
 * The never tier is enforced here: nothing outside shared storage, and nothing in `Android/`, where other apps keep
 * their own files (MediaProvider refuses Android/data and Android/obb too). Deleting, and replacing a file, ask first.
 */
object Files {
    val root: File
        get() = Environment.getExternalStorageDirectory()

    private val ALIASES = mapOf("downloads" to "Download", "download" to "Download", "documents" to "Documents",
        "pictures" to "Pictures", "photos" to "Pictures", "music" to "Music", "movies" to "Movies", "videos" to "Movies",
        "camera" to "DCIM/Camera", "screenshots" to "Pictures/Screenshots")

    /** [path] in shared storage: relative to its top, or absolute as Android or the Linux environment names it. */
    fun resolve(path: String): File {
        var p = path.trim().replace('\\', '/')
        for (prefix in listOf("/storage/emulated/0", "/sdcard", "/mnt/shared/0", "/mnt/shared", "~", "/")) {
            if (p == prefix) {
                p = ""
                break
            }
            if (p.startsWith("$prefix/")) {
                p = p.removePrefix("$prefix/")
                break
            }
        }
        val first = p.substringBefore('/')
        ALIASES[first.lowercase()]?.let { p = it + p.removePrefix(first) }
        val rootReal = root.canonicalFile
        val f = File(rootReal, p).canonicalFile
        if (f != rootReal && !f.path.startsWith(rootReal.path + "/")) {
            throw ToolError("Quire's file tools reach only the person's files in shared storage.")
        }
        val rel = f.path.removePrefix(rootReal.path).trimStart('/')
        if (rel == "Android" || rel.startsWith("Android/")) {
            throw ToolError("Android/ holds other apps' own files, which Quire never touches.")
        }
        return f
    }

    fun rel(f: File): String = f.path.removePrefix(root.canonicalPath).trimStart('/').ifEmpty { "(shared storage)" }

    fun mime(f: File): String = MimeTypeMap.getSingleton()
        .getMimeTypeFromExtension(f.extension.lowercase()) ?: "application/octet-stream"

    fun describe(c: Context, f: File): String {
        val date = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.ROOT).format(Date(f.lastModified()))
        return if (f.isDirectory) "${f.name}/ (folder, ${f.list()?.size ?: 0} items, $date)"
        else "${f.name} (${Formatter.formatShortFileSize(c, f.length())}, $date)"
    }

    /** A document URI of the external storage provider, which Files opens and Quire can grant. */
    fun documentUri(f: File) = DocumentsContract.buildDocumentUri("com.android.externalstorage.documents",
        "primary:" + f.path.removePrefix(root.canonicalPath).trimStart('/'))

    fun exists(f: File, what: String = "") {
        if (!f.exists()) throw ToolError("There is no ${what.ifEmpty { "file or folder" }} ${rel(f)}.")
    }

    fun count(f: File): Int = if (f.isDirectory) (f.listFiles()?.sumOf { count(it) } ?: 0) + 1 else 1
}

object FileTools {
    private val TEXT = setOf("txt", "md", "csv", "json", "xml", "html", "htm", "log", "ini", "yaml", "yml", "kt", "java",
        "py", "js", "ts", "sh", "c", "h", "cpp", "go", "rs", "css", "tsv", "srt", "conf", "toml")
    private const val MAX_READ = 256 * 1024
    private const val MAX_WRITE = 5 * 1024 * 1024

    private val listFiles = object : Tool("list_files", Tier.OBSERVE, "read") {
        override val description = "List a folder of the person's files, newest first. Folders: Download, Documents, " +
            "Pictures, DCIM, Music, Movies; an empty path lists the top."
        override val schema = Schema.obj("path" to Schema.str("The folder, e.g. \"Download\" (optional)."),
            "hidden" to Schema.bool("Include hidden files (optional)."))
        override fun title(c: Context, args: JSONObject) = "Looking in ${args.str("path") ?: "your files"}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val dir = Files.resolve(args.optString("path"))
            Files.exists(dir, "folder")
            if (!dir.isDirectory) return ToolResult.text(Files.describe(c, dir))
            val entries = (dir.listFiles() ?: emptyArray())
                .filter { args.optBoolean("hidden") || !it.name.startsWith(".") }
                .filter { Files.rel(it) != "Android" }
                .sortedByDescending { it.lastModified() }
            if (entries.isEmpty()) return ToolResult.text("${Files.rel(dir)} is empty.")
            val shown = entries.take(200)
            return ToolResult.text("${Files.rel(dir)}, ${entries.size} items, newest first:\n" +
                shown.joinToString("\n") { Files.describe(c, it) } +
                if (entries.size > shown.size) "\n… and ${entries.size - shown.size} more" else "")
        }
    }

    private val searchFiles = object : Tool("search_files", Tier.OBSERVE, "search") {
        override val description = "Find the person's files whose names contain some text, in all of shared storage " +
            "or in one folder."
        override val schema = Schema.obj("query" to Schema.str("Part of the name, e.g. \"invoice\" or \".pdf\"."),
            "path" to Schema.str("Search only in this folder (optional)."), required = listOf("query"))
        override fun title(c: Context, args: JSONObject) = "Searching for “${args.optString("query")}”"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val q = args.req("query").lowercase()
            val start = Files.resolve(args.optString("path"))
            val found = ArrayList<File>()
            fun walk(d: File, depth: Int) {
                if (found.size >= 100 || depth > 8 || note.cancelled) return
                for (f in d.listFiles() ?: return) {
                    if (f.name.startsWith(".") || Files.rel(f) == "Android") continue
                    if (f.name.lowercase().contains(q)) found += f
                    if (f.isDirectory) walk(f, depth + 1)
                }
            }
            walk(start, 0)
            if (found.isEmpty()) return ToolResult.text("No file name contains \"$q\".")
            return ToolResult.text(found.sortedByDescending { it.lastModified() }
                .joinToString("\n") { Files.rel(it) + " — " + Files.describe(c, it).substringAfter(" (").let { "($it" } })
        }
    }

    private val readFile = object : Tool("read_file", Tier.OBSERVE, "read") {
        override val description = "Read one of the person's files: the text of a text file, or a picture. Other " +
            "files are described; open_file shows them to the person."
        override val schema = Schema.obj("path" to Schema.str("The file, e.g. \"Download/notes.txt\"."),
            required = listOf("path"))
        override fun title(c: Context, args: JSONObject) = "Reading ${File(args.optString("path")).name}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val f = Files.resolve(args.req("path"))
            Files.exists(f, "file")
            if (f.isDirectory) throw ToolError("${Files.rel(f)} is a folder; use list_files.")
            val mime = Files.mime(f)
            return when {
                mime.startsWith("image/") -> {
                    val opts = BitmapFactory.Options().apply { inSampleSize = 1 }
                    val b = BitmapFactory.decodeFile(f.path, opts) ?: throw ToolError("${f.name} can't be read as a picture.")
                    ToolResult.image("${Files.rel(f)}, ${b.width}×${b.height}:", b)
                }
                f.extension.lowercase() in TEXT || mime.startsWith("text/") -> {
                    if (f.length() > MAX_READ) {
                        ToolResult.text("${Files.rel(f)} (first ${MAX_READ / 1024} KB of ${f.length() / 1024} KB):\n" +
                            f.inputStream().use { String(it.readNBytes(MAX_READ)) })
                    } else {
                        ToolResult.text(f.readText())
                    }
                }
                else -> ToolResult.text("${Files.describe(c, f)}, $mime. Its content isn't text; open_file shows it.")
            }
        }
    }

    private val writeFile = object : Tool("write_file", Tier.ACT, "edit") {
        override val description = "Write a text file in the person's files. Replacing a file that exists asks the " +
            "person first (pass overwrite: true)."
        override val schema = Schema.obj("path" to Schema.str("The file, e.g. \"Documents/list.md\"."),
            "text" to Schema.str("The file's whole text."),
            "overwrite" to Schema.bool("Replace the file if it exists (asks the person)."), required = listOf("path", "text"))
        override fun title(c: Context, args: JSONObject) = "Writing ${File(args.optString("path")).name}"
        override fun ask(c: Context, args: JSONObject): Ask? {
            val f = Files.resolve(args.req("path"))
            if (!f.exists()) return null
            if (f.isDirectory) throw ToolError("${Files.rel(f)} is a folder.")
            if (!args.optBoolean("overwrite")) throw ToolError("${Files.rel(f)} exists. Pass overwrite: true to " +
                "replace it (the person is asked), or choose another name.")
            return Ask("Replace ${f.name}?", listOf(Change(f.name, Files.rel(f.parentFile!!), Files.describe(c, f)
                .substringAfter(" (").trimEnd(')'), "new text")), why = "Its current content will be lost.",
                verb = "Replace", keep = "Keep it")
        }
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val f = Files.resolve(args.req("path"))
            val text = args.optString("text")
            if (text.length > MAX_WRITE) throw ToolError("That is too long to write here.")
            f.parentFile?.mkdirs()
            f.writeText(text)
            return ToolResult.text("Wrote ${Files.rel(f)} (${f.length()} bytes).")
        }
    }

    private val makeFolder = object : Tool("make_folder", Tier.ACT, "edit") {
        override val description = "Make a folder in the person's files."
        override val schema = Schema.obj("path" to Schema.str("The new folder, e.g. \"Documents/Taxes\"."),
            required = listOf("path"))
        override fun title(c: Context, args: JSONObject) = "Making ${File(args.optString("path")).name}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val f = Files.resolve(args.req("path"))
            if (f.exists()) return ToolResult.text("${Files.rel(f)} already exists.")
            if (!f.mkdirs()) throw ToolError("${Files.rel(f)} couldn't be made.")
            return ToolResult.text("Made ${Files.rel(f)}.")
        }
    }

    /** [to], or [from]'s name inside [to] when [to] is a folder. A target that exists is refused, never replaced. */
    private fun target(from: File, to: String): File {
        val t = Files.resolve(to)
        val out = if (t.isDirectory) File(t, from.name).canonicalFile else t
        Files.resolve(out.path)
        if (out.exists()) throw ToolError("${Files.rel(out)} already exists; choose another name.")
        return out
    }

    private val copyFile = object : Tool("copy_file", Tier.ACT, "edit") {
        override val description = "Copy a file or folder of the person's files to another name or folder."
        override val schema = Schema.obj("from" to Schema.str("What to copy."),
            "to" to Schema.str("The new name, or a folder to copy into."), required = listOf("from", "to"))
        override fun title(c: Context, args: JSONObject) = "Copying ${File(args.optString("from")).name}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val from = Files.resolve(args.req("from"))
            Files.exists(from)
            val to = target(from, args.req("to"))
            if (to.path.startsWith(from.path + "/")) throw ToolError("A folder can't be copied into itself.")
            from.copyRecursively(to, overwrite = false)
            return ToolResult.text("Copied ${Files.rel(from)} to ${Files.rel(to)}.")
        }
    }

    private val moveFile = object : Tool("move_file", Tier.ACT, "move") {
        override val description = "Move or rename a file or folder of the person's files."
        override val schema = Schema.obj("from" to Schema.str("What to move or rename."),
            "to" to Schema.str("The new name, or a folder to move into."), required = listOf("from", "to"))
        override fun title(c: Context, args: JSONObject) = "Moving ${File(args.optString("from")).name}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val from = Files.resolve(args.req("from"))
            Files.exists(from)
            if (from == Files.root.canonicalFile) throw ToolError("That is the top of shared storage.")
            val to = target(from, args.req("to"))
            if (!from.renameTo(to)) {
                from.copyRecursively(to, overwrite = false)
                from.deleteRecursively()
            }
            return ToolResult.text("Moved ${Files.rel(from)} to ${Files.rel(to)}.")
        }
    }

    private val deleteFile = object : Tool("delete_file", Tier.CONFIRM, "delete") {
        override val description = "Delete a file or folder of the person's files. The person is asked first, in " +
            "the note."
        override val schema = Schema.obj("path" to Schema.str("What to delete, e.g. \"Download/old.zip\"."),
            required = listOf("path"))
        override fun title(c: Context, args: JSONObject) = "Deleting ${File(args.optString("path")).name}"
        override fun ask(c: Context, args: JSONObject): Ask {
            val f = Files.resolve(args.req("path"))
            Files.exists(f)
            if (f == Files.root.canonicalFile) throw ToolError("That is the person's whole shared storage.")
            val n = Files.count(f) - 1
            val what = if (f.isDirectory) "folder with $n items" else Files.describe(c, f).substringAfter(" (").trimEnd(')')
                .replace(", ", " · ")
            return Ask("Delete ${f.name}?", listOf(Change(f.name, "${Files.rel(f.parentFile!!)} · $what", "", "")),
                why = "This can't be undone: Quire can't bring deleted files back.", verb = "Delete", keep = "Keep it")
        }
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val f = Files.resolve(args.req("path"))
            Files.exists(f)
            if (!f.deleteRecursively()) throw ToolError("${Files.rel(f)} couldn't be deleted completely.")
            return ToolResult.text("Deleted ${Files.rel(f)}.")
        }
    }

    private val openFile = object : Tool("open_file", Tier.ACT, "app") {
        override val description = "Show one of the person's files on the laptop's screen, in the app for it, or in " +
            "the app they name."
        override val schema = Schema.obj("path" to Schema.str("The file."),
            "app" to Schema.str("The app to open it with (optional)."), required = listOf("path"))
        override fun title(c: Context, args: JSONObject) = "Opening ${File(args.optString("path")).name}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val f = Files.resolve(args.req("path"))
            Files.exists(f, "file")
            if (f.isDirectory) return showFolder(c, f, note)
            val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Files.documentUri(f), Files.mime(f))
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            args.str("app")?.let { intent.setPackage(Apps.find(c, it).pkg) }
            Apps.start(c, intent)
            return ToolResult.text("Opened ${Files.rel(f)}.")
        }
    }

    private val openFolder = object : Tool("open_folder", Tier.ACT, "app") {
        override val description = "Show a folder of the person's files in the Files app, e.g. \"Download\" for " +
            "their Downloads."
        override val schema = Schema.obj("path" to Schema.str("The folder, e.g. \"Download\"."), required = listOf("path"))
        override fun title(c: Context, args: JSONObject) = "Opening ${args.optString("path")} in Files"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val f = Files.resolve(args.req("path"))
            Files.exists(f, "folder")
            if (!f.isDirectory) throw ToolError("${Files.rel(f)} is a file; use open_file.")
            return showFolder(c, f, note)
        }
    }

    private fun showFolder(c: Context, f: File, note: CallNote): ToolResult {
        val rel = Files.rel(f)
        if (rel == Environment.DIRECTORY_DOWNLOADS) {
            // Files' own Downloads view, as the Downloads notification opens it.
            Apps.start(c, Intent(DownloadManager.ACTION_VIEW_DOWNLOADS))
            note.retitle("Opened Downloads in Files")
            return ToolResult.text("Files shows Downloads.")
        }
        Apps.start(c, Intent(Intent.ACTION_VIEW).setDataAndType(Files.documentUri(f),
            DocumentsContract.Document.MIME_TYPE_DIR))
        note.retitle("Opened $rel in Files")
        return ToolResult.text("Files shows $rel.")
    }

    val all: List<Tool> = listOf(listFiles, searchFiles, readFile, openFile, openFolder, writeFile, makeFolder, copyFile,
        moveFile, deleteFile)
}
