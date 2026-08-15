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
    val ink = Color.rgb(29, 39, 53)
    val muted = Color.rgb(91, 105, 120)
    val blue = Color.rgb(66, 130, 196)
    val sky = Color.rgb(221, 238, 250)
    val cloud = Color.rgb(248, 251, 253)
    val white = Color.WHITE
    val line = Color.argb(38, 35, 65, 90)

    fun weatherBackground(): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        intArrayOf(Color.rgb(235, 246, 253), Color.WHITE, Color.rgb(244, 247, 244), Color.rgb(232, 242, 249))
    )

    fun surface(context: Context, radius: Float = 28f, color: Int = Color.argb(228, 255, 255, 255)): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = radius
            setColor(color)
            setStroke(1, line)
        }

    fun text(context: Context, value: String, size: Float, color: Int = ink): TextView = TextView(context).apply {
        text = value
        textSize = size
        setTextColor(color)
        setLineSpacing(2f, 1.08f)
    }

    fun title(context: Context, value: String, size: Float = 30f): TextView = text(context, value, size).apply {
        typeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.NORMAL)
        gravity = Gravity.CENTER_VERTICAL
    }

    fun body(context: Context, value: String): TextView = text(context, value, 15f, muted)

    fun logo(context: Context, size: Int = 64): View = object : View(context) {
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val s = min(width, height).toFloat()
            paint.color = Color.argb(220, 255, 255, 255)
            canvas.drawCircle(s / 2, s / 2, s * .47f, paint)
            paint.color = blue
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = s * .07f
            val p = Path().apply {
                moveTo(s * .23f, s * .57f)
                quadTo(s * .34f, s * .37f, s * .49f, s * .51f)
                quadTo(s * .66f, s * .68f, s * .78f, s * .39f)
            }
            canvas.drawPath(p, paint)
            paint.style = Paint.Style.FILL
            paint.color = Color.rgb(238, 176, 67)
            canvas.drawCircle(s * .73f, s * .28f, s * .075f, paint)
        }
    }.apply { layoutParams = ViewGroup.LayoutParams(size, size) }

    fun iconButton(context: Context, icon: String, onClick: () -> Unit): TextView = TextView(context).apply {
        text = icon
        textSize = 20f
        gravity = Gravity.CENTER
        setTextColor(ink)
        background = surface(context, 20f)
        isClickable = true
        isFocusable = true
        setPadding(0, 0, 0, 0)
        setOnClickListener { press(this); onClick() }
    }

    fun button(context: Context, label: String, onClick: () -> Unit, primary: Boolean = false): TextView = TextView(context).apply {
        text = label
        textSize = 14.5f
        gravity = Gravity.CENTER
        setTextColor(if (primary) Color.WHITE else ink)
        background = if (primary) GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = 22f
            setColor(blue)
        } else surface(context, 22f)
        setPadding(20, 15, 20, 15)
        isClickable = true
        isFocusable = true
        setOnClickListener { press(this); onClick() }
    }

    fun navItem(context: Context, icon: String, label: String, selected: Boolean, onClick: () -> Unit): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(8, 8, 8, 7)
            background = if (selected) surface(context, 20f, Color.argb(255, 229, 241, 250)) else null
            addView(text(context, icon, 19f, if (selected) blue else muted).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 27))
            addView(text(context, label, 11f, if (selected) ink else muted).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, 22))
            isClickable = true
            isFocusable = true
            setOnClickListener { press(this); onClick() }
        }

    fun card(context: Context, heading: String, description: String, action: String? = null, onClick: (() -> Unit)? = null): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(22, 20, 22, 20)
            background = surface(context)
            addView(title(context, heading, 18f), LinearLayout.LayoutParams(-1, -2))
            addView(body(context, description).apply { setPadding(0, 8, 0, 12) }, LinearLayout.LayoutParams(-1, -2))
            if (action != null && onClick != null) addView(button(context, action, onClick, false), LinearLayout.LayoutParams(-1, -2))
        }

    fun section(context: Context, value: String): TextView = text(context, value.uppercase(), 11f, blue).apply {
        letterSpacing = .12f
        setPadding(4, 12, 4, 5)
    }

    fun press(view: View) {
        view.animate().scaleX(.96f).scaleY(.96f).setDuration(70).withEndAction {
            view.animate().scaleX(1f).scaleY(1f).setDuration(130).setInterpolator(DecelerateInterpolator()).start()
        }.start()
    }

    fun fadeIn(view: View) {
        view.alpha = 0f
        view.translationY = 20f
        view.animate().alpha(1f).translationY(0f).setDuration(420).setInterpolator(DecelerateInterpolator()).start()
    }

    fun animatePulse(view: View) {
        ValueAnimator.ofFloat(1f, 1.06f, 1f).apply {
            duration = 900
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
