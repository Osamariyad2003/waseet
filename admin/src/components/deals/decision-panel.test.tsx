import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DecisionPanel } from "@/components/deals/decision-panel";
import type { MediationRecommendation } from "@/lib/types";
import { render } from "@/test/render";

const recommendation: MediationRecommendation = {
  recommendation: "refund",
  reasoning: "The agreed vector file was never delivered.",
  suggested_seller_amount: null,
  advisory_notice: "advisory",
};

describe("DecisionPanel", () => {
  it("shows the AI recommendation and marks it advisory", () => {
    render(
      <DecisionPanel
        dealAmount="250.00"
        currency="USD"
        recommendation={recommendation}
        onSubmit={vi.fn()}
      />,
    );
    const panel = within(screen.getByRole("region", { name: /ai recommendation/i }));
    expect(panel.getByText("Refund the buyer")).toBeInTheDocument();
    expect(
      panel.getByText("The agreed vector file was never delivered."),
    ).toBeInTheDocument();
    expect(screen.getByText(/only that decision moves money/i)).toBeInTheDocument();
  });

  it("does not preselect the AI's recommendation", async () => {
    // A reviewer who only ever confirms the AI is a rubber stamp, not a
    // human in the loop — so the form starts with nothing chosen.
    render(
      <DecisionPanel
        dealAmount="250.00"
        currency="USD"
        recommendation={recommendation}
        onSubmit={vi.fn()}
      />,
    );
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).not.toBeChecked();
    }
  });

  it("requires reasoning before it will submit", async () => {
    const onSubmit = vi.fn();
    render(<DecisionPanel dealAmount="250.00" currency="USD" onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole("radio", { name: /refund the buyer/i }));
    await userEvent.click(screen.getByRole("button", { name: /execute decision/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits a refund with the reviewer's reasoning", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<DecisionPanel dealAmount="250.00" currency="USD" onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole("radio", { name: /refund the buyer/i }));
    await userEvent.type(
      screen.getByRole("textbox", { name: "Your reasoning" }),
      "The file is a PNG, not a vector.",
    );
    await userEvent.click(screen.getByRole("button", { name: /execute decision/i }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        action: "refund",
        reasoning: "The file is a PNG, not a vector.",
        seller_amount: null,
      });
    });
  });

  it("asks for a seller amount only when splitting", async () => {
    render(<DecisionPanel dealAmount="250.00" currency="USD" onSubmit={vi.fn()} />);

    expect(screen.queryByRole("textbox", { name: "Amount to the seller" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /^split/i }));
    expect(screen.getByRole("textbox", { name: "Amount to the seller" })).toBeInTheDocument();
  });

  it("rejects a split amount at or above the deal amount", async () => {
    const onSubmit = vi.fn();
    render(<DecisionPanel dealAmount="250.00" currency="USD" onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole("radio", { name: /^split/i }));
    await userEvent.type(screen.getByRole("textbox", { name: "Amount to the seller" }), "250.00");
    await userEvent.type(screen.getByRole("textbox", { name: "Your reasoning" }), "Partial work.");
    await userEvent.click(screen.getByRole("button", { name: /execute decision/i }));

    await waitFor(() => {
      expect(screen.getByText(/more than 0 and less than/i)).toBeInTheDocument();
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("rejects a zero split amount", async () => {
    const onSubmit = vi.fn();
    render(<DecisionPanel dealAmount="250.00" currency="USD" onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole("radio", { name: /^split/i }));
    await userEvent.type(screen.getByRole("textbox", { name: "Amount to the seller" }), "0");
    await userEvent.type(screen.getByRole("textbox", { name: "Your reasoning" }), "Nothing usable.");
    await userEvent.click(screen.getByRole("button", { name: /execute decision/i }));

    await waitFor(() => expect(onSubmit).not.toHaveBeenCalled());
  });

  it("submits a valid split with its amount", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<DecisionPanel dealAmount="250.00" currency="USD" onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole("radio", { name: /^split/i }));
    await userEvent.type(screen.getByRole("textbox", { name: "Amount to the seller" }), "100.00");
    await userEvent.type(screen.getByRole("textbox", { name: "Your reasoning" }), "Half the work landed.");
    await userEvent.click(screen.getByRole("button", { name: /execute decision/i }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        action: "split",
        reasoning: "Half the work landed.",
        seller_amount: "100.00",
      });
    });
  });

  it("stays usable when the mediator is unavailable", () => {
    render(
      <DecisionPanel
        dealAmount="250.00"
        currency="USD"
        recommendationError="Could not get a recommendation. You can still decide."
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText(/you can still decide/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /execute decision/i })).toBeInTheDocument();
  });

  it("shows a loading state while the mediator is thinking", () => {
    render(
      <DecisionPanel
        dealAmount="250.00"
        currency="USD"
        isLoadingRecommendation
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getAllByText(/asking the mediator/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
