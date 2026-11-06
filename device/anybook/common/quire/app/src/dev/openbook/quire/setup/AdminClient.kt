// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.setup

import android.content.Context
import android.os.ParcelFileDescriptor
import android.system.ErrnoException
import android.system.Os
import android.system.OsConstants
import android.util.Base64
import dev.openbook.quire.agents.AcpConnection
import dev.openbook.quire.agents.AcpError
import dev.openbook.quire.agents.Connectors
import java.io.Closeable
import java.io.FileInputStream
import java.io.FileOutputStream
import org.json.JSONArray
import org.json.JSONObject

/**
 * The guest's admin worker (docs/quire-setup.md §4.3): JSON-RPC over the Terminal app's relay to vsock 7691, where a
 * root worker takes three fixed operations from Android and nothing else. `quired` and the agents never reach it.
 */
class AdminClient private constructor(private val pfd: ParcelFileDescriptor, onLine: (String) -> Unit) : Closeable {
    private val connection = AcpConnection(
        FileInputStream(pfd.fileDescriptor),
        FileOutputStream(pfd.fileDescriptor),
        object : AcpConnection.Handler {
            override fun onNotification(method: String, params: JSONObject) {
                if (method == "progress") onLine(params.optString("line"))
            }

            override fun onRequest(method: String, params: JSONObject): Any? =
                throw AcpError(AcpError.METHOD_NOT_FOUND, "Quire offers the admin worker nothing")
        },
        Closeable {
            try {
                Os.shutdown(pfd.fileDescriptor, OsConstants.SHUT_RDWR)
            } catch (_: ErrnoException) {
            }
            pfd.close()
        })

    /** Debian packages from the worker's own list (Node.js, git, …); anything else is refused there. */
    fun debianInstall(packages: List<String>): JSONObject =
        connection.call("debian-install", JSONObject().put("packages", JSONArray(packages)), DEBIAN_MS)

    /** Hands the worker a quired package and its hash; it installs it in a unit of its own. Returns the job id. */
    fun quiredUpdate(deb: ByteArray, sha256: String): String =
        connection.call("quired-update", JSONObject().put("deb", Base64.encodeToString(deb, Base64.NO_WRAP))
            .put("sha256", sha256), CALL_MS).getString("job")

    fun job(id: String): JSONObject = connection.call("job", JSONObject().put("id", id), CALL_MS)

    fun version(): String = connection.call("version", JSONObject(), CALL_MS).optString("version")

    override fun close() = connection.close()

    companion object {
        private const val DEBIAN_MS = 20 * 60_000L
        private const val CALL_MS = 60_000L

        /** Opens the worker through the bridge. Throws when the guest has none (quired before 0.4.0). */
        fun open(context: Context, onLine: (String) -> Unit = {}): AdminClient =
            AdminClient(Connectors.LinuxEnvironment.connectAdmin(context), onLine)
    }
}
