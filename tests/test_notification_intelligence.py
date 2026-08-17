from tom.notifications.intelligence import NotificationEvent, NotificationIntelligence, NotificationPriority


def test_sensitive_notifications_never_auto_act() -> None:
    decision = NotificationIntelligence().classify(NotificationEvent("com.bank", "Bank", "Your OTP is 123456", "1"))
    assert decision.priority is NotificationPriority.RELEVANT
    assert decision.requires_user_confirmation is True


def test_urgent_notification_gets_fast_attention() -> None:
    decision = NotificationIntelligence().classify(NotificationEvent("com.chat", "Security alert", "Urgent fraud alert", "2"))
    assert decision.priority is NotificationPriority.URGENT


def test_normal_notification_is_relevant() -> None:
    decision = NotificationIntelligence().classify(NotificationEvent("com.whatsapp", "Muskan", "Hey bhai", "3"))
    assert decision.priority is NotificationPriority.RELEVANT
