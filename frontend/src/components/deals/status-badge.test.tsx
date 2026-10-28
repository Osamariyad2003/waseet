import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/deals/status-badge";
import { statusStyle } from "@/lib/status";
import { DEAL_STATES } from "@/lib/types";
import { render } from "@/test/render";

describe("StatusBadge", () => {
  it("labels every lifecycle state in English", () => {
    for (const state of DEAL_STATES) {
      const { unmount } = render(<StatusBadge state={state} />);
      // A state with no translation would render the raw key, which this
      // catches.
      expect(screen.getByText(/^[A-Z]/)).toBeInTheDocument();
      unmount();
    }
  });

  it("labels every lifecycle state with valid text", () => {
    for (const state of DEAL_STATES) {
      const { container, unmount } = render(<StatusBadge state={state} />);
      expect(container.textContent).not.toContain("states.");
      expect(container.textContent?.trim()).not.toBe("");
      unmount();
    }
  });

  it("shows what the state means when asked", () => {
    render(<StatusBadge state="FUNDED" withMeaning />);
    expect(screen.getByText("Money is held in escrow")).toBeInTheDocument();
  });

  it("never relies on colour alone", () => {
    // Each state carries a glyph as well as a colour, so the status is
    // readable in greyscale and to colour-blind users.
    for (const state of DEAL_STATES) {
      const { container, unmount } = render(<StatusBadge state={state} />);
      expect(container.textContent).toContain(statusStyle(state).glyph);
      unmount();
    }
  });

  it("maps the lifecycle onto the documented colour roles", () => {
    expect(statusStyle("DRAFT").role).toBe("held");
    expect(statusStyle("FUNDED").role).toBe("held");
    expect(statusStyle("DELIVERED").role).toBe("progress");
    expect(statusStyle("VERIFYING").role).toBe("progress");
    expect(statusStyle("RELEASED").role).toBe("paid");
    expect(statusStyle("SPLIT").role).toBe("paid");
    expect(statusStyle("REFUNDED").role).toBe("returned");
    expect(statusStyle("DISPUTED").role).toBe("attention");
  });

  it("gives each state a distinct glyph", () => {
    const glyphs = DEAL_STATES.map((state) => statusStyle(state).glyph);
    expect(new Set(glyphs).size).toBe(DEAL_STATES.length);
  });
});
