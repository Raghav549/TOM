from tom.readiness import build_readiness


def test_readiness_does_not_claim_optional_capabilities_are_available():
    report = build_readiness(
        llm_enabled=False,
        vision_enabled=False,
        voice_enabled=True,
        android_bridge_enabled=True,
        tts_engine=False,
        asr_engine=False,
        smart_turn=False,
    )

    assert report.ready is True
    assert report.checks["agent_runtime"] is True
    assert report.checks["android_bridge"] is True
    assert report.checks["streaming_tts"] is False
    assert report.checks["streaming_asr"] is False
    assert report.checks["smart_turn"] is False


def test_readiness_reports_configured_capabilities():
    report = build_readiness(
        llm_enabled=True,
        vision_enabled=True,
        voice_enabled=True,
        android_bridge_enabled=True,
        tts_engine=True,
        asr_engine=True,
        smart_turn=True,
    )

    assert report.ready is True
    assert all(report.checks.values())
