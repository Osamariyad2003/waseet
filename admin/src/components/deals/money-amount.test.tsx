import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MoneyAmount } from "@/components/deals/money-amount";
import { render } from "@/test/render";

describe("MoneyAmount", () => {
  it("renders the amount with its currency", () => {
    render(<MoneyAmount amount="250.00" currency="USD" />);
    expect(screen.getByText("$250.00")).toBeInTheDocument();
  });

  it("always shows two decimal places", () => {
    render(<MoneyAmount amount="250.5" currency="USD" />);
    expect(screen.getByText("$250.50")).toBeInTheDocument();
  });

  it("groups thousands", () => {
    render(<MoneyAmount amount="1250.00" currency="USD" />);
    expect(screen.getByText("$1,250.00")).toBeInTheDocument();
  });

  it("exposes the plain value as the accessible name", () => {
    render(<MoneyAmount amount="250.00" currency="USD" />);
    // A screen reader should hear "250.00 USD", not a formatted glyph.
    expect(screen.getByLabelText("250.00 USD")).toBeInTheDocument();
  });

  it("does not lose precision on a value a float would round", () => {
    // 0.1 + 0.2 territory: the string must survive untouched.
    render(<MoneyAmount amount="1234.56" currency="USD" />);
    expect(screen.getByLabelText("1234.56 USD")).toBeInTheDocument();
    expect(screen.getByText("$1,234.56")).toBeInTheDocument();
  });

  it("falls back to the raw string rather than showing NaN", () => {
    render(<MoneyAmount amount="not-a-number" currency="USD" />);
    expect(screen.getByText("not-a-number USD")).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it("renders other currencies", () => {
    render(<MoneyAmount amount="99.99" currency="EUR" />);
    expect(screen.getByLabelText("99.99 EUR")).toBeInTheDocument();
  });

  it("uses Western digits in Arabic so amounts match the PayPal balances", () => {
    render(<MoneyAmount amount="250.00" currency="USD" />, { locale: "ar" });
    expect(screen.getByLabelText("250.00 USD")).toBeInTheDocument();
    expect(screen.getByText(/250\.00/)).toBeInTheDocument();
  });

  it("shows a label when given one", () => {
    render(<MoneyAmount amount="250.00" currency="USD" label="Held in escrow" />);
    expect(screen.getByText("Held in escrow")).toBeInTheDocument();
  });
});
