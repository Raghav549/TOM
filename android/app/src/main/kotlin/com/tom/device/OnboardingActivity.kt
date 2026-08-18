package com.tom.device

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import com.google.android.material.progressindicator.LinearProgressIndicator

class OnboardingActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var content: LinearLayout
    private val mainHandler = Handler(Looper.getMainLooper())
    private var splashRunnable: Runnable? = null
    private var step = 0
    private var language = "English"
    private var style = "Friendly"
    private var name = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.WHITE
        window.navigationBarColor = Color.WHITE
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR

        root = FrameLayout(this)
        root.setBackgroundColor(Color.rgb(246, 250, 253))
        setContentView(root)

        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.updatePadding(left = bars.left, top = bars.top, right = bars.right, bottom = bars.bottom)
            insets
        }

        val completed = getSharedPreferences("tom_preferences", MODE_PRIVATE).getBoolean("onboarding_completed", false)
        if (completed) openMain() else showSplash()
    }

    override fun onDestroy() {
        splashRunnable?.let(mainHandler::removeCallbacks)
        mainHandler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun showSplash() {
        root.removeAllViews()
        val splash = FrameLayout(this).apply { setBackgroundColor(Color.rgb(239, 247, 252)) }
        val stack = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(28), dp(28), dp(28), dp(28))
        }

        val logo = TomGlassUi.logo(this, dp(128))
        stack.addView(logo, LinearLayout.LayoutParams(dp(128), dp(128)))

        val title = TomGlassUi.title(this, "TOM", 40f).apply {
            gravity = Gravity.CENTER
            includeFontPadding = false
        }
        stack.addView(title, LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(14) })

        val subtitle = TomGlassUi.body(this, "Observe  •  Understand  •  Assist").apply {
            gravity = Gravity.CENTER
            includeFontPadding = false
        }
        stack.addView(subtitle, LinearLayout.LayoutParams(-1, dp(28)).apply { topMargin = dp(4) })

        val progress = LinearProgressIndicator(this).apply {
            max = 100
            trackThickness = dp(4)
            setIndicatorColor(TomGlassUi.brown)
            trackColor = Color.rgb(222, 232, 239)
            setProgressCompat(0, false)
        }
        stack.addView(progress, LinearLayout.LayoutParams(-1, dp(4)).apply {
            leftMargin = dp(30); rightMargin = dp(30); topMargin = dp(26)
        })

        val percent = TomGlassUi.body(this, "0%").apply {
            gravity = Gravity.CENTER
            includeFontPadding = false
        }
        stack.addView(percent, LinearLayout.LayoutParams(-1, dp(28)).apply { topMargin = dp(6) })

        splash.addView(stack, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER))
        root.addView(splash, FrameLayout.LayoutParams(-1, -1))

        stack.alpha = 0f
        stack.scaleX = .94f
        stack.scaleY = .94f
        stack.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(520).start()

        var value = 0
        splashRunnable = object : Runnable {
            override fun run() {
                if (isFinishing || splash.parent == null) return
                value = (value + 4).coerceAtMost(100)
                progress.setProgressCompat(value, true)
                percent.text = "$value%"
                if (value < 100) {
                    mainHandler.postDelayed(this, 42)
                } else {
                    mainHandler.postDelayed({
                        if (isFinishing || splash.parent == null) return@postDelayed
                        splash.animate().alpha(0f).setDuration(280).withEndAction {
                            if (!isFinishing) showStep()
                        }.start()
                    }, 180)
                }
            }
        }
        mainHandler.postDelayed(splashRunnable!!, 80)
    }

    private fun showStep() {
        root.removeAllViews()
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22), dp(20), dp(22), dp(28))
        }
        val scroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS
            addView(content, ViewGroup.LayoutParams(-1, -2))
        }
        root.addView(scroll, FrameLayout.LayoutParams(-1, -1))
        when (step) {
            0 -> languageStep()
            1 -> personalizeStep()
            else -> permissionStep()
        }
    }

    private fun top(title: String, subtitle: String) {
        val header = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        header.addView(TomGlassUi.logo(this, dp(44)), LinearLayout.LayoutParams(dp(44), dp(44)))
        val brand = TomGlassUi.title(this, "TOM", 21f).apply { includeFontPadding = false }
        header.addView(brand, LinearLayout.LayoutParams(0, dp(44), 1f).apply { leftMargin = dp(11) })
        header.addView(TomGlassUi.body(this, "${step + 1} / 3").apply { gravity = Gravity.CENTER; includeFontPadding = false }, LinearLayout.LayoutParams(dp(55), dp(44)))
        content.addView(header)

        val heading = TomGlassUi.title(this, title, 29f).apply {
            includeFontPadding = false
            setLineSpacing(0f, 1.05f)
        }
        content.addView(heading, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(30) })
        val sub = TomGlassUi.body(this, subtitle).apply { includeFontPadding = false; setLineSpacing(0f, 1.18f) }
        content.addView(sub, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
    }

    private fun section(value: String) {
        content.addView(TomGlassUi.section(this, value), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(22) })
    }

    private fun languageStep() {
        top("How should TOM speak?", "Choose the language you normally use. You can change this later in Settings.")
        section("LANGUAGE")
        listOf("English", "Hindi", "Hinglish", "Bengali").forEach { item -> choice(item, item == language) { language = item; showStep() } }
        primaryButton("Continue") { step = 1; showStep() }
    }

    private fun personalizeStep() {
        top("Make TOM feel like yours", "Set the name and character style TOM should use in conversation.")
        section("YOUR NAME")
        val input = EditText(this).apply {
            hint = "What should TOM call you?"
            text = name
            textSize = 16f
            singleLine = true
            setTextColor(TomGlassUi.ink)
            setHintTextColor(TomGlassUi.muted)
            setPadding(dp(16), 0, dp(16), 0)
            background = rounded(Color.WHITE, 16, TomGlassUi.line)
        }
        content.addView(input, LinearLayout.LayoutParams(-1, dp(56)).apply { topMargin = dp(10) })

        section("CHARACTER")
        listOf("Friendly", "Calm", "Playful", "Focused").forEach { item -> choice(item, item == style) { style = item; showStep() } }
        infoCard("Private by default", "Your choices stay on this phone and are sent to the Core only when a live session starts.")
        primaryButton("Continue") { name = input.text?.toString()?.trim().orEmpty(); step = 2; showStep() }
        secondaryText("Skip personalization") { name = ""; step = 2; showStep() }
    }

    private fun permissionStep() {
        top("Connect TOM to your phone", "Every control below opens the real Android permission or special-access screen. Nothing is a fake switch.")
        section("CAPABILITIES")
        permissionCard("Microphone", "Live voice input and barge-in.", micGranted(), "Allow microphone") { requestPermission(Manifest.permission.RECORD_AUDIO, 20) }
        permissionCard("Accessibility", "UI observation and controlled device actions.", accessibilityGranted(), "Open Accessibility") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        permissionCard("Notification access", "Read notifications only after you explicitly enable TOM.", notificationAccessGranted(), "Open notification access") { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }
        permissionCard("Screen capture", "Fresh screen pixels for visual grounding and verification.", false, "Grant screen access") { requestScreenCapture() }
        permissionCard("Camera", "Explicit visual/video assistance.", cameraGranted(), "Allow camera") { requestPermission(Manifest.permission.CAMERA, 21) }
        permissionCard("Floating controls", "Optional overlay controls managed by Android.", overlayGranted(), "Open overlay access") { startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))) }
        infoCard("Safety boundary", "Permissions never equal authorization. High-impact actions remain approval-gated and missing verification remains UNKNOWN.")
        primaryButton("Finish setup") { saveAndOpen() }
        secondaryText("Skip permissions for now") { saveAndOpen() }
    }

    private fun choice(label: String, selected: Boolean, onClick: () -> Unit) {
        val card = com.google.android.material.card.MaterialCardView(this).apply {
            radius = dp(17).toFloat()
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = if (selected) TomGlassUi.brown else TomGlassUi.line
            setCardBackgroundColor(if (selected) Color.rgb(250, 245, 240) else Color.WHITE)
            isClickable = true
            isFocusable = true
            setOnClickListener { TomGlassUi.press(this); onClick() }
        }
        val row = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; setPadding(dp(17), 0, dp(12), 0) }
        row.addView(TomGlassUi.title(this, label, 16f).apply { includeFontPadding = false }, LinearLayout.LayoutParams(0, dp(54), 1f))
        row.addView(TomGlassUi.body(this, if (selected) "Selected" else "Choose").apply { gravity = Gravity.CENTER; setTextColor(TomGlassUi.brown); includeFontPadding = false }, LinearLayout.LayoutParams(dp(72), dp(54)))
        card.addView(row, ViewGroup.LayoutParams(-1, dp(56)))
        content.addView(card, LinearLayout.LayoutParams(-1, dp(58)).apply { topMargin = dp(8) })
    }

    private fun permissionCard(title: String, desc: String, granted: Boolean, action: String, onClick: () -> Unit) {
        val card = com.google.android.material.card.MaterialCardView(this).apply {
            radius = dp(20).toFloat()
            cardElevation = dp(1).toFloat()
            strokeWidth = dp(1)
            strokeColor = TomGlassUi.line
            setCardBackgroundColor(Color.WHITE)
        }
        val body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(17), dp(15), dp(17), dp(15)) }
        val head = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        head.addView(TomGlassUi.title(this, title, 17f).apply { includeFontPadding = false }, LinearLayout.LayoutParams(0, dp(27), 1f))
        head.addView(TomGlassUi.body(this, if (granted) "Enabled" else "Not enabled").apply { gravity = Gravity.CENTER; includeFontPadding = false; setTextColor(if (granted) TomGlassUi.brown else TomGlassUi.muted) }, LinearLayout.LayoutParams(dp(90), dp(27)))
        body.addView(head)
        body.addView(TomGlassUi.body(this, desc).apply { includeFontPadding = false; setPadding(0, dp(5), 0, dp(11)) })
        body.addView(TomGlassUi.button(this, if (granted) "Manage" else action, onClick, granted), LinearLayout.LayoutParams(-1, dp(50)))
        card.addView(body, ViewGroup.LayoutParams(-1, -2))
        content.addView(card, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(9) })
    }

    private fun infoCard(title: String, description: String) {
        content.addView(TomGlassUi.card(this, title, description), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(18) })
    }

    private fun primaryButton(label: String, onClick: () -> Unit) {
        content.addView(TomGlassUi.button(this, label, onClick, true), LinearLayout.LayoutParams(-1, dp(54)).apply { topMargin = dp(26) })
    }

    private fun secondaryText(label: String, onClick: () -> Unit) {
        content.addView(TomGlassUi.text(this, label, 14f, TomGlassUi.brown).apply {
            gravity = Gravity.CENTER
            includeFontPadding = false
            isClickable = true
            isFocusable = true
            setPadding(0, dp(15), 0, dp(8))
            setOnClickListener { onClick() }
        }, LinearLayout.LayoutParams(-1, dp(50)))
    }

    private fun rounded(fill: Int, radius: Int, stroke: Int): GradientDrawable = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        cornerRadius = dp(radius).toFloat()
        setColor(fill)
        setStroke(dp(1), stroke)
    }

    private fun micGranted() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    private fun cameraGranted() = checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    private fun accessibilityGranted(): Boolean = runCatching {
        val services = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        services.split(':').any { it.contains(packageName, ignoreCase = true) }
    }.getOrDefault(false)
    private fun notificationAccessGranted(): Boolean = runCatching {
        val enabled = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: return false
        enabled.split(':').any { it.contains(packageName, ignoreCase = true) }
    }.getOrDefault(false)
    private fun overlayGranted() = Settings.canDrawOverlays(this)
    private fun requestPermission(permission: String, code: Int) {
        if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(permission), code)
    }
    private fun requestScreenCapture() {
        val manager = getSystemService(MediaProjectionManager::class.java)
        if (manager != null) startActivityForResult(manager.createScreenCaptureIntent(), 31)
    }
    private fun saveAndOpen() {
        getSharedPreferences("tom_preferences", MODE_PRIVATE).edit()
            .putBoolean("onboarding_completed", true)
            .putString("language", language)
            .putString("name", name)
            .putString("character", style)
            .apply()
        openMain()
    }
    private fun openMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }
}
