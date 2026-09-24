"""Errors raised by the Instagram integration.

Messages are safe to show to users: they never contain tokens, URLs with
credentials, or raw API payloads.
"""


class InstagramError(Exception):
    """Base class for all Instagram integration failures."""

    user_message = (
        "The Instagram post could not be retrieved.\n"
        "It may be unavailable or inaccessible to the configured account/API."
    )

    def __init__(self, detail: str | None = None) -> None:
        # `detail` is for server-side logs only.
        super().__init__(detail or self.__class__.__name__)
        self.detail = detail


class InstagramAuthError(InstagramError):
    user_message = (
        "Instagram integration authentication failed.\n"
        "Check the configured API credentials and permissions."
    )


class InstagramRateLimitError(InstagramError):
    user_message = "Instagram API rate limit reached. Please try again later."


class InstagramPostUnavailableError(InstagramError):
    """Post could not be resolved (deleted, bad response, network failure...)."""


class InstagramPostNotPublicError(InstagramPostUnavailableError):
    """Instagram refused the post because it is not public (e.g. a private account)."""

    user_message = (
        "This post is from a private account (or is no longer public), "
        "so we can't show the image."
    )
