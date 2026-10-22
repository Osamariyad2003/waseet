// The walkthrough manifest: each screen, its caption, and how long it shows.
// Captions follow the demo story — the agent judges, the policy gates, the
// human resolves.

export const FPS = 30;
export const WIDTH = 1280;
export const HEIGHT = 720;

export interface Screen {
  image: string;
  chapter: string;
  title: string;
  caption: string;
  seconds: number;
}

export const screens: Screen[] = [
  {
    image: "screens/01-deals-list.png",
    chapter: "The product",
    title: "Two deals, two outcomes",
    caption:
      "A buyer funds work, an AI verifies the delivery, and the money is released — or held for a human.",
    seconds: 5,
  },
  {
    image: "screens/02-create-deal.png",
    chapter: "1 · Agree the terms",
    title: "Describe the work in plain language",
    caption:
      "The AI turns the description into a testable checklist that both parties confirm before any money moves.",
    seconds: 5,
  },
  {
    image: "screens/04-checklist.png",
    chapter: "1 · Agree the terms",
    title: "An AI-drafted acceptance checklist",
    caption: "Both the buyer and the seller confirm it. The verifier is held to exactly these criteria.",
    seconds: 5,
  },
  {
    image: "screens/05-verification-pass.png",
    chapter: "2 · The agent judges",
    title: "The verifier reads the work",
    caption:
      "Per-criterion pass/fail, a confidence score, and reasoning — the agent judges, it never moves money.",
    seconds: 6,
  },
  {
    image: "screens/03-released-hero.png",
    chapter: "3 · The policy releases",
    title: "A confident pass auto-releases",
    caption:
      "A deterministic policy — not the model — clears the payout, pinned to the deal's amount and seller.",
    seconds: 5,
  },
  {
    image: "screens/06-audit-trail.png",
    chapter: "Explainable",
    title: "Every step is on the record",
    caption:
      "An append-only audit trail links each state change and decision to its PayPal reference id.",
    seconds: 5,
  },
  {
    image: "screens/07-disputed-hero.png",
    chapter: "4 · Fail safe, not open",
    title: "Uncertainty holds the money",
    caption:
      "A fail, low confidence, or a buyer contest routes the deal to a human — with the funds still in escrow.",
    seconds: 5,
  },
  {
    image: "screens/08-verification-fail.png",
    chapter: "4 · Fail safe, not open",
    title: "The verifier flags the miss",
    caption: "A raster file where the checklist asked for vector — the agent fails it and will not release.",
    seconds: 5,
  },
  {
    image: "screens/09-reviewer-decision.png",
    chapter: "5 · The human decides",
    title: "A human resolves the dispute",
    caption:
      "The AI recommends; the reviewer decides. Only that decision moves money, and it stays on the record.",
    seconds: 6,
  },
];

export const INTRO_SECONDS = 3.5;
export const OUTRO_SECONDS = 3.5;

export const totalDurationInFrames = Math.round(
  (INTRO_SECONDS + OUTRO_SECONDS + screens.reduce((s, x) => s + x.seconds, 0)) * FPS,
);
