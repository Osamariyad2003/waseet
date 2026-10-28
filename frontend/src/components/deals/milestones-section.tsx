"use client";

import { useTranslations } from "next-intl";

import { DeliverableUploader } from "@/components/deals/deliverable-uploader";
import { MoneyAmount } from "@/components/deals/money-amount";
import { StatusBadge } from "@/components/deals/status-badge";
import { VerificationReport } from "@/components/deals/verification-report";
import { Button } from "@/components/ui/button";
import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useSubmitMilestoneDeliverable, useVerifyMilestone } from "@/hooks/use-deals";
import { ApiError } from "@/lib/api";
import { statusStyle } from "@/lib/status";
import type { DealWithTimeline, Milestone } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * A milestone deal's body: a progress bar over the capture, then one card per
 * milestone, each running its own deliver → verify → release flow. The deal is
 * funded once; this is where each slice is worked and paid.
 */
export function MilestonesSection({
  deal,
  isBuyer,
  isSeller,
}: {
  deal: DealWithTimeline;
  isBuyer: boolean;
  isSeller: boolean;
}) {
  const t = useTranslations();

  const total = Number(deal.amount) || 0;
  const releasedAmount = deal.milestones
    .filter((m) => m.state === "RELEASED")
    .reduce((sum, m) => sum + (Number(m.amount) || 0), 0);
  const pct = total > 0 ? Math.round((releasedAmount / total) * 100) : 0;

  return (
    <Card>
      <CardTitle>{t("milestoneDeal.title")}</CardTitle>
      <CardSubtitle>{t("milestoneDeal.subtitle")}</CardSubtitle>

      {/* Progress over the capture. */}
      <div className="mt-5 space-y-2">
        <div
          className="h-2.5 w-full overflow-hidden rounded-full bg-surface-muted"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full rounded-full bg-status-paid transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="flex items-baseline gap-1.5 text-sm text-ink-muted">
          <MoneyAmount amount={releasedAmount.toFixed(2)} currency={deal.currency} size="sm" />
          <span className="text-ink-faint">
            / <span className="tabular">{total.toFixed(2)}</span> {deal.currency}{" "}
            {t("milestoneDeal.releasedLabel")}
          </span>
        </p>
      </div>

      <ul className="mt-5 space-y-4">
        {deal.milestones.map((milestone) => (
          <li key={milestone.id}>
            <MilestoneCard
              deal={deal}
              milestone={milestone}
              isBuyer={isBuyer}
              isSeller={isSeller}
            />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function MilestoneCard({
  deal,
  milestone,
  isBuyer,
  isSeller,
}: {
  deal: DealWithTimeline;
  milestone: Milestone;
  isBuyer: boolean;
  isSeller: boolean;
}) {
  const t = useTranslations();
  const submit = useSubmitMilestoneDeliverable(deal.id, milestone.id);
  const verify = useVerifyMilestone(deal.id, milestone.id);

  const style = statusStyle(milestone.state);
  const latestDeliverable = milestone.deliverables[milestone.deliverables.length - 1];
  const report = milestone.verification_reports[milestone.verification_reports.length - 1];

  return (
    <div className={cn("overflow-hidden rounded-card border", style.surface)}>
      <div className="flex items-start justify-between gap-3 p-4 sm:p-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              aria-hidden
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
                style.badge,
              )}
            >
              {style.glyph}
            </span>
            <h3 className="truncate font-semibold text-ink">
              {milestone.position + 1}. {milestone.title}
            </h3>
          </div>
          {milestone.description ? (
            <p className="mt-1.5 text-sm text-ink-muted">{milestone.description}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <MoneyAmount amount={milestone.amount} currency={deal.currency} size="md" />
          <StatusBadge state={milestone.state} />
        </div>
      </div>

      <div className="border-t border-border-subtle/60 bg-surface p-4 sm:p-5">
        {/* Criteria for this milestone. */}
        {milestone.criteria.length > 0 ? (
          <ul className="space-y-1.5 text-sm">
            {milestone.criteria.map((criterion) => (
              <li key={criterion.id} className="flex gap-2 text-ink-muted">
                <span aria-hidden className="text-ink-faint">
                  •
                </span>
                <span>{criterion.text}</span>
              </li>
            ))}
          </ul>
        ) : null}

        {/* FUNDED: the seller delivers this milestone. */}
        {milestone.state === "FUNDED" ? (
          isSeller ? (
            <div className="mt-4">
              <p className="mb-3 text-sm font-medium text-ink">{t("milestoneDeal.deliver")}</p>
              <DeliverableUploader
                onSubmit={async (values) => {
                  await submit.mutateAsync(values);
                }}
                isSubmitting={submit.isPending}
                error={submit.error instanceof ApiError ? submit.error.message : undefined}
              />
            </div>
          ) : (
            <p className="mt-4 text-sm text-ink-faint">{t("milestoneDeal.waitingSeller")}</p>
          )
        ) : null}

        {/* The submitted work. */}
        {latestDeliverable ? (
          <div className="mt-4 space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              {t("deal.deliverableTitle")}
            </p>
            {latestDeliverable.type === "url" || latestDeliverable.type === "repo" ? (
              <a
                href={latestDeliverable.content_ref}
                target="_blank"
                rel="noopener noreferrer nofollow"
                className="block break-all text-sm font-medium text-accent underline"
              >
                {latestDeliverable.content_ref}
              </a>
            ) : (
              <p className="whitespace-pre-line break-words rounded-lg bg-surface-muted p-3 text-sm text-ink">
                {latestDeliverable.content_ref}
              </p>
            )}
          </div>
        ) : null}

        {/* DELIVERED: trigger verification of this milestone. */}
        {milestone.state === "DELIVERED" && (isBuyer || isSeller) ? (
          <div className="mt-4 space-y-2">
            <Button onClick={() => verify.mutate()} disabled={verify.isPending}>
              {verify.isPending ? (
                <>
                  <Spinner label={t("verification.running")} />
                  {t("verification.running")}
                </>
              ) : (
                t("milestoneDeal.verify")
              )}
            </Button>
            {verify.error instanceof ApiError ? (
              <p role="alert" className="text-sm text-status-attention">
                {verify.error.message}
              </p>
            ) : null}
          </div>
        ) : null}

        {/* The verification report, once there is one. */}
        {report ? (
          <div className="mt-4">
            <VerificationReport report={report} />
          </div>
        ) : null}

        {/* RELEASED / DISPUTED footnotes. */}
        {milestone.state === "RELEASED" ? (
          <p className="mt-3 rounded-lg border border-status-paid/20 bg-status-paid-soft px-3 py-2 text-sm text-status-paid">
            {t("verification.autoReleased")}
          </p>
        ) : milestone.state === "DISPUTED" ? (
          <p className="mt-3 rounded-lg border border-status-attention/20 bg-status-attention-soft px-3 py-2 text-sm text-status-attention">
            {t("milestoneDeal.disputed")}
          </p>
        ) : null}
      </div>
    </div>
  );
}
