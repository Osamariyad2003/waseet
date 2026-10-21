"""Fetching the deliverable so the verifier can actually inspect it.

FR-5 asks for a multimodal verifier that reads "text/image/URL/file". A URL
is only a pointer, so something has to resolve it — and that something is
fetching a URL chosen by the seller, which is a server-side request forgery
vector by construction. The guards live in the implementation; this module
is the contract.

A fetch never raises for a bad deliverable: an unreachable link, a blocked
address, an oversized file or an unsupported type all come back as
`unavailable` with a reason. The verifier is told plainly that it could not
look, and the prompt requires it to fail those criteria with low confidence
— which the policy routes to a human. Guessing is never an option.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

ContentKind = Literal["text", "image", "unavailable"]


@dataclass(frozen=True, slots=True)
class FetchedContent:
    """What the verifier gets to look at."""

    kind: ContentKind
    source_url: str = ""
    text: str | None = None
    image_base64: str | None = None
    media_type: str | None = None
    truncated: bool = False
    #: Why there is nothing to inspect. Shown to the model verbatim.
    reason: str | None = None

    @property
    def is_available(self) -> bool:
        return self.kind != "unavailable"

    @classmethod
    def unavailable(cls, reason: str, source_url: str = "") -> FetchedContent:
        return cls(kind="unavailable", reason=reason, source_url=source_url)


@runtime_checkable
class ContentFetcher(Protocol):
    """Resolves a deliverable URL into something inspectable."""

    async def fetch(self, url: str) -> FetchedContent:
        """Retrieve the content at `url`.

        Never raises on a bad or hostile URL — returns `unavailable` with a
        reason instead, so a broken deliverable routes to a dispute rather
        than failing the request.
        """
        ...
