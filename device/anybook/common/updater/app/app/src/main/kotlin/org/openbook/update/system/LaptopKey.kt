// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.system

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import java.io.File
import java.math.BigInteger
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.PublicKey
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.Date
import java.util.zip.ZipFile
import javax.security.auth.x500.X500Principal

/**
 * This laptop's own update key (phase 4): an RSA-4096 key in Android Keystore that never leaves it. It signs
 * the payloads the laptop builds for itself. update_engine accepts them only once the key's certificate is
 * in the running system's otacerts.zip, which takes one OpenBook update ("enrollment"); until then the app
 * says so and installs nothing. The certificate is public: the shell can read it (ExportCertReceiver).
 */
object LaptopKey {
    const val ALIAS = "openbook-laptop-ota"
    private const val TAG = "OpenBookUpdate"
    const val OTACERTS = "/system/etc/security/otacerts.zip"

    /** DER prefix of a SHA-256 DigestInfo: what `openssl pkeyutl -pkeyopt digest:sha256` signs, as update_engine verifies. */
    private val SHA256_DIGEST_INFO = byteArrayOf(
        0x30, 0x31, 0x30, 0x0d, 0x06, 0x09, 0x60, 0x86.toByte(), 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01, 0x05, 0x00, 0x04, 0x20,
    )

    private fun store(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    fun exists(): Boolean = runCatching { store().containsAlias(ALIAS) }.getOrDefault(false)

    /** Creates the key once (a few seconds for RSA-4096). Returns its certificate. */
    @Synchronized
    fun ensure(): X509Certificate {
        certificate()?.let { return it }
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setKeySize(4096)
            .setDigests(KeyProperties.DIGEST_NONE)
            .setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)
            .setCertificateSubject(X500Principal("CN=OpenBook laptop update key, O=OpenBook"))
            .setCertificateSerialNumber(BigInteger.valueOf(System.currentTimeMillis()))
            .setCertificateNotBefore(Date(System.currentTimeMillis() - 86_400_000L))
            .setCertificateNotAfter(Date(4_102_444_800_000L)) // 2100-01-01, like the payloads' timestamp limit
            .build()
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, "AndroidKeyStore").apply { initialize(spec) }.generateKeyPair()
        Log.i(TAG, "created this laptop's update key")
        return certificate() ?: error("the new key has no certificate")
    }

    fun certificate(): X509Certificate? = runCatching { store().getCertificate(ALIAS) as? X509Certificate }.getOrNull()

    fun certificatePem(cert: X509Certificate): String =
        "-----BEGIN CERTIFICATE-----\n" + Base64.encodeToString(cert.encoded, Base64.DEFAULT) + "-----END CERTIFICATE-----\n"

    /** The DER DigestInfo of a SHA-256 hash: what the signature covers. */
    fun digestInfo(hash: ByteArray): ByteArray = SHA256_DIGEST_INFO + hash

    /** Signs a SHA-256 hash for update_engine: RSA PKCS#1 v1.5 over its DigestInfo (512 bytes). */
    fun signHash(hash: ByteArray): ByteArray {
        require(hash.size == 32) { "a SHA-256 hash is 32 bytes" }
        val key = store().getKey(ALIAS, null) as? PrivateKey ?: error("this laptop has no update key")
        return Signature.getInstance("NONEwithRSA").run {
            initSign(key)
            update(SHA256_DIGEST_INFO + hash)
            sign()
        }
    }

    /** Whether the running system trusts this laptop's key: its public key is in otacerts.zip. */
    fun enrolled(otacerts: File = File(OTACERTS)): Boolean {
        val mine = certificate()?.publicKey ?: return false
        return trustedKeys(otacerts).any { it.encoded.contentEquals(mine.encoded) }
    }

    fun trustedKeys(otacerts: File): List<PublicKey> = runCatching {
        val factory = CertificateFactory.getInstance("X.509")
        ZipFile(otacerts).use { zip ->
            zip.entries().toList().filter { !it.isDirectory }.mapNotNull { entry ->
                runCatching { zip.getInputStream(entry).use { factory.generateCertificate(it).publicKey } }.getOrNull()
            }
        }
    }.getOrDefault(emptyList())
}
