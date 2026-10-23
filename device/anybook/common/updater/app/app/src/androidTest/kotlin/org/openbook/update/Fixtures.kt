// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import android.content.Context
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/**
 * A synthetic Google listing for this device: newer releases built from its own build number and build ID.
 * A device whose build ID is not a release-train ID (an emulator's) classifies against Googlebook's own,
 * through the engine's OPENBOOK_UPDATER_TEST_BUILD_ID.
 */
class Fixtures(context: Context) {
    val root = File(context.filesDir, "test-fixtures").apply { deleteRecursively(); mkdirs() }
    val running = Build.VERSION.INCREMENTAL.toLong()
    val newer = running + 1000
    val buildId: String = Build.ID.takeIf { TRAIN_ID.matches(it) } ?: "CL3B.260622.276.R4"
    private val train = buildId.substringBefore('.')
    private val date = buildId.split('.')[1].toInt()
    /** The same train, one month later: a monthly update. */
    val monthly = "$train.${date + 100}.001"
    /** The next quarter's train. */
    val quarterly = "${train.take(2)}${train[2].digitToInt() % 9 + 1}A.${date + 300}.001"
    val release = File(root, "recovery.zip").apply { writeBytes(ByteArray(2_000_000) { (it * 31 % 251).toByte() }) }
    val md5: String = MessageDigest.getInstance("MD5").digest(release.readBytes()).joinToString("") { "%02x".format(it) }

    /** The engine's environment for these tests: a smaller space reserve, and the test build ID if needed. */
    val environment: Map<String, String> = SMALL_RESERVE +
        (if (buildId != Build.ID) mapOf("OPENBOOK_UPDATER_TEST_BUILD_ID" to buildId) else emptyMap())

    fun listing(name: String, buildId: String, url: String = "file://${release.path}"): String {
        val entries = JSONArray().put(JSONObject()
            .put("device", Build.DEVICE).put("channel", "STABLE").put("buildidentifier", "${newer}_$buildId")
            .put("dateupdated", "2026-11-20").put("url", url).put("md5", md5).put("filesize", release.length()))
        return File(root, name).apply { writeText(entries.toString()) }.path
    }

    companion object {
        private val TRAIN_ID = Regex("[A-Z][A-Z][0-9][A-Z0-9]\\.[0-9]{6}\\..+")
        /** The engine keeps 20 GiB free by default; an emulator's /data has about 8 GiB. */
        val SMALL_RESERVE = mapOf("OPENBOOK_UPDATER_RESERVE_KB" to "1048576")
    }
}
