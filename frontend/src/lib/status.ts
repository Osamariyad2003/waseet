/**
 * The one status colour system. Every badge, timeline dot and panel reads
 * from here, so a state cannot be green in one view and blue in another.
 *
 * Colour is never the only signal: each state also carries a distinct label
 * and an icon glyph, for colour-blind users and for anyone reading a
 * greyscale screenshot.
 */

import type { DealState } from "./types";

export type StatusRole = "held" | "progress" | "paid" | "returned" | "attention";

interface StatusStyle {
  role: StatusRole;
  /** Badge classes: background, text, ring. */
  badge: string;
  /** A solid dot for timelines. */
  dot: string;
  /** The role's text colour on its own, for a glyph on a white circle. */
  text: string;
  /** Soft surface for panels. */
  surface: string;
  /** A shape cue that survives greyscale. */
  glyph: string;
}

const STYLES: Record<StatusRole, Omit<StatusStyle, "role" | "glyph">> = {
  held: {
    badge: "bg-status-held-soft text-status-held ring-status-held/20",
    dot: "bg-status-held",
    text: "text-status-held",
    surface: "bg-status-held-soft border-status-held/20",
  },
  progress: {
    badge: "bg-status-progress-soft text-status-progress ring-status-progress/20",
    dot: "bg-status-progress",
    text: "text-status-progress",
    surface: "bg-status-progress-soft border-status-progress/20",
  },
  paid: {
    badge: "bg-status-paid-soft text-status-paid ring-status-paid/20",
    dot: "bg-status-paid",
    text: "text-status-paid",
    surface: "bg-status-paid-soft border-status-paid/20",
  },
  returned: {
    badge: "bg-status-returned-soft text-status-returned ring-status-returned/25",
    dot: "bg-status-returned",
    text: "text-status-returned",
    surface: "bg-status-returned-soft border-status-returned/25",
  },
  attention: {
    badge: "bg-status-attention-soft text-status-attention ring-status-attention/20",
    dot: "bg-status-attention",
    text: "text-status-attention",
    surface: "bg-status-attention-soft border-status-attention/20",
  },
};

const ROLE_BY_STATE: Record<DealState, StatusRole> = {
  DRAFT: "held",
  FUNDED: "held",
  DELIVERED: "progress",
  VERIFYING: "progress",
  RELEASED: "paid",
  SPLIT: "paid",
  REFUNDED: "returned",
  DISPUTED: "attention",
};

const GLYPH_BY_STATE: Record<DealState, string> = {
  DRAFT: "○",
  FUNDED: "●",
  DELIVERED: "◆",
  VERIFYING: "◍",
  RELEASED: "✓",
  SPLIT: "⇄",
  REFUNDED: "↩",
  DISPUTED: "!",
};

export function statusStyle(state: DealState): StatusStyle {
  const role = ROLE_BY_STATE[state];
  return { role, glyph: GLYPH_BY_STATE[state], ...STYLES[role] };
}

/** True while the deal is waiting on the model, so the UI can show motion
 * rather than looking frozen. */
export function isInFlight(state: DealState): boolean {
  return state === "VERIFYING";
}
