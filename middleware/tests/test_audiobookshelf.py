from typing import Any, Dict

import pytest


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for key in [
        "ABS_API_TOKEN",
        "ABS_USERNAME",
        "ABS_PASSWORD",
        "ABS_CACHE_NAMESPACE",
        "ABS_CACHE_TTL",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ABS_API_BASE_URL", "http://abs")
    monkeypatch.setenv("ABS_HTTP_TIMEOUT", "1.0")
    yield


def test_client_logins_when_credentials_are_configured(monkeypatch):
    from app import audiobookshelf

    monkeypatch.setenv("ABS_USERNAME", "root")
    monkeypatch.setenv("ABS_PASSWORD", "gotic")

    login_calls: Dict[str, Any] = {}

    class LoginResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"token": "abc"}

    class ShareResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"id": "share", "streamUrl": "/stream"}

    def fake_post(url, json, timeout):
        login_calls["url"] = url
        login_calls["payload"] = json
        return LoginResponse()

    def fake_get(url, headers, timeout):
        login_calls["headers"] = headers
        return ShareResponse()

    monkeypatch.setattr(audiobookshelf.httpx, "post", fake_post)
    monkeypatch.setattr(audiobookshelf.httpx, "get", fake_get)
    monkeypatch.setattr(audiobookshelf, "get_cache", lambda: None)

    client = audiobookshelf.AudiobookshelfClient()
    data = client.ensure_share_available("CgyUpslyCx")

    assert login_calls["url"] == "http://abs/api/login"
    assert login_calls["payload"] == {"username": "root", "password": "gotic"}
    assert login_calls["headers"]["Authorization"] == "Bearer abc"
    assert data["streamUrl"] == "http://abs/stream"


def test_client_raises_when_login_fails(monkeypatch):
    from app import audiobookshelf

    monkeypatch.setenv("ABS_USERNAME", "root")
    monkeypatch.setenv("ABS_PASSWORD", "badpass")

    class LoginResponse:
        status_code = 401
        headers: Dict[str, str] = {}

    monkeypatch.setattr(audiobookshelf.httpx, "post", lambda *a, **k: LoginResponse())

    client = audiobookshelf.AudiobookshelfClient()

    with pytest.raises(audiobookshelf.AudiobookshelfUnavailable):
        client.ensure_share_available("share")


def test_client_falls_back_to_public_share_endpoint(monkeypatch):
    from app import audiobookshelf

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}
            self.headers = {"content-type": "application/json"}
            self.text = "{}"

        def json(self):
            return self._payload

    calls = []

    def fake_get(url, headers, timeout):
        calls.append(url)
        if url.endswith("/api/shares/CgyUpslyCx"):
            return Response(401, {"message": "Unauthorized"})
        return Response(200, {"share": {"streamUrl": "/stream", "libraryItem": {}}})

    monkeypatch.setattr(audiobookshelf, "get_cache", lambda: None)
    monkeypatch.setattr(audiobookshelf.httpx, "get", fake_get)

    client = audiobookshelf.AudiobookshelfClient()
    data = client.ensure_share_available("CgyUpslyCx")

    assert calls == [
        "http://abs/api/shares/CgyUpslyCx",
        "http://abs/api/public/share/CgyUpslyCx",
    ]
    assert data["streamUrl"] == "http://abs/stream"


def test_client_raises_not_found_when_all_endpoints_fail(monkeypatch):
    from app import audiobookshelf

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {"content-type": "application/json"}
            self.text = "{}"

        def json(self):
            return {"error": "not found"}

    def fake_get(url, headers, timeout):
        return Response(404)

    monkeypatch.setattr(audiobookshelf.httpx, "get", fake_get)
    monkeypatch.setattr(audiobookshelf, "get_cache", lambda: None)

    client = audiobookshelf.AudiobookshelfClient()

    with pytest.raises(audiobookshelf.AudiobookshelfNotFound):
        client.ensure_share_available("missing")
