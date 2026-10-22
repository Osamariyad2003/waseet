"use client";

import { useLocale } from "next-intl";

import { cn } from "@/lib/utils";

interface MoneyAmountProps {
  /** A decimal string from the API, e.g. "250.00". Never a number. */
  amount: string;
  currency: string;
  size?: "sm" | "md" | "lg" | "hero";
  className?: string;
  label?: string;
}

const SIZES = {
  sm: "text-sm",
  md: "text-base",
  lg: "text-2xl",
  // Large, legible money numbers — the thing both sides look for first.
  hero: "text-4xl sm:text-5xl",
} as const;

/**
 * Currency-aware money.
 *
 * The amount stays a string end to end: parsing "250.00" into a float to
 * render it would introduce the one class of error this product cannot
 * afford. `Intl.NumberFormat` is used for grouping and the currency symbol
 * only, and if it cannot parse the value we show the raw string rather than
 * NaN.
 *
 * Arabic renders with Western digits deliberately: the demo audience reads
 * PayPal sandbox balances in Western digits, and mixing the two makes the
 * amounts hard to compare at a glance.
 */
export function MoneyAmount({
  amount,
  currency,
  size = "md",
  className,
  label,
}: MoneyAmountProps) {
  const locale = useLocale();
  const numeric = Number(amount);

  const formatted = Number.isFinite(numeric)
    ? new Intl.NumberFormat(locale === "ar" ? "ar-EG-u-nu-latn" : locale, {
        style: "currency",
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numeric)
    : `${amount} ${currency}`;

  return (
    <span className={cn("inline-flex flex-col", className)}>
      {label ? (
        <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          {label}
        </span>
      ) : null}
      <span
        className={cn("tabular font-semibold text-ink", SIZES[size])}
        // The accessible name is the plain value, so a screen reader reads
        // "250.00 USD" rather than a formatted glyph soup.
        aria-label={`${amount} ${currency}`}
      >
        {formatted}
      </span>
    </span>
  );
}
