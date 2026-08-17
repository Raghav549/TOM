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
import kotlin.math.min

object TomGlassUi {
    val ink = Color.rgb(22, 22, 22)
    val muted = Color.rgb(104, 99, 95)
    val brown = Color.rgb(122, 78, 47)
    val brownLight = Color.rgb(176, 128, 91)
    val cream = Color.rgb(249, 247, 244)
    val white = Color.WHITE
    val line = Color.rgb(231, 226, 221)

    fun weatherBackground(): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        intArrayOf(Color.WHITE, Color.rgb(252, 250, 248), Color.rgb(248, 246, 243))
    )

    fun surface(context: Context, radius: Float = 24f, color: Int = white): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = radius
            setColor(color)
            setStroke(1, line)
        }

    private fun darkAction(): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.LEFT_RIGHT,
        intArrayOf(Color.rgb(18, 18, 18), brown)
    ).apply { cornerRadius = 22f }

    fun text(context: Context, value: String, size: Float, color: Int = ink): TextView = TextView(context).apply {
        text = value
        textSize = size
        setTextColor(color)
        setLineSpacing(2f, 1.08f)
        includeFontPadding = true
    }

    fun title(context: Context, value: String, size: Float = 30f): TextView = text(context, value, size).apply {
        typeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.NORMAL)
        gravity = Gravity.CENTER_VERTICAL
    }

    fun body(context: Context, value: String): TextView = text(context, value, 15f, muted)

    fun logo(context: Context, size: Int = 64): View = object : View(context) {
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        private var phase = 0f
        private var animator: ValueAnimator? = null

        override fun onAttachedToWindow() {
            super.onAttachedToWindow()
            if (size >= 100) {
                animator = ValueAnimator.ofFloat(0f, 1f).apply {
                    duration = 1800
                    repeatCount = ValueAnimator.INFINITE
                    addUpdateListener { phase = it.animatedValue as Float; invalidate() }
                    start()
                }
            }
        }

        override fun onDetachedFromWindow() {
            animator?.cancel()
            animator = null
            super.onDetachedFromWindow()
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val s = min(width, height).toFloat()
            val cx = s / 2f
            val cy = s / 2f

            paint.style = Paint.Style.FILL
            paint.color = Color.rgb(250, 248, 245)
            canvas.drawCircle(cx, cy, s * .47f, paint)
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = s * .018f
            paint.color = Color.rgb(224, 217, 210)
            canvas.drawCircle(cx, cy, s * .47f, paint)

            paint.strokeWidth = s * .045f
            paint.strokeCap = Paint.Cap.ROUND
            paint.color = ink
            val wave = Path().apply {
                moveTo(s * .22f, s * .56f)
                quadTo(s * .35f, s * .36f, s * .49f, s * .51f)
                quadTo(s * .65f, s * .68f, s * .79f, s * .38f)
            }
            canvas.drawPath(wave, paint)

            paint.style = Paint.Style.FILL
            paint.color = brown
            canvas.drawCircle(s * .77f, s * .28f, s * .055f, paint)

            if (size >= 100) {
                paint.color = Color.argb(125, 122, 78, 47)
                val t = phase * 6.28318f
                for (i in 0 until 8) {
                    val a = t + i * .7854f
                    val radius = s * (.25f + .18f * ((i % 3) / 2f))
                    val x = cx + kotlin.math.cos(a.toDouble()).toFloat() * radius
                    val y = cy + kotlin.math.sin(a.toDouble()).toFloat() * radius
                    canvas.drawCircle(x, y, s * (.012f + .006f * ((i + 1) % 2)), paint)
                }
                paint.style = Paint.Style.STROKE
                paint.strokeWidth = s * .012f
                paint.color = Color.argb(95, 22, 22, 22)
                for (r in floatArrayOf(.29f, .36f, .43f)) {
                    val rr = s * (r + .018f * kotlin.math.sin(t.toDouble()).toFloat())
                    canvas.drawCircle(cx, cy, rr, paint)
                }
            }
        }
    }.apply { layoutParams = ViewGroup.LayoutParams(size, size) }

    fun iconButton(context: Context, icon: String, onClick: () -> Unit): TextView = TextView(context).apply {
        text = icon
        textSize = 20f
        gravity = Gravity.CENTER
        setTextColor(ink)
        background = surface(context, 18f, cream)
        minHeight = 48
        minWidth = 48
        isClickable = true
        isFocusable = true
        setOnClickListener { press(this); onClick() }
    }

    fun button(context: Context, label: String, onClick: () -> Unit, primary: Boolean = false): TextView = TextView(context).apply {
        text = label
        textSize = 14.5f
        gravity = Gravity.CENTER
        setTextColor(if (primary) white else ink)
        background = if (primary) darkAction() else surface(context, 20f, cream)
        setPadding(20, 15, 20, 15)
        minHeight = 50
        isClickable = true
        isFocusable = true
        elevation = 2f
        setOnClickListener { press(this); onClick() }
    }

    fun navItem(context: Context, icon: String, label: String, selected: Boolean, onClick: () -> Unit): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(5, 7, 5, 7)
            background = if (selected) darkAction() else null
            elevation = if (selected) 4f else 0f
            addView(text(context, icon, 19f, if (selected) white else muted).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 27))
            addView(text(context, label, 11f, if (selected) white else muted).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 22))
            isClickable = true
            isFocusable = true
            setOnClickListener { press(this); onClick() }
        }

    fun card(context: Context, heading: String, description: String, action: String? = null, onClick: (() -> Unit)? = null): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(20, 19, 20, 19)
            background = surface(context, 22f)
            elevation = 1.5f
            addView(title(context, heading, 18f), LinearLayout.LayoutParams(-1, -2))
            addView(body(context, description).apply { setPadding(0, 7, 0, 11) }, LinearLayout.LayoutParams(-1, -2))
            if (action != null && onClick != null) addView(button(context, action, onClick, false), LinearLayout.LayoutParams(-1, -2))
        }

    fun section(context: Context, value: String): TextView = text(context, value.uppercase(), 11f, brown).apply {
        letterSpacing = .14f
        setPadding(3, 11, 3, 5)
        typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
    }

    fun toggle(context: Context, checked: Boolean, onChanged: (Boolean) -> Unit): TextView = TextView(context).apply {
        text = if (checked) "ON" else "OFF"
        textSize = 11f
        gravity = Gravity.CENTER
        setTextColor(if (checked) white else muted)
        background = if (checked) darkAction() else surface(context, 18f, cream)
        setPadding(14, 7, 14, 7)
        minWidth = 64
        minHeight = 40
        isClickable = true
        isFocusable = true
        setOnClickListener {
            val next = !checked
            text = if (next) "ON" else "OFF"
            setTextColor(if (next) white else muted)
            background = if (next) darkAction() else surface(context, 18f, cream)
            press(this)
            onChanged(next)
        }
    }

    fun press(view: View) {
        view.animate().scaleX(.95f).scaleY(.95f).setDuration(70).withEndAction {
            view.animate().scaleX(1f).scaleY(1f).setDuration(150).setInterpolator(DecelerateInterpolator()).start()
        }.start()
    }

    fun fadeIn(view: View) {
        view.alpha = 0f
        view.translationY = 14f
        view.animate().alpha(1f).translationY(0f).setDuration(300).setInterpolator(DecelerateInterpolator()).start()
    }

    fun animatePulse(view: View) {
        ValueAnimator.ofFloat(1f, 1.035f, 1f).apply {
            duration = 1000
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener { v ->
                val scale = v.animatedValue as Float
                view.scaleX = scale
                view.scaleY = scale
            }
            start()
        }
    }
}
