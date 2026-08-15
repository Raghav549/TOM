package com.tom.device

import android.app.Activity
import android.os.Bundle
import android.provider.Settings
import android.content.Intent
import android.graphics.Color
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Minimal native setup screen for the device bridge test build.
 * Accessibility must always be explicitly enabled by the user in Android Settings.
 */
class MainActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildView())
        refreshStatus()
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) refreshStatus()
    }

    private fun buildView() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER_HORIZONTAL
        setPadding(48, 64, 48, 48)

        addView(TextView(context).apply {
            text = "TOM"
            textSize = 32f
            setTextColor(Color.BLACK)
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2))

        addView(TextView(context).apply {
            text = "Device bridge setup"
            textSize = 18f
            setTextColor(Color.DKGRAY)
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2))

        status = TextView(context).apply {
            textSize = 16f
            setPadding(0, 40, 0, 40)
        }
        addView(status, LinearLayout.LayoutParams(-1, -2))

        addView(Button(context).apply {
            text = "Enable Accessibility Service"
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
        }, LinearLayout.LayoutParams(-1, -2))

        addView(TextView(context).apply {
            text = "TOM will never enable Accessibility automatically.\nEnable only after installing a build you trust."
            textSize = 14f
            setTextColor(Color.DKGRAY)
            setPadding(0, 28, 0, 0)
        }, LinearLayout.LayoutParams(-1, -2))
    }

    private fun refreshStatus() {
        val enabled = runCatching {
            val services = Settings.Secure.getString(
                contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            ) ?: ""
            services.split(':').any {
                it.equals("$packageName/.TomAccessibilityService", ignoreCase = true) ||
                    it.contains(packageName, ignoreCase = true)
            }
        }.getOrDefault(false)
        status.text = if (enabled) {
            "Accessibility: ENABLED\n\nTOM is ready for the live bridge test."
        } else {
            "Accessibility: NOT ENABLED\n\nTap the button below, open Downloaded apps → TOM, and enable the service."
        }
    }
}
