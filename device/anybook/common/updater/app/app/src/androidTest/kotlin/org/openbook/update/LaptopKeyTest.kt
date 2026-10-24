// SPDX-License-Identifier: Apache-2.0
package org.openbook.update

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.openbook.update.system.LaptopKey
import java.io.File
import java.security.MessageDigest
import java.security.Signature
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** This laptop's update key in Android Keystore: what update_engine verifies, and the enrollment check. */
@RunWith(AndroidJUnit4::class)
class LaptopKeyTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun signsHashesTheWayUpdateEngineVerifies() {
        val cert = LaptopKey.ensure()
        assertEquals(cert, LaptopKey.ensure()) // created once
        assertTrue(LaptopKey.exists())
        val data = "an update payload's bytes".toByteArray()
        val hash = MessageDigest.getInstance("SHA-256").digest(data)
        val sig = LaptopKey.signHash(hash)
        assertEquals(512, sig.size)
        // RSA PKCS#1 v1.5 over the DigestInfo of the hash is a standard SHA256withRSA signature of the data:
        // exactly what `openssl pkeyutl -pkeyopt digest:sha256` makes and update_engine checks.
        assertTrue(Signature.getInstance("SHA256withRSA").run { initVerify(cert.publicKey); update(data); verify(sig) })
        assertTrue(LaptopKey.certificatePem(cert).startsWith("-----BEGIN CERTIFICATE-----\n"))
    }

    @Test fun enrolledOnlyWhenTheRunningSystemTrustsTheKey() {
        val cert = LaptopKey.ensure()
        fun zip(vararg certs: ByteArray) = File(context.cacheDir, "otacerts-${certs.size}.zip").apply {
            ZipOutputStream(outputStream()).use { z ->
                certs.forEachIndexed { i, der -> z.putNextEntry(ZipEntry("cert$i.x509.pem")); z.write(der); z.closeEntry() }
            }
        }
        assertFalse(LaptopKey.enrolled(zip()))
        assertTrue(LaptopKey.enrolled(zip(LaptopKey.certificatePem(cert).toByteArray())))
        assertTrue(LaptopKey.enrolled(zip(byteArrayOf(1, 2, 3), cert.encoded))) // DER too; junk entries are skipped
        assertFalse(LaptopKey.enrolled(File(context.cacheDir, "missing.zip")))
    }
}
