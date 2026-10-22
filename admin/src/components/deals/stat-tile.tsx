"use client";

import { MoneyAmount } from "@/components/deals/money-amount";
import type { StatTile as StatTileData } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * A KPI tile for the reviewer dashboard, after the Behance escrow dashboard's
 * stat row: a soft-tinted icon square, a large count, the label, and the
 * money underneath. Rendered in Waseet's navy identity, not the reference's
 * teal.
 */
export function StatTile({
  tile,
  label,
  glyph,
  tone,
}: {
  tile: StatTileData;
  label: string;
  glyph: string;
  tone: "accent" | "attention" | "paid" | "returned";
}) {
  const toneClasses = {
    accent: "bg-accent-soft text-accent",
    attention: "bg-status-attention-soft text-status-attention",
    paid: "bg-status-paid-soft text-status-paid",
    returned: "bg-status-returned-soft text-status-returned",
  }[tone];

  return (
    <div className="rounded-card border border-border-subtle/60 bg-surface p-5 shadow-sheet">
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-xl text-lg font-bold",
            toneClasses,
          )}
        >
          {glyph}
        </span>
        <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          {label}
        </span>
      </div>

      <div className="mt-4 flex items-end justify-between gap-2">
        <span className="tabular text-3xl font-semibold text-ink">{tile.count}</span>
        {Number(tile.amount) > 0 ? (
          <MoneyAmount
            amount={tile.amount}
            currency={tile.currency}
            size="sm"
            className="pb-1 text-ink-muted"
          />
        ) : null}
      </div>
    </div>
  );
}
