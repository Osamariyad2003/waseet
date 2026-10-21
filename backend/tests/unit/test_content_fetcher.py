"""The deliverable fetcher, and the guards that make it safe.

The URL is chosen by the seller and the request is made by our server, from
inside our network. That is server-side request forgery by construction, so
most of this file is adversarial: the useful question is not "does it fetch
a page" but "what does it refuse".

Nothing here raises. A refusal comes back as `unavailable` with a reason,
because an unfetchable deliverable has to route to a human, not 500 the
verification.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from app.config import Settings
from app.integrations.content.client import HttpContentFetcher, _html_to_text, _is_public
from app.integrations.content.interface import ContentFetcher, FetchedContent

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def make_settings(**overrides) -> Settings:
    config = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "jwt_secret": "test-secret-long-enough-for-hs256-here",
        **overrides,
    }
    return Settings(**config)


def fetcher_for(handler, **settings_overrides) -> HttpContentFetcher:
    """A fetcher whose socket is replaced but whose guards are real."""
    settings = make_settings(**settings_overrides)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    return HttpContentFetcher(settings, http_client=client)


def ok(content: bytes, content_type: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-type": content_type})

    return handler


@pytest.fixture
def allow_public_dns(monkeypatch):
    """Resolve every host to a public address, so the transport is what
    answers rather than real DNS."""

    async def resolve(self, hostname):
        import ipaddress

        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(HttpContentFetcher, "_resolve", resolve)


def test_the_fetcher_satisfies_the_protocol():
    assert isinstance(fetcher_for(ok(b"x", "text/plain")), ContentFetcher)


class TestSsrfGuards:
    """The reason this module needs to exist."""

    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "10.0.0.1",
            "192.168.1.1",
            "172.16.0.1",
            "169.254.169.254",  # cloud instance metadata
            "[::1]",
            "[fd00::1]",
        ],
    )
    async def test_private_and_internal_addresses_are_refused(self, host):
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, content=b"secret", headers={"content-type": "text/plain"})

        result = await fetcher_for(handler).fetch(f"http://{host}/admin")

        assert not result.is_available
        assert "private or internal" in (result.reason or "")
        assert not called, "the request must not be made at all"

    async def test_a_public_hostname_resolving_to_a_private_ip_is_refused(self, monkeypatch):
        """DNS rebinding: the name looks fine, the address does not."""
        import ipaddress

        async def resolve(self, hostname):
            return [ipaddress.ip_address("127.0.0.1")]

        monkeypatch.setattr(HttpContentFetcher, "_resolve", resolve)

        result = await fetcher_for(ok(b"x", "text/plain")).fetch("https://looks-fine.example.com/")
        assert not result.is_available
        assert "private or internal" in (result.reason or "")

    async def test_a_host_with_one_private_address_among_several_is_refused(self, monkeypatch):
        """Every resolved address has to be safe, not just the first."""
        import ipaddress

        async def resolve(self, hostname):
            return [
                ipaddress.ip_address("93.184.216.34"),
                ipaddress.ip_address("10.1.2.3"),
            ]

        monkeypatch.setattr(HttpContentFetcher, "_resolve", resolve)

        result = await fetcher_for(ok(b"x", "text/plain")).fetch("https://mixed.example.com/")
        assert not result.is_available

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://example.com/",
            "data:text/plain;base64,aGVsbG8=",
            "ftp://example.com/x",
            "javascript:alert(1)",
        ],
    )
    async def test_only_http_and_https_are_allowed(self, url):
        result = await fetcher_for(ok(b"x", "text/plain")).fetch(url)
        assert not result.is_available
        assert "http and https" in (result.reason or "")

    async def test_a_redirect_into_a_private_address_is_refused(self, monkeypatch):
        """The first hop is public; the second is metadata. Following
        redirects blindly would hand the model our instance credentials."""
        import ipaddress

        async def resolve(self, hostname):
            if "metadata" in hostname or hostname.startswith("169.254"):
                return [ipaddress.ip_address("169.254.169.254")]
            return [ipaddress.ip_address("93.184.216.34")]

        monkeypatch.setattr(HttpContentFetcher, "_resolve", resolve)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "start.example.com":
                return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
            return httpx.Response(200, content=b"creds", headers={"content-type": "text/plain"})

        result = await fetcher_for(handler).fetch("https://start.example.com/")
        assert not result.is_available
        assert "private or internal" in (result.reason or "")

    async def test_a_redirect_loop_terminates(self, allow_public_dns):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://example.com/again"})

        result = await fetcher_for(handler).fetch("https://example.com/start")
        assert not result.is_available
        assert "redirected too many times" in (result.reason or "")

    async def test_an_unresolvable_host_is_refused(self):
        result = await fetcher_for(ok(b"x", "text/plain")).fetch(
            "https://this-host-does-not-exist.invalid/"
        )
        assert not result.is_available
        assert "resolved" in (result.reason or "")


class TestTextContent:
    async def test_plain_text_is_returned(self, allow_public_dns):
        result = await fetcher_for(ok(b"a vector logo spec", "text/plain")).fetch(
            "https://example.com/spec.txt"
        )
        assert result.kind == "text"
        assert result.text == "a vector logo spec"

    async def test_svg_is_read_as_text(self, allow_public_dns):
        """A vector logo is text, and the verifier should read it."""
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'
        result = await fetcher_for(ok(svg, "image/svg+xml")).fetch("https://example.com/logo.svg")
        assert result.kind == "text"
        assert "<circle" in (result.text or "")

    async def test_html_is_stripped_to_its_words(self, allow_public_dns):
        html = (
            b"<html><head><style>p{color:red}</style></head>"
            b"<body><h1>Logo</h1><p>Vector file</p>"
            b"<script>evil()</script></body></html>"
        )
        result = await fetcher_for(ok(html, "text/html")).fetch("https://example.com/page")

        assert result.kind == "text"
        assert "Logo" in (result.text or "")
        assert "Vector file" in (result.text or "")
        assert "evil()" not in (result.text or "")
        assert "<h1>" not in (result.text or "")

    async def test_oversized_text_is_truncated_and_says_so(self, allow_public_dns):
        body = b"x" * 50_000
        result = await fetcher_for(ok(body, "text/plain"), content_max_text_chars=1_000).fetch(
            "https://example.com/big.txt"
        )

        assert result.kind == "text"
        assert len(result.text or "") == 1_000
        assert result.truncated

    async def test_a_byte_cap_stops_a_huge_download(self, allow_public_dns):
        body = b"y" * 2_000_000
        result = await fetcher_for(ok(body, "text/plain"), content_max_bytes=1_000).fetch(
            "https://example.com/huge.txt"
        )
        assert result.truncated
        assert len(result.text or "") <= 1_000

    async def test_invalid_utf8_does_not_crash_the_verification(self, allow_public_dns):
        result = await fetcher_for(ok(b"\xff\xfe broken", "text/plain")).fetch(
            "https://example.com/x"
        )
        assert result.kind == "text"
        assert result.text is not None


class TestImageContent:
    async def test_a_png_comes_back_as_base64_for_the_model(self, allow_public_dns):
        result = await fetcher_for(ok(PNG_BYTES, "image/png")).fetch("https://example.com/logo.png")

        assert result.kind == "image"
        assert result.media_type == "image/png"
        assert base64.b64decode(result.image_base64 or "") == PNG_BYTES

    async def test_an_oversized_image_is_unavailable_not_half_decoded(self, allow_public_dns):
        """Half an image is not an image — better to say so than to show the
        model a corrupt file and let it guess."""
        result = await fetcher_for(ok(PNG_BYTES * 100, "image/png"), content_max_bytes=50).fetch(
            "https://example.com/big.png"
        )

        assert not result.is_available
        assert "larger than the inspection limit" in (result.reason or "")


class TestUnsupportedAndBroken:
    @pytest.mark.parametrize(
        "content_type", ["application/pdf", "application/zip", "video/mp4", ""]
    )
    async def test_a_type_that_cannot_be_inspected_is_reported(
        self, allow_public_dns, content_type
    ):
        result = await fetcher_for(ok(b"...", content_type)).fetch("https://example.com/file")
        assert not result.is_available
        assert "cannot be inspected" in (result.reason or "")

    @pytest.mark.parametrize("status", [404, 403, 500, 503])
    async def test_an_error_response_is_reported_with_its_status(self, allow_public_dns, status):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, content=b"nope")

        result = await fetcher_for(handler).fetch("https://example.com/missing")
        assert not result.is_available
        assert str(status) in (result.reason or "")

    async def test_a_timeout_is_reported_rather_than_raised(self, allow_public_dns):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("too slow")

        result = await fetcher_for(handler).fetch("https://example.com/slow")
        assert not result.is_available
        assert "timed out" in (result.reason or "")

    async def test_a_connection_error_is_reported_rather_than_raised(self, allow_public_dns):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        result = await fetcher_for(handler).fetch("https://example.com/down")
        assert not result.is_available

    async def test_fetching_can_be_turned_off_entirely(self, allow_public_dns):
        result = await fetcher_for(ok(b"x", "text/plain"), enable_deliverable_fetch=False).fetch(
            "https://example.com/x"
        )
        assert not result.is_available
        assert "disabled" in (result.reason or "")


class TestAddressClassification:
    @pytest.mark.parametrize(
        "address", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"]
    )
    def test_public_addresses_are_allowed(self, address):
        import ipaddress

        assert _is_public(ipaddress.ip_address(address))

    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.0.1",
            "169.254.169.254",
            "0.0.0.0",
            "::1",
            "fe80::1",
            "fd00::1",
            "::ffff:127.0.0.1",  # IPv4-mapped loopback hiding in a v6 address
            "::ffff:10.0.0.1",
        ],
    )
    def test_internal_addresses_are_refused(self, address):
        import ipaddress

        assert not _is_public(ipaddress.ip_address(address))


class TestHtmlToText:
    def test_it_keeps_the_words_and_drops_the_markup(self):
        assert "Hello" in _html_to_text("<p>Hello</p>")
        assert "<p>" not in _html_to_text("<p>Hello</p>")

    def test_it_decodes_common_entities(self):
        assert "Tom & Jerry" in _html_to_text("<p>Tom &amp; Jerry</p>")

    def test_it_collapses_runs_of_blank_lines(self):
        assert "\n\n\n" not in _html_to_text("<p>a</p>\n\n\n\n\n<p>b</p>")


class TestFetchedContent:
    def test_unavailable_carries_its_reason(self):
        result = FetchedContent.unavailable("nope", "https://example.com")
        assert not result.is_available
        assert result.reason == "nope"
        assert result.source_url == "https://example.com"
