"use client";

import { MoneyAmount } from "@/components/deals/money-amount";
import type { StatTile as StatTileData } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Enhanced KPI tile for the reviewer dashboard:
 * Professional fintech card with high-contrast tone iconography,
 * attention badge for pending disputes, and currency amount breakdown.
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
  const toneConfig = {
    accent: {
      cardBorder: "hover:border-accent/50",
      topStripe: "bg-accent",
      badge: "bg-accent-soft text-accent border border-accent/20",
    },
    attention: {
      cardBorder: "hover:border-status-attention/50",
      topStripe: "bg-status-attention",
      badge: "bg-status-attention-soft text-status-attention border border-status-attention/20",
    },
    paid: {
      cardBorder: "hover:border-status-paid/50",
      topStripe: "bg-status-paid",
      badge: "bg-status-paid-soft text-status-paid border border-status-paid/20",
    },
    returned: {
      cardBorder: "hover:border-status-returned/50",
      topStripe: "bg-status-returned",
      badge: "bg-status-returned-soft text-status-returned border border-status-returned/20",
    },
  }[tone];

  const renderIcon = () => {
    switch (tone) {
      case "accent":
        return (
          <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        );
      case "attention":
        return (
          <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        );
      case "paid":
        return (
          <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
      case "returned":
        return (
          <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
          </svg>
        );
      default:
        return <span>{glyph}</span>;
    }
  };

  const isAttentionAlert = tone === "attention" && tile.count > 0;

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-card border border-border-subtle/70 bg-surface p-5 shadow-sheet transition-all hover:shadow-md",
        toneConfig.cardBorder,
        isAttentionAlert && "ring-1 ring-status-attention/30 bg-status-attention-soft/10",
      )}
    >
      {/* Top accent accentuator */}
      <div className={cn("absolute top-0 inset-x-0 h-1", toneConfig.topStripe)} />

      <div className="flex items-center justify-between gap-3">
        <span
          aria-hidden
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-xl shadow-2xs",
            toneConfig.badge,
          )}
        >
          {renderIcon()}
        </span>

        {isAttentionAlert ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-status-attention px-2 py-0.5 text-[10px] font-semibold text-white animate-pulse">
            Action needed
          </span>
        ) : null}
      </div>

      <div className="mt-4">
        <span className="text-xs font-semibold uppercase tracking-wider text-ink-muted">
          {label}
        </span>
        <div className="mt-1 flex items-baseline justify-between gap-2">
          <span className="tabular text-3xl font-bold tracking-tight text-ink">
            {tile.count}
          </span>
          {Number(tile.amount) > 0 ? (
            <MoneyAmount
              amount={tile.amount}
              currency={tile.currency}
              size="sm"
              className="font-medium text-ink-muted"
            />
          ) : (
            <span className="text-xs text-ink-faint">0.00 {tile.currency}</span>
          )}
        </div>
      </div>
    </div>
  );
}
