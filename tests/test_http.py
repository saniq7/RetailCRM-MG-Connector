from retailcrm_mg.errors import AuthError, NotFoundError, RateLimitError
from retailcrm_mg.http import _classify, _redact, build_url


def test_build_url_normalizes_slashes_and_skips_none():
    url = build_url("https://api.example/", "/channels", {"limit": 10, "since_id": None})
    assert url == "https://api.example/channels?limit=10"


def test_build_url_serializes_booleans_lowercase():
    assert build_url("https://a", "/b", {"active": True}).endswith("active=true")


def test_redact_hides_api_key():
    redacted = _redact("https://crm.example.com/api/v5/credentials?apiKey=super-secret&page=1")
    assert "super-secret" not in redacted
    assert "page=1" in redacted


def test_classify_maps_status_to_exception_types():
    assert isinstance(_classify(403, "https://a", {"errorMsg": "нет прав"}), AuthError)
    assert isinstance(_classify(404, "https://a", {}), NotFoundError)
    assert isinstance(_classify(429, "https://a", {}), RateLimitError)


def test_classify_extracts_error_message():
    error = _classify(400, "https://a", {"errors": {"code": "занят"}})
    assert "занят" in str(error)
