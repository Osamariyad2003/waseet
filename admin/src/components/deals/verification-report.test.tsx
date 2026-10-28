import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ConfidenceMeter,
  VerificationReport,
} from "@/components/deals/verification-report";
import type { VerificationReport as Report } from "@/lib/types";
import { render } from "@/test/render";

function report(overrides: Partial<Report> = {}): Report {
  return {
    id: "report-1",
    verdict: "pass",
    confidence: "0.94",
    reasoning: "Both criteria are met by the submitted file.",
    per_criterion: [
      {
        criterion_id: "c1",
        text: "The deliverable is a working link.",
        pass: true,
        note: "The link resolves to an SVG.",
      },
      {
        criterion_id: "c2",
        text: "The logo is a vector file.",
        pass: true,
        note: "The file is an SVG.",
      },
    ],
    verified_criteria: [
      "The deliverable is a working link.",
      "The logo is a vector file.",
    ],
    unmet_or_missing_criteria: [],
    decided_by: "ai",
    recommendation: null,
    decided_at: "2026-10-20T10:00:00Z",
    ...overrides,
  };
}

describe("VerificationReport", () => {
  it("shows the verdict, confidence and reasoning", () => {
    render(<VerificationReport report={report()} />);
    expect(screen.getByText("Meets the checklist")).toBeInTheDocument();
    expect(screen.getByText("94%")).toBeInTheDocument();
    expect(
      screen.getByText("Both criteria are met by the submitted file."),
    ).toBeInTheDocument();
  });

  it("lists each criterion with its finding", () => {
    render(<VerificationReport report={report()} />);
    // The condition text appears in both the audit summary and the detail list.
    expect(screen.getAllByText("The deliverable is a working link.").length).toBeGreaterThan(0);
    expect(screen.getByText("The link resolves to an SVG.")).toBeInTheDocument();
  });

  it("groups conditions into a met / unmet audit summary", () => {
    render(
      <VerificationReport
        report={report({
          verdict: "fail",
          per_criterion: [
            { criterion_id: "c1", text: "Has a subject line.", pass: true, note: "Present." },
            { criterion_id: "c2", text: "Exactly three bullets.", pass: false, note: "Had four." },
          ],
          verified_criteria: ["Has a subject line."],
          unmet_or_missing_criteria: ["Exactly three bullets."],
        })}
      />,
    );
    expect(screen.getByText("Conditions met · 1")).toBeInTheDocument();
    expect(screen.getByText("Conditions unmet or missing · 1")).toBeInTheDocument();
  });

  it("states that an AI verdict is advisory", () => {
    // The SRS honesty requirement: never presented as a guarantee.
    render(<VerificationReport report={report()} />);
    expect(screen.getByText(/advisory/i)).toBeInTheDocument();
    expect(screen.getByText(/human reviewer resolves any dispute/i)).toBeInTheDocument();
  });

  it("does not show the AI advisory notice on a human decision", () => {
    render(<VerificationReport report={report({ decided_by: "human" })} />);
    expect(screen.getByText("Decided by a human reviewer")).toBeInTheDocument();
    expect(screen.queryByText(/advisory/i)).not.toBeInTheDocument();
  });

  it("shows a failed criterion as not met, in text as well as colour", () => {
    render(
      <VerificationReport
        report={report({
          verdict: "fail",
          per_criterion: [
            {
              criterion_id: "c2",
              text: "The logo is a vector file.",
              pass: false,
              note: "The file is a raster PNG.",
            },
          ],
          verified_criteria: [],
          unmet_or_missing_criteria: ["The logo is a vector file."],
        })}
      />,
    );
    expect(screen.getByText("Does not meet the checklist")).toBeInTheDocument();
    // The screen-reader-only label states the outcome in words.
    expect(screen.getByText("Not met.", { exact: false })).toBeInTheDocument();
  });

  it("renders an inconclusive verdict rather than guessing", () => {
    render(
      <VerificationReport
        report={report({ verdict: "inconclusive", confidence: "0.000", per_criterion: [] })}
      />,
    );
    expect(screen.getByText("Could not be determined")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});

describe("ConfidenceMeter", () => {
  it("exposes the value to assistive tech", () => {
    render(<ConfidenceMeter confidence="0.62" />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "62");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
  });

  it("clamps a value outside 0-1", () => {
    render(<ConfidenceMeter confidence="1.4" />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "100");
  });

  it("treats an unparseable confidence as zero rather than NaN", () => {
    render(<ConfidenceMeter confidence="unknown" />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "0");
  });
});
