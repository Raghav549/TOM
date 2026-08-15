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

class MainActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var content: LinearLayout
    private lateinit var nav: LinearLayout
    private lateinit var status: TextView
    private var voiceLoop: TomVoiceLoop? = null
    private var selectedVoice = "tom_m1"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.rgb(238, 245, 249)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
        setContentView(buildShell())
        showSplash()
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) refreshStatus()
    }

    override fun onDestroy() {
        voiceLoop?.stop()
        voiceLoop = null
        super.onDestroy()
    }

    private fun buildShell(): View {
        root = FrameLayout(this)
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = TomGlassUi.weatherBackground()
        }
        val header = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(20, 18, 20, 10)
            addView(TomGlassUi.logo(this@MainActivity, 48), LinearLayout.LayoutParams(48, 48))
            val titleBox = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(13, 0, 0, 0)
                addView(TomGlassUi.title(this@MainActivity, "TOM", 25f), LinearLayout.LayoutParams(-1, 31))
                addView(TomGlassUi.body(this@MainActivity, "Your personal device intelligence"), LinearLayout.LayoutParams(-1, 23))
            }
            addView(titleBox, LinearLayout.LayoutParams(0, -2, 1f))
            addView(TomGlassUi.iconButton(this@MainActivity, "⚙", ::showSettings), LinearLayout.LayoutParams(48, 48))
        }
        shell.addView(header, LinearLayout.LayoutParams(-1, -2))
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 2, 18, 20) }
        shell.addView(ScrollView(this).apply {
            isFillViewport = true
            addView(content)
            clipToPadding = false
        }, LinearLayout.LayoutParams(-1, 0, 1f))
        nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(10, 8, 10, 10)
            background = TomGlassUi.surface(this@MainActivity, 28f, Color.argb(244, 255, 255, 255))
        }
        shell.addView(nav, LinearLayout.LayoutParams(-1, 82))
        root.addView(shell, FrameLayout.LayoutParams(-1, -1))
        return root
    }

    private fun showSplash() {
        val splash = FrameLayout(this).apply { setBackgroundColor(Color.rgb(235, 245, 251)) }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            addView(TomGlassUi.logo(this@MainActivity, 116), LinearLayout.LayoutParams(116, 116))
            addView(TomGlassUi.title(this@MainActivity, "TOM", 42f).apply { gravity = Gravity.CENTER; setPadding(0, 14, 0, 0) }, LinearLayout.LayoutParams(-1, 60))
            addView(TomGlassUi.body(this@MainActivity, "Observe • Understand • Assist").apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 34))
        }
        splash.addView(box, FrameLayout.LayoutParams(-1, -1))
        root.addView(splash, FrameLayout.LayoutParams(-1, -1))
        box.alpha = 0f; box.scaleX = .88f; box.scaleY = .88f
        box.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(600).start()
        Handler(Looper.getMainLooper()).postDelayed({
            splash.animate().alpha(0f).setDuration(420).withEndAction {
                root.removeView(splash); showHome()
            }.start()
        }, 1100)
    }

    private fun add(view: View, top: Int = 12) {
        content.addView(view, LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, top, 0, 0) })
        TomGlassUi.fadeIn(view)
    }

    private fun heading(title: String, subtitle: String = "") {
        add(TomGlassUi.title(this, title, 30f), 4)
        if (subtitle.isNotBlank()) add(TomGlassUi.body(this, subtitle), 4)
    }

    private fun setNav(selected: Int) {
        nav.removeAllViews()
        listOf(Triple("⌂", "Home", 0), Triple("◉", "Voice", 1), Triple("◌", "Connect", 2), Triple("☷", "More", 3)).forEach { item ->
            nav.addView(TomGlassUi.navItem(this, item.first, item.second, selected == item.third) {
                when (item.third) { 0 -> showHome(); 1 -> showVoice(); 2 -> showConnection(); else -> showMore() }
            }, LinearLayout.LayoutParams(0, 66, 1f).apply { setMargins(3, 0, 3, 0) })
        }
    }

    private fun showHome() {
        content.removeAllViews(); setNav(0)
        heading("Good to see you", "A calm Android-native control center for your private AI companion.")
        val hero = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(24, 22, 24, 24)
            background = TomGlassUi.surface(this@MainActivity, 30f, Color.argb(235, 245, 250, 253))
            addView(TomGlassUi.body(this@MainActivity, "TOM STATUS"), LinearLayout.LayoutParams(-1, 22))
            addView(TomGlassUi.title(this@MainActivity, if (isAccessibilityEnabled()) "Ready" else "Almost ready", 42f), LinearLayout.LayoutParams(-1, 55))
            addView(TomGlassUi.body(this@MainActivity, if (isAccessibilityEnabled()) "Device bridge is available. Start a voice session or connect your Core." else "Grant the capabilities you actually want. Android stays in control of every special permission."), LinearLayout.LayoutParams(-1, -2))
            status = TomGlassUi.body(this@MainActivity, ""); status.setPadding(0, 13, 0, 0)
            addView(status, LinearLayout.LayoutParams(-1, -2))
        }
        add(hero, 16); refreshStatus()
        add(TomGlassUi.card(this, "Live voice", "Natural microphone → ASR → reasoning → expressive streaming speech. Barge-in is designed to interrupt TOM without waiting for a sentence to finish.", "Open voice", ::showVoice), 18)
        add(TomGlassUi.card(this, "Device abilities", "Accessibility, notifications, screen capture, camera and overlay are separated so you can approve only what you need.", "Permission center", ::showPermissions))
        add(TomGlassUi.card(this, "Secure connection", "Pair this phone with a trusted TOM Core and keep production credentials inside Android Keystore rather than the UI.", "Connection", ::showConnection))
        add(TomGlassUi.section(this, "QUICK CONTROLS"), 20)
        add(TomGlassUi.button(this, "Review permissions", ::showPermissions), 5)
        add(TomGlassUi.button(this, "Choose TOM voice", ::showVoice), 8)
        add(TomGlassUi.button(this, "Open settings", ::showSettings), 8)
    }

    private fun showVoice() {
        content.removeAllViews(); setNav(1)
        heading("TOM voice", "Choose the personality of the voice loop. Every option is explicit, cancellable and connected to the same real transport.")
        add(TomGlassUi.card(this, "Listening mode", "Continuous audio frames are delivered to the Core while the session is active. Neural VAD and turn prediction decide boundaries; local Android echo cancellation reduces speaker feedback.", null, null), 16)
        add(TomGlassUi.section(this, "VOICE LIBRARY"), 18)
        voiceCard("tom_m1", "TOM • Rohit", "Warm, balanced Indian male voice • natural conversational delivery", "Hindi • Hinglish • English")
        voiceCard("tom_m2", "TOM • Aman", "Slightly deeper, calm male voice • focused and composed", "Hindi • English")
        voiceCard("tom_f1", "TOM • Divya", "Warm Indian female voice • friendly and expressive", "Hindi • Hinglish • English")
        add(TomGlassUi.section(this, "VOICE BEHAVIOUR"), 20)
        add(TomGlassUi.card(this, "Natural pacing", "TOM can vary speaking rate around a stable baseline, insert sentence and phrase pauses, and adapt energy without using random fake effects.", null, null))
        add(TomGlassUi.card(this, "Emotion", "Warm, calm, curious, empathetic, concerned, happy, amused, excited and serious delivery are represented as explicit style signals for the TTS adapter.", null, null))
        add(TomGlassUi.card(this, "Barge-in", "When you begin speaking while TOM is talking, the Android loop sends an interrupt event and immediately drains playback. The server remains authoritative for turn completion.", null, null))
        add(TomGlassUi.card(this, "Audio pipeline", "16 kHz mono PCM input → live WebSocket → ASR/prosody/turn prediction → response → 24 kHz PCM output. No fake prerecorded response is used by the Android loop.", "Start selected voice", ::startVoice), 14)
        add(TomGlassUi.section(this, "VOICE SETTINGS"), 20)
        add(TomGlassUi.button(this, "Open full voice settings", ::showVoiceSettings), 5)
        add(TomGlassUi.button(this, "Test microphone permission", { requestPermission(Manifest.permission.RECORD_AUDIO, 20) }), 8)
    }

    private fun voiceCard(id: String, name: String, desc: String, languages: String) {
        val selected = id == selectedVoice
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(18, 16, 14, 16)
            background = TomGlassUi.surface(this@MainActivity, 25f, if (selected) Color.rgb(232, 243, 251) else Color.WHITE)
            addView(TomGlassUi.logo(this@MainActivity, 48), LinearLayout.LayoutParams(48, 48))
            val info = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL; setPadding(13, 0, 8, 0)
                addView(TomGlassUi.title(this@MainActivity, name, 17f), LinearLayout.LayoutParams(-1, 29))
                addView(TomGlassUi.body(this@MainActivity, desc), LinearLayout.LayoutParams(-1, -2))
                addView(TomGlassUi.body(this@MainActivity, languages), LinearLayout.LayoutParams(-1, -2))
            }
            addView(info, LinearLayout.LayoutParams(0, -2, 1f))
            addView(TomGlassUi.button(this@MainActivity, if (selected) "Selected" else "Choose", { selectedVoice = id; showVoice() }, selected), LinearLayout.LayoutParams(105, 50))
            isClickable = true; setOnClickListener { selectedVoice = id; showVoice() }
        }
        add(card, 8)
    }

    private fun showVoiceSettings() {
        content.removeAllViews(); setNav(1)
        heading("Voice settings", "Fine control over how TOM sounds and when it should speak.")
        add(TomGlassUi.section(this, "CONVERSATION"), 16)
        add(TomGlassUi.card(this, "Speaking rate", "Default: natural. Slow delivery is preferred for explanations and emotional moments; faster delivery is reserved for concise confirmations.", null, null))
        add(TomGlassUi.card(this, "Pitch", "Pitch changes are intentionally subtle. The system should preserve voice identity instead of turning every response into an effect.", null, null))
        add(TomGlassUi.card(this, "Warmth", "Warmth controls prosody and descriptive style for supported TTS models. It does not alter the meaning or system policy.", null, null))
        add(TomGlassUi.card(this, "Backchannels", "Optional short acknowledgement cues can be enabled in the Core. They must never interrupt your own speech or pretend TOM understood something it did not.", null, null))
        add(TomGlassUi.section(this, "LANGUAGE"), 20)
        add(TomGlassUi.card(this, "Hindi", "Native Hindi output when the model supports it. Devanagari remains untouched in the text pipeline.", null, null))
        add(TomGlassUi.card(this, "Hinglish", "Mixed Hindi-English conversation uses the same semantic response while the TTS adapter chooses an appropriate multilingual speaker.", null, null))
        add(TomGlassUi.card(this, "English", "Clear conversational English with the selected TOM voice profile.", null, null))
        add(TomGlassUi.section(this, "RESET"), 20)
        add(TomGlassUi.button(this, "Reset voice preferences", { selectedVoice = "tom_m1"; showVoice() }))
    }

    private fun startVoice() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) { requestPermission(Manifest.permission.RECORD_AUDIO, 20); return }
        voiceLoop?.stop()
        voiceLoop = TomVoiceLoop(this, BuildConfig.TOM_VOICE_WS_URL, voiceId = selectedVoice,
            onState = { state -> runOnUiThread { if (::status.isInitialized) status.text = "Voice • $state" } },
            onTranscript = { text -> runOnUiThread { if (::status.isInitialized) status.text = "You • $text" } },
            onError = { error -> runOnUiThread { if (::status.isInitialized) status.text = "Voice error • $error" } })
        voiceLoop?.start(); showVoice()
    }

    private fun showConnection() {
        content.removeAllViews(); setNav(2)
        heading("Device connection", "A calm surface for the serious part: secure pairing and live transport health.")
        add(TomGlassUi.card(this, "Current endpoint", "${BuildConfig.TOM_VOICE_WS_URL}\n\nDevelopment builds may use an emulator/LAN endpoint. Production should use WSS, authenticated pairing and certificate-validated transport.", null, null), 16)
        add(TomGlassUi.card(this, "Secure pairing", "The production pairing flow should issue a short-lived code or QR, bind it to this device, then store the resulting credential in Android Keystore. Never display long-lived secrets on this screen.", "Pair device", ::showPairingInfo))
        add(TomGlassUi.card(this, "Transport health", "A connection is not success by itself. TOM tracks authenticated session state, observation freshness, action acknowledgements and post-action verification separately.", "Readiness check", ::showReadyCheck))
        add(TomGlassUi.section(this, "NETWORK BEHAVIOUR"), 20)
        add(TomGlassUi.card(this, "Reconnect policy", "Temporary network loss may reconnect with backoff. A reconnect never replays a consequential action. Unknown state stays UNKNOWN until fresh observation verifies it.", null, null))
        add(TomGlassUi.card(this, "Privacy on transport", "Only capabilities required by the active session should be streamed. Sensitive device data is not included merely because the transport is connected.", null, null))
        add(TomGlassUi.card(this, "LAN testing", "For a physical phone, replace the emulator host in the build configuration with the Core machine's LAN address. Keep both devices on a trusted network during development.", null, null))
        add(TomGlassUi.section(this, "DIAGNOSTICS"), 20)
        add(TomGlassUi.button(this, "Open Android network settings", { startActivity(Intent(Settings.ACTION_WIRELESS_SETTINGS)) }), 5)
        add(TomGlassUi.button(this, "Run local readiness check", ::showReadyCheck), 8)
    }

    private fun showMore() {
        content.removeAllViews(); setNav(3)
        heading("More", "Everything important that should not be hidden behind a tiny overflow menu.")
        add(TomGlassUi.card(this, "Permissions & privacy", "Review every sensitive Android capability, why it exists, and how TOM handles it.", "Open permission center", ::showPermissions), 16)
        add(TomGlassUi.card(this, "Appearance", "Choose the calm weather-inspired visual system and motion behaviour.", "Appearance", ::showAppearance))
        add(TomGlassUi.card(this, "Safety rules", "Consequential actions, uncertainty, approvals, retries and recovery are explicit.", "Safety", ::showSafety))
        add(TomGlassUi.card(this, "Privacy policy", "A detailed long-form explanation of device data, voice data, permissions, transport, retention and deletion.", "Privacy policy", { showLongPage("Privacy policy", privacySections()) }))
        add(TomGlassUi.card(this, "Open-source licenses", "TOM's license plus third-party dependency notices and model licensing responsibilities.", "Licenses", { showLongPage("Licenses & notices", licenseSections()) }))
        add(TomGlassUi.card(this, "Help & diagnostics", "Troubleshooting for microphone, accessibility, WebSocket, model loading, playback and Android permissions.", "Help", { showLongPage("Help & diagnostics", helpSections()) }))
        add(TomGlassUi.card(this, "About TOM", "Build identity, architecture, voice stack and project principles.", "About", { showLongPage("About TOM", aboutSections()) }))
        add(TomGlassUi.card(this, "Settings", "Voice, connection, notifications, privacy and reset controls.", "Open settings", ::showSettings))
    }

    private fun showSettings() {
        content.removeAllViews(); setNav(3)
        heading("Settings", "Native Android settings-style controls with large touch targets and clear explanations.")
        add(TomGlassUi.section(this, "VOICE"), 16)
        add(TomGlassUi.button(this, "Selected voice: $selectedVoice", ::showVoiceSettings), 5)
        add(TomGlassUi.button(this, "Voice library", ::showVoice), 8)
        add(TomGlassUi.section(this, "DEVICE"), 20)
        add(TomGlassUi.button(this, "Permission center", ::showPermissions), 5)
        add(TomGlassUi.button(this, "Accessibility settings", ::openAccessibility), 8)
        add(TomGlassUi.button(this, "Notification access", { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }), 8)
        add(TomGlassUi.section(this, "CONNECTION"), 20)
        add(TomGlassUi.button(this, "Connection & pairing", ::showConnection), 5)
        add(TomGlassUi.section(this, "APP"), 20)
        add(TomGlassUi.button(this, "Appearance & motion", ::showAppearance), 5)
        add(TomGlassUi.button(this, "Privacy policy", { showLongPage("Privacy policy", privacySections()) }), 8)
        add(TomGlassUi.button(this, "Licenses & notices", { showLongPage("Licenses & notices", licenseSections()) }), 8)
        add(TomGlassUi.button(this, "About TOM", { showLongPage("About TOM", aboutSections()) }), 8)
        add(TomGlassUi.section(this, "RESET"), 20)
        add(TomGlassUi.card(this, "Reset local preferences", "This build keeps the selected voice in memory only. Production preferences should be stored in encrypted app storage and reset here without touching server data.", "Reset voice", { selectedVoice = "tom_m1"; showSettings() }))
    }

    private fun showAppearance() {
        content.removeAllViews(); setNav(3)
        heading("Appearance", "Inspired by polished weather apps: airy surfaces, atmospheric backgrounds, oversized status, soft motion and strong readability.")
        add(TomGlassUi.card(this, "Weather-inspired", "The design uses sky/cloud neutrals, white translucent surfaces, a restrained blue accent and warm status highlights. It intentionally avoids a generic black cyberpunk dashboard.", null, null), 16)
        add(TomGlassUi.card(this, "Native Android feel", "Large touch targets, edge-aware spacing, system typography, light status/navigation bars, scrollable settings pages and clear hierarchy are used instead of web-like controls.", null, null))
        add(TomGlassUi.card(this, "Motion", "Buttons compress on touch, pages fade upward, the splash scales gently, and important status elements can pulse without becoming distracting.", null, null))
        add(TomGlassUi.card(this, "Accessibility", "High-contrast text, predictable navigation order, focusable controls and generous tap areas are preferred. Motion should remain secondary to content.", null, null))
        add(TomGlassUi.section(this, "THEME"), 20)
        add(TomGlassUi.button(this, "Light sky • active", {}), 5)
        add(TomGlassUi.button(this, "Reduce motion (system setting)", { showTextPage("Motion", "Android system animation settings remain authoritative. TOM keeps motion short and functional so the interface still works when system animation scales are reduced.") }), 8)
        add(TomGlassUi.section(this, "BRAND"), 20)
        add(TomGlassUi.card(this, "TOM mark", "The app mark is drawn locally as a simple atmospheric signal: a curved communication path plus a warm status point inside a clean circular field. No external image asset is required for the core icon.", null, null))
    }

    private fun showPermissions() {
        content.removeAllViews(); setNav(3)
        heading("Permission center", "One capability at a time. Android's own consent screens remain the source of truth.")
        add(TomGlassUi.card(this, "Microphone", "Used by the live voice loop. TOM needs RECORD_AUDIO to capture PCM from the microphone. Stop the voice session to release the recorder.", "Allow microphone", { requestPermission(Manifest.permission.RECORD_AUDIO, 20) }), 16)
        add(TomGlassUi.card(this, "Accessibility", "Used for semantic UI observation and explicitly permitted actions. Enable only if you want device-control features.", "Open Accessibility", ::openAccessibility))
        add(TomGlassUi.card(this, "Notifications", "The notification listener can read notifications only after you explicitly enable the Android service. It should be disabled if you do not need notification assistance.", "Open notification access", { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }))
        add(TomGlassUi.card(this, "Screen capture", "MediaProjection gives TOM actual pixels for visual verification. Android displays a consent dialog for every capture session.", "Request screen capture", ::requestScreenCapture))
        add(TomGlassUi.card(this, "Camera", "Reserved for explicit camera/video assistance. It is not needed for normal text or voice use.", "Allow camera", { requestPermission(Manifest.permission.CAMERA, 21) }))
        add(TomGlassUi.card(this, "Overlay", "Optional floating controls. Android manages this as special access and TOM should never silently grant it.", "Open overlay access", { startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))) }))
        add(TomGlassUi.section(this, "PERMISSION PRINCIPLES"), 22)
        add(TomGlassUi.card(this, "Least privilege", "A capability should be requested only when a user action needs it. A connected Core does not automatically justify every Android permission.", null, null))
        add(TomGlassUi.card(this, "Revocation", "You can revoke permissions from Android Settings. TOM must handle missing access as a normal state and should not loop on permission requests.", null, null))
        add(TomGlassUi.card(this, "Sensitive data", "Microphone, notifications, screen pixels and accessibility trees can contain highly sensitive information. Production deployments should apply authentication, minimization and retention limits at the Core as well.", null, null))
    }

    private fun showSafety() = showLongPage("Safety rules", safetySections())

    private fun showTextPage(title: String, text: String) = showLongPage(title, listOf("Overview" to text, "How it works" to "TOM separates observation, planning, execution and verification. A successful network response is not treated as proof that a consequential device action actually happened.", "User control" to "The Android app keeps powerful capabilities behind explicit system permissions and user-facing controls."))

    private fun showLongPage(title: String, sections: List<Pair<String, String>>) {
        content.removeAllViews(); setNav(3)
        heading(title, "Detailed reference • scroll freely • no hidden sections")
        sections.forEachIndexed { index, section ->
            add(TomGlassUi.section(this, "${index + 1}. ${section.first}"), if (index == 0) 16 else 24)
            add(TomGlassUi.card(this, section.first, section.second, null, null), 5)
        }
        add(TomGlassUi.button(this, "Back to More", ::showMore), 26)
    }

    private fun privacySections() = listOf(
        "Scope" to "This Android app is a device-side bridge for TOM. It can interact with microphones, accessibility services, notifications, screen capture, camera and network transport only when the relevant Android capability is enabled. The app should not infer consent from installation alone.",
        "Microphone & voice" to "During a live voice session, the microphone produces PCM audio frames for speech recognition, prosody analysis, turn prediction and response generation. Audio handling must follow the active session boundary. When the session stops, the recorder and playback objects are released.",
        "Accessibility data" to "Accessibility trees may contain text, labels, buttons, account information and other sensitive UI state. TOM should observe only what is needed for the requested task and avoid persisting full UI trees unless a separate, explicit diagnostic workflow requires it.",
        "Screen images" to "MediaProjection provides pixels for visual grounding. Android asks for user consent for the capture session. Screen images can contain passwords, messages, financial information and private photographs, so the Core should process them minimally and avoid unnecessary retention.",
        "Notifications" to "If notification access is enabled, the notification listener can see notification content. This permission is optional. Users can revoke it at any time through Android Settings.",
        "Camera" to "Camera access is intended for explicit visual or video-assistance workflows. It is not required for ordinary voice conversations and should remain disabled otherwise.",
        "Network transport" to "Development builds may use a local WebSocket endpoint. Production deployments should use authenticated WSS, certificate validation, replay protection and short-lived device credentials. A network connection is not itself authorization for every action.",
        "Retention" to "The Android bridge should keep ephemeral audio, pixels and UI observations in memory whenever possible. Server-side retention must be separately configured and documented. Logs should avoid secrets and unnecessary personal content.",
        "Security" to "Production credentials belong in Android Keystore or an equivalent protected credential store. Never place long-lived secrets in source code, screenshots, chat messages or ordinary preferences. Device pairing should bind credentials to the intended phone.",
        "User controls" to "The user can stop voice, revoke permissions, disable accessibility, disable notification access, stop screen capture and remove the app. TOM should treat revoked access as a normal state rather than trying to work around Android controls.",
        "Sensitive contexts" to "Do not use autonomous device control in situations where a user cannot understand or supervise the consequences. High-impact account, payment, legal, medical or security actions should remain explicitly approved and verified.",
        "Changes" to "Privacy documentation should be versioned whenever data handling, model routing, retention or permissions change. Production releases should identify the build and document material changes before deployment."
    )

    private fun licenseSections() = listOf(
        "Project license" to "TOM's project code is intended to be distributed under the Apache License 2.0 as represented by the repository LICENSE file. The license text in the repository is the authoritative project notice.",
        "Android components" to "The Android app uses AndroidX and Android platform APIs. Their respective licenses and notices remain applicable. Distribution builds should retain required third-party notices.",
        "OkHttp" to "The voice transport uses OkHttp. OkHttp is an open-source project with its own license and notice requirements. Do not remove upstream copyright or license notices from a redistribution.",
        "Voice models" to "TTS, ASR, VAD and turn-prediction models are separate intellectual-property artifacts. Their model cards and licenses govern redistribution, commercial use, gated access and attribution. A software license does not automatically license a model.",
        "Indic Parler" to "The Indic Parler adapter is an integration layer. The exact upstream model and any gated model weights must be used according to the upstream model card, terms and license. Keep model provenance documented in production deployments.",
        "Smart Turn" to "The Smart Turn ONNX integration is designed around the open upstream model family and its published terms. Keep the downloaded model's license and attribution alongside deployment artifacts.",
        "Apache obligations" to "If you redistribute Apache-licensed code, retain the license, preserve copyright notices and include required NOTICE information when applicable. Modified files should be identifiable where the license requires it.",
        "Trademark" to "Open-source licensing does not grant trademark rights. Names and logos may have separate brand restrictions. Use the repository's current branding policy when distributing modified builds.",
        "No warranty" to "Open-source software is provided according to its license terms. Production deployments should independently test security, reliability, model quality, privacy and device compatibility before use.",
        "Model downloads" to "The model downloader intentionally keeps gated-model instructions visible instead of embedding credentials. Accept upstream terms through the official provider when required and provide credentials through secure environment configuration.",
        "Notices" to "A release-quality APK should ship with a complete third-party notices screen or document. This UI page is the product-facing summary; repository LICENSE and dependency metadata remain authoritative.",
        "Build provenance" to "Record the source commit, model versions, dependency lock state and Android build version for each production artifact. This makes security reviews and bug reproduction practical."
    )

    private fun helpSections() = listOf(
        "APK build" to "If the GitHub Android workflow fails, inspect the first Kotlin or Gradle compilation error. A later summary such as 'Build failed' is only the consequence. Re-run after the exact source error is fixed.",
        "Ruff test" to "The Python CI has separate installation, pytest and Ruff stages. If installation succeeds and pytest passes but Ruff fails, the runtime tests are healthy and the failure is a static-style check. Run ruff check . locally or use the exact CI output.",
        "Microphone" to "Confirm Android microphone permission, make sure another app is not exclusively holding the audio input, then start the voice session again. If the endpoint is unreachable, microphone capture can still initialize but the WebSocket will fail separately.",
        "Voice playback" to "The Android loop expects 24 kHz mono PCM output from the Core. If the server sends a different codec or sample rate, playback may sound wrong. Keep audio format metadata explicit in the WebSocket protocol.",
        "Barge-in" to "Barge-in depends on microphone frames continuing while TOM speaks. Android echo cancellation reduces feedback but is device-dependent. The server's VAD and turn predictor remain authoritative for conversational turn completion.",
        "WebSocket" to "An emulator may reach the host through 10.0.2.2, while a physical phone normally needs the Core machine's LAN IP or DNS name. Production should use WSS and authenticated pairing rather than a plain local ws URL.",
        "Accessibility" to "Open Android Settings → Accessibility → installed services and enable TOM. Android may display additional security warnings. TOM should not request or bypass this through another mechanism.",
        "Notifications" to "Notification access is under Android's notification listener settings. If disabled, notification features should simply show unavailable rather than repeatedly requesting access.",
        "Screen capture" to "MediaProjection consent is session-based. Start capture only after the user presses the control and accept the Android dialog. A previous grant should not be assumed to last forever.",
        "Camera" to "Camera is not needed for voice. If camera assistance is used, grant CAMERA only when the feature requests it and release the camera when the feature ends.",
        "Connection health" to "Use the readiness page to distinguish accessibility state, endpoint configuration and model availability. 'Connected' should never be displayed as 'task completed'. Verification happens after the action.",
        "Model loading" to "If Indic Parler or another neural voice model fails, inspect model path, Python extra dependencies, upstream model terms and available RAM/VRAM. Keep optional model dependencies out of the minimal core installation."
    )

    private fun aboutSections() = listOf(
        "What TOM is" to "TOM is a personal AI device bridge designed around observation, reasoning, controlled execution and verification. The Android app is the local surface through which a user grants capabilities and starts live interactions.",
        "Design direction" to "The UI deliberately borrows the calm visual language of polished weather apps: large atmospheric status, airy cards, soft sky tones, clear information hierarchy and restrained motion. It is an inspiration for visual clarity, not a copy of any specific application.",
        "Android architecture" to "The app uses native Android Activity/View APIs for predictable device behaviour. The shell contains a scrollable content area and a custom animated bottom navigation. Sensitive capabilities continue to flow through Android's own permission and special-access screens.",
        "Voice architecture" to "The live loop captures 16 kHz mono PCM, sends continuous frames to a WebSocket Core, receives transcript/state events and streams 24 kHz PCM to AudioTrack. Android echo cancellation is enabled when the platform exposes it.",
        "Turn-taking" to "The Core can combine neural VAD, prosody, transcript state and Smart Turn-style endpoint prediction. The Android side also detects local speech energy to issue a low-latency interruption signal when TOM is talking.",
        "Expressive speech" to "The voice stack exposes explicit style signals such as warmth, emotion, pitch, speaking rate and pause cues. Expressiveness is intended to improve communication rather than fabricate certainty or manipulate a user.",
        "Safety model" to "TOM distinguishes observation from execution and execution from verification. If post-action state is unknown, the correct state is UNKNOWN, not a blind retry. Consequential actions should remain approval-gated.",
        "Open-source approach" to "Core runtime code should favour auditable, local or open components where practical. Optional model adapters remain modular so deployments can choose the hardware and licensing terms that fit them.",
        "No fake demo layer" to "The Android voice control is wired to a real WebSocket, real AudioRecord and real AudioTrack. A UI status label is not treated as proof that a model answered. Production monitoring should expose real transport and model state.",
        "Build identity" to "This development build uses application ID com.tom.device and a versioned Android build pipeline. Each release should record its source commit, model versions and dependency state.",
        "Project principles" to "Private by default, explicit permissions, observable actions, verifiable outcomes, graceful uncertainty, real functionality over demo placeholders and a calm interface that does not get in the user's way.",
        "Release readiness" to "Before public distribution, add signed release configuration, secure WSS pairing, encrypted credential storage, complete third-party notices, accessibility testing, device matrix testing and end-to-end voice/model tests on representative hardware."
    )

    private fun safetySections() = listOf(
        "User authority" to "TOM assists the user; it does not silently become the owner of the device. Android permission prompts, special-access screens and user actions remain authoritative.",
        "Observation first" to "Before acting, TOM should ground itself in fresh UI or API state. Stale observations should expire. Missing evidence is not evidence of success.",
        "Approval gates" to "Payments, purchases, destructive deletes, messages, account changes and other consequential operations should require explicit approval unless the user has intentionally configured a narrowly scoped policy.",
        "Transport ACK is not success" to "A WebSocket acknowledgement means a message was received or queued. It does not prove that the external side effect occurred. TOM must verify the post-action state.",
        "Unknown state" to "If verification is unavailable, label the outcome UNKNOWN and stop. Never retry a consequential action merely because a confirmation did not arrive.",
        "Interruptibility" to "Voice sessions must be stoppable. Barge-in should interrupt speech without waiting for TTS to finish. Device-control plans should also expose a clear stop path.",
        "Least privilege" to "Only request the Android capability required for the active task. Accessibility, notifications, screen capture, camera, microphone and overlay should remain independently controllable.",
        "No credential leakage" to "Never put API keys, pairing secrets, cookies, tokens or passwords in UI logs, screenshots, source control or model prompts. Use protected credential storage and redacted diagnostics.",
        "External side effects" to "Sending a message, editing a document, changing an account setting or purchasing something can affect other people. TOM should state what it intends to do and verify what actually happened.",
        "Recovery" to "When a tool fails, recover using fresh observation and an explicit plan. Do not chain retries indefinitely or repeat actions whose state cannot be determined.",
        "Model uncertainty" to "ASR, vision, VAD, turn prediction and LLM outputs are probabilistic. A confident model response is not equivalent to verified device state.",
        "Production checklist" to "Use WSS, authenticated pairing, Android Keystore, short-lived credentials, audit logs without secrets, explicit approvals, fresh verification, model version pinning and end-to-end tests before enabling autonomous device actions."
    )

    private fun showPairingInfo() = showTextPage("Secure pairing", "Pairing should be a short-lived, user-visible operation. The server issues a code or QR, the phone proves its identity, and the resulting credential is stored in Android Keystore. The app should never ask the user to paste a long-lived token into a normal text field.")

    private fun showReadyCheck() = showLongPage("Readiness check", listOf(
        "Accessibility" to if (isAccessibilityEnabled()) "ENABLED — Android has granted the accessibility service." else "NOT ENABLED — voice can still work, but UI observation/actions are unavailable.",
        "Voice endpoint" to BuildConfig.TOM_VOICE_WS_URL,
        "Selected voice" to selectedVoice,
        "Microphone" to if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) "GRANTED" else "NOT GRANTED",
        "Core requirements" to "The Core machine must have its ASR, reasoning model, turn prediction/VAD and TTS adapters configured. The Android app does not pretend those models exist merely because the UI is installed.",
        "Production requirements" to "Use WSS, authenticated pairing, protected credentials, pinned model versions and post-action verification before enabling consequential device actions."
    ))

    private fun refreshStatus() {
        if (!::status.isInitialized) return
        status.text = if (isAccessibilityEnabled()) "Accessibility • enabled" else "Accessibility • not enabled"
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
