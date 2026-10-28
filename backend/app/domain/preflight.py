"""The pre-flight intake screen for deliverable submissions.

A read-only, deterministic gate that runs before the verifier agent. It treats
every byte of the submission as untrusted data and never executes anything
inside it — its only output is a risk assessment. Deterministic on purpose: a
security filter must not itself be steerable by the content it inspects, which
an LLM screener would be. It moves no money and changes no state; the caller
decides what to do with a REJECT (route to a human reviewer).

Checks (FR, mirrored from the intake spec):
  1. Injection        — adversarial "override the verifier" attempts.
  2. Off-platform     — attempts to move settlement off PayPal.
  3. Corrupt payload  — declared type vs. content mismatch, empty submissions.
  4. Anomaly/tamper   — placeholder text, near-empty bodies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class IntakeStatus(str, Enum):
    PASS = "PASS"
    FLAGGED = "FLAGGED"
    REJECT = "REJECT"


class IntakeSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IntakeCategory(str, Enum):
    INJECTION = "INJECTION"
    OFF_PLATFORM = "OFF_PLATFORM"
    CORRUPT_PAYLOAD = "CORRUPT_PAYLOAD"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class IntakeFinding:
    category: IntakeCategory
    severity: IntakeSeverity
    detail: str


@dataclass(frozen=True, slots=True)
class IntakeReport:
    deal_id: str
    status: IntakeStatus
    risk_score: float
    injection_detected: bool
    off_platform_leakage: bool
    findings: tuple[IntakeFinding, ...]
    proceed_to_verifier: bool

    def to_dict(self) -> dict:
        """The exact JSON shape the intake contract specifies."""
        findings = [
            {
                "category": f.category.value,
                "severity": f.severity.value,
                "detail": f.detail,
            }
            for f in self.findings
        ] or [{"category": IntakeCategory.NONE.value, "severity": IntakeSeverity.LOW.value, "detail": "No issues found."}]
        return {
            "deal_id": self.deal_id,
            "status": self.status.value,
            "risk_score": round(self.risk_score, 2),
            "injection_detected": self.injection_detected,
            "off_platform_leakage": self.off_platform_leakage,
            "findings": findings,
            "proceed_to_verifier": self.proceed_to_verifier,
        }

    def summary(self) -> str:
        """A one-line, human-readable reason, for an audit entry or a report."""
        if not self.findings:
            return "Pre-flight intake passed with no findings."
        parts = "; ".join(f"{f.category.value} ({f.severity.value}): {f.detail}" for f in self.findings)
        return f"Pre-flight intake {self.status.value} — {parts}"


# --- detectors -------------------------------------------------------------

# Adversarial attempts to override the verifier. Case-insensitive.
_INJECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), label)
    for pattern, label in (
        (r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|rules)", "an 'ignore previous instructions' directive"),
        (r"disregard\s+(the\s+)?(criteria|checklist|instructions|rules|above)", "a 'disregard the criteria' directive"),
        (r"mark\s+(this|it|the\s+\w+)?\s*(as\s+)?(verified|passed|approved|complete|done)", "a 'mark as verified/approved' directive"),
        (r"you\s+must\s+(return|output|respond|reply|approve|pass|mark)", "a 'you must approve/return' directive"),
        (r"(set|return|with)\s+confidence\s*(score\s*)?(of\s*)?(=\s*)?1(\.0+)?\b", "a forced confidence-1.0 directive"),
        (r"system\s+(override|prompt|instruction|message)", "a fake 'system override/prompt' marker"),
        (r"\b(as|to)\s+the\s+(verifier|ai|assistant|system|model)\b", "text addressed to the verifier/AI"),
        (r"do\s+not\s+(mention|reveal|tell|disclose|flag)", "a 'do not mention this' directive"),
        (r"\b(this|the)\s+(deliverable|work|submission)\s+is\s+(already\s+)?(approved|accepted|verified)", "a self-approval claim"),
    )
)

# Attempts to pull settlement off PayPal.
_CRYPTO_BTC = re.compile(r"\b(bc1[a-z0-9]{20,}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
_CRYPTO_ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_PAYMENT_LINKS = re.compile(r"\b(paypal\.me|venmo|cash\.?app|wise\.com|revolut|zelle|chime|t\.me|wa\.me|whatsapp)\b", re.IGNORECASE)
_WIRE_TERMS = re.compile(r"\b(wire\s+transfer|bank\s+transfer|iban|swift\s*code|routing\s+number|account\s+number)\b", re.IGNORECASE)
_OFF_PLATFORM_ASK = re.compile(r"\b(pay|send|transfer|wire)\s+(me\s+)?(the\s+)?(money|funds|payment|balance|amount)\b", re.IGNORECASE)
_CONTACT_OFFPLATFORM = re.compile(r"\b(contact|email|reach|message|dm|text|call)\s+me\s+(at|on|directly|here)\b", re.IGNORECASE)

# Anomaly / tampering signals.
_PLACEHOLDER = re.compile(r"\b(lorem ipsum|will send later|coming soon|placeholder|to be (determined|added|decided)|\btbd\b|\btodo\b|work in progress|sample text|test test|asdf|qwerty)\b", re.IGNORECASE)
_URL_LIKE = re.compile(r"https?://", re.IGNORECASE)

_SEVERITY_WEIGHT = {IntakeSeverity.LOW: 0.25, IntakeSeverity.MEDIUM: 0.55, IntakeSeverity.HIGH: 0.9}


def screen(
    *,
    deal_id: str,
    agreement_summary: str,
    deliverable_type: str,
    content_ref: str,
    note: str | None = None,
    urls: tuple[str, ...] = (),
) -> IntakeReport:
    """Screen a submission. Pure and deterministic; never raises."""
    haystack = "\n".join(part for part in (content_ref or "", note or "", *urls) if part)
    findings: list[IntakeFinding] = []

    # 1. Injection — scan all free text.
    for pattern, label in _INJECTION_PATTERNS:
        if pattern.search(haystack):
            findings.append(
                IntakeFinding(IntakeCategory.INJECTION, IntakeSeverity.HIGH, f"The submission contains {label}.")
            )
            break  # one injection finding is enough to route to a human

    # 2. Off-platform circumvention.
    if _CRYPTO_BTC.search(haystack) or _CRYPTO_ETH.search(haystack):
        findings.append(IntakeFinding(IntakeCategory.OFF_PLATFORM, IntakeSeverity.HIGH, "The submission contains a cryptocurrency wallet address."))
    if _PAYMENT_LINKS.search(haystack):
        findings.append(IntakeFinding(IntakeCategory.OFF_PLATFORM, IntakeSeverity.HIGH, "The submission links to an off-platform payment service."))
    if _WIRE_TERMS.search(haystack) or _OFF_PLATFORM_ASK.search(haystack):
        findings.append(IntakeFinding(IntakeCategory.OFF_PLATFORM, IntakeSeverity.MEDIUM, "The submission asks to move payment off PayPal (wire/bank/direct transfer)."))
    if _CONTACT_OFFPLATFORM.search(haystack):
        findings.append(IntakeFinding(IntakeCategory.OFF_PLATFORM, IntakeSeverity.MEDIUM, "The submission asks the buyer to make contact off-platform."))

    # 3. Corrupt payload — declared type vs. content.
    body = (content_ref or "").strip()
    if not body:
        findings.append(IntakeFinding(IntakeCategory.CORRUPT_PAYLOAD, IntakeSeverity.HIGH, "The submission is empty."))
    elif deliverable_type in {"url", "repo", "image", "file"} and not _URL_LIKE.search(body) and not urls:
        findings.append(IntakeFinding(IntakeCategory.CORRUPT_PAYLOAD, IntakeSeverity.HIGH, f"A '{deliverable_type}' deliverable has no URL to the work."))

    # 4. Anomaly / tampering.
    if _PLACEHOLDER.search(haystack):
        findings.append(IntakeFinding(IntakeCategory.CORRUPT_PAYLOAD, IntakeSeverity.MEDIUM, "The submission looks like a placeholder, not finished work."))
    elif deliverable_type == "text" and len(body) < 20:
        findings.append(IntakeFinding(IntakeCategory.CORRUPT_PAYLOAD, IntakeSeverity.LOW, "The text submission is suspiciously short."))

    return _assemble(deal_id, tuple(findings))


def _assemble(deal_id: str, findings: tuple[IntakeFinding, ...]) -> IntakeReport:
    if not findings:
        return IntakeReport(deal_id, IntakeStatus.PASS, 0.0, False, False, (), True)

    severities = [f.severity for f in findings]
    base = max(_SEVERITY_WEIGHT[s] for s in severities)
    risk = min(1.0, base + 0.05 * (len(findings) - 1))

    has_high = IntakeSeverity.HIGH in severities
    status = IntakeStatus.REJECT if has_high else IntakeStatus.FLAGGED

    return IntakeReport(
        deal_id=deal_id,
        status=status,
        risk_score=risk,
        injection_detected=any(f.category is IntakeCategory.INJECTION for f in findings),
        off_platform_leakage=any(f.category is IntakeCategory.OFF_PLATFORM for f in findings),
        findings=findings,
        proceed_to_verifier=status is not IntakeStatus.REJECT,
    )
