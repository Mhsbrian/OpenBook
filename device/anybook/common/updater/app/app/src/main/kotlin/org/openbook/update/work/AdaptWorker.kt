// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.work

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import org.openbook.update.Graph
import org.openbook.update.data.Capabilities
import org.openbook.update.data.HistoryEntry
import org.openbook.update.engine.AdaptFacts
import org.openbook.update.engine.EngineExit
import org.openbook.update.system.LaptopKey
import org.json.JSONObject
import java.io.File

/**
 * Builds a verified download for this laptop (phase 3), then signs its update payload with this laptop's
 * key (phase 4). Local work only: no network, nothing installed. The engine runs openbook-adapt and keeps
 * the payload; a release Google changed where OpenBook adapts it is held, with the reason. Signing happens
 * only once this laptop's key is enrolled in the running system, so a signed payload can always install.
 */
class AdaptWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        if (!Graph.runsHere() || !Capabilities.CURRENT.adaptOnLaptop) return Result.success()
        val engine = Graph.engine()
        val release = engine.verifiedDownload() ?: return Result.success()
        var facts = engine.adaptFacts(release)
        if (facts.status != AdaptFacts.Status.ADAPTED && facts.status != AdaptFacts.Status.READY) {
            val result = engine.run("adapt")
            Log.i(TAG, "adapt finished: exit ${result.code} (${result.exit})")
            facts = engine.adaptFacts(release)
            when (result.exit) {
                EngineExit.OK -> Unit
                EngineExit.HELD -> {
                    val settings = Graph.settings
                    if (settings.announcedAdaptHeld != release.number) {
                        Graph.history.add(HistoryEntry(System.currentTimeMillis(), HistoryEntry.Type.ADAPTATION_HELD, release.label()))
                        settings.announcedAdaptHeld = release.number
                    }
                    if (settings.notifiedAdaptHeld != release.number && Graph.notifier.adaptationHeld(release)) {
                        settings.notifiedAdaptHeld = release.number
                    }
                    return Result.success()
                }
                EngineExit.SPACE -> { Graph.notifier.storage(); return Result.failure() }
                EngineExit.BUSY, EngineExit.STOPPED -> return Result.retry()
                else -> {
                    Graph.notifier.adaptationFailed()
                    return if (runAttemptCount < 1) Result.retry() else Result.failure()
                }
            }
        }
        if (facts.status == AdaptFacts.Status.ADAPTED && Capabilities.CURRENT.installOnLaptop) {
            sign(engine.payloadDir(release))
            val signed = engine.run("sign")
            if (signed.exit != EngineExit.OK) {
                Log.w(TAG, "signing the payload failed: ${signed.output.takeLast(500)}")
                return Result.failure()
            }
            facts = engine.adaptFacts(release)
        }
        val settings = Graph.settings
        if (settings.announcedAdapted != release.number) {
            Graph.history.add(HistoryEntry(System.currentTimeMillis(), HistoryEntry.Type.BUILT_FOR_LAPTOP, release.label()))
            settings.announcedAdapted = release.number
        }
        if (settings.notifiedAdapted != release.number) {
            val posted = if (facts.status == AdaptFacts.Status.READY) Graph.notifier.readyToInstall(release)
                         else Graph.notifier.builtAwaitingKey(release)
            if (posted) settings.notifiedAdapted = release.number
        }
        return Result.success()
    }

    /**
     * Signs the payload's two hashes with this laptop's key (Android Keystore) for the engine's `sign`, and
     * leaves the key's certificate beside them: the engine checks both signatures with it before inserting.
     */
    private fun sign(dir: File) {
        val json = JSONObject(File(dir, "payload.json").readText())
        fun hex(s: String) = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        val cert = LaptopKey.ensure()
        for ((name, key) in listOf("metadata" to "metadata_hash_to_sign", "payload" to "payload_hash_to_sign")) {
            val hash = hex(json.getString(key))
            val sig = LaptopKey.signHash(hash)
            check(java.security.Signature.getInstance("NONEwithRSA").run {
                initVerify(cert.publicKey); update(LaptopKey.digestInfo(hash)); verify(sig)
            }) { "this laptop's key made a signature its certificate does not verify" }
            File(dir, "$name.sig.tmp").apply { writeBytes(sig) }.renameTo(File(dir, "$name.sig"))
        }
        File(dir, "laptop.x509.pem").writeText(LaptopKey.certificatePem(cert))
    }

    companion object {
        const val TAG = "OpenBookUpdate"
    }
}
