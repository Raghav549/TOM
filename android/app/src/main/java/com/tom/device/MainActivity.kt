package com.tom.device.legacy

import android.app.Activity
import android.os.Bundle
import android.provider.Settings
import android.content.Intent

/** Legacy bootstrap retained outside the production com.tom.device namespace. */
class LegacyMainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!isAccessibilityEnabled()) {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        finish()
    }

    private fun isAccessibilityEnabled(): Boolean =
        runCatching {
            val enabled = Settings.Secure.getString(
                contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            )
            enabled?.contains(packageName, ignoreCase = true) == true
        }.getOrDefault(false)
}
