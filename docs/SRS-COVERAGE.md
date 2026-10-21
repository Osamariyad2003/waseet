# SRS coverage report

Audited against the code on 21 Oct 2026, at commit `a4301a8`, and updated
the same day after Gap 1 was closed. Every claim
below was checked by reading the implementation or running it — not from
memory of having built it.

**Totals:** 542 backend tests, 34 frontend tests, 19 endpoints.

---

## FR-1 … FR-13

| ID | Requirement | Priority | Status | Where |
|---|---|---|---|---|
| FR-1 | Create a deal from a plain-language description | Must | **Done** | `POST /deals` → `DealService.create_deal` |
| FR-2 | AI drafts a checklist; both parties confirm before funding | Must | **Done** | criteria agent + `POST /deals/{id}/criteria/confirm`; the state machine's `_guard_fundable` refuses funding until both sides confirm |
| FR-3 | Buyer funds via PayPal; captured into the platform account | Must | **Done** | `POST /deals/{id}/order` + `/capture`, Orders v2 |
| FR-4 | Seller submits a deliverable (URL, **uploaded file**, image, repo, text) | Must | **Partial** | all five types are accepted and now *inspected*, but as references — no binary upload. See Gap 2 |
| FR-5 | AI verifies against each criterion: pass/fail, verdict, confidence, reasoning | Must | **Done** | the deliverable is fetched and the retrieved text or image is what the verifier judges — Gap 1, now closed |
| FR-6 | High-confidence pass auto-releases via Payout | Must | **Done** | `decision_policy.decide` → `SettlementService.settle` |
| FR-7 | Fail, low confidence, or buyer contest → DISPUTED | Must | **Done** | policy + `POST /deals/{id}/contest` |
| FR-8 | AI recommends release/refund/split; a human decides | Must | **Done** | `GET /dispute/recommendation`, `POST /dispute/resolve`, reviewer-only |
| FR-9 | Refund returns funds; split pays part and refunds the rest | Must / Could | **Done** | both implemented, incl. the optional split |
| FR-10 | Append-only audit log linked to the PayPal reference | Must | **Done** | `audit_log` + a DB trigger that rejects UPDATE and DELETE |
| FR-11 | Both parties read a deal timeline | Should | **Done** | `GET /deals/{id}` returns the timeline in one call |
| FR-12 | Parties are *updated* on key events via webhook-driven state | Should | **Partial** | state is reflected, not pushed — see Gap 3 |
| FR-13 | Configurable platform fee on release | Could | **Done** | `PLATFORM_FEE_PERCENT`, default 0 |

**12 of 13 complete; 1 partial (FR-4, no binary upload).**

---

## Gaps

### Gap 1 — the verifier could not open what it was judging (FR-5) · **closed**

**Originally:** the model was sent the deliverable's `content_ref` as a
string. Nothing fetched a URL and no image was ever attached, so for `url`,
`repo`, `image` and `file` deliverables the verifier was judging a link
rather than the work. It failed safely — anything it could not inspect was
marked failed at low confidence and routed to a human — but the demo's happy
path could not auto-release from a link.

**Now:** `integrations/content/` resolves the deliverable before the
verifier sees it. Retrieved text is embedded in the prompt inside a
`<retrieved_content>` boundary; a retrieved image is attached as a
multimodal image block; and content that could not be opened is reported to
the model in words, with an explicit instruction that it has not seen the
work and must fail those criteria.

The URL is attacker-controlled and the request comes from our server, so the
fetcher is written as a security boundary:

| Guard | Behaviour |
|---|---|
| Scheme | http and https only — no `file://`, `data:`, `gopher://` |
| Address | every hostname resolved and **every** resolved address checked; private, loopback, link-local (incl. `169.254.169.254` metadata), reserved and multicast refused — including IPv4-mapped IPv6 |
| Redirects | followed manually, at most 3, re-validating each hop so a public URL cannot bounce to metadata |
| Size | response streamed and cut at `CONTENT_MAX_BYTES`; a truncated image is reported unavailable rather than shown half-decoded |
| Types | plain text, Markdown, HTML, CSV, JSON, XML and SVG as text; PNG/JPEG/GIF/WebP as images; everything else refused |
| Failure | never raises — an unreachable, refused or oversized deliverable returns a reason, which routes to a human |

Retrieved content is treated as *more* hostile than the reference, not less:
the prompt's untrusted-data boundary explicitly covers "anything retrieved
from a link they supplied".

Covered by 57 tests in `tests/unit/test_content_fetcher.py`, plus prompt
assembly tests, toolbox tests and end-to-end flow tests.

### Gap 2 — no binary upload (FR-4)

The SRS says "uploaded file". The backend stores a `content_ref` and the UI
collects a reference; there is no upload endpoint and no file storage. A
seller links to a file rather than uploading one.

Deliberate: object storage, access control to the deal's parties, and
virus/content handling are a day's work that buys nothing the demo shows. The
`file` and `image` types remain selectable because a seller may legitimately
be pasting a link to either — and now that Gap 1 is closed, such a link is
fetched and inspected like any other, so what the verifier sees is the file
itself either way. What is missing is only the upload mechanism, not the
inspection.

### Gap 3 — events are reflected, not pushed (FR-12)

The SRS asks that parties "are updated on key events … via webhook-driven
state". Implemented: every key event lands in the deal's state and audit
trail, webhooks confirm captures, and the UI refetches after every action and
**polls while a deal is `VERIFYING`** so the verification result appears
without a manual refresh.

Not implemented: any outbound notification — no email, no push, no websocket.
A party who is not looking at the page learns nothing until they return to it.
FR-12 is a *Should*, and for a two-sided demo with both windows open the
distinction is invisible; for a real product it is not.

---

## Assumptions

Where the SRS was silent, with what was chosen and why.

| Assumption | Value | Reasoning |
|---|---|---|
| Auto-release confidence threshold | **0.80** | The Agentic Workflow doc's own example. Configurable via `AUTO_RELEASE_CONFIDENCE_THRESHOLD`; the gate is `>=`, so exactly 0.8 releases |
| Platform fee | **0%** | FR-13 is a *Could*. Wired end to end and tested, off by default so the demo's numbers are clean |
| Fee is taken from the seller's share only | — | On a split the buyer always gets back exactly `captured − seller_amount`; the platform never profits from a refund |
| JWT | **HS256, 24h** | Demo-grade. Production refuses to boot on a secret under 32 bytes or the dev default |
| Token storage (frontend) | **sessionStorage** | Readable by any script on the origin, so demo-grade; dies with the tab. Production wants an httpOnly cookie |
| Supported currencies | USD, EUR, GBP | Single-currency per deal; no FX, which the SRS puts out of scope |
| Amount bounds | 1.00 – 10,000.00 | Keeps sandbox payouts sane; rejects zero and negative at the edge |
| Deliverable size sent to the model | 20,000 chars | The SRS assumes deliverables "small enough for a model to inspect directly" |
| AI retry policy | 1 retry, transient errors only | Per the Agentic Workflow doc; anything still unresolved becomes `INCONCLUSIVE` → `DISPUTED` |
| Timeouts | PayPal 15s, AI 45s | Verification must "return within a few seconds" but a multimodal call needs headroom |
| Buyer contest window | `FUNDED` or `DELIVERED` only | The SRS lifecycle table lists exactly these two |
| Only a buyer may create a deal | — | The SRS has no "either party creates" requirement; one direction is simpler to reason about |
| A deal belonging to someone else | reported as **404** | So the API does not confirm which deal ids exist |
| Payout recipient | seller's `paypal_account_ref`, falling back to `PAYPAL_SELLER_RECEIVER_EMAIL` | Lets one env var drive the demo without editing the database |
| `PAYMENT.PAYOUTSBATCH.DENIED` | recorded, state unchanged | Nothing silently reverses a terminal state; a human is told instead |
| Postgres port | **5434** | 5432 and 5433 were taken by other projects on the dev machine |
| Default model | `claude-sonnet-5` | Multimodal and fast enough for a live demo; swappable via `AI_MODEL` |

---

## Deviations from the approved architecture

The layering holds: dependencies point inward, business logic lives only in
services and the domain, the state machine is the single place a state change
is decided, PayPal and the AI are reached only through their Protocols, and
every state change commits with its money movement and audit entry in one
transaction. Five additions to the specced module tree, each with a reason.

| Addition | Why |
|---|---|
| `domain/errors.py` | The backend prompt puts `errors.py` in `core/`. The domain raising from `core` would invert the dependency rule, so domain errors are defined in the domain and `core/errors.py` holds only the HTTP mapping |
| `domain/spend_mandate.py` | The Agentic Workflow doc's spend mandate — "pinned to this deal's exact amount and the designated seller". Pure policy over a deal, so it belongs in the domain |
| `services/agent_toolbox.py` | The same doc's read-only tool scope (`read_deal`, `read_criteria`, `read_deliverable`). Routing all agent context through one narrow class is what makes "no agent holds a pay capability" testable |
| `core/security.py` | JWT and password hashing, kept out of `dependencies.py` so the crypto is unit-testable without FastAPI |
| `models/sql_enums.py` | A Postgres enum is a database-level type; two tables sharing one needs a single object or the migration tries to `CREATE TYPE` twice |
| `integrations/content/` | FR-5 requires the verifier to read "text/image/URL/file". A URL is a pointer, so resolving it is an integration with the outside world and belongs behind a Protocol like the others |

### Endpoints beyond the documented contract

| Endpoint | Why |
|---|---|
| `POST /deals/{id}/contest` | Not in the doc's endpoint table, but the SRS lifecycle requires a buyer contest from FUNDED/DELIVERED and the frontend brief lists "contest" as a buyer action |
| `GET /paypal/client-token` | PayPal JS SDK **v6**, which the SRS mandates over v5, authenticates the browser with a short-lived client token. Without this the client secret would have to reach the browser |
| `GET /deals/{id}/dispute/recommendation` | FR-8 requires the reviewer to see the AI recommendation; the doc's table has only the resolve endpoint |
| `GET /auth/me` | Lets the frontend restore a session without trusting what it cached |
| `POST /webhooks/paypal/simulate` | Dev-only, env-gated, refused in production. Exercises the webhook idempotency path without a public tunnel |
| `GET /health` | Container health checks |

### Dependency changes

- **passlib dropped for `bcrypt` directly.** passlib 1.7.4 is incompatible
  with bcrypt 5 and would have silently truncated passwords at 72 bytes.
  Passwords are now SHA-256 pre-digested before bcrypt, which removes the
  limit instead of hiding it.
- **`lazy="selectin"` on `Deal.buyer`/`seller`.** A joined eager load adds an
  outer join, and Postgres refuses `SELECT … FOR UPDATE` against the nullable
  side of one — so the row lock every money path depends on was silently
  broken until the tests caught it.

### Scope held

Nothing was built that the SRS does not ask for. Specifically not built:
notifications, file upload, multi-reviewer arbitration, FX, KYC/AML, and the
optional sponsor integrations (AG Grid, Postman, Render) — all of which were
listed as optional or out of scope.

---

## Non-functional requirements

| Requirement | Status |
|---|---|
| Secrets in env, never committed | **Done** — `SecretStr`, `.env` gitignored, a log processor redacts known-sensitive keys as a backstop |
| Webhook signatures verified before acting | **Done** — and fails closed: a missing header or an unreachable PayPal is a rejection, never a pass |
| Idempotent transitions and payouts | **Done** — three independent layers: deterministic PayPal keys, a unique index on `event_id`, and the state machine recognising an already-applied event. Tested with a webhook replayed three times |
| Explainability | **Done** — every settlement is backed by stored reasoning; the backend rejects a dispute decision with empty reasoning |
| Latency / visible VERIFYING | **Done** — the state commits before the model call, and the UI polls rather than freezing |
| Auditability | **Done** — enforced by a database trigger, not convention |
| Privacy — only what is needed goes to the model | **Done** — `read_deal` returns description, amount and currency only; no emails, PayPal ids or party ids |
| Honesty — the verdict is advisory | **Done** — stated in the API response and in the UI, in both languages |

---

## What has never been run

Worth stating plainly before the submission:

- **The agents have never run against a real model.** All 542 backend tests
  use fakes. `ANTHROPIC_API_KEY` is still unset. In particular the multimodal
  image path has never been exercised against the real API.
- **No deliverable has ever been fetched from the real internet.** The
  fetcher's guards are tested against a mock transport, which exercises the
  real validation code but not real DNS or TLS.
- **No money has moved in the sandbox.** OAuth, the Payouts scope and Orders
  v2 create are confirmed live; capture, payout and refund have only ever run
  against the in-memory fake.
- **The webhook signature path has never seen a real PayPal signature** —
  `PAYPAL_WEBHOOK_ID` is unset and no tunnel has been run.

None of these is blocked by code. All three are blocked on credentials and a
single end-to-end run.
