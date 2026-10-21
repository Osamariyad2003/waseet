"""HTTP deliverable fetcher, with the guards that make it safe to point at a
URL a seller chose.

The threat is server-side request forgery: the seller controls the URL, and
the server making the request sits inside the deployment's network. So:

  * only http and https — no file://, gopher://, data: or anything else;
  * every hostname is resolved before connecting and every resolved address
    is checked, so `localhost`, `127.0.0.1`, `169.254.169.254` (cloud
    metadata), private ranges and reserved space are all refused;
  * redirects are followed manually, at most three, re-validating the target
    each hop — otherwise a public URL could redirect straight to metadata;
  * the response is streamed and cut off at a byte cap, so a multi-gigabyte
    file cannot exhaust memory;
  * only text and common image types are accepted;
  * everything has a timeout.

A refusal is never an error: it comes back as `unavailable` with a reason
the verifier is shown, and the verifier is required to fail what it could
not inspect.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import re
import socket
from urllib.parse import urlparse, urlunparse

import httpx
import structlog

from app.config import Settings
from app.integrations.content.interface import FetchedContent

logger = structlog.get_logger(__name__)

MAX_REDIRECTS = 3

TEXT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/html",
    "text/csv",
    "application/json",
    "application/xml",
    "text/xml",
    "image/svg+xml",  # a vector logo is text, and worth reading as text
}

IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# Anthropic accepts these as image blocks.
SUPPORTED_IMAGE_BLOCKS = IMAGE_TYPES

_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\n{3,}")


class HttpContentFetcher:
    """Implements `ContentFetcher` over httpx."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._max_bytes = settings.content_max_bytes
        self._max_text_chars = settings.content_max_text_chars
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.content_fetch_timeout_seconds),
            follow_redirects=False,  # followed manually, re-validating each hop
            headers={"User-Agent": "Waseet-Verifier/0.1 (+escrow deliverable check)"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def fetch(self, url: str) -> FetchedContent:
        if not self._settings.enable_deliverable_fetch:
            return FetchedContent.unavailable(
                "fetching deliverables is disabled on this deployment", url
            )

        target = url.strip()
        for _ in range(MAX_REDIRECTS + 1):
            refusal = await self._validate(target)
            if refusal is not None:
                logger.info("content.refused", reason=refusal)
                return FetchedContent.unavailable(refusal, url)

            try:
                response = await self._http.get(target)
            except httpx.TimeoutException:
                return FetchedContent.unavailable("the link timed out", url)
            except httpx.HTTPError as exc:
                return FetchedContent.unavailable(
                    f"the link could not be opened ({type(exc).__name__})", url
                )

            if response.is_redirect:
                location = response.headers.get("location", "").strip()
                if not location:
                    return FetchedContent.unavailable(
                        "the link redirected without a destination", url
                    )
                target = str(httpx.URL(target).join(location))
                await response.aclose()
                continue

            return await self._read(response, url)

        return FetchedContent.unavailable("the link redirected too many times", url)

    # --- validation -------------------------------------------------------

    async def _validate(self, url: str) -> str | None:
        """None when the URL is safe to request, otherwise the reason it is not."""
        try:
            parsed = urlparse(url)
        except ValueError:
            return "the link is not a valid URL"

        if parsed.scheme not in {"http", "https"}:
            return f"only http and https links can be checked, not {parsed.scheme or 'none'}"
        if not parsed.hostname:
            return "the link has no host"

        try:
            addresses = await self._resolve(parsed.hostname)
        except OSError:
            return "the link's host could not be resolved"

        if not addresses:
            return "the link's host could not be resolved"

        for address in addresses:
            if not _is_public(address):
                # Blocks localhost, private ranges, link-local (including
                # cloud metadata at 169.254.169.254) and reserved space.
                return "the link points at a private or internal address"

        return None

    async def _resolve(self, hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        infos = await asyncio.get_running_loop().getaddrinfo(
            hostname, None, proto=socket.IPPROTO_TCP
        )
        resolved = []
        for info in infos:
            raw = info[4][0]
            try:
                resolved.append(ipaddress.ip_address(raw))
            except ValueError:
                continue
        return resolved

    # --- reading ----------------------------------------------------------

    async def _read(self, response: httpx.Response, source_url: str) -> FetchedContent:
        if response.status_code >= httpx.codes.BAD_REQUEST:
            await response.aclose()
            return FetchedContent.unavailable(
                f"the link returned HTTP {response.status_code}", source_url
            )

        media_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()

        if media_type not in TEXT_TYPES and media_type not in IMAGE_TYPES:
            await response.aclose()
            return FetchedContent.unavailable(
                f"the link is a {media_type or 'unknown'} file, which cannot be inspected",
                source_url,
            )

        body, truncated = await self._read_capped(response)

        if media_type in IMAGE_TYPES:
            if truncated:
                # A half-downloaded image is not an image.
                return FetchedContent.unavailable(
                    "the image is larger than the inspection limit", source_url
                )
            logger.info("content.fetched", kind="image", media_type=media_type, bytes=len(body))
            return FetchedContent(
                kind="image",
                source_url=source_url,
                image_base64=base64.b64encode(body).decode("ascii"),
                media_type=media_type,
            )

        text = body.decode("utf-8", errors="replace")
        if media_type == "text/html":
            text = _html_to_text(text)

        clipped = text[: self._max_text_chars]
        truncated = truncated or len(text) > self._max_text_chars
        logger.info("content.fetched", kind="text", media_type=media_type, chars=len(clipped))
        return FetchedContent(
            kind="text",
            source_url=source_url,
            text=clipped,
            media_type=media_type,
            truncated=truncated,
        )

    async def _read_capped(self, response: httpx.Response) -> tuple[bytes, bool]:
        """Read at most `max_bytes`, reporting whether more was available."""
        chunks: list[bytes] = []
        total = 0
        truncated = False
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            total += len(chunk)
            if total >= self._max_bytes:
                truncated = True
                break
        await response.aclose()
        return b"".join(chunks)[: self._max_bytes], truncated


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether it is safe to make a server-side request to this address."""
    if address.is_private or address.is_loopback or address.is_link_local:
        return False
    if address.is_reserved or address.is_multicast or address.is_unspecified:
        return False
    # An IPv6-mapped IPv4 address hides a private v4 behind a public-looking
    # v6, so unwrap it and check again.
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        return _is_public(mapped)
    return True


def _html_to_text(html: str) -> str:
    """Crude tag stripping, so the model reads the page rather than markup.

    Not a parser and does not need to be: the goal is to let a verifier see
    the words on a page, and markup noise only makes the judgment worse.
    """
    without_code = _SCRIPT_OR_STYLE.sub(" ", html)
    text = _TAG.sub(" ", without_code)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    lines = [line.strip() for line in text.splitlines()]
    return _WHITESPACE.sub("\n\n", "\n".join(line for line in lines if line))


def normalize_url(url: str) -> str:
    """Strip fragments and whitespace, so the same link is one cache key."""
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(fragment=""))
