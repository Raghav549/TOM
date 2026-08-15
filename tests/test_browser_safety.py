from tom.browser.safety import BrowserSafetyPolicy


def test_browser_policy_allows_http_and_https():
    policy = BrowserSafetyPolicy()
    assert policy.check_navigation("https://example.com").allowed
    assert policy.check_navigation("http://example.com/path").allowed


def test_browser_policy_blocks_unsafe_urls():
    policy = BrowserSafetyPolicy()
    assert not policy.check_navigation("javascript:alert(1)").allowed
    assert not policy.check_navigation("https://user:pass@example.com").allowed


def test_browser_policy_can_allowlist_hosts():
    policy = BrowserSafetyPolicy(allowed_hosts={"example.com"})
    assert policy.check_navigation("https://example.com").allowed
    assert not policy.check_navigation("https://other.example").allowed
