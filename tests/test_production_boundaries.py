import pytest

from tom.browser.safety import BrowserSafetyPolicy
from tom.providers import OpenAICompatibleLLM


def test_llm_rejects_invalid_base_url():
    with pytest.raises(ValueError):
        OpenAICompatibleLLM(base_url="file:///tmp", model="qwen")


def test_llm_requires_model():
    with pytest.raises(ValueError):
        OpenAICompatibleLLM(base_url="http://127.0.0.1:11434/v1", model="")


def test_browser_blocks_embedded_credentials_and_bad_schemes():
    policy = BrowserSafetyPolicy()
    assert not policy.check_navigation("https://user:pass@example.com").allowed
    assert not policy.check_navigation("file:///etc/passwd").allowed


def test_browser_allowlist_is_exact_host_match():
    policy = BrowserSafetyPolicy(allowed_hosts={"example.com"})
    assert policy.check_navigation("https://example.com/path").allowed
    assert not policy.check_navigation("https://evil-example.com/path").allowed
