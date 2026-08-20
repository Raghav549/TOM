package com.tom.device

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding

class MainActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var content: LinearLayout
    private lateinit var nav: LinearLayout
    private lateinit var status: TextView
    private var voiceLoop: TomVoiceLoop? = null
    private var selectedVoice = "tom_m1"
    private var splashHandler: Handler? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.WHITE
        window.navigationBarColor = Color.WHITE
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR

        root = FrameLayout(this).apply { setBackgroundColor(Color.rgb(239, 247, 252)) }
        setContentView(root)
        startConfiguredBridge()
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.updatePadding(left = bars.left, top = bars.top, right = bars.right, bottom = bars.bottom)
            insets
        }
        showSplash()
    }

    private fun startConfiguredBridge() {
        val endpoint = BuildConfig.TOM_BRIDGE_WS_URL
        val deviceId = BuildConfig.TOM_DEVICE_ID
        if (!endpoint.startsWith("wss://") || deviceId.isBlank()) return
        val intent = Intent(this, TomBridgeForegroundService::class.java)
            .putExtra(TomBridgeForegroundService.EXTRA_ENDPOINT, endpoint)
            .putExtra(TomBridgeForegroundService.EXTRA_DEVICE_ID, deviceId)
        ContextCompat.startForegroundService(this, intent)
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) refreshStatus()
    }

    override fun onDestroy() {
        splashHandler?.removeCallbacksAndMessages(null)
        splashHandler = null
        voiceLoop?.stop()
        voiceLoop = null
        super.onDestroy()
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun showSplash() {
        root.removeAllViews()
        val splash = FrameLayout(this).apply { setBackgroundColor(Color.rgb(239, 247, 252)) }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(28), dp(28), dp(28), dp(28))
        }
        box.addView(TomGlassUi.logo(this, dp(132)), LinearLayout.LayoutParams(dp(132), dp(132)))
        box.addView(TomGlassUi.title(this, "TOM", 40f).apply { gravity = Gravity.CENTER; includeFontPadding = false }, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(14) })
        box.addView(TomGlassUi.body(this, "Observe  •  Understand  •  Assist").apply { gravity = Gravity.CENTER; includeFontPadding = false }, LinearLayout.LayoutParams(-1, dp(28)).apply { topMargin = dp(4) })
        splash.addView(box, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER))
        root.addView(splash, FrameLayout.LayoutParams(-1, -1))

        box.alpha = 0f; box.scaleX = .94f; box.scaleY = .94f
        box.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(520).start()
        splashHandler = Handler(Looper.getMainLooper())
        splashHandler!!.postDelayed({
            if (!isFinishing) splash.animate().alpha(0f).setDuration(300).withEndAction { if (!isFinishing) showHome() }.start()
        }, 1050)
    }

    private fun buildShell() {
        root.removeAllViews()
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = TomGlassUi.weatherBackground()
        }

        val header = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(10))
        }
        header.addView(TomGlassUi.logo(this, dp(44)), LinearLayout.LayoutParams(dp(44), dp(44)))
        val titleBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_VERTICAL }
        titleBox.addView(TomGlassUi.title(this, "TOM", 22f).apply { includeFontPadding = false }, LinearLayout.LayoutParams(-1, dp(27)))
        titleBox.addView(TomGlassUi.body(this, "Personal device intelligence").apply { includeFontPadding = false }, LinearLayout.LayoutParams(-1, dp(20)))
        header.addView(titleBox, LinearLayout.LayoutParams(0, dp(48), 1f).apply { leftMargin = dp(12) })
        header.addView(TomGlassUi.iconButton(this, "⚙", ::showSettings), LinearLayout.LayoutParams(dp(48), dp(48)))
        shell.addView(header, LinearLayout.LayoutParams(-1, -2))

        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(2), dp(18), dp(22))
        }
        shell.addView(ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS
            addView(content, LinearLayout.LayoutParams(-1, -2))
        }, LinearLayout.LayoutParams(-1, 0, 1f))

        nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(dp(8), dp(7), dp(8), dp(8))
            background = TomGlassUi.surface(this@MainActivity, 26f, Color.argb(235, 255, 255, 255))
        }
        shell.addView(nav, LinearLayout.LayoutParams(-1, dp(78)))
        root.addView(shell, FrameLayout.LayoutParams(-1, -1))
    }

    private fun showPage(selected: Int, title: String, subtitle: String, builder: () -> Unit) {
        if (!::content.isInitialized || root.childCount == 0) buildShell()
        content.removeAllViews()
        setNav(selected)
        add(TomGlassUi.title(this, title, 30f).apply { includeFontPadding = false }, 4)
        add(TomGlassUi.body(this, subtitle).apply { includeFontPadding = false; setLineSpacing(0f, 1.18f) }, 6)
        builder()
    }

    private fun add(view: View, top: Int = 12) {
        content.addView(view, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(top) })
        TomGlassUi.fadeIn(view)
    }

    private fun setNav(selected: Int) {
        nav.removeAllViews()
        val items = listOf("⌂" to "Home", "◉" to "Voice", "◌" to "Device", "☷" to "More")
        items.forEachIndexed { index, pair ->
            nav.addView(TomGlassUi.navItem(this, pair.first, pair.second, selected == index) {
                when (index) {
                    0 -> showHome()
                    1 -> showVoice()
                    2 -> showDevice()
                    else -> showMore()
                }
            }, LinearLayout.LayoutParams(0, dp(62), 1f).apply { setMargins(dp(3), 0, dp(3), 0) })
        }
    }

    private fun showHome() {
        showPage(0, "Good to see you", "A calm control center for your private AI companion.") {
            val hero = TomGlassUi.card(this, "TOM STATUS", "Checking Android capabilities and the local voice bridge…", null, null)
            add(hero, 18)
            status = TomGlassUi.body(this, "")
            status.setTextColor(TomGlassUi.brown)
            status.setPadding(dp(20), 0, dp(20), 0)
            content.addView(status, LinearLayout.LayoutParams(-1, dp(28)))
            refreshStatus()

            add(TomGlassUi.card(this, "Live voice", "Real microphone → WebSocket Core → ASR/reasoning → streaming speech. Voice can be interrupted while TOM is speaking.", "Open voice", ::showVoice), 10)
            add(TomGlassUi.card(this, "Device abilities", "Accessibility, notifications, screen capture, camera and overlay are independent Android capabilities. Grant only what you need.", "Open device controls", ::showDevice))
            add(TomGlassUi.card(this, "Secure connection", "Pairing and transport are separate from task success. Production actions must be verified after execution.", "Connection status", ::showDevice))
            add(TomGlassUi.section(this, "QUICK ACTIONS"), 18)
            add(TomGlassUi.button(this, "Permission center", ::showDevice), 4)
            add(TomGlassUi.button(this, "Choose TOM voice", ::showVoice), 7)
            add(TomGlassUi.button(this, "Settings", ::showSettings), 7)
        }
    }

    private fun showVoice() {
        showPage(1, "TOM voice", "A real-time voice surface with explicit start/stop control.") {
            add(TomGlassUi.card(this, "Current voice", voiceName(selectedVoice) + "\n\n16 kHz mono input • live WebSocket • 24 kHz mono output", null, null), 18)
            add(TomGlassUi.section(this, "VOICE LIBRARY"), 14)
            voiceChoice("tom_m1", "TOM • Rohit", "Warm, balanced Indian male voice", "Hindi • Hinglish • English")
            voiceChoice("tom_m2", "TOM • Aman", "Deeper, calm conversational voice", "Hindi • English")
            voiceChoice("tom_f1", "TOM • Divya", "Warm, expressive Indian female voice", "Hindi • Hinglish • English")
            add(TomGlassUi.section(this, "LIVE SESSION"), 18)
            add(TomGlassUi.card(this, "Barge-in", "When you speak while TOM is talking, the Android loop can interrupt playback instead of waiting for TTS to finish.", null, null))
            add(TomGlassUi.button(this, "Start selected voice", ::startVoice, true), 12)
            add(TomGlassUi.button(this, "Stop voice", { voiceLoop?.stop(); voiceLoop = null; updateVoiceStatus("Voice stopped") }), 8)
            add(TomGlassUi.button(this, "Microphone permission", { requestPermission(Manifest.permission.RECORD_AUDIO, 20) }), 8)
            add(TomGlassUi.section(this, "SESSION STATUS"), 18)
            add(TomGlassUi.card(this, "Transport", "${BuildConfig.TOM_VOICE_WS_URL}\n\nA configured endpoint is not proof of a successful connection. Runtime state is shown here only when the real loop reports it.", null, null))
        }
    }

    private fun voiceChoice(id: String, name: String, desc: String, languages: String) {
        val selected = id == selectedVoice
        add(TomGlassUi.card(this, name, "$desc\n$languages", if (selected) "Selected" else "Choose") {
            selectedVoice = id
            showVoice()
        }, 8)
    }

    private fun voiceName(id: String) = when (id) {
        "tom_m2" -> "TOM • Aman"
        "tom_f1" -> "TOM • Divya"
        else -> "TOM • Rohit"
    }

    private fun startVoice() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermission(Manifest.permission.RECORD_AUDIO, 20)
            return
        }
        voiceLoop?.stop()
        voiceLoop = TomVoiceLoop(this, BuildConfig.TOM_VOICE_WS_URL, voiceId = selectedVoice,
            onState = { state -> runOnUiThread { updateVoiceStatus("Voice • $state") } },
            onTranscript = { text -> runOnUiThread { updateVoiceStatus("You • $text") } },
            onError = { error -> runOnUiThread { updateVoiceStatus("Voice error • $error") } })
        voiceLoop?.start()
        updateVoiceStatus("Voice starting…")
    }

    private fun updateVoiceStatus(value: String) {
        if (::status.isInitialized) status.text = value
    }

    private fun showDevice() {
        showPage(2, "Device controls", "Real Android permissions and special access. Android remains authoritative.") {
            add(TomGlassUi.section(this, "CAPABILITIES"), 18)
            permissionCard("Microphone", "Live voice input and barge-in.", checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED, "Allow microphone") { requestPermission(Manifest.permission.RECORD_AUDIO, 20) }
            permissionCard("Accessibility", "Semantic UI observation and controlled device actions.", isAccessibilityEnabled(), "Open Accessibility") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
            permissionCard("Notification access", "Read notifications only when explicitly enabled.", isNotificationAccessEnabled(), "Open notification access") { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }
            permissionCard("Screen capture", "Fresh pixels for visual grounding and verification. Android asks for consent per capture session.", false, "Grant screen access") { requestScreenCapture() }
            permissionCard("Camera", "Explicit visual or video assistance.", checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED, "Allow camera") { requestPermission(Manifest.permission.CAMERA, 21) }
            permissionCard("Floating controls", "Optional overlay controls managed by Android.", Settings.canDrawOverlays(this), "Open overlay access") { startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))) }
            add(TomGlassUi.section(this, "CONNECTION"), 18)
            add(TomGlassUi.card(this, "Core endpoint", BuildConfig.TOM_VOICE_WS_URL + "\n\nDevelopment can use an emulator/LAN endpoint. Production should use authenticated WSS and protected credentials.", null, null))
            add(TomGlassUi.card(this, "Verification", "A network ACK is not task success. TOM should obtain fresh post-action evidence and keep UNKNOWN as a valid state.", null, null))
        }
    }

    private fun permissionCard(title: String, desc: String, granted: Boolean, action: String, onClick: () -> Unit) {
        add(TomGlassUi.card(this, title, desc, if (granted) "Enabled • Manage" else "Not enabled • $action") {
            onClick()
        }, 8)
    }

    private fun showMore() {
        showPage(3, "More", "Security, privacy, appearance and diagnostics without hiding important controls.") {
            add(TomGlassUi.card(this, "Appearance", "Weather-inspired sky tones, liquid-glass surfaces, restrained motion and native Android spacing.", "Open appearance", ::showAppearance), 18)
            add(TomGlassUi.card(this, "Safety rules", "Observation → planning → execution → verification. Consequential actions remain approval-gated.", "Safety", { showTextPage("Safety rules", safetyText()) }))
            add(TomGlassUi.card(this, "Privacy", "Microphone, notifications, screen pixels and accessibility data are sensitive and should be minimized and protected.", "Privacy", { showTextPage("Privacy", privacyText()) }))
            add(TomGlassUi.card(this, "Help & diagnostics", "Troubleshoot microphone, accessibility, WebSocket, permissions and model readiness.", "Diagnostics", { showTextPage("Help & diagnostics", helpText()) }))
            add(TomGlassUi.card(this, "About TOM", "Native Android bridge, real voice transport, explicit permissions and verifiable device actions.", "About", { showTextPage("About TOM", aboutText()) }))
            add(TomGlassUi.button(this, "Settings", ::showSettings), 14)
        }
    }

    private fun showSettings() {
        showPage(3, "Settings", "Clear Android-native controls with large touch targets and no hidden state.") {
            add(TomGlassUi.section(this, "VOICE"), 18)
            add(TomGlassUi.button(this, "Selected voice: ${voiceName(selectedVoice)}", ::showVoice), 5)
            add(TomGlassUi.section(this, "DEVICE"), 18)
            add(TomGlassUi.button(this, "Permission center", ::showDevice), 5)
            add(TomGlassUi.button(this, "Accessibility settings", { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }), 8)
            add(TomGlassUi.button(this, "Notification access", { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }), 8)
            add(TomGlassUi.section(this, "APPEARANCE"), 18)
            add(TomGlassUi.button(this, "Weather-inspired light theme", ::showAppearance), 5)
            add(TomGlassUi.section(this, "RESET"), 18)
            add(TomGlassUi.button(this, "Reset selected voice", { selectedVoice = "tom_m1"; showSettings() }), 5)
        }
    }

    private fun showAppearance() {
        showPage(3, "Appearance", "A polished weather-inspired Android interface: atmospheric, spacious and readable.") {
            add(TomGlassUi.card(this, "Atmosphere", "Soft sky neutrals, white translucent surfaces, subtle borders and restrained blue-gray accents create the visual foundation.", null, null), 18)
            add(TomGlassUi.card(this, "Liquid glass", "Glass is used as a surface treatment, not as a blur-heavy effect. Content remains readable and controls keep clear boundaries.", null, null))
            add(TomGlassUi.card(this, "Motion", "Short fade/slide transitions and tiny press compression keep interaction smooth without blocking the UI.", null, null))
            add(TomGlassUi.card(this, "Layout rules", "Scrollable content, wrap-content text, generous horizontal margins and system-bar-aware insets prevent clipping and overlap across phone sizes.", null, null))
        }
    }

    private fun showTextPage(title: String, text: String) {
        showPage(3, title, "TOM documentation") {
            add(TomGlassUi.card(this, "Overview", text, null, null), 18)
            add(TomGlassUi.button(this, "Back to More", ::showMore), 18)
        }
    }

    private fun refreshStatus() {
        if (!::status.isInitialized) return
        status.text = if (isAccessibilityEnabled()) "Accessibility • enabled" else "Accessibility • not enabled"
    }

    private fun isAccessibilityEnabled(): Boolean = runCatching {
        val services = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        services.split(':').any { it.contains(packageName, ignoreCase = true) }
    }.getOrDefault(false)

    private fun isNotificationAccessEnabled(): Boolean = runCatching {
        val enabled = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: return false
        enabled.split(':').any { it.contains(packageName, ignoreCase = true) }
    }.getOrDefault(false)

    private fun requestPermission(permission: String, code: Int) {
        if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(permission), code)
    }

    private fun requestScreenCapture() {
        val manager = getSystemService(MediaProjectionManager::class.java)
        if (manager != null) startActivityForResult(manager.createScreenCaptureIntent(), 31)
    }

    private fun safetyText() = "TOM separates fresh observation from execution and execution from verification. A WebSocket acknowledgement is not proof that an external action succeeded. Payments, purchases, destructive changes, messages and other consequential actions remain explicitly approved and must be verified afterward. If evidence is unavailable, the result stays UNKNOWN rather than triggering a blind retry."
    private fun privacyText() = "The Android bridge can access microphone audio, notifications, accessibility state, screen pixels, camera input and network transport only when the corresponding Android capability is enabled. These sources can contain sensitive information. Production deployments should use least privilege, protected credentials, authenticated transport, minimization and short retention. Revoked permissions are normal states and must never be bypassed."
    private fun helpText() = "Microphone: grant RECORD_AUDIO and start the real voice session. Accessibility: enable TOM under Android Settings → Accessibility. Notifications: enable TOM under notification listener access. Screen capture: Android asks for MediaProjection consent for a session. Voice transport: the development endpoint is ${BuildConfig.TOM_VOICE_WS_URL}; a physical phone normally needs the Core machine's LAN address, while production should use authenticated WSS."
    private fun aboutText() = "TOM is a native Android device bridge for a personal AI companion. The Android layer provides explicit capabilities, live voice transport, device observation and controlled execution. The interface is deliberately calm and weather-inspired, with liquid-glass surfaces, strong hierarchy and short native animations. The architecture treats observation, execution and verification as separate states so an unverified action never becomes a false success."
}
