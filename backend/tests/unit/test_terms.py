"""The Deal Terms Acknowledgment: deterministic, hash-pinned, rights-preserving."""

from __future__ import annotations

from app.domain.terms import (
    RIGHTS_NOTICE,
    build_terms,
    canonical_checklist,
    checklist_hash,
)


def test_canonical_is_order_independent() -> None:
    a = canonical_checklist(("Deliver an SVG logo.", "Two color variants."))
    b = canonical_checklist(("Two color variants.", "Deliver an SVG logo."))
    assert a == b


def test_canonical_collapses_whitespace() -> None:
    assert canonical_checklist(("  Deliver   an  SVG   logo. ",)) == "1. Deliver an SVG logo."


def test_hash_tracks_content_not_order() -> None:
    items = ("A clear subject line.", "Exactly three bullets.")
    h1 = checklist_hash(canonical_checklist(items))
    h2 = checklist_hash(canonical_checklist(tuple(reversed(items))))
    assert h1 == h2
    assert len(h1) == 64  # sha-256 hex


def test_hash_changes_when_a_criterion_changes() -> None:
    base = checklist_hash(canonical_checklist(("One.", "Two.")))
    changed = checklist_hash(canonical_checklist(("One.", "Two!", "Three.")))
    assert base != changed


def test_build_terms_confirmation_flags() -> None:
    t = build_terms(descriptions=("One.",), buyer_confirmed=True, seller_confirmed=False)
    assert t.buyer_confirmed is True
    assert t.seller_confirmed is False
    assert t.both_confirmed is False


def test_rights_notice_preserves_paypal_and_advisory() -> None:
    # The honest counterpart to a chargeback waiver: it must NOT waive rights.
    assert "waives no rights" in RIGHTS_NOTICE
    assert "PayPal" in RIGHTS_NOTICE
    assert "advisory" in RIGHTS_NOTICE
