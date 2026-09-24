import pytest
import requests

from instagram.client import MetaOEmbedInstagramClient
from instagram.exceptions import (
    InstagramAuthError,
    InstagramPostNotPublicError,
    InstagramPostUnavailableError,
    InstagramRateLimitError,
)
from services.post_service import normalize_instagram_url, validate_instagram_url

TOKEN = "123|secret-client-token"
POST_URL = "https://www.instagram.com/p/C0ffee123/"


# ---------------------------------------------------------------- URL validation


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.instagram.com/p/C0ffee123/", "https://www.instagram.com/p/C0ffee123/"),
        ("https://www.instagram.com/p/C0ffee123", "https://www.instagram.com/p/C0ffee123/"),
        ("https://instagram.com/p/C0ffee123/?igsh=xyz", "https://www.instagram.com/p/C0ffee123/"),
        ("https://m.instagram.com/p/C0ffee123/#frag", "https://www.instagram.com/p/C0ffee123/"),
        ("https://WWW.Instagram.com/reel/Ab-_12345/", "https://www.instagram.com/reel/Ab-_12345/"),
        ("https://www.instagram.com/reels/Ab-_12345/", "https://www.instagram.com/reel/Ab-_12345/"),
        ("https://www.instagram.com/tv/Ab-_12345/", "https://www.instagram.com/tv/Ab-_12345/"),
        ("https://www.instagram.com/some.user/p/C0ffee123/", "https://www.instagram.com/p/C0ffee123/"),
        ("  https://www.instagram.com/p/C0ffee123/  ", "https://www.instagram.com/p/C0ffee123/"),
    ],
)
def test_valid_instagram_urls(url, expected):
    assert validate_instagram_url(url) is True
    assert normalize_instagram_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "http://www.instagram.com/p/C0ffee123/",  # not HTTPS
        "https://example.com/p/C0ffee123/",
        "https://instagram.com.evil.com/p/C0ffee123/",
        "https://evilinstagram.com/p/C0ffee123/",
        "https://www.instagram.com@evil.com/p/C0ffee123/",
        "https://user:pass@www.instagram.com/p/C0ffee123/",
        "https://www.instagram.com:8443/p/C0ffee123/",
        "https://www.instagram.com/",
        "https://www.instagram.com/someuser/",  # profile, not a post
        "https://www.instagram.com/stories/someuser/123/",
        "https://www.instagram.com/p/",
        "https://www.instagram.com/p/C0ffee123/extra/",
        "javascript:alert(1)",
        None,
    ],
)
def test_invalid_urls(url):
    assert validate_instagram_url(url) is False


# ---------------------------------------------------------------- oEmbed client (HTTP mocked)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeHTTP:
    """Returns `response` (or each of a list of responses in turn)."""

    def __init__(self, response=None, exc=None):
        self.responses = response if isinstance(response, list) else [response]
        self.exc, self.requests = exc, []

    def get(self, url, params=None, timeout=None):
        self.requests.append((url, params, timeout))
        if self.exc:
            raise self.exc
        return self.responses[min(len(self.requests), len(self.responses)) - 1]


def make_client(response=None, exc=None, token=TOKEN):
    http = FakeHTTP(response, exc)
    return MetaOEmbedInstagramClient(token, api_version="v25.0", timeout=5, http=http), http


def graph_error(code, subcode=None):
    return {"error": {"message": "nope", "type": "OAuthException", "code": code, "error_subcode": subcode}}


def test_public_post_returns_embed():
    html = '<blockquote class="instagram-media"></blockquote><script src="//www.instagram.com/embed.js"></script>'
    client, http = make_client(FakeResponse(200, {"version": "1.0", "type": "rich", "html": html}))

    post = client.get_post(POST_URL)

    assert post.instagram_url == POST_URL
    assert post.embed_html == html
    assert post.media_url is None
    url, params, timeout = http.requests[0]
    assert url == "https://graph.facebook.com/v25.0/instagram_oembed"
    assert params["url"] == POST_URL and params["access_token"] == TOKEN
    assert timeout == 5


def test_thumbnail_used_as_media_url_when_provided():
    client, _ = make_client(
        FakeResponse(200, {"html": "<b></b>", "thumbnail_url": "https://cdn/img.jpg", "title": "Hi"})
    )
    post = client.get_post(POST_URL)
    assert post.media_url == "https://cdn/img.jpg"
    assert post.caption == "Hi"


@pytest.mark.parametrize(
    "status, payload, expected",
    [
        (400, graph_error(190), InstagramAuthError),
        (401, {}, InstagramAuthError),
        (403, graph_error(10), InstagramAuthError),
        (400, graph_error(200), InstagramAuthError),
        (429, {}, InstagramRateLimitError),
        (400, graph_error(4), InstagramRateLimitError),
        (400, graph_error(32), InstagramRateLimitError),
        (400, graph_error(100, 2207046), InstagramPostNotPublicError),
        (404, {}, InstagramPostNotPublicError),
        (500, ValueError("not json"), InstagramPostUnavailableError),
        (400, ["not", "an", "object"], InstagramPostUnavailableError),
        (400, {"error": "just a string"}, InstagramPostUnavailableError),
    ],
)
def test_error_mapping(status, payload, expected):
    client, _ = make_client(FakeResponse(status, payload))
    with pytest.raises(expected):
        client.get_post(POST_URL)


def test_private_post_message():
    client, _ = make_client(FakeResponse(400, graph_error(100)))
    with pytest.raises(InstagramPostNotPublicError) as info:
        client.get_post(POST_URL)
    assert "private account" in info.value.user_message


def test_tokenless_request_omits_access_token():
    client, http = make_client(FakeResponse(200, {"html": "<b></b>"}), token=None)
    assert client.get_post(POST_URL).embed_html == "<b></b>"
    _, params, _ = http.requests[0]
    assert "access_token" not in params and params["url"] == POST_URL


def test_network_error_does_not_leak_token():
    exc = requests.ConnectionError(f"failed GET ...?access_token={TOKEN}")
    client, _ = make_client(exc=exc)
    with pytest.raises(InstagramPostUnavailableError) as info:
        client.get_post(POST_URL)
    assert TOKEN not in str(info.value)
    assert info.value.__cause__ is None
    assert TOKEN not in info.value.user_message


@pytest.mark.parametrize("payload", [{"type": "rich"}, ["unexpected"], ValueError("bad json")])
def test_unusable_success_payload(payload):
    client, _ = make_client(FakeResponse(200, payload))
    with pytest.raises(InstagramPostUnavailableError):
        client.get_post(POST_URL)


def test_settings_repr_hides_token(monkeypatch):
    from config import get_settings

    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", TOKEN)
    assert TOKEN not in repr(get_settings())


# ---------------------------------------------------------------- token fallback

UNREVIEWED = FakeResponse(400, graph_error(10))  # "Meta oEmbed Read must be reviewed"
OK = FakeResponse(200, {"html": "<b></b>"})


def test_rejected_token_falls_back_to_tokenless():
    client, http = make_client([UNREVIEWED, OK])

    assert client.get_post(POST_URL).embed_html == "<b></b>"
    assert http.requests[0][1]["access_token"] == TOKEN
    assert "access_token" not in http.requests[1][1]


def test_rejected_token_is_not_retried_on_later_calls():
    client, http = make_client([UNREVIEWED, OK])
    client.get_post(POST_URL)
    client.get_post(POST_URL)

    assert len(http.requests) == 3
    assert "access_token" not in http.requests[2][1]


def test_working_token_is_used_without_fallback():
    client, http = make_client(OK)
    client.get_post(POST_URL)
    client.get_post(POST_URL)
    assert [p["access_token"] for _, p, _ in http.requests] == [TOKEN, TOKEN]


@pytest.mark.parametrize(
    "payload, expected",
    [(graph_error(4), InstagramRateLimitError), (graph_error(24, 2207045), InstagramPostNotPublicError)],
)
def test_non_auth_errors_do_not_trigger_fallback(payload, expected):
    client, http = make_client(FakeResponse(400, payload))
    with pytest.raises(expected):
        client.get_post(POST_URL)
    assert len(http.requests) == 1
