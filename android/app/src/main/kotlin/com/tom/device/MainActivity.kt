package com.tom.device

import android.app.Activity
import android.os.Bundle
import android.provider.Settings
import android.content.Intent

/**
 * Intentionally tiny bootstrap: TOM's first phase has no polished UI.
 * Configuration is supplied by the future setup client or local test harness.
 */
class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The user must explicitly enable AccessibilityService in Android Settings.
        if (!isAccessibilityEnabled()) {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        finish()
    }

    private fun isAccessibilityEnabled(): Boolean =
        runCatching {
            val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES)
            enabled?.contains(packageName, ignoreCase = true) == true
        }.getOrDefault(false)
}
