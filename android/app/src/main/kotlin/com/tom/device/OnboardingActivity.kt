package com.tom.device

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class OnboardingActivity : android.app.Activity() {
    private lateinit var root: FrameLayout
    private lateinit var content: LinearLayout
    private var step = 0
    private var language = "English"
    private var style = "Friendly"
    private var name = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.WHITE
        window.navigationBarColor = Color.WHITE
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR

        if (getPreferences(MODE_PRIVATE).getBoolean("completed", false)) {
            openMain()
            return
        }
        root = FrameLayout(this)
        setContentView(root)
        showSystemSplash()
    }

    private fun showSystemSplash() {
        val splash = FrameLayout(this).apply { setBackgroundColor(Color.WHITE) }
        val progress = TextView(this).apply {
            text = "0%"
            gravity = Gravity.CENTER
            textSize = 13f
            setTextColor(TomGlassUi.brown)
            setPadding(0, 14, 0, 0)
        }
        val center = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            addView(TomGlassUi.logo(this@OnboardingActivity, 150), LinearLayout.LayoutParams(150, 150))
            addView(TomGlassUi.title(this@OnboardingActivity, "TOM", 40f).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 54))
            addView(TomGlassUi.body(this@OnboardingActivity, "Building your private AI companion").apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 32))
            addView(progress, LinearLayout.LayoutParams(-1, 42))
        }
        splash.addView(center, FrameLayout.LayoutParams(-1, -1))
        root.addView(splash, FrameLayout.LayoutParams(-1, -1))
        center.alpha = 0f
        center.animate().alpha(1f).setDuration(500).start()

        var value = 0
        val tick = object : Runnable {
            override fun run() {
                value = (value + 4).coerceAtMost(100)
                progress.text = "$value%"
                center.scaleX = .98f + value / 100f * .02f
                if (value < 100) Handler(Looper.getMainLooper()).postDelayed(this, 45)
                else Handler(Looper.getMainLooper()).postDelayed({
                    splash.animate().alpha(0f).setDuration(350).withEndAction {
                        root.removeView(splash)
                        showStep()
                    }.start()
                }, 250)
            }
        }
        Handler(Looper.getMainLooper()).postDelayed(tick, 80)
    }

    private fun showStep() {
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 28, 24, 28)
        }
        root.removeAllViews()
        root.addView(ScrollView(this).apply {
            isFillViewport = true
            addView(content)
        }, FrameLayout.LayoutParams(-1, -1))

        when (step) {
            0 -> languageStep()
            1 -> personalizeStep()
            else -> permissionStep()
        }
    }

    private fun top(title: String, subtitle: String) {
        val row = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            addView(TomGlassUi.logo(this@OnboardingActivity, 44), LinearLayout.LayoutParams(44, 44))
            addView(TomGlassUi.title(this@OnboardingActivity, "TOM", 22f).apply { setPadding(12, 0, 0, 0) }, LinearLayout.LayoutParams(0, 44, 1f))
            addView(TomGlassUi.body(this@OnboardingActivity, "${step + 1}/3").apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(45, 44))
        }
        content.addView(row)
        content.addView(TomGlassUi.title(this, title, 31f).apply { setPadding(0, 42, 0, 4) }, LinearLayout.LayoutParams(-1, -2))
        content.addView(TomGlassUi.body(this, subtitle), LinearLayout.LayoutParams(-1, -2))
    }

    private fun languageStep() {
        top("How should TOM speak?", "Choose your default conversation language. You can change it later in Voice settings.")
        section("LANGUAGE")
        listOf("English", "Hindi", "Hinglish", "Bengali").forEach { item ->
            choice(item, item == language) { language = item; showStep() }
        }
        bottom("Continue", { step = 1; showStep() })
    }

    private fun personalizeStep() {
        top("Make TOM feel like yours", "Give the companion a name and choose the character style you want to hear in everyday conversation.")
        section("YOUR NAME")
        val input = EditText(this).apply {
            hint = "What should TOM call you?"
            textSize = 16f
            setSingleLine(true)
            setPadding(18, 14, 18, 14)
            background = TomGlassUi.surface(this@OnboardingActivity, 20f, TomGlassUi.cream)
            setText(name)
        }
        content.addView(input, LinearLayout.LayoutParams(-1, 56).apply { setMargins(0, 10, 0, 0) })
        section("CHARACTER")
        listOf("Friendly", "Calm", "Playful", "Focused").forEach { item ->
            choice(item, item == style) { style = item; showStep() }
        }
        val note = TomGlassUi.card(this, "Private by default", "Your choices are stored locally for this Android setup flow. They become inputs to TOM's character and voice configuration when the Core is connected.")
        content.addView(note, LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, 18, 0, 0) })
        bottom("Continue", { name = input.text.toString().trim(); step = 2; showStep() })
        skip("Skip personalization") { name = ""; step = 2; showStep() }
    }

    private fun permissionStep() {
        top("Give TOM the right capabilities", "Nothing is silently enabled. Android's own permission and special-access screens stay in control.")
        section("CAPABILITIES")
        capability("Microphone", "Required for live voice conversations.", "Later")
        capability("Accessibility", "Required only for device UI observation and controlled actions.", "Later")
        capability("Notifications", "Optional notification assistance.", "Later")
        capability("Screen capture", "Optional visual grounding with Android consent.", "Later")
        capability("Camera", "Optional visual/video assistance.", "Later")
        val security = TomGlassUi.card(this, "Safety first", "High-impact actions remain approval-gated. Missing evidence stays unknown. TOM does not treat a transport acknowledgement as proof that something happened.")
        content.addView(security, LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, 18, 0, 0) })
        bottom("Finish setup", { saveAndOpen() })
        skip("Skip for now") { saveAndOpen() }
    }

    private fun section(value: String) {
        content.addView(TomGlassUi.section(this, value), LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, 26, 0, 0) })
    }

    private fun choice(label: String, selected: Boolean, onClick: () -> Unit) {
        val row = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(18, 14, 14, 14)
            background = if (selected) TomGlassUi.darkActionForCard() else TomGlassUi.surface(this@OnboardingActivity, 20f, TomGlassUi.cream)
            isClickable = true
            setOnClickListener { TomGlassUi.press(this); onClick() }
            addView(TomGlassUi.title(this@OnboardingActivity, label, 16f).apply { setTextColor(if (selected) Color.WHITE else TomGlassUi.ink) }, LinearLayout.LayoutParams(0, 52, 1f))
            addView(TomGlassUi.body(this@OnboardingActivity, if (selected) "Selected" else "Choose").apply { setTextColor(if (selected) Color.WHITE else TomGlassUi.brown) }, LinearLayout.LayoutParams(70, 52))
        }
        content.addView(row, LinearLayout.LayoutParams(-1, 60).apply { setMargins(0, 8, 0, 0) })
    }

    private fun capability(title: String, desc: String, state: String) {
        val card = TomGlassUi.card(this, title, desc, state) { }
        content.addView(card, LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, 8, 0, 0) })
    }

    private fun bottom(label: String, onClick: () -> Unit) {
        content.addView(TomGlassUi.button(this, label, onClick, true), LinearLayout.LayoutParams(-1, 52).apply { setMargins(0, 28, 0, 0) })
    }

    private fun skip(label: String, onClick: () -> Unit) {
        content.addView(TomGlassUi.text(this, label, 14f, TomGlassUi.brown).apply {
            gravity = Gravity.CENTER
            setPadding(0, 20, 0, 10)
            isClickable = true
            setOnClickListener { onClick() }
        }, LinearLayout.LayoutParams(-1, 48))
    }

    private fun saveAndOpen() {
        getPreferences(MODE_PRIVATE).edit()
            .putBoolean("completed", true)
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
