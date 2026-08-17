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
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import com.google.android.material.card.MaterialCardView
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout

class OnboardingActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var content: LinearLayout
    private var step = 0
    private var language = "English"
    private var style = "Friendly"
    private var name = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT
        window.decorView.systemUiVisibility =
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR

        root = FrameLayout(this)
        setContentView(root)

        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )
            view.updatePadding(
                left = bars.left,
                top = bars.top,
                right = bars.right,
                bottom = bars.bottom
            )
            insets
        }

        if (getPreferences(MODE_PRIVATE).getBoolean("completed", false)) {
            openMain()
            return
        }
        showSystemSplash()
    }

    override fun onResume() {
        super.onResume()
        if (::content.isInitialized && step == 2) {
            showStep()
        }
    }

    private fun showSystemSplash() {
        val splash = FrameLayout(this)
        splash.setBackgroundColor(Color.WHITE)

        val progressLabel = TextView(this)
        progressLabel.gravity = Gravity.CENTER
        progressLabel.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
        progressLabel.setTextColor(TomGlassUi.brown)
        progressLabel.text = "0%"

        val bar = LinearProgressIndicator(this)
        bar.max = 100
        bar.trackThickness = 5
        bar.indicatorColor = TomGlassUi.brown
        bar.trackColor = Color.rgb(238, 233, 228)
        bar.setProgressCompat(0, false)

        val center = LinearLayout(this)
        center.orientation = LinearLayout.VERTICAL
        center.gravity = Gravity.CENTER_HORIZONTAL
        center.setPadding(32, 32, 32, 32)
        center.addView(
            TomGlassUi.logo(this, 154),
            LinearLayout.LayoutParams(154, 154)
        )
        val title = TomGlassUi.title(this, "TOM", 42f)
        title.gravity = Gravity.CENTER
        title.setPadding(0, 18, 0, 0)
        center.addView(title, LinearLayout.LayoutParams(-1, 66))

        val subtitle = TomGlassUi.body(this, "Building your private AI companion")
        subtitle.gravity = Gravity.CENTER
        center.addView(subtitle, LinearLayout.LayoutParams(-1, 40))
        val barParams = LinearLayout.LayoutParams(-1, 5)
        barParams.setMargins(28, 18, 28, 0)
        center.addView(bar, barParams)
        val progressParams = LinearLayout.LayoutParams(-1, 40)
        progressParams.setMargins(0, 4, 0, 0)
        center.addView(progressLabel, progressParams)

        splash.addView(center, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER))
        root.addView(splash, FrameLayout.LayoutParams(-1, -1))

        center.alpha = 0f
        center.scaleX = 0.94f
        center.scaleY = 0.94f
        center.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(650).start()

        var value = 0
        val tick = object : Runnable {
            override fun run() {
                value = (value + 2).coerceAtMost(100)
                bar.setProgressCompat(value, false)
                progressLabel.text = "$value%"
                if (value < 100) {
                    Handler(Looper.getMainLooper()).postDelayed(this, 34)
                } else {
                    Handler(Looper.getMainLooper()).postDelayed({
                        splash.animate().alpha(0f).setDuration(360).withEndAction {
                            root.removeView(splash)
                            showStep()
                        }.start()
                    }, 220)
                }
            }
        }
        Handler(Looper.getMainLooper()).postDelayed(tick, 80)
    }

    private fun showStep() {
        content = LinearLayout(this)
        content.orientation = LinearLayout.VERTICAL
        content.setPadding(24, 22, 24, 32)

        root.removeAllViews()
        val scroll = ScrollView(this)
        scroll.isFillViewport = true
        scroll.clipToPadding = false
        scroll.addView(content)
        root.addView(scroll, FrameLayout.LayoutParams(-1, -1))

        when (step) {
            0 -> languageStep()
            1 -> personalizeStep()
            else -> permissionStep()
        }
    }

    private fun top(title: String, subtitle: String) {
        val row = LinearLayout(this)
        row.gravity = Gravity.CENTER_VERTICAL
        row.addView(TomGlassUi.logo(this, 42), LinearLayout.LayoutParams(42, 42))

        val brand = TomGlassUi.title(this, "TOM", 21f)
        brand.setPadding(11, 0, 0, 0)
        row.addView(brand, LinearLayout.LayoutParams(0, 48, 1f))

        val page = TomGlassUi.body(this, "${step + 1} of 3")
        page.gravity = Gravity.CENTER
        row.addView(page, LinearLayout.LayoutParams(60, 48))
        content.addView(row)

        val heading = TomGlassUi.title(this, title, 30f)
        heading.setPadding(0, 34, 0, 5)
        content.addView(heading, LinearLayout.LayoutParams(-1, -2))
        content.addView(TomGlassUi.body(this, subtitle), LinearLayout.LayoutParams(-1, -2))
    }

    private fun languageStep() {
        top(
            "How should TOM speak?",
            "Choose the language you normally use. You can change this later without repeating setup."
        )
        section("LANGUAGE")
        listOf("English", "Hindi", "Hinglish", "Bengali").forEach { item ->
            choice(item, item == language) {
                language = item
                showStep()
            }
        }
        bottom("Continue") {
            step = 1
            showStep()
        }
    }

    private fun personalizeStep() {
        top(
            "Make TOM feel like yours",
            "Set the name and character style TOM should use when the connected Core starts a voice session."
        )
        section("YOUR NAME")

        val inputLayout = TextInputLayout(this)
        inputLayout.hint = "What should TOM call you?"
        inputLayout.boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
        inputLayout.setBoxCornerRadii(16f, 16f, 16f, 16f)
        inputLayout.boxStrokeColor = TomGlassUi.brown

        val input = TextInputEditText(this)
        input.setSingleLine(true)
        input.setText(name)
        input.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        inputLayout.addView(input, LinearLayout.LayoutParams(-1, 58))

        val inputParams = LinearLayout.LayoutParams(-1, -2)
        inputParams.setMargins(0, 10, 0, 0)
        content.addView(inputLayout, inputParams)

        section("CHARACTER")
        listOf("Friendly", "Calm", "Playful", "Focused").forEach { item ->
            choice(item, item == style) {
                style = item
                showStep()
            }
        }

        addInfoCard(
            "Private by default",
            "Your setup choices stay on this phone and are sent to the Core as session preferences only when a live connection is started."
        )

        bottom("Continue") {
            name = input.text?.toString()?.trim().orEmpty()
            step = 2
            showStep()
        }
        skip("Skip personalization") {
            name = ""
            step = 2
            showStep()
        }
    }

    private fun permissionStep() {
        top(
            "Connect TOM to your phone",
            "These are real Android capabilities. Each button opens the Android permission or special-access flow; nothing here is a fake switch."
        )
        section("CAPABILITIES")

        permissionCard(
            "Microphone",
            "Live voice input and barge-in.",
            micGranted(),
            "Allow microphone"
        ) {
            requestPermission(Manifest.permission.RECORD_AUDIO, 20)
        }
        permissionCard(
            "Accessibility",
            "UI observation and controlled device actions.",
            accessibilityGranted(),
            "Open Accessibility"
        ) {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        permissionCard(
            "Notification access",
            "Read notifications only after you explicitly enable TOM's listener.",
            notificationAccessGranted(),
            "Open notification access"
        ) {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
        permissionCard(
            "Screen capture",
            "Fresh screen pixels for visual grounding and verification. Android asks every capture session.",
            false,
            "Grant screen access"
        ) {
            requestScreenCapture()
        }
        permissionCard(
            "Camera",
            "Explicit visual/video assistance.",
            cameraGranted(),
            "Allow camera"
        ) {
            requestPermission(Manifest.permission.CAMERA, 21)
        }
        permissionCard(
            "Floating controls",
            "Optional overlay controls. Android owns this special access.",
            overlayGranted(),
            "Open overlay access"
        ) {
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
            )
        }

        addInfoCard(
            "Safety boundary",
            "Permissions do not authorize actions by themselves. High-impact actions remain approval-gated, and missing verification evidence remains UNKNOWN."
        )
        bottom("Finish setup") { saveAndOpen() }
        skip("Skip permissions for now") { saveAndOpen() }
    }

    private fun section(value: String) {
        val params = LinearLayout.LayoutParams(-1, -2)
        params.setMargins(0, 25, 0, 0)
        content.addView(TomGlassUi.section(this, value), params)
    }

    private fun choice(label: String, selected: Boolean, onClick: () -> Unit) {
        val card = MaterialCardView(this)
        card.radius = 17f
        card.cardElevation = 0f
        card.strokeWidth = 1
        card.strokeColor = if (selected) TomGlassUi.brown else Color.rgb(229, 224, 219)
        card.setCardBackgroundColor(
            if (selected) Color.rgb(250, 245, 240) else Color.WHITE
        )
        card.isClickable = true
        card.isFocusable = true
        card.setOnClickListener {
            TomGlassUi.press(card)
            onClick()
        }

        val row = LinearLayout(this)
        row.gravity = Gravity.CENTER_VERTICAL
        row.setPadding(18, 4, 12, 4)
        row.addView(
            TomGlassUi.title(this, label, 16f),
            LinearLayout.LayoutParams(0, 50, 1f)
        )
        val state = TomGlassUi.body(this, if (selected) "Selected" else "Choose")
        state.setTextColor(TomGlassUi.brown)
        row.addView(state, LinearLayout.LayoutParams(66, 50))
        card.addView(row, ViewGroup.LayoutParams(-1, 58))

        val params = LinearLayout.LayoutParams(-1, 58)
        params.setMargins(0, 8, 0, 0)
        content.addView(card, params)
    }

    private fun permissionCard(
        title: String,
        desc: String,
        granted: Boolean,
        action: String,
        onClick: () -> Unit
    ) {
        val card = MaterialCardView(this)
        card.radius = 20f
        card.cardElevation = 1f
        card.strokeWidth = 1
        card.strokeColor = Color.rgb(229, 224, 219)
        card.setCardBackgroundColor(Color.WHITE)

        val body = LinearLayout(this)
        body.orientation = LinearLayout.VERTICAL
        body.setPadding(18, 16, 18, 16)

        val head = LinearLayout(this)
        head.gravity = Gravity.CENTER_VERTICAL
        head.addView(
            TomGlassUi.title(this, title, 17f),
            LinearLayout.LayoutParams(0, 30, 1f)
        )
        val status = TomGlassUi.body(this, if (granted) "Enabled" else "Not enabled")
        status.setTextColor(if (granted) TomGlassUi.brown else TomGlassUi.muted)
        status.gravity = Gravity.CENTER
        head.addView(status, LinearLayout.LayoutParams(88, 30))
        body.addView(head)

        val description = TomGlassUi.body(this, desc)
        description.setPadding(0, 4, 0, 12)
        body.addView(description)
        body.addView(
            TomGlassUi.button(this, if (granted) "Manage" else action, onClick, granted),
            LinearLayout.LayoutParams(-1, 50)
        )

        card.addView(body, ViewGroup.LayoutParams(-1, -2))
        val params = LinearLayout.LayoutParams(-1, -2)
        params.setMargins(0, 9, 0, 0)
        content.addView(card, params)
    }

    private fun addInfoCard(title: String, description: String) {
        val params = LinearLayout.LayoutParams(-1, -2)
        params.setMargins(0, 18, 0, 0)
        content.addView(TomGlassUi.card(this, title, description), params)
    }

    private fun bottom(label: String, onClick: () -> Unit) {
        val params = LinearLayout.LayoutParams(-1, 52)
        params.setMargins(0, 28, 0, 0)
        content.addView(TomGlassUi.button(this, label, onClick, true), params)
    }

    private fun skip(label: String, onClick: () -> Unit) {
        val view = TomGlassUi.text(this, label, 14f, TomGlassUi.brown)
        view.gravity = Gravity.CENTER
        view.setPadding(0, 17, 0, 8)
        view.isClickable = true
        view.isFocusable = true
        view.setOnClickListener { onClick() }
        content.addView(view, LinearLayout.LayoutParams(-1, 48))
    }

    private fun micGranted(): Boolean =
        checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun cameraGranted(): Boolean =
        checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    private fun accessibilityGranted(): Boolean = runCatching {
        val services = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false
        services.split(':').any { it.contains(packageName, ignoreCase = true) }
    }.getOrDefault(false)

    private fun notificationAccessGranted(): Boolean = runCatching {
        val enabled = Settings.Secure.getString(
            contentResolver,
            "enabled_notification_listeners"
        ) ?: return false
        enabled.split(':').any { it.contains(packageName, ignoreCase = true) }
    }.getOrDefault(false)

    private fun overlayGranted(): Boolean = Settings.canDrawOverlays(this)

    private fun requestPermission(permission: String, code: Int) {
        if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(permission), code)
        }
    }

    private fun requestScreenCapture() {
        val manager = getSystemService(MediaProjectionManager::class.java)
        startActivityForResult(manager.createScreenCaptureIntent(), 31)
    }

    private fun saveAndOpen() {
        getSharedPreferences("tom_preferences", MODE_PRIVATE)
            .edit()
            .putBoolean("onboarding_completed", true)
            .putString("language", language)
            .putString("name", name)
            .putString("character", style)
            .apply()

        getPreferences(MODE_PRIVATE)
            .edit()
            .putBoolean("completed", true)
            .apply()
        openMain()
    }

    private fun openMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }
}
