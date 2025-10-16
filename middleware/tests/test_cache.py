import fakeredis
from app.cache import Cache, override_cache
from app.audiobookshelf import AudiobookshelfClient


class _FakeResponse:
    status_code = 200
    headers = {"content-type": "application/json"}

    def json(self):
        return {
            "streamUrl": "/stream/share-123",
            "webUrl": "/web/share-123",
        }


class _CountingClient(AudiobookshelfClient):
    def __init__(self):
        super().__init__(base_url="http://abs.test")
        self.calls = 0

    def _request(self, path: str):  # type: ignore[override]
        self.calls += 1
        return _FakeResponse()


def test_audiobookshelf_share_response_is_cached():
    fake = fakeredis.FakeRedis(decode_responses=True)
    cache = Cache(client_factory=lambda: fake, default_ttl=120)
    previous = override_cache(cache)
    try:
        client = _CountingClient()
        first = client.ensure_share_available("share-123")
        second = client.ensure_share_available("share-123")

        assert first == second
        assert client.calls == 1
        ttl = fake.ttl(f"{client.cache_namespace}:share-123")
        assert ttl == 120 or ttl > 0
    finally:
        override_cache(previous)
