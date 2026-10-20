"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { Criterion, Role } from "@/lib/types";

interface CriteriaChecklistProps {
  criteria: Criterion[];
  /** Which side the viewer is on, so we show their own confirmation state. */
  viewerRole: Role;
  canConfirm: boolean;
  onConfirm?: () => void;
  isConfirming?: boolean;
  error?: string;
}

/**
 * The AI-drafted acceptance checklist, confirmable by each party.
 *
 * Confirmation is per party and covers the whole list — the backend records
 * a single confirmation per side, so offering per-row checkboxes would
 * imply a granularity the API does not have.
 */
export function CriteriaChecklist({
  criteria,
  viewerRole,
  canConfirm,
  onConfirm,
  isConfirming,
  error,
}: CriteriaChecklistProps) {
  const t = useTranslations();

  if (criteria.length === 0) {
    return <p className="text-sm text-ink-muted">{t("criteria.empty")}</p>;
  }

  const viewerConfirmed =
    viewerRole === "buyer"
      ? criteria.every((criterion) => criterion.confirmed_by_buyer)
      : criteria.every((criterion) => criterion.confirmed_by_seller);

  const bothConfirmed = criteria.every(
    (criterion) => criterion.confirmed_by_buyer && criterion.confirmed_by_seller,
  );

  return (
    <div className="space-y-4">
      <ul className="space-y-2.5">
        {criteria.map((criterion, index) => (
          <li key={criterion.id} className="flex gap-3">
            <span
              aria-hidden
              className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-surface-muted text-xs font-semibold text-ink-muted tabular"
            >
              {index + 1}
            </span>
            <span className="text-sm leading-relaxed text-ink">{criterion.text}</span>
          </li>
        ))}
      </ul>

      <dl className="flex flex-wrap gap-x-6 gap-y-1 border-t border-border-subtle pt-3 text-xs">
        <div className="flex gap-1.5">
          <dt className="text-ink-faint">{t("deal.buyer")}:</dt>
          <dd className="font-medium text-ink-muted">
            {criteria.every((criterion) => criterion.confirmed_by_buyer)
              ? `✓ ${t("criteria.buyerConfirmed")}`
              : t("criteria.notConfirmed")}
          </dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-ink-faint">{t("deal.seller")}:</dt>
          <dd className="font-medium text-ink-muted">
            {criteria.every((criterion) => criterion.confirmed_by_seller)
              ? `✓ ${t("criteria.sellerConfirmed")}`
              : t("criteria.notConfirmed")}
          </dd>
        </div>
      </dl>

      {bothConfirmed ? (
        <p className="rounded-lg border border-status-paid/20 bg-status-paid-soft px-3 py-2 text-sm text-status-paid">
          {t("criteria.bothConfirmed")}
        </p>
      ) : viewerConfirmed ? (
        <p className="text-sm text-ink-muted">{t("criteria.waitingForOther")}</p>
      ) : canConfirm && onConfirm ? (
        <div className="space-y-2">
          <Button onClick={onConfirm} disabled={isConfirming}>
            {isConfirming ? (
              <>
                <Spinner label={t("criteria.confirming")} />
                {t("criteria.confirming")}
              </>
            ) : (
              t("criteria.confirm")
            )}
          </Button>
          {error ? (
            <p role="alert" className="text-sm text-status-attention">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
