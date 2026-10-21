# The Waseet demo — under three minutes

Two deals. The happy path pays out automatically; the dispute path holds the
money for a human. Both end in a visible balance change and an audit trail.

## Before you record

```bash
docker compose up -d postgres
cd backend && uv run alembic upgrade head && uv run python scripts/seed.py --reset
cd backend && uv run uvicorn app.main:app --port 8000
cd frontend && npm run dev
```

`--reset` clears every deal but keeps the accounts, so you can rehearse and
re-record without a stale timeline in shot.

Checks worth doing once, before the camera is on:

- `uv run python scripts/smoke_paypal.py` — credentials work, Payouts scope present
- `PAYPAL_SELLER_RECEIVER_EMAIL` points at the **seller's sandbox personal
  account**, or the release lands nowhere useful
- `ANTHROPIC_API_KEY` is set, or deal creation fails at the checklist step
- Open the seller's sandbox account at
  [sandbox.paypal.com](https://www.sandbox.paypal.com) in a second window and
  note the starting balance — the balance change is the payoff shot

Three browser windows, signed in as buyer, seller and reviewer, saves fumbling
between accounts on camera.

---

## Scene 1 — the deal and its checklist (~35s)

**As the buyer.** New deal:

> **Title:** Coffee shop logo
> **Seller:** the seller's Waseet email
> **Description:** Design a logo for a coffee shop, delivered as an SVG vector
> file with a transparent background.
> **Amount:** 250.00 USD

Submit. The criteria agent drafts the acceptance checklist — **this is the
first agent, on screen.** Say what it is: plain language in, testable criteria
out, and neither party can be held to anything they did not confirm.

Confirm as the buyer, then as the seller. The deal is now fundable.

> **Say:** "The AI turns the description into a checklist. Both sides confirm
> it before any money moves — that is what the verifier will be held to later."

## Scene 2 — fund the escrow (~25s)

**As the buyer.** Pay with PayPal → sandbox checkout → approve.

The deal moves to **FUNDED**. The money is captured into the platform account:
held, not forwarded.

> **Say:** "Captured into the platform account. The seller cannot touch it, and
> neither can the buyer."

## Scene 3 — deliver and auto-release (~45s)

**As the seller.** Submit a deliverable that meets the checklist — a link to a
vector file.

The deal goes to **VERIFYING** and the screen says so rather than freezing.
Then the report appears: per-criterion findings, an overall verdict, a
confidence score, and the model's reasoning.

Confidence clears the gate, so the policy releases. **Cut to the seller's
sandbox balance — it has gone up.**

> **Say:** "The agent judged the work. It did not pay anyone. A fixed policy
> read the verdict and the confidence, and only then did the system release."

## Scene 4 — the dispute path (~45s)

A second deal, already funded, where the seller's deliverable **misses a
criterion** — a raster PNG where the checklist asked for a vector.

Submit it. The verifier fails it and the deal goes to **DISPUTED**, not to a
payout. The money is still held.

**As the reviewer.** The dispute panel shows the mediator agent's
recommendation and its reasoning — labelled advisory, and deliberately not
preselected. Choose **Refund the buyer**, type the reasoning, execute.

**Cut to the buyer's sandbox balance — refunded.**

> **Say:** "Fail, low confidence, or a buyer contest — all of them land here,
> with the money held. The AI recommends. A human decides. Only that decision
> moves money."

## Scene 5 — the audit trail (~20s)

Open either timeline and scroll. Every state change, who caused it, the AI's
reasoning, and the PayPal reference id against each money movement.

> **Say:** "Nothing happened without a recorded reason. The log is append-only
> — the database itself rejects an update or a delete."

Optional closer, if there is time: switch the language toggle to Arabic and let
the whole interface mirror to RTL.

---

## If something goes wrong on camera

| Symptom | Cause | Fix |
|---|---|---|
| Deal creation fails at the checklist | `ANTHROPIC_API_KEY` missing or rate-limited | Check the key; the error says "the AI could not draft a checklist" and nothing was created, so just retry |
| Checkout popup blocked | Browser popup blocker | Allow popups for localhost before recording |
| Release fails with a payout error | `PAYPAL_SELLER_RECEIVER_EMAIL` unset or not a real sandbox account | The deal stays mid-flight and no money moved — fix the env var and retry |
| Verification sits in VERIFYING | The model call is slow | The page polls; it resolves or routes to DISPUTED rather than hanging forever |
| Seller balance does not move | Sandbox payouts can take a moment | Refresh the sandbox account page |

Nothing in the demo depends on a public webhook URL. Webhooks confirm state;
they never release, refund or split.

---

## The three sentences that matter

If the video only lands three ideas, make them these:

1. **An agent reads real work and causes a real payment** on PayPal rails —
   not a recommendation someone else acts on.
2. **The agent cannot pay.** A deterministic policy decides whether its
   judgment clears the bar, and the payment is pinned to the deal's own amount
   and the designated seller.
3. **Uncertainty goes to a human**, with the money still held and the agent's
   reasoning on the record for the reviewer to read.
