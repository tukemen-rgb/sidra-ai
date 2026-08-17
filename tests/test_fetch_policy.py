import pytest

from sidra_ai.fetch import FetchPolicy, FetchPolicyError


PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"


def policy(**kwargs):
    return FetchPolicy(allowed_hosts=frozenset({"docs.example.com"}), **kwargs)


def test_default_policy_fetches_nothing():
    with pytest.raises(FetchPolicyError, match="allowlisted"):
        FetchPolicy().validate_target("https://docs.example.com/", [PUBLIC_V4])


def test_exact_allowlist_normalizes_case_and_trailing_dot():
    configured = FetchPolicy(allowed_hosts=frozenset({"Docs.Example.COM."}))
    target = configured.validate_target(
        "https://DOCS.EXAMPLE.COM.:443/reference",
        [PUBLIC_V4, PUBLIC_V6],
    )
    assert target.url == "https://docs.example.com/reference"
    assert target.host == "docs.example.com"
    assert target.port == 443
    assert target.resolved_ips == (PUBLIC_V4, PUBLIC_V6)


def test_query_strings_are_rejected_without_echoing_sensitive_values():
    configured = policy()
    synthetic_secret = "ghp_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd"
    sensitive_url = (
        "https://docs.example.com/reference?"
        f"token={synthetic_secret}&email=person%40private.invalid"
    )

    with pytest.raises(FetchPolicyError, match="query strings") as exc_info:
        configured.canonicalize_url(sensitive_url)

    message = str(exc_info.value)
    assert synthetic_secret not in message
    assert "person" not in message

    with pytest.raises(FetchPolicyError, match="query strings"):
        configured.validate_redirect(
            "https://docs.example.com/a",
            f"/b?token={synthetic_secret}",
            [PUBLIC_V4],
            redirects_taken=0,
        )


def test_exact_allowlist_rejects_suffix_escape():
    with pytest.raises(FetchPolicyError, match="allowlisted"):
        policy().validate_target("https://docs.example.com.evil.example/", [PUBLIC_V4])


def test_userinfo_confusion_is_rejected_before_host_use():
    with pytest.raises(FetchPolicyError, match="userinfo"):
        policy().validate_target("https://docs.example.com@evil.example/", [PUBLIC_V4])


def test_non_https_non_443_fragment_and_ip_literal_are_rejected():
    configured = policy()
    with pytest.raises(FetchPolicyError, match="https"):
        configured.validate_target("http://docs.example.com/", [PUBLIC_V4])
    with pytest.raises(FetchPolicyError, match="port 443"):
        configured.validate_target("https://docs.example.com:8443/", [PUBLIC_V4])
    with pytest.raises(FetchPolicyError, match="fragments"):
        configured.validate_target("https://docs.example.com/#section", [PUBLIC_V4])

    ip_policy = FetchPolicy(allowed_hosts=frozenset({PUBLIC_V4}))
    with pytest.raises(FetchPolicyError, match="IP-literal"):
        ip_policy.validate_target(f"https://{PUBLIC_V4}/", [PUBLIC_V4])


def test_unicode_host_input_is_rejected_in_phase_one():
    with pytest.raises(FetchPolicyError, match="non-ASCII"):
        FetchPolicy(allowed_hosts=frozenset({"éxample.com"}))


def test_empty_or_mixed_unsafe_dns_answers_fail_closed():
    configured = policy()
    with pytest.raises(FetchPolicyError, match="empty"):
        configured.validate_target("https://docs.example.com/", [])

    for unsafe in (
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "192.0.2.10",
        "198.51.100.20",
        "203.0.113.30",
        "198.18.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "2001:db8::1",
        "::ffff:10.0.0.1",
    ):
        with pytest.raises(FetchPolicyError, match="unsafe"):
            configured.validate_target("https://docs.example.com/", [unsafe])

    with pytest.raises(FetchPolicyError, match="unsafe"):
        configured.validate_target(
            "https://docs.example.com/",
            [PUBLIC_V4, "10.0.0.1"],
        )


def test_redirect_is_resolved_then_fully_revalidated():
    configured = policy(max_redirects=2)
    target = configured.validate_redirect(
        "https://docs.example.com/a/index.html",
        "../guide",
        [PUBLIC_V4],
        redirects_taken=0,
    )
    assert target.url == "https://docs.example.com/guide"

    with pytest.raises(FetchPolicyError, match="allowlisted"):
        configured.validate_redirect(
            "https://docs.example.com/a",
            "https://evil.example/",
            [PUBLIC_V4],
            redirects_taken=0,
        )
    with pytest.raises(FetchPolicyError, match="https"):
        configured.validate_redirect(
            "https://docs.example.com/a",
            "http://docs.example.com/",
            [PUBLIC_V4],
            redirects_taken=0,
        )
    with pytest.raises(FetchPolicyError, match="redirect limit"):
        configured.validate_redirect(
            "https://docs.example.com/a",
            "/b",
            [PUBLIC_V4],
            redirects_taken=2,
        )


def test_content_type_and_size_policy_are_narrow_and_bounded():
    configured = policy(max_response_bytes=1024)
    assert configured.validate_content_type("Text/HTML; charset=utf-8") == "text/html"
    assert configured.validate_content_type("application/json") == "application/json"
    with pytest.raises(FetchPolicyError, match="content type"):
        configured.validate_content_type("application/octet-stream")
    assert configured.validate_body_size(1024) == 1024
    with pytest.raises(FetchPolicyError, match="byte limit"):
        configured.validate_body_size(1025)


def test_invalid_policy_limits_fail_closed():
    with pytest.raises(FetchPolicyError, match="max_redirects"):
        policy(max_redirects=-1)
    with pytest.raises(FetchPolicyError, match="max_response_bytes"):
        policy(max_response_bytes=0)
