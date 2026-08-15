package com.tom.device

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class MainActivity : Activity() {
    private lateinit var root: LinearLayout
    private lateinit var content: LinearLayout
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildShell())
        showHome()
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) refreshStatus()
    }

    private fun buildShell(): View {
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(248, 247, 251))
        }
        val header = LinearLayout(this).apply {
            setPadding(28, 28, 28, 20)
            addView(TomGlassUi.title(context, "TOM", 34f), LinearLayout.LayoutParams(0, -2, 1f))
            addView(TomGlassUi.button(context, "⌂", ::showHome).apply { textSize = 20f }, LinearLayout.LayoutParams(56, 52))
        }
        shell.addView(header, LinearLayout.LayoutParams(-1, -2))
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        shell.addView(ScrollView(this).apply {
            addView(content)
            setPadding(18, 0, 18, 0)
        }, LinearLayout.LayoutParams(-1, 0, 1f))
        val nav = LinearLayout(this).apply {
            setPadding(10, 10, 10, 18)
            addView(TomGlassUi.button(context, "Home", ::showHome), LinearLayout.LayoutParams(0, 52, 1f).apply { setMargins(4, 0, 4, 0) })
            addView(TomGlassUi.button(context, "Permissions", ::showPermissions), LinearLayout.LayoutParams(0, 52, 1f).apply { setMargins(4, 0, 4, 0) })
            addView(TomGlassUi.button(context, "Connection", ::showConnection), LinearLayout.LayoutParams(0, 52, 1f).apply { setMargins(4, 0, 4, 0) })
            addView(TomGlassUi.button(context, "More", ::showMore), LinearLayout.LayoutParams(0, 52, 1f).apply { setMargins(4, 0, 4, 0) })
        }
        shell.addView(nav, LinearLayout.LayoutParams(-1, -2))
        return shell
    }

    private fun page(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(6, 12, 6, 28)
    }

    private fun add(view: View, top: Int = 12) {
        content.addView(view, LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, top, 0, 0) })
    }

    private fun heading(text: String, sub: String) {
        add(TomGlassUi.title(this, text, 25f), 4)
        add(TomGlassUi.body(this, sub), 7)
    }

    private fun showHome() {
        content.removeAllViews(); heading("Ready when you are", "A private device bridge for observation, approved actions, and verified recovery.")
        status = TomGlassUi.body(this, "")
        add(status, 18); refreshStatus()
        add(TomGlassUi.card(this, "Accessibility", "Lets TOM observe the active UI and perform explicitly permitted accessibility actions.", "Open settings") { openAccessibility() })
        add(TomGlassUi.card(this, "Live bridge", "Connect the device to the Core only after secure pairing. No secret is shown on this screen.", "Open connection") { showConnection() })
        add(TomGlassUi.card(this, "Permission center", "Review special access and runtime permissions one by one. TOM never silently enables them.", "Review permissions") { showPermissions() })
    }

    private fun showPermissions() {
        content.removeAllViews(); heading("Permission center", "Every powerful capability is opt-in. Android system confirmation remains in control.")
        add(TomGlassUi.card(this, "Accessibility", "UI-tree observation, semantic node grounding, and approved interaction.", "Open Accessibility") { openAccessibility() })
        add(TomGlassUi.card(this, "Notifications", "Read device notifications only after Android grants notification-listener access.", "Open notification access") { startActivity(Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS")) })
        add(TomGlassUi.card(this, "Screen capture", "Capture actual pixels for visual verification. Android will show its MediaProjection consent dialog each session.", "Request screen capture") { requestScreenCapture() })
        add(TomGlassUi.card(this, "Microphone", "Needed only for voice conversations and audio-call features.", "Allow microphone") { requestPermission(Manifest.permission.RECORD_AUDIO, 20) })
        add(TomGlassUi.card(this, "Camera", "Needed only for video-call assistance when the user explicitly starts it.", "Allow camera") { requestPermission(Manifest.permission.CAMERA, 21) })
        add(TomGlassUi.card(this, "Overlay", "Optional on-screen TOM controls. Android keeps this as a separate special access.", "Open overlay access") { startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))) })
    }

    private fun showConnection() {
        content.removeAllViews(); heading("Device connection", "Pair this phone with a trusted TOM Core before live execution.")
        add(TomGlassUi.card(this, "Secure pairing", "Use a server-issued pairing code or QR. Credentials belong in Android Keystore; never paste a secret into chat.", "Pair device") { showPairingInfo() })
        add(TomGlassUi.card(this, "Connection health", "Live transport will report authenticated session, last observation, and action verification state.", "Run local readiness check") { showReadyCheck() })
    }

    private fun showMore() {
        content.removeAllViews(); heading("More", "System information, safety controls, and project notices.")
        add(TomGlassUi.card(this, "Safety", "Consequential actions require policy approval. Unknown post-action state never triggers a blind retry.", "View safety rules") { showTextPage("Safety", "TOM treats transport ACK as receipt, not success. Purchases, payments, sends, deletes, and account changes remain approval-gated. Missing observation is UNKNOWN; it does not authorize retry.") })
        add(TomGlassUi.card(this, "Privacy", "TOM exposes sensitive capabilities only through explicit Android grants and authenticated device sessions.", "View privacy") { showTextPage("Privacy", "Device observations are intended for the active TOM session. Secrets are not rendered in the UI. Password fields are redacted at the accessibility layer. Review your Core retention settings before production use.") })
        add(TomGlassUi.card(this, "License", "Open-source notices and project licensing information.", "View license") { showTextPage("License", "TOM is distributed with the license files in its repository. Third-party components retain their own licenses. See the repository LICENSE and NOTICE files before redistribution.") })
        add(TomGlassUi.card(this, "About", "TOM device bridge build.", "View build info") { showTextPage("About", "TOM\nDevice bridge build\n\nCapabilities are intentionally permission-gated and transport-authenticated.") })
    }

    private fun showTextPage(title: String, text: String) {
        content.removeAllViews(); heading(title, "")
        add(TomGlassUi.body(this, text), 20)
        add(TomGlassUi.button(this, "Back to More", ::showMore), 24)
    }

    private fun showPairingInfo() = showTextPage("Secure pairing", "Pairing is intentionally not automatic. The production flow should display a short-lived server-issued code or QR, bind it to this device identity, then provision an encrypted credential into Android Keystore. Never share the credential itself.")

    private fun showReadyCheck() = showTextPage("Readiness", "Accessibility: ${if (isAccessibilityEnabled()) "ENABLED" else "NOT ENABLED"}\n\nThe next live test requires a reachable WSS Core endpoint and a provisioned device credential. Until those exist, TOM will not attempt live execution.")

    private fun refreshStatus() {
        status.text = if (isAccessibilityEnabled()) "Accessibility: ENABLED\n\nTOM is ready for the live bridge test." else "Accessibility: NOT ENABLED\n\nEnable it from Android Settings before testing UI observation."
    }

    private fun isAccessibilityEnabled(): Boolean = runCatching {
        val services = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        services.split(':').any { it.contains(packageName, ignoreCase = true) }
    }.getOrDefault(false)

    private fun openAccessibility() = startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))

    private fun requestPermission(permission: String, code: Int) {
        if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(permission), code)
    }

    private fun requestScreenCapture() {
        val manager = getSystemService(MediaProjectionManager::class.java)
        startActivityForResult(manager.createScreenCaptureIntent(), 31)
    }
}
