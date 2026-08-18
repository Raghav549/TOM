package com.tom.device

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.animation.DecelerateInterpolator
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.switchmaterial.SwitchMaterial
import kotlin.math.min

/** TOM visual system: native Android primitives with a restrained liquid-glass surface language. */
object TomGlassUi {
    val ink = Color.rgb(25, 27, 30)
    val muted = Color.rgb(91, 98, 105)
    val brown = Color.rgb(76, 91, 104)
    val brownLight = Color.rgb(132, 151, 166)
    val cream = Color.rgb(244, 248, 251)
    val white = Color.WHITE
    val line = Color.rgb(218, 226, 232)
    val glass = Color.argb(218, 255, 255, 255)

    private fun dp(context: Context, value: Int): Int = (value * context.resources.displayMetrics.density).toInt()

    fun weatherBackground(): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        intArrayOf(Color.rgb(238, 247, 252), Color.rgb(248, 244, 250), Color.rgb(245, 248, 244))
    )

    fun surface(context: Context, radius: Float = 24f, color: Int = glass): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(context, radius.toInt()).toFloat()
            setColor(color)
            setStroke(dp(context, 1), Color.argb(145, 255, 255, 255))
        }

    private fun darkAction(context: Context): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        intArrayOf(Color.rgb(25, 35, 43), Color.rgb(66, 84, 96))
    ).apply { cornerRadius = dp(context, 22).toFloat() }

    fun darkActionForCard(context: Context): GradientDrawable = darkAction(context)

    fun text(context: Context, value: String, size: Float, color: Int = ink): TextView = TextView(context).apply {
        text = value
        textSize = size
        setTextColor(color)
        setLineSpacing(0f, 1.16f)
        includeFontPadding = false
        breakStrategy = android.text.Layout.BREAK_STRATEGY_HIGH_QUALITY
        hyphenationFrequency = android.text.Layout.HYPHENATION_FREQUENCY_NORMAL
    }

    fun title(context: Context, value: String, size: Float = 30f): TextView = text(context, value, size).apply {
        typeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.NORMAL)
        gravity = Gravity.CENTER_VERTICAL
    }

    fun body(context: Context, value: String): TextView = text(context, value, 14.5f, muted)

    fun logo(context: Context, size: Int = 64): View = object : View(context) {
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        private var phase = 0f
        private var animator: ValueAnimator? = null

        override fun onAttachedToWindow() {
            super.onAttachedToWindow()
            if (size >= 100) {
                animator = ValueAnimator.ofFloat(0f, 1f).apply {
                    duration = 2200
                    repeatCount = ValueAnimator.INFINITE
                    addUpdateListener { phase = it.animatedValue as Float; invalidate() }
                    start()
                }
            }
        }

        override fun onDetachedFromWindow() {
            animator?.cancel(); animator = null
            super.onDetachedFromWindow()
        }

        override fun onDraw(canvas: Canvas) {
            val s = min(width, height).toFloat()
            if (s <= 0f) return
            val cx = s / 2f; val cy = s / 2f
            paint.style = Paint.Style.FILL
            paint.color = Color.argb(235, 255, 255, 255)
            canvas.drawCircle(cx, cy, s * .47f, paint)
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = s * .014f
            paint.color = Color.argb(180, 195, 209, 218)
            canvas.drawCircle(cx, cy, s * .47f, paint)
            paint.strokeWidth = s * .043f
            paint.strokeCap = Paint.Cap.ROUND
            paint.color = ink
            val wave = Path().apply {
                moveTo(s * .21f, s * .57f)
                quadTo(s * .35f, s * .35f, s * .50f, s * .51f)
                quadTo(s * .66f, s * .69f, s * .80f, s * .37f)
            }
            canvas.drawPath(wave, paint)
            paint.style = Paint.Style.FILL
            paint.color = Color.rgb(88, 151, 184)
            canvas.drawCircle(s * .77f, s * .27f, s * .055f, paint)
            if (size >= 100) {
                val t = phase * 6.28318f
                paint.color = Color.argb(80, 70, 130, 165)
                for (i in 0 until 9) {
                    val a = t + i * .698f
                    val r = s * (.28f + .10f * (i % 3))
                    canvas.drawCircle(cx + kotlin.math.cos(a.toDouble()).toFloat() * r,
                        cy + kotlin.math.sin(a.toDouble()).toFloat() * r,
                        s * .012f, paint)
                }
            }
        }
    }.apply { layoutParams = ViewGroup.LayoutParams(size, size) }

    fun iconButton(context: Context, icon: String, onClick: () -> Unit): TextView = TextView(context).apply {
        text = icon; textSize = 20f; gravity = Gravity.CENTER; setTextColor(ink)
        background = surface(context, 17f, Color.argb(210, 255, 255, 255))
        minHeight = dp(context, 48); minWidth = dp(context, 48)
        isClickable = true; isFocusable = true
        contentDescription = "Settings"
        setOnClickListener { press(this); onClick() }
    }

    fun button(context: Context, label: String, onClick: () -> Unit, primary: Boolean = false): TextView = TextView(context).apply {
        text = label; textSize = 14f; gravity = Gravity.CENTER
        setPadding(dp(context, 12), 0, dp(context, 12), 0)
        minHeight = dp(context, 50)
        setTextColor(if (primary) white else ink)
        background = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(context, 18).toFloat()
            setColor(if (primary) ink else Color.argb(235, 255, 255, 255))
            setStroke(dp(context, 1), if (primary) Color.TRANSPARENT else line)
        }
        isClickable = true; isFocusable = true
        setOnClickListener { press(this); onClick() }
    }

    fun navItem(context: Context, icon: String, label: String, selected: Boolean, onClick: () -> Unit): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            setPadding(dp(context, 6), dp(context, 6), dp(context, 6), dp(context, 5))
            background = if (selected) darkAction(context) else null
            elevation = if (selected) dp(context, 4).toFloat() else 0f
            addView(text(context, icon, 19f, if (selected) white else muted).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, dp(context, 26)))
            addView(text(context, label, 11f, if (selected) white else muted).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, dp(context, 20)))
            isClickable = true; isFocusable = true; contentDescription = label
            setOnClickListener { press(this); onClick() }
        }

    fun card(context: Context, heading: String, description: String, action: String? = null, onClick: (() -> Unit)? = null): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 18), dp(context, 20), dp(context, 18))
            background = surface(context, 24f, Color.argb(222, 255, 255, 255))
            elevation = dp(context, 1).toFloat()
            addView(title(context, heading, 18f), LinearLayout.LayoutParams(-1, -2))
            addView(body(context, description).apply { setPadding(0, dp(context, 7), 0, if (action == null) 0 else dp(context, 12)) }, LinearLayout.LayoutParams(-1, -2))
            if (action != null && onClick != null) addView(button(context, action, onClick, false), LinearLayout.LayoutParams(-1, dp(context, 50)))
        }

    fun section(context: Context, value: String): TextView = text(context, value.uppercase(), 10.5f, brown).apply {
        letterSpacing = .15f; setPadding(dp(context, 3), dp(context, 10), dp(context, 3), dp(context, 5))
        typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
    }

    fun toggle(context: Context, checked: Boolean, onChanged: (Boolean) -> Unit): SwitchMaterial = SwitchMaterial(context).apply {
        isChecked = checked; minWidth = dp(context, 56); minHeight = dp(context, 48)
        setOnCheckedChangeListener { _, value -> press(this); onChanged(value) }
    }

    fun press(view: View) {
        view.animate().scaleX(.975f).scaleY(.975f).setDuration(65).withEndAction {
            view.animate().scaleX(1f).scaleY(1f).setDuration(170).setInterpolator(DecelerateInterpolator()).start()
        }.start()
    }

    fun fadeIn(view: View) {
        view.alpha = 0f; view.translationY = 10f
        view.animate().alpha(1f).translationY(0f).setDuration(280).setInterpolator(DecelerateInterpolator()).start()
    }

    fun animatePulse(view: View) {
        ValueAnimator.ofFloat(1f, 1.025f, 1f).apply {
            duration = 1400; repeatCount = ValueAnimator.INFINITE
            addUpdateListener { v -> val scale = v.animatedValue as Float; view.scaleX = scale; view.scaleY = scale }
            start()
        }
    }
}
