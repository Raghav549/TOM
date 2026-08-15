package com.tom.device

import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

object TomGlassUi {
    private val ink = Color.rgb(35, 36, 48)
    private val muted = Color.rgb(102, 105, 120)
    private val pink = Color.rgb(255, 222, 238)
    private val green = Color.rgb(218, 247, 229)
    private val white = Color.rgb(255, 255, 255)

    fun plasmaBackground(): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        intArrayOf(pink, white, green, Color.rgb(241, 235, 255), pink)
    )

    fun background(context: Context): View = View(context).apply { background = plasmaBackground() }

    fun glass(context: Context, radius: Float = 28f): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = radius
            setColor(Color.argb(205, 255, 255, 255))
            setStroke(1, Color.argb(150, 255, 255, 255))
        }

    fun title(context: Context, text: String, size: Float = 32f): TextView = TextView(context).apply {
        this.text = text
        textSize = size
        setTextColor(ink)
        gravity = Gravity.CENTER_VERTICAL
        typeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.NORMAL)
    }

    fun body(context: Context, text: String): TextView = TextView(context).apply {
        this.text = text
        textSize = 15f
        setTextColor(muted)
        setLineSpacing(3f, 1.08f)
    }

    fun button(context: Context, text: String, onClick: () -> Unit): TextView = TextView(context).apply {
        this.text = text
        textSize = 15f
        setTextColor(ink)
        gravity = Gravity.CENTER
        setPadding(22, 18, 22, 18)
        background = glass(context, 22f)
        isClickable = true
        isFocusable = true
        setOnClickListener { onClick() }
    }

    fun card(context: Context, heading: String, description: String, action: String, onClick: () -> Unit): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 22, 24, 22)
            background = glass(context)
            addView(title(context, heading, 19f), LinearLayout.LayoutParams(-1, -2))
            addView(body(context, description).apply { setPadding(0, 8, 0, 14) }, LinearLayout.LayoutParams(-1, -2))
            addView(button(context, action, onClick), LinearLayout.LayoutParams(-1, -2))
        }
}
