// Capture the demo screens with Playwright at a crisp 1280x720 @2x.
//
// Logs in as each role, hides the Next dev indicator, and screenshots each
// screen of the walkthrough. Deal ids come from scripts/demo_setup.py output,
// passed as env or read from a small json the setup writes.
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const RELEASED = process.env.RELEASED_DEAL;
const DISPUTED = process.env.DISPUTED_DEAL;
const OUT = new URL("./public/screens/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");

const PASSWORD = "demo-password-123";

if (!RELEASED || !DISPUTED) {
  console.error("Set RELEASED_DEAL and DISPUTED_DEAL env vars (from demo_setup.py).");
  process.exit(1);
}

const HIDE_DEV = `nextjs-portal,#__next-build-watcher{display:none!important}`;

async function login(page, email) {
  await page.goto(`${BASE}/en/login`, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: HIDE_DEV });
  await page.fill('input[type=email]', email);
  await page.fill('input[type=password]', PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL("**/deals", { timeout: 10000 });
}

async function shot(page, name) {
  await page.addStyleTag({ content: HIDE_DEV });
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}${name}.png` });
  console.log("captured", name);
}

async function scrollTo(page, text) {
  await page.evaluate((t) => {
    const el = [...document.querySelectorAll("h2,h1,section")].find((e) =>
      new RegExp(t, "i").test(e.textContent),
    );
    el?.scrollIntoView({ block: "start" });
    window.scrollBy(0, -24);
  }, text);
  await page.waitForTimeout(500);
}

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 2,
});
const page = await context.newPage();
await mkdir(OUT, { recursive: true });

// --- Buyer's view --------------------------------------------------------
await login(page, "buyer@waseet.example.com");
await page.goto(`${BASE}/en/deals`, { waitUntil: "networkidle" });
await shot(page, "01-deals-list");

await page.goto(`${BASE}/en/deals/new`, { waitUntil: "networkidle" });
await shot(page, "02-create-deal");

// The released deal: outcome, checklist, verification, audit.
await page.goto(`${BASE}/en/deals/${RELEASED}`, { waitUntil: "networkidle" });
await page.waitForTimeout(600);
await shot(page, "03-released-hero");
await scrollTo(page, "Acceptance checklist");
await shot(page, "04-checklist");
await scrollTo(page, "Verification report");
await shot(page, "05-verification-pass");
await scrollTo(page, "History");
await shot(page, "06-audit-trail");

// The disputed deal: held hero + failed verification.
await page.goto(`${BASE}/en/deals/${DISPUTED}`, { waitUntil: "networkidle" });
await page.waitForTimeout(600);
await shot(page, "07-disputed-hero");
await scrollTo(page, "Verification report");
await shot(page, "08-verification-fail");

// --- Reviewer's view -----------------------------------------------------
await context.clearCookies();
await page.evaluate(() => sessionStorage.clear());
await login(page, "reviewer@waseet.example.com");
await page.goto(`${BASE}/en/deals/${DISPUTED}`, { waitUntil: "networkidle" });
await page.waitForTimeout(800);
await scrollTo(page, "Resolve this dispute");
await shot(page, "09-reviewer-decision");

await browser.close();
console.log("done");
