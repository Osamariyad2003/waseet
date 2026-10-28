"use client";

import { useTranslations } from "next-intl";

import { MoneyAmount } from "@/components/deals/money-amount";
import { Button } from "@/components/ui/button";
import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import { usePaypalActivity } from "@/hooks/use-deals";
import type { ActivityEntry, ActivityKind } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The deal's full PayPal money trail, each step read live from PayPal: the
 * order the buyer approved, the capture held in escrow, every release payout,
 * and any refund. This is the real money movement behind Waseet's own state —
 * read through the same PayPal APIs the AI Toolkit's MCP server wraps.
 */
export function PaypalActivity({ dealId }: { dealId: string }) {
  const t = useTranslations();
  const { data, isPending, isError, refetch, isRefetching } = usePaypalActivity(dealId);

  // Nothing has moved yet (DRAFT), or the lookup failed — stay quiet.
  if (isPending || isError || !data || data.length === 0) return null;

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <CardTitle>{t("activity.title")}</CardTitle>
          <CardSubtitle>{t("activity.subtitle")}</CardSubtitle>
        </div>
        <Button
          variant="secondary"
          onClick={() => void refetch()}
          disabled={isRefetching}
          className="h-9 shrink-0 px-3 text-sm"
        >
          {t("activity.refresh")}
        </Button>
      </div>

      <ol className="mt-5 space-y-3">
        {data.map((entry, index) => (
          <li key={`${entry.kind}-${entry.reference_id || index}`}>
            <ActivityRow entry={entry} />
          </li>
        ))}
      </ol>

      <p className="mt-4 text-xs text-ink-faint">{t("activity.footnote")}</p>
    </Card>
  );
}

function ActivityRow({ entry }: { entry: ActivityEntry }) {
  const t = useTranslations();
  const failed = entry.error !== null;

  // A payout row is labelled by its milestone when it has one; the base kinds
  // use their own label.
  const kindLabel = t(`activity.kinds.${entry.kind}` as const);
  const heading =
    entry.kind === "payout" && entry.label !== "deal" ? `${kindLabel} · ${entry.label}` : kindLabel;

  return (
    <div className="rounded-card border border-border-subtle/70 bg-surface-muted/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
              KIND_TONE[entry.kind],
            )}
          >
            {KIND_GLYPH[entry.kind]}
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">{heading}</p>
            {entry.receiver ? (
              <p className="truncate text-xs text-ink-faint">{entry.receiver}</p>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          {entry.amount ? (
            <MoneyAmount amount={entry.amount} currency={entry.currency ?? "USD"} size="sm" />
          ) : null}
          {failed ? (
            <span className="rounded-full bg-status-returned-soft px-2.5 py-0.5 text-xs font-medium text-status-returned">
              {t("activity.unavailable")}
            </span>
          ) : (
            <StatusBadge status={entry.status} />
          )}
        </div>
      </div>

      {entry.reference_id ? (
        <p className="mt-2 truncate text-xs text-ink-faint">
          <span className="tabular">{entry.reference_id}</span>
        </p>
      ) : null}
      {failed ? <p className="mt-1 text-xs text-ink-muted">{entry.error}</p> : null}
    </div>
  );
}

const KIND_GLYPH: Record<ActivityKind, string> = {
  order: "①",
  capture: "▣",
  payout: "✓",
  refund: "↩",
};

const KIND_TONE: Record<ActivityKind, string> = {
  order: "bg-status-held-soft text-status-held",
  capture: "bg-status-held-soft text-status-held",
  payout: "bg-status-paid-soft text-status-paid",
  refund: "bg-status-returned-soft text-status-returned",
};

/** PayPal's own status strings mapped onto the product's status tones. */
function StatusBadge({ status }: { status: string }) {
  const upper = status.toUpperCase();
  const tone =
    upper === "COMPLETED" || upper === "SUCCESS"
      ? "bg-status-paid-soft text-status-paid"
      : upper === "DENIED" || upper === "CANCELED" || upper === "FAILED" || upper === "VOIDED"
        ? "bg-status-attention-soft text-status-attention"
        : "bg-status-held-soft text-status-held";
  return (
    <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", tone)}>
      {status || "—"}
    </span>
  );
}
