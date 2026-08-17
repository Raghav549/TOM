package com.tom.device

import android.animation.ValueAnimator
import android.content.Context
import android.content.res.ColorStateList
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
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.switchmaterial.SwitchMaterial
import kotlin.math.min

object TomGlassUi {
    val ink = Color.rgb(24, 24, 24)
    val muted = Color.rgb(101, 97, 93)
    val brown = Color.rgb(122, 78, 47)
    val brownLight = Color.rgb(174, 128, 91)
    val cream = Color.rgb(249, 247, 244)
    val white = Color.WHITE
    val line = Color.rgb(229, 224, 219)

    fun weatherBackground(): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        intArrayOf(Color.WHITE, Color.rgb(252, 250, 248), Color.rgb(248, 246, 243))
    )

    fun surface(context: Context, radius: Float = 20f, color: Int = white): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = radius
            setColor(color)
            setStroke(1, line)
        }

    private fun darkAction(): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.LEFT_RIGHT,
        intArrayOf(Color.rgb(18, 18, 18), brown)
    ).apply { cornerRadius = 20f }

    fun darkActionForCard(): GradientDrawable = darkAction()

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
            if (s <= 0f) return
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
                val t = phase * 6.28318f
                paint.color = Color.argb(125, 122, 78, 47)
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
        background = surface(context, 16f, cream)
        minHeight = 48
        minWidth = 48
        isClickable = true
        isFocusable = true
        contentDescription = "Settings"
        setOnClickListener { press(this); onClick() }
    }

    fun button(context: Context, label: String, onClick: () -> Unit, primary: Boolean = false): MaterialButton =
        MaterialButton(context).apply {
            text = label
            textSize = 14.5f
            isAllCaps = false
            minHeight = 52
            minimumHeight = 52
            insetTop = 0
            insetBottom = 0
            cornerRadius = 18
            strokeWidth = if (primary) 0 else 1
            strokeColor = ColorStateList.valueOf(brown)
            backgroundTintList = ColorStateList.valueOf(if (primary) ink else Color.WHITE)
            setTextColor(if (primary) white else ink)
            rippleColor = ColorStateList.valueOf(Color.argb(30, 122, 78, 47))
            isClickable = true
            isFocusable = true
            setOnClickListener { press(this); onClick() }
        }

    fun navItem(context: Context, icon: String, label: String, selected: Boolean, onClick: () -> Unit): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(6, 6, 6, 6)
            background = if (selected) darkAction() else null
            elevation = if (selected) 3f else 0f
            addView(text(context, icon, 19f, if (selected) white else muted).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 26))
            addView(text(context, label, 11f, if (selected) white else muted).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 22))
            isClickable = true
            isFocusable = true
            contentDescription = label
            setOnClickListener { press(this); onClick() }
        }

    fun card(context: Context, heading: String, description: String, action: String? = null, onClick: (() -> Unit)? = null): MaterialCardView =
        MaterialCardView(context).apply {
            radius = 20f
            cardElevation = 1.5f
            strokeWidth = 1
            strokeColor = line
            setCardBackgroundColor(white)
            val body = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(20, 18, 20, 18)
                addView(title(context, heading, 18f), LinearLayout.LayoutParams(-1, -2))
                addView(body(context, description).apply { setPadding(0, 7, 0, if (action == null) 0 else 12) }, LinearLayout.LayoutParams(-1, -2))
                if (action != null && onClick != null) addView(button(context, action, onClick, false), LinearLayout.LayoutParams(-1, 52))
            }
            addView(body, ViewGroup.LayoutParams(-1, -2))
        }

    fun section(context: Context, value: String): TextView = text(context, value.uppercase(), 11f, brown).apply {
        letterSpacing = .14f
        setPadding(3, 12, 3, 5)
        typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
    }

    fun toggle(context: Context, checked: Boolean, onChanged: (Boolean) -> Unit): SwitchMaterial = SwitchMaterial(context).apply {
        isChecked = checked
        minWidth = 56
        minHeight = 48
        setOnCheckedChangeListener { _, value -> press(this); onChanged(value) }
    }

    fun press(view: View) {
        view.animate().scaleX(.97f).scaleY(.97f).setDuration(70).withEndAction {
            view.animate().scaleX(1f).scaleY(1f).setDuration(150).setInterpolator(DecelerateInterpolator()).start()
        }.start()
    }

    fun fadeIn(view: View) {
        view.alpha = 0f
        view.translationY = 12f
        view.animate().alpha(1f).translationY(0f).setDuration(260).setInterpolator(DecelerateInterpolator()).start()
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
