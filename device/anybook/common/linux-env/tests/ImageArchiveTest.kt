// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// Host tests for the Terminal app's OpenBook install (aosp/patches/packages/modules/Virtualization/0003,
// docs/quire-setup.md §4.1 and §8), on a non-debuggable build: which image, the staged and resumed download, the
// whole-file check before extraction, the extraction's refusals, and the swap that keeps an existing install.
// Run by image-archive-test.sh.

package openbook.test

import com.android.virtualization.terminal.openbook.FetchResponse
import com.android.virtualization.terminal.openbook.Fetcher
import com.android.virtualization.terminal.openbook.HttpFetcher
import com.android.virtualization.terminal.openbook.ImageManifest
import com.android.virtualization.terminal.openbook.ImageRefusedException
import com.android.virtualization.terminal.openbook.ImageSource
import com.android.virtualization.terminal.openbook.InstallCommit
import com.android.virtualization.terminal.openbook.OpenBookInstall
import com.android.virtualization.terminal.openbook.SafeExtractor
import com.android.virtualization.terminal.openbook.StagedDownload
import com.sun.net.httpserver.HttpServer
import java.io.ByteArrayOutputStream
import java.io.FileNotFoundException
import java.io.IOException
import java.net.InetSocketAddress
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.concurrent.CancellationException
import org.apache.commons.compress.archivers.tar.TarArchiveEntry
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream
import org.apache.commons.compress.archivers.tar.TarConstants
import org.apache.commons.compress.compressors.gzip.GzipCompressorOutputStream

private var failures = 0
private var passes = 0

private fun check(name: String, ok: Boolean, detail: () -> String = { "" }) {
    if (ok) {
        passes++
        println("ok   $name")
    } else {
        failures++
        println("FAIL $name ${detail()}")
    }
}

private inline fun <reified T : Throwable> throws(block: () -> Unit): T? =
    try {
        block()
        null
    } catch (e: Throwable) {
        e as? T ?: throw e
    }

private fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

private fun tmp(): Path = Files.createTempDirectory("obimg")

private const val MARKER = "completed"

/** A tar.gz with [entries]: (entry, content). */
private fun targz(vararg entries: Pair<TarArchiveEntry, ByteArray>): ByteArray {
    val bytes = ByteArrayOutputStream()
    TarArchiveOutputStream(GzipCompressorOutputStream(bytes)).use { t ->
        t.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX)
        for ((e, data) in entries) {
            if (e.isFile && !e.isSymbolicLink && !e.isLink && !e.isCharacterDevice && !e.isBlockDevice && !e.isFIFO &&
                !e.isDirectory) {
                e.size = data.size.toLong()
            }
            t.putArchiveEntry(e)
            if (e.size > 0) t.write(data)
            t.closeArchiveEntry()
        }
    }
    return bytes.toByteArray()
}

private fun file(name: String, data: String) = TarArchiveEntry(name, true) to data.toByteArray()

private fun goodImage(rootPart: String = "new root") =
    targz(
        file("./build_id", "openbook_x86_64-1-Mon Oct 19 13:19:46 UTC 2026"),
        file("./root_part", rootPart),
        file("./vm_config.json", "{}"),
        file("./vmlinuz", "k"),
        file("./initrd.img", "i"),
    )

private fun manifest(url: String, data: ByteArray, installed: Long? = 10_000) =
    ImageManifest("test", url, sha(data), data.size.toLong(), installed)

/** A server for one file, with ranges, an ETag and If-Range, and a log of what it was asked. */
private class Server(@Volatile var data: ByteArray, @Volatile var etag: String = "\"a\"") : AutoCloseable {
    enum class Mode { RANGES, IGNORE_RANGES, NOT_FOUND, TOO_LONG }

    @Volatile var mode = Mode.RANGES
    val asked = mutableListOf<String>()
    private val http = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
    val url: String

    init {
        http.createContext("/images.tar.gz") { x ->
            val range = x.requestHeaders.getFirst("Range")
            val ifRange = x.requestHeaders.getFirst("If-Range")
            synchronized(asked) { asked += "range=${range ?: "-"} if-range=${ifRange ?: "-"}" }
            if (etag.isNotEmpty()) x.responseHeaders.add("ETag", etag)
            val d = data
            when {
                mode == Mode.NOT_FOUND -> {
                    x.sendResponseHeaders(404, -1)
                    x.close()
                    return@createContext
                }
                mode == Mode.TOO_LONG -> {
                    val more = d + ByteArray(100)
                    x.sendResponseHeaders(200, more.size.toLong())
                    x.responseBody.use { it.write(more) }
                    return@createContext
                }
            }
            val from = range?.removePrefix("bytes=")?.removeSuffix("-")?.toLongOrNull()
            if (mode == Mode.RANGES && from != null && (ifRange == null || ifRange == etag) && from < d.size) {
                x.responseHeaders.add("Content-Range", "bytes $from-${d.size - 1}/${d.size}")
                val part = d.copyOfRange(from.toInt(), d.size)
                x.sendResponseHeaders(206, part.size.toLong())
                x.responseBody.use { it.write(part) }
            } else {
                x.sendResponseHeaders(200, d.size.toLong())
                x.responseBody.use { it.write(d) }
            }
        }
        http.start()
        url = "http://127.0.0.1:${http.address.port}/images.tar.gz"
    }

    override fun close() = http.stop(0)
}

private val noProgress = StagedDownload.Listener { _, _, _ -> }

/** Stops a download once it has [n] bytes, as the process ending would. */
private fun stopAfter(n: Long): Pair<StagedDownload.Listener, () -> Boolean> {
    var got = 0L
    return StagedDownload.Listener { phase, bytes, _ -> if (phase == "download") got = bytes } to { got >= n }
}

private fun bigImage(): ByteArray {
    // Incompressible, so the archive is several MB and a download can be stopped half-way.
    val r = java.util.Random(7)
    val root = ByteArray(6 shl 20).also { r.nextBytes(it) }
    return targz(
        TarArchiveEntry("./build_id", true) to "b".toByteArray(),
        TarArchiveEntry("./root_part", true) to root,
        TarArchiveEntry("./vm_config.json", true) to "{}".toByteArray(),
    )
}

fun main() {
    sources()
    downloads()
    extraction()
    installs()
    println("$passes passed, $failures failed")
    if (failures > 0) System.exit(1)
}

private fun sources() {
    val d = tmp()
    val sdcard = d.resolve("sdcard/images.tar.gz").also { Files.createDirectories(it.parent); Files.write(it, byteArrayOf(1)) }
    val m = d.resolve("product/etc/openbook/linux-env.json")
    Files.createDirectories(m.parent)
    val ready = """{"version":"1","url":"https://example.invalid/i.tar.gz","sha256":"${"ab".repeat(32)}","size":10,"installed_size":20}"""
    Files.write(m, ready.toByteArray())
    check("user build: /sdcard is ignored, the manifest's image is used",
        ImageSource.select(false, sdcard, m) is ImageSource.OpenBook)
    check("debuggable build: /sdcard is used", ImageSource.select(true, sdcard, m) is ImageSource.SdCard)
    Files.write(m, """{"version":"1","url":null,"sha256":null,"size":null}""".toByteArray())
    val noUrl = ImageSource.select(false, sdcard, m)
    check("a manifest with no URL: no_image, never Google's", noUrl is ImageSource.NoImage) { "$noUrl" }
    for ((what, text) in listOf(
        "not JSON" to "{oops",
        "a bad hash" to """{"url":"https://x.invalid/a","sha256":"12","size":10}""",
        "no size" to """{"url":"https://x.invalid/a","sha256":"${"ab".repeat(32)}"}""",
        "another scheme" to """{"url":"file:///sdcard/a","sha256":"${"ab".repeat(32)}","size":10}""",
    )) {
        Files.write(m, text.toByteArray())
        check("an invalid manifest ($what): no_image", ImageSource.select(false, sdcard, m) is ImageSource.NoImage)
    }
    Files.delete(m)
    val missing = ImageSource.select(false, sdcard, m)
    check("an OpenBook build whose manifest is missing: no_image", missing is ImageSource.NoImage) { "$missing" }
    check("a build that isn't OpenBook's keeps AOSP's download",
        ImageSource.select(false, sdcard, d.resolve("none/etc/openbook/linux-env.json"),
            d.resolve("none/priv-app/OpenBookQuire")) is ImageSource.Upstream)
    val quire = Files.createDirectories(d.resolve("system_ext/priv-app/OpenBookQuire"))
    check("an OpenBook build (Quire installed) with no manifest folder at all: no_image, never Google's",
        ImageSource.select(false, sdcard, d.resolve("none/etc/openbook/linux-env.json"), quire) is ImageSource.NoImage)
}

private fun downloads() {
    val img = bigImage()
    Server(img).use { s ->
        val d = tmp()
        val got = StagedDownload(d, manifest(s.url, img), HttpFetcher()).run(0, noProgress) { false }
        check("a whole download verifies", Files.readAllBytes(got).contentEquals(img))
    }

    // Resume after the process ended: a new StagedDownload over the same folder.
    Server(img).use { s ->
        val d = tmp()
        val m = manifest(s.url, img)
        val (l, stop) = stopAfter(2L shl 20)
        val stopped = throws<CancellationException> { StagedDownload(d, m, HttpFetcher()).run(0, l, stop) }
        val staged = StagedDownload(d, m, HttpFetcher()).staged()
        check("a stopped download keeps what it had", stopped != null && staged > 0 && staged < img.size) { "staged $staged" }
        val got = StagedDownload(d, m, HttpFetcher()).run(0, noProgress) { false }
        val second = s.asked.last()
        check("it continues with a Range request after a restart",
            second.startsWith("range=bytes=$staged-") && second.contains("if-range=\"a\"")) { second }
        check("the continued download verifies", Files.readAllBytes(got).contentEquals(img))
    }

    Server(img).use { s ->
        val d = tmp()
        val m = manifest(s.url, img)
        val (l, stop) = stopAfter(2L shl 20)
        throws<CancellationException> { StagedDownload(d, m, HttpFetcher()).run(0, l, stop) }
        s.mode = Server.Mode.IGNORE_RANGES
        val got = StagedDownload(d, m, HttpFetcher()).run(0, noProgress) { false }
        check("a server that answers 200 to a Range request: it starts over and still verifies",
            Files.readAllBytes(got).contentEquals(img))
    }

    // The file on the server changed after part of it was staged: If-Range gets the whole new file, which doesn't
    // match the pinned hash, so it is refused and nothing stays staged.
    Server(img).use { s ->
        val d = tmp()
        val m = manifest(s.url, img)
        val (l, stop) = stopAfter(2L shl 20)
        throws<CancellationException> { StagedDownload(d, m, HttpFetcher()).run(0, l, stop) }
        s.data = img.copyOf().also { it[it.size - 10] = (it[it.size - 10] + 1).toByte() }
        s.etag = "\"b\""
        val e = throws<ImageRefusedException> { StagedDownload(d, m, HttpFetcher()).run(0, noProgress) { false } }
        check("a changed file is refused", e != null && e.message!!.contains("SHA-256")) { "${e?.message}" }
        check("the refused download is dropped", !Files.exists(d.resolve("images.tar.gz.part")))
    }

    // The same change on a server without validators: the ranges continue, and the whole-file hash still refuses it.
    Server(img, etag = "").use { s ->
        val d = tmp()
        val m = manifest(s.url, img)
        val (l, stop) = stopAfter(2L shl 20)
        throws<CancellationException> { StagedDownload(d, m, HttpFetcher()).run(0, l, stop) }
        s.data = img.copyOf().also { it[it.size - 10] = (it[it.size - 10] + 1).toByte() }
        val e = throws<ImageRefusedException> { StagedDownload(d, m, HttpFetcher()).run(0, noProgress) { false } }
        check("a changed file continued by range is refused by the whole-file hash", e != null)
    }

    Server(img).use { s ->
        val wrong = ImageManifest("t", s.url, "00".repeat(32), img.size.toLong(), 10_000)
        val e = throws<ImageRefusedException> { StagedDownload(tmp(), wrong, HttpFetcher()).run(0, noProgress) { false } }
        check("a wrong hash is refused", e != null)
        s.mode = Server.Mode.TOO_LONG
        val e2 = throws<ImageRefusedException> { StagedDownload(tmp(), manifest(s.url, img), HttpFetcher()).run(0, noProgress) { false } }
        check("more bytes than pinned are refused", e2 != null) { "$e2" }
        s.mode = Server.Mode.NOT_FOUND
        val e3 = throws<FileNotFoundException> { StagedDownload(tmp(), manifest(s.url, img), HttpFetcher()).run(0, noProgress) { false } }
        check("a missing file (404) is a permanent error", e3 != null)
    }

    val e = throws<IOException> {
        StagedDownload(tmp(), manifest("http://127.0.0.1:9/x", ByteArray(100)), { _, _, _ -> error("no fetch") }) {
            50_000_000L
        }.run(4_000_000_000L, noProgress) { false }
    }
    check("too little space: refused before downloading, as no space",
        e != null && e.message!!.contains("No space left on device")) { "${e?.message}" }
    check("Content-Range parsing", StagedDownload.rangeMatches("bytes 5-9/10", 5, 10) &&
        !StagedDownload.rangeMatches("bytes 0-9/10", 5, 10) && !StagedDownload.rangeMatches("bytes 5-9/11", 5, 10) &&
        StagedDownload.rangeMatches("bytes 5-9/*", 5, 10))
}

private fun extraction() {
    val d = tmp()
    val good = d.resolve("good.tar.gz").also { Files.write(it, goodImage()) }
    val dest = d.resolve("linux.new")
    val names = SafeExtractor.extract(good, dest, 10_000)
    check("a good image extracts", names == setOf("build_id", "root_part", "vm_config.json", "vmlinuz", "initrd.img") &&
        String(Files.readAllBytes(dest.resolve("root_part"))) == "new root")

    fun refused(what: String, archive: ByteArray, limit: Long? = 10_000) {
        val root = tmp()
        val a = root.resolve("a.tar.gz").also { Files.write(it, archive) }
        val out = root.resolve("x/linux.new")
        Files.createDirectories(out.parent)
        val e = throws<ImageRefusedException> { SafeExtractor.extract(a, out, limit) }
        val stray = Files.walk(root).use { w -> w.filter { Files.isRegularFile(it) && it != a }.count() }
        check("refused: $what (${e?.message?.substringAfter("is ")})", e != null && !Files.exists(out) && stray == 0L) {
            "e=$e out=${Files.exists(out)} stray=$stray"
        }
    }
    refused("a path with ..", targz(file("./root_part", "x"), file("../escape", "x")))
    refused("an absolute path", targz(file("/tmp/escape", "x")))
    refused("a name in a subfolder", targz(file("./sub/root_part", "x")))
    refused("a symbolic link", targz(TarArchiveEntry("./root_part", TarConstants.LF_SYMLINK).also { it.linkName = "/etc/passwd" } to ByteArray(0)))
    refused("a hard link", targz(file("./build_id", "b"),
        TarArchiveEntry("./root_part", TarConstants.LF_LINK).also { it.linkName = "build_id" } to ByteArray(0)))
    refused("a character device", targz(TarArchiveEntry("./vmlinuz", TarConstants.LF_CHR) to ByteArray(0)))
    refused("a block device", targz(TarArchiveEntry("./vmlinuz", TarConstants.LF_BLK) to ByteArray(0)))
    refused("a FIFO", targz(TarArchiveEntry("./vmlinuz", TarConstants.LF_FIFO) to ByteArray(0)))
    refused("a folder", targz(TarArchiveEntry("./root_part/", TarConstants.LF_DIR) to ByteArray(0)))
    refused("an unknown name", targz(file("./root_part", "x"), file("./autorun.sh", "x")))
    refused("a name twice", targz(file("./root_part", "x"), file("./root_part", "y")))
    refused("more than the installed size", targz(file("./root_part", "x".repeat(200))), limit = 100)
}

private fun installs() {
    val img = goodImage("new root")
    Server(img).use { s ->
        // An upgrade: the old guest's disk is kept as root_part_backup, the old image's files are replaced.
        val d = tmp()
        val install = d.resolve("files/linux")
        Files.createDirectories(install)
        Files.write(install.resolve("root_part_backup"), "the person's old disk".toByteArray())
        Files.write(install.resolve("vm_config.json"), "old".toByteArray())
        var cidataNames: Set<String>? = null
        OpenBookInstall(manifest(s.url, img), d.resolve("nobackup/linux-staging"), install, MARKER)
            .run({ dir, names -> cidataNames = names; Files.write(dir.resolve("cidata.iso"), "c".toByteArray()) },
                noProgress) { false }
        check("install: the new image is in place, with its marker",
            String(Files.readAllBytes(install.resolve("root_part"))) == "new root" &&
                Files.exists(install.resolve(MARKER)) && String(Files.readAllBytes(install.resolve("vm_config.json"))) == "{}")
        check("install: root_part_backup is kept",
            String(Files.readAllBytes(install.resolve("root_part_backup"))) == "the person's old disk")
        check("install: cidata sees the archive's names and lands in the image", cidataNames?.contains("root_part") == true &&
            Files.exists(install.resolve("cidata.iso")))
        check("install: no .new or .old is left, and the staged download is freed",
            !Files.exists(d.resolve("files/linux.new")) && !Files.exists(d.resolve("files/linux.old")) &&
                !Files.exists(d.resolve("nobackup/linux-staging/images.tar.gz.part")))
    }

    Server(img).use { s ->
        // A wrong hash: nothing is extracted, and the existing install stays as it was.
        val d = tmp()
        val install = d.resolve("files/linux")
        Files.createDirectories(install)
        Files.write(install.resolve("root_part"), "the guest".toByteArray())
        Files.write(install.resolve(MARKER), ByteArray(0))
        val wrong = ImageManifest("t", s.url, "00".repeat(32), img.size.toLong(), 10_000)
        var cidataCalled = false
        val e = throws<ImageRefusedException> {
            OpenBookInstall(wrong, d.resolve("staging"), install, MARKER).run({ _, _ -> cidataCalled = true }, noProgress) { false }
        }
        check("a wrong hash extracts nothing", e != null && !cidataCalled && !Files.exists(d.resolve("files/linux.new")))
        check("a wrong hash keeps the existing install",
            String(Files.readAllBytes(install.resolve("root_part"))) == "the guest" && Files.exists(install.resolve(MARKER)))
    }

    val bad = targz(file("./root_part", "x"), file("../escape", "x"))
    Server(bad).use { s ->
        val d = tmp()
        val install = d.resolve("files/linux")
        Files.createDirectories(install)
        Files.write(install.resolve("root_part"), "the guest".toByteArray())
        val e = throws<ImageRefusedException> {
            OpenBookInstall(manifest(s.url, bad), d.resolve("staging"), install, MARKER).run({ _, _ -> }, noProgress) { false }
        }
        check("an unsafe archive that matches its hash is still refused, and dropped",
            e != null && !Files.exists(d.resolve("files/escape")) && !Files.exists(d.resolve("escape")) &&
                String(Files.readAllBytes(install.resolve("root_part"))) == "the guest" &&
                !Files.exists(d.resolve("staging/images.tar.gz.part")))
    }

    // A crash in the middle of the swap.
    run {
        val d = tmp()
        val install = d.resolve("linux")
        val old = d.resolve("linux.old")
        val new = d.resolve("linux.new")
        Files.createDirectories(old)
        Files.write(old.resolve("root_part_backup"), "disk".toByteArray())
        Files.createDirectories(new)
        Files.write(new.resolve("root_part"), "n".toByteArray())
        Files.write(new.resolve(MARKER), ByteArray(0))
        InstallCommit.recover(install, MARKER)
        check("recover: a complete .new is finished, keeping the backup",
            Files.exists(install.resolve(MARKER)) && Files.exists(install.resolve("root_part_backup")) && !Files.exists(old))
    }
    run {
        val d = tmp()
        val install = d.resolve("linux")
        val old = d.resolve("linux.old")
        Files.createDirectories(old)
        Files.write(old.resolve("root_part"), "the guest".toByteArray())
        Files.createDirectories(d.resolve("linux.new"))
        InstallCommit.recover(install, MARKER)
        check("recover: an incomplete .new is dropped and the old folder comes back",
            String(Files.readAllBytes(install.resolve("root_part"))) == "the guest" && !Files.exists(d.resolve("linux.new")))
    }
}

@Suppress("unused")
private val keepFetcherType: Fetcher = Fetcher { _, _, _ -> FetchResponse(500, null, null, ByteArray(0).inputStream()) }
