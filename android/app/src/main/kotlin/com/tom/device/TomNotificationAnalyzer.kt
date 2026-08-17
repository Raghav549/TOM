package com.tom.device

/** Lightweight on-device notification triage. It never sends notification text anywhere by itself. */
object TomNotificationAnalyzer {
    data class Result(
        val priority: String,
        val category: String,
        val likelyNeedsResponse: Boolean,
        val suggestedCommentary: String?
    )

    fun analyze(packageName: String, title: String, text: String, category: String): Result {
        val blob = "$title $text $category".lowercase()
        val messaging = packageName in setOf("com.whatsapp", "com.instagram.android", "org.telegram.messenger", "com.google.android.apps.messaging")
        val call = blob.contains("incoming call") || blob.contains("calling") || category.equals("call", true)
        val urgent = call || blob.contains("otp") || blob.contains("verification code") || blob.contains("security alert") || blob.contains("emergency")
        val payment = blob.contains("payment") || blob.contains("paid") || blob.contains("transaction") || blob.contains("debited") || blob.contains("credited")
        val likelyReply = messaging && !blob.contains("sent") && !blob.contains("delivered") && !blob.contains("read")
        val resolvedCategory = when {
            call -> "call"
            payment -> "finance"
            messaging -> "message"
            urgent -> "security_or_urgent"
            else -> "general"
        }
        val priority = when {
            call || blob.contains("emergency") -> "critical"
            urgent || payment -> "high"
            messaging -> "normal"
            else -> "low"
        }
        val commentary = when {
            call -> "Bhai, incoming call aa rahi hai."
            payment -> "Bhai, payment/transaction ka notification aaya hai."
            messaging && likelyReply -> "Bhai, message aaya hai. Main dekh raha hoon kya response chahiye."
            urgent -> "Bhai, ek important notification aaya hai. Main check kar raha hoon."
            else -> null
        }
        return Result(priority, resolvedCategory, likelyReply, commentary)
    }
}
