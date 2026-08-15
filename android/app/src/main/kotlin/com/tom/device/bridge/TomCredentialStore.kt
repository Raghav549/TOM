package com.tom.device.bridge

import android.content.Context
import android.util.Base64
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Device secret never lives in plain SharedPreferences or source code. */
class TomCredentialStore(context: Context) {
    private val prefs = context.getSharedPreferences("tom_bridge_credentials", Context.MODE_PRIVATE)
    private val keyAlias = "tom.device.bridge.aes"
    private val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    private fun key(): SecretKey {
        keyStore.getKey(keyAlias, null)?.let { return it as SecretKey }
        val generator = KeyGenerator.getInstance("AES", "AndroidKeyStore")
        generator.init(256)
        return generator.generateKey().also { generated ->
            // AndroidKeyStore persists the key; no key material is written to preferences.
            check(keyStore.containsAlias(keyAlias)) { "keystore key was not persisted" }
        }
    }

    fun provision(deviceId: String, secret: ByteArray) {
        require(deviceId.isNotBlank())
        require(secret.size >= 32) { "device secret must be at least 32 bytes" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val ciphertext = cipher.doFinal(secret)
        val blob = Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + "." +
            Base64.encodeToString(ciphertext, Base64.NO_WRAP)
        prefs.edit().putString("$deviceId.secret", blob).apply()
    }

    fun read(deviceId: String): ByteArray? {
        val blob = prefs.getString("$deviceId.secret", null) ?: return null
        val parts = blob.split('.', limit = 2)
        if (parts.size != 2) return null
        val iv = Base64.decode(parts[0], Base64.NO_WRAP)
        val ciphertext = Base64.decode(parts[1], Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        return cipher.doFinal(ciphertext)
    }

    fun revoke(deviceId: String) {
        prefs.edit().remove("$deviceId.secret").apply()
    }
}
