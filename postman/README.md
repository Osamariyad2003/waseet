# Waseet — Postman collection

A ready-to-run Postman collection for the Waseet escrow API. It walks a deal
through its whole lifecycle and covers the dispute, milestone, marketplace and
dashboard routes — 37 requests across 6 folders, generated from the live
OpenAPI surface.

## Files

- `Waseet.postman_collection.json` — the collection (schema v2.1.0).
- `Waseet-Local.postman_environment.json` — a matching environment pointing at
  `http://localhost:8000`.

## Setup

1. Import both files into Postman (**Import** → drop the two `.json` files).
2. Select the **Waseet — Local (sandbox)** environment.
3. Set the `password` variable to your seed password. If you don't know it,
   reseed with a chosen one:
   ```bash
   cd backend
   SEED_PASSWORD=changeme ./.venv/Scripts/python.exe scripts/seed.py --reset
   ```
   > `--reset` clears existing deals. Omit it to only (re)set the accounts.
4. Run the three **Login** requests first (buyer, seller, reviewer). Each
   captures its bearer token into a collection variable; `dealId`,
   `milestoneId` and `offerId` are captured automatically as you go.

## The happy path

Folder **2 · Deal lifecycle** runs top to bottom:

create → confirm criteria → fund (real capture, or the dev simulator) →
submit deliverable → **verify** (the AI judges the checklist and auto-releases
on high confidence) → read the report, payouts, activity and audit log.

The collection's auth defaults to the buyer's token; requests that act as the
seller or reviewer override it with their own token, so the flow is
role-correct no matter the order once all three logins have run.

Everything runs against the PayPal **sandbox** — no real money moves.

## Run it headless (optional)

With [newman](https://github.com/postmanlabs/newman):

```bash
newman run postman/Waseet.postman_collection.json \
  -e postman/Waseet-Local.postman_environment.json \
  --env-var password=<your-seed-password>
```
