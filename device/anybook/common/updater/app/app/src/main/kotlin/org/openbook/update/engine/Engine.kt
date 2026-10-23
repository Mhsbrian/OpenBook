// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.engine

import android.content.Context
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.runInterruptible
import kotlinx.coroutines.withContext
import org.openbook.update.BuildConfig
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/** openbook-updater's exit codes (see the engine's header). */
enum class EngineExit(val code: Int) {
    OK(0), USAGE(2), NETWORK(3), CHECKSUM(4), SPACE(5), BUSY(6), NOT_LISTED(7), HELD(8), LISTING_REFUSED(9),
    UPDATE_AVAILABLE(10), STOPPED(130), UNKNOWN(-1);

    companion object {
        fun of(code: Int) = entries.firstOrNull { it.code == code } ?: UNKNOWN
    }
}

data class EngineResult(val exit: EngineExit, val code: Int, val output: String)

/** The engine script, shipped as an APK asset and copied into the app's private files. */
object EngineFiles {
    const val ASSET = "openbook-updater"

    fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /** Copies the packaged engine into place when missing or different; refuses an engine that is not the pinned one. */
    @Synchronized
    fun install(context: Context): File {
        val asset = context.assets.open(ASSET).use { it.readBytes() }
        check(sha256(asset) == BuildConfig.ENGINE_SHA256) { "The packaged engine differs from its pin" }
        val dir = File(context.filesDir, "engine").apply { mkdirs() }
        val script = File(dir, ASSET)
        if (!script.isFile || sha256(script.readBytes()) != BuildConfig.ENGINE_SHA256) {
            val tmp = File(dir, "$ASSET.tmp")
            tmp.writeBytes(asset)
            check(tmp.renameTo(script)) { "Cannot install the engine" }
        }
        return script
    }
}

/**
 * Runs openbook-updater as a child process (`/system/bin/sh SCRIPT --dir DIR COMMAND`) in the app's
 * own SELinux domain. Cancelling the coroutine stops the engine cleanly: SIGTERM, which ends its
 * transfer and keeps a partial download; SIGKILL only if it has not exited after [stopGraceMillis].
 */
class EngineRunner(
    private val context: Context,
    val dataDir: File = File(context.filesDir, "updater"),
    private val listing: String? = null,
    /** Extra environment for the engine (tests: a smaller space reserve on a small emulator). */
    private val environment: Map<String, String> = emptyMap(),
    private val shell: String = "/system/bin/sh",
    private val stopGraceMillis: Long = 10_000,
) {
    val stateFile get() = File(dataDir, "state")

    suspend fun run(command: String): EngineResult = withContext(Dispatchers.IO) {
        val script = EngineFiles.install(context)
        val runs = File(dataDir, "runs").apply { mkdirs() }
        val args = buildList {
            add(shell); add(script.path); add("--dir"); add(dataDir.path)
            if (listing != null) { add("--listing"); add(listing) }
            add(command)
        }
        // Output goes to a file, not a pipe: stopping the process (Process.destroy closes its pipes) must not
        // cut the engine off while it records that it stopped.
        val output = File.createTempFile("$command-", ".txt", runs)
        try {
            val process = ProcessBuilder(args).redirectErrorStream(true).redirectOutput(output)
                .apply { environment().putAll(environment) }.start()
            try {
                val code = try {
                    runInterruptible { process.waitFor() }
                } catch (e: CancellationException) {
                    withContext(NonCancellable) { stop(process) }
                    throw e
                }
                EngineResult(EngineExit.of(code), code, tail(output))
            } finally {
                if (process.isAlive) process.destroyForcibly()
            }
        } finally {
            output.delete()
        }
    }

    private suspend fun stop(process: Process) {
        process.destroy() // SIGTERM: the engine's trap ends curl and records "stopped"
        val exited = runInterruptible { process.waitFor(stopGraceMillis, TimeUnit.MILLISECONDS) }
        if (!exited) process.destroyForcibly()
    }

    /** The end of a run's output (the engine also keeps its own capped log, updater.log). */
    private fun tail(file: File, limit: Int = 64 * 1024): String {
        val text = runCatching { file.readText() }.getOrDefault("")
        return if (text.length <= limit) text else text.takeLast(limit)
    }

    /** The engine's last run (key=value lines; replaced atomically by the engine). */
    fun readState(): EngineState = EngineState.parse(runCatching { stateFile.readText() }.getOrDefault(""))

    /** The newest release Google listed at the last successful check (kept across failed runs). */
    fun readRelease(): EngineState = EngineState.parse(runCatching { File(dataDir, "release").readText() }.getOrDefault(""))

    /** The newest verified download on disk (zip, MD5 marker and the engine's release.info), if any. */
    fun verifiedDownload(): Release? = dataDir.listFiles { f -> f.isDirectory && f.name.all(Char::isDigit) }.orEmpty()
        .filter { File(it, "recovery.zip").isFile && File(it, "recovery.zip.md5").isFile }
        .mapNotNull { dir -> Release.of(EngineState.parse(runCatching { File(dir, "release.info").readText() }.getOrDefault("")))
            ?.takeIf { it.number.toString() == dir.name } }
        .maxByOrNull { it.number }

    /** On disk for [release]: the engine's verified download (zip + MD5 marker) or a partial one. */
    fun downloadFacts(release: Release?): DownloadFacts {
        if (release == null) return DownloadFacts.NONE
        val dir = File(dataDir, release.number.toString())
        val verified = File(dir, "recovery.zip").isFile && File(dir, "recovery.zip.md5").isFile
        return DownloadFacts(verified, File(dir, "recovery.zip.part").takeIf { it.isFile }?.length() ?: 0)
    }
}
