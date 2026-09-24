"""Instagram integration.

Everything that talks to Meta/Instagram lives in this module. The rest of the
application only depends on `InstagramClient.get_post()` and `InstagramPost`,
so swapping the integration means changing this file and its configuration.

The default implementation uses Meta's official oEmbed endpoint
(`GET /{version}/instagram_oembed`), which resolves a *public* Instagram post
URL. Meta does not return oEmbed data for posts from private accounts, which
is how the "private post" case is detected. No HTML is scraped.

Since June 2026 Meta also serves this endpoint without an access token (at
lower rate limits). The token is therefore optional. When one is configured it
is tried first; if Meta rejects it (e.g. the app's "Meta oEmbed Read" feature
hasn't passed App Review yet), the request is retried tokenless and the token
is skipped for the rest of the process.
"""

from __future__ import annotations

import functools
import logging
from abc import ABC, abstractmethod

import requests
from pydantic import BaseModel, ConfigDict, ValidationError

from instagram.exceptions import (
    InstagramAuthError,
    InstagramPostNotPublicError,
    InstagramPostUnavailableError,
    InstagramRateLimitError,
)

logger = logging.getLogger(__name__)

GRAPH_API_BASE_URL = "https://graph.facebook.com"

# Graph API error codes, see Meta's "Handling Errors" documentation.
_RATE_LIMIT_CODES = {4, 17, 32, 613}
_AUTH_CODES = {102, 190}
_PERMISSION_CODES = {10} | set(range(200, 300))
# oEmbed answers "invalid parameter" for URLs it will not embed: private
# accounts, deleted posts, or posts whose owner disabled embedding.
_NOT_PUBLIC_CODES = {24, 100}


class InstagramPost(BaseModel):
    """Normalized post data handed to the rest of the application."""

    instagram_url: str
    media_url: str | None = None
    caption: str | None = None
    embed_html: str | None = None


class _OEmbedResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    html: str | None = None
    thumbnail_url: str | None = None
    title: str | None = None


class InstagramClient(ABC):
    """Interface the service layer uses to resolve Instagram post URLs."""

    @abstractmethod
    def get_post(self, instagram_url: str) -> InstagramPost:
        """
        Resolve an Instagram post URL into the media information
        that the configured/authorized Instagram integration permits
        the application to access.

        Raises an `InstagramError` subclass when that is not possible.
        """


class MetaOEmbedInstagramClient(InstagramClient):
    """`InstagramClient` backed by Meta's official Instagram oEmbed endpoint."""

    def __init__(
        self,
        access_token: str | None,
        api_version: str = "v25.0",
        timeout: float = 10.0,
        http: requests.Session | None = None,  # injectable for tests
    ) -> None:
        self._access_token = access_token
        self._token_rejected = False
        self._endpoint = f"{GRAPH_API_BASE_URL}/{api_version}/instagram_oembed"
        self._timeout = timeout
        self._http = http or requests

    def get_post(self, instagram_url: str) -> InstagramPost:
        if self._access_token and not self._token_rejected:
            try:
                response = self._request(instagram_url, self._access_token)
            except InstagramAuthError:
                logger.warning(
                    "Meta rejected INSTAGRAM_ACCESS_TOKEN (not approved for oEmbed Read?); "
                    "falling back to tokenless oEmbed"
                )
                self._token_rejected = True
                response = self._request(instagram_url, None)
        else:
            response = self._request(instagram_url, None)

        try:
            data = _OEmbedResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            logger.warning("Instagram oEmbed returned an unexpected payload")
            raise InstagramPostUnavailableError("unexpected oEmbed payload") from None

        if not data.thumbnail_url and not data.html:
            raise InstagramPostUnavailableError("oEmbed response contained no media")

        # Current oEmbed responses only carry `html` (Instagram's official embed).
        # `thumbnail_url`/`title` were removed by Meta; they're still read if
        # present so a direct image is used whenever one is provided.
        return InstagramPost(
            instagram_url=instagram_url,
            media_url=data.thumbnail_url,
            caption=data.title or None,
            embed_html=data.html,
        )

    def _request(self, instagram_url: str, access_token: str | None) -> requests.Response:
        """GET the oEmbed endpoint; return a 200 response or raise an InstagramError."""
        params = {"url": instagram_url, "maxwidth": 540}
        if access_token:
            params["access_token"] = access_token
        try:
            response = self._http.get(self._endpoint, params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            # Don't log str(exc): it can contain the request URL, token included.
            logger.warning("Instagram oEmbed request failed: %s", type(exc).__name__)
            raise InstagramPostUnavailableError(f"network error: {type(exc).__name__}") from None

        if response.status_code != 200:
            raise self._error_from_response(response)
        return response

    @staticmethod
    def _error_from_response(response: requests.Response) -> Exception:
        try:
            body = response.json()
        except ValueError:
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            error = {}
        code = error.get("code")
        subcode = error.get("error_subcode")
        status = response.status_code
        detail = f"HTTP {status}, code={code}, subcode={subcode}"
        logger.warning("Instagram oEmbed error: %s", detail)

        if status == 429 or code in _RATE_LIMIT_CODES:
            return InstagramRateLimitError(detail)
        if status == 401 or code in _AUTH_CODES or code in _PERMISSION_CODES:
            return InstagramAuthError(detail)
        if code in _NOT_PUBLIC_CODES or status == 404:
            return InstagramPostNotPublicError(detail)
        return InstagramPostUnavailableError(detail)


@functools.lru_cache(maxsize=1)
def get_instagram_client() -> InstagramClient:
    """The configured Instagram client, shared for the life of the process
    (so a rejected token is only tried once). Restart to pick up new settings."""
    from config import get_settings

    settings = get_settings()
    return MetaOEmbedInstagramClient(
        access_token=settings.instagram_access_token,
        api_version=settings.graph_api_version,
        timeout=settings.instagram_timeout_seconds,
    )
