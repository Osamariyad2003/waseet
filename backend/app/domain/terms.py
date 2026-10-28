"""The Deal Terms Acknowledgment.

A plain-language summary of what both parties agreed to, pinned to the exact
confirmed checklist with a SHA-256 so the terms cannot drift. Deliberately an
honest record, not a binding legal instrument: it states the process in plain
words, it preserves every right, and it never claims the AI verdict is binding
evidence or that PayPal's dispute process can be waived.

Pure and deterministic — the hash depends only on the checklist text, so both
parties and any later reader compute the same value.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# The lifecycle, stated truthfully. These are shown to both parties, not a
# contract — they describe how Waseet actually behaves.
PROCESS_STEPS: tuple[str, ...] = (
    "The buyer and seller agree on this checklist before any money moves.",
    "The buyer funds the deal; the money is held in escrow on PayPal (sandbox).",
    "The seller delivers the work.",
    "An AI verifier checks the delivery against each checklist item and gives an "
    "advisory verdict with a confidence score.",
    "A confident pass releases the funds to the seller automatically; anything "
    "less goes to a human reviewer.",
    "Either party can contest the verdict, and a human reviewer makes the final "
    "decision.",
)

# The honest counterpart to the pasted spec's chargeback waiver: it preserves
# rights instead of stripping them.
RIGHTS_NOTICE: str = (
    "This summary records what both parties agreed to. It is not legal advice "
    "and waives no rights: it does not limit PayPal's dispute or buyer-protection "
    "process, and the AI verdict is advisory, not binding evidence."
)


@dataclass(frozen=True, slots=True)
class DealTerms:
    criteria: tuple[str, ...]
    canonical_checklist: str
    checklist_sha256: str
    buyer_confirmed: bool
    seller_confirmed: bool
    both_confirmed: bool


def canonical_checklist(descriptions: tuple[str, ...]) -> str:
    """A sorted, deterministic rendering of the checklist.

    Whitespace is collapsed and items are sorted, so the same set of criteria
    in any order yields the same string — and therefore the same hash.
    """
    cleaned = sorted(" ".join(d.split()) for d in descriptions if d.strip())
    return "\n".join(f"{i + 1}. {text}" for i, text in enumerate(cleaned))


def checklist_hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_terms(
    *,
    descriptions: tuple[str, ...],
    buyer_confirmed: bool,
    seller_confirmed: bool,
) -> DealTerms:
    canonical = canonical_checklist(descriptions)
    return DealTerms(
        criteria=tuple(" ".join(d.split()) for d in descriptions if d.strip()),
        canonical_checklist=canonical,
        checklist_sha256=checklist_hash(canonical),
        buyer_confirmed=buyer_confirmed,
        seller_confirmed=seller_confirmed,
        both_confirmed=buyer_confirmed and seller_confirmed,
    )
