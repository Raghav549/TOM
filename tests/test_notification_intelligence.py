from tom.notifications.intelligence import NotificationEvent, NotificationIntelligence, NotificationPriority


def test_sensitive_notifications_never_auto_act() -> None:
    decision = NotificationIntelligence().classify(NotificationEvent("com.bank", "Bank", "Your OTP is 123456", "1"))
    assert decision.priority is NotificationPriority.RELEVANT
    assert decision.requires_user_confirmation is True


def test_urgent_authorized_notification_is_spoken() -> None:
    decision = NotificationIntelligence(authorized_packages={"com.chat"}).classify(NotificationEvent("com.chat", "Security alert", "Urgent fraud alert", "2"))
    assert decision.priority is NotificationPriority.URGENT
    assert decision.should_speak is True


def test_background_notification_is_silent() -> None:
    decision = NotificationIntelligence(authorized_packages={"com.example"}).classify(NotificationEvent("com.example", "Sync complete", "Done", "3"))
    assert decision.priority is NotificationPriority.BACKGROUND
    assert decision.should_speak is False


def test_duplicate_notification_is_suppressed() -> None:
    intelligence = NotificationIntelligence()
    event = NotificationEvent("com.example", "Message", "hello", "4")
    intelligence.classify(event, now=100.0)
    decision = intelligence.classify(event, now=110.0)
    assert decision.priority is NotificationPriority.BACKGROUND
