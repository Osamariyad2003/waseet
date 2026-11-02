"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { CriteriaChecklist } from "@/components/deals/criteria-checklist";
import { DealTimeline } from "@/components/deals/deal-timeline";
import { DecisionPanel } from "@/components/deals/decision-panel";
import { MoneyAmount } from "@/components/deals/money-amount";
import { StatusBadge } from "@/components/deals/status-badge";
import { VerificationReport } from "@/components/deals/verification-report";
import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import {
  useDeal,
  useRecommendation,
  useResolveDispute,
  useResolveMilestoneDispute,
} from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";
import { ApiError } from "@/lib/api";
import { statusStyle } from "@/lib/status";
import { TERMINAL_STATES, type DealWithTimeline, type Milestone } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Reviewer Operations & Dispute Resolution Workspace:
 * Professional two-column command center with live AI recommendation,
 * PayPal sandbox references, criteria verification, and decision controls.
 */
export default function AdminDealPage() {
  const t = useTranslations();
  const locale = useLocale();
  const params = useParams<{ dealId: string }>();
  const dealId = params.dealId;
  const { user, isLoading } = useRequireSession(locale);

  const { data: deal, isPending, isError, error, refetch } = useDeal(dealId);

  if (isLoading || !user || isPending) {
    return <div className="mx-auto h-96 max-w-7xl animate-pulse rounded-card bg-surface" />;
  }

  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Card className="mx-auto max-w-3xl space-y-3">
        <CardTitle>{t("common.errorTitle")}</CardTitle>
        <CardSubtitle>{notFound ? t("deal.notFound") : t("deal.loadFailed")}</CardSubtitle>
        <Link
          href={`/${locale}/dashboard`}
          className="inline-flex h-11 items-center text-sm font-semibold text-accent hover:underline"
        >
          ← {t("common.back")}
        </Link>
      </Card>
    );
  }

  const isDisputed = deal.state === "DISPUTED";

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Navigation Breadcrumb */}
      <div className="flex items-center justify-between">
        <Link
          href={`/${locale}/dashboard`}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-muted hover:text-accent transition-colors"
        >
          <span>← Back to Operations Dashboard</span>
        </Link>
        <span className="font-mono text-xs text-ink-faint">Deal ID: {deal.id}</span>
      </div>

      {/* Outcome Confirmation (if terminal) */}
      <OutcomeConfirmation deal={deal} />

      {/* 2-Column Split Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Deal Details, Deliverable, Verification (8 cols) */}
        <div className="space-y-6 lg:col-span-7 xl:col-span-8">
          <DealHero deal={deal} />

          {/* Acceptance Checklist */}
          <Card>
            <div className="flex items-center justify-between pb-3 border-b border-border-subtle/50">
              <CardTitle>{t("criteria.title")}</CardTitle>
              <span className="text-xs text-ink-faint font-medium">
                {deal.criteria.length} condition{deal.criteria.length > 1 ? "s" : ""}
              </span>
            </div>
            <div className="mt-4">
              <CriteriaChecklist criteria={deal.criteria} viewerRole="reviewer" canConfirm={false} />
            </div>
          </Card>

          {/* Deliverable Submission */}
          {deal.deliverables.length > 0 ? <DeliverableCard deal={deal} /> : null}

          {/* AI Verification Report */}
          {deal.verification_reports.length > 0 ? (
            <Card>
              <div className="flex items-center justify-between pb-3 border-b border-border-subtle/50">
                <CardTitle>{t("verification.title")}</CardTitle>
                <span className="text-xs font-medium text-accent bg-accent-soft px-2 py-0.5 rounded-full">
                  AI Evaluated
                </span>
              </div>
              <div className="mt-4">
                <VerificationReport
                  report={deal.verification_reports[deal.verification_reports.length - 1]!}
                />
              </div>
            </Card>
          ) : null}

          {/* Milestones Review */}
          {deal.milestones.length > 0 ? (
            <MilestonesReviewCard deal={deal} onResolved={() => void refetch()} />
          ) : null}
        </div>

        {/* Right Column: Sticky Dispute Action Panel & PayPal Ledger (5 cols) */}
        <div className="space-y-6 lg:col-span-5 xl:col-span-4">
          {/* Dispute Decision Panel (Prominent when disputed) */}
          {isDisputed ? (
            <DisputeCard deal={deal} onResolved={() => void refetch()} />
          ) : null}

          {/* PayPal Sandbox Ledger References Card */}
          <PayPalLedgerCard deal={deal} />

          {/* Immutable Audit Trail & History */}
          <Card>
            <div className="flex items-center justify-between pb-3 border-b border-border-subtle/50">
              <CardTitle>{t("timeline.title")}</CardTitle>
              <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/50">
                Append-only
              </span>
            </div>
            <div className="mt-4">
              <DealTimeline entries={deal.timeline} />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function DealHero({ deal }: { deal: DealWithTimeline }) {
  const t = useTranslations();
  const style = statusStyle(deal.state);
  const label =
    deal.state === "RELEASED"
      ? t("deal.amountReleased")
      : deal.state === "REFUNDED"
        ? t("deal.amountRefunded")
        : deal.state === "DRAFT" || deal.state === "SPLIT"
          ? t("deal.amount")
          : t("deal.amountHeld");

  return (
    <Card className={cn("border border-border-subtle/80 bg-surface shadow-sheet", style.surface)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-bold tracking-tight text-ink">{deal.title}</h1>
          <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-ink-muted">
            {deal.description}
          </p>
        </div>
        <StatusBadge state={deal.state} size="lg" withMeaning />
      </div>

      <div className="mt-5 pt-4 border-t border-border-subtle/60 flex items-baseline justify-between">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-muted block">
            {label}
          </span>
          <div className="mt-1">
            <AnimatePresence mode="wait">
              <motion.div
                key={deal.state}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25 }}
              >
                <MoneyAmount amount={deal.amount} currency={deal.currency} size="hero" />
              </motion.div>
            </AnimatePresence>
          </div>
        </div>

        <div className="text-end">
          <span className="text-[11px] font-medium text-ink-faint block uppercase">Currency</span>
          <span className="font-semibold text-sm text-ink">{deal.currency}</span>
        </div>
      </div>

      {/* Counterparties Summary Cards */}
      <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3 pt-4 border-t border-border-subtle/60 text-xs">
        {/* Buyer Card */}
        <div className="p-3 rounded-xl bg-surface-muted/60 border border-border-subtle/50">
          <div className="flex items-center gap-1.5 font-bold text-ink mb-1">
            <span className="size-2 rounded-full bg-blue-500" />
            <span>Buyer</span>
          </div>
          <div className="font-semibold text-ink truncate">
            {deal.buyer.full_name || "Unnamed Buyer"}
          </div>
          <div className="text-ink-muted truncate font-mono text-[11px]">
            {deal.buyer.email}
          </div>
        </div>

        {/* Seller Card */}
        <div className="p-3 rounded-xl bg-surface-muted/60 border border-border-subtle/50">
          <div className="flex items-center gap-1.5 font-bold text-ink mb-1">
            <span className="size-2 rounded-full bg-emerald-500" />
            <span>Seller</span>
          </div>
          <div className="font-semibold text-ink truncate">
            {deal.seller.full_name || "Unnamed Seller"}
          </div>
          <div className="text-ink-muted truncate font-mono text-[11px]">
            {deal.seller.email}
          </div>
        </div>
      </div>
    </Card>
  );
}

function OutcomeConfirmation({ deal }: { deal: DealWithTimeline }) {
  const t = useTranslations();
  if (!TERMINAL_STATES.includes(deal.state)) return null;
  const style = statusStyle(deal.state);
  const reference = deal.payout_batch_id || deal.refund_id;

  return (
    <section
      aria-label={t(`confirmation.${deal.state}.title`)}
      className="overflow-hidden rounded-card shadow-sheet border border-border-subtle/60"
    >
      <div className="bg-[#16203a] px-6 py-6 text-center text-white">
        <span
          aria-hidden
          className={cn(
            "mx-auto flex size-14 items-center justify-center rounded-full bg-white text-xl font-bold shadow-sm",
            style.text,
          )}
        >
          {style.glyph}
        </span>
        <h2 className="mt-3 text-lg font-bold">{t(`confirmation.${deal.state}.title`)}</h2>
        <p className="mt-1 text-xs text-white/80">{t(`confirmation.${deal.state}.detail`)}</p>
      </div>
      {reference ? (
        <div className="flex items-center justify-between gap-4 bg-surface px-6 py-3 text-xs border-t border-border-subtle/50">
          <span className="font-semibold uppercase tracking-wide text-ink-muted">
            {t("timeline.paypalReference")}
          </span>
          <span className="tabular truncate font-mono font-medium text-accent">{reference}</span>
        </div>
      ) : null}
    </section>
  );
}

function DeliverableCard({ deal }: { deal: DealWithTimeline }) {
  const t = useTranslations();
  const latest = deal.deliverables[deal.deliverables.length - 1];
  if (!latest) return null;
  const isLink = latest.type === "url" || latest.type === "repo";

  return (
    <Card>
      <div className="flex items-center justify-between pb-3 border-b border-border-subtle/50">
        <CardTitle>{t("deal.deliverableTitle")}</CardTitle>
        <span className="rounded-full bg-surface-muted px-2.5 py-0.5 text-xs font-medium text-ink-muted">
          {t(`deliverable.types.${latest.type}`)}
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {isLink ? (
          <div className="p-3.5 rounded-lg bg-surface-muted/60 border border-border-subtle/60 flex items-center justify-between gap-3">
            <span className="font-mono text-xs text-ink truncate break-all">
              {latest.content_ref}
            </span>
            <a
              href={latest.content_ref}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white shadow-2xs hover:bg-accent-hover transition-colors"
            >
              <span>Inspect Link</span>
              <svg className="size-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
        ) : (
          <p className="whitespace-pre-line break-words rounded-lg bg-surface-muted p-3 text-sm text-ink font-mono">
            {latest.content_ref}
          </p>
        )}

        {latest.note ? (
          <div className="text-xs text-ink-muted">
            <strong className="text-ink font-semibold">Seller note:</strong> {latest.note}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function PayPalLedgerCard({ deal }: { deal: DealWithTimeline }) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const copy = (key: string, val: string) => {
    navigator.clipboard.writeText(val);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const rows = [
    { key: "order", label: "PayPal Order ID", val: deal.paypal_order_id },
    { key: "capture", label: "PayPal Capture ID", val: deal.paypal_capture_id },
    { key: "payout", label: "PayPal Payout Batch", val: deal.payout_batch_id },
    { key: "refund", label: "PayPal Refund ID", val: deal.refund_id },
  ].filter((r) => Boolean(r.val));

  return (
    <Card className="border border-border-subtle/80 bg-surface shadow-sheet">
      <div className="flex items-center justify-between pb-3 border-b border-border-subtle/50">
        <CardTitle className="text-sm font-bold flex items-center gap-2">
          <span>PayPal Ledger References</span>
        </CardTitle>
        <span className="rounded-full bg-blue-50 text-blue-700 text-[10px] px-2 py-0.5 font-semibold">
          Sandbox API
        </span>
      </div>

      <div className="mt-3 space-y-2.5">
        {rows.length === 0 ? (
          <p className="text-xs text-ink-faint">No PayPal transaction recorded yet.</p>
        ) : (
          rows.map((row) => (
            <div
              key={row.key}
              className="flex items-center justify-between gap-2 p-2 rounded-lg bg-surface-muted/50 border border-border-subtle/40 text-xs"
            >
              <div className="min-w-0">
                <span className="text-[10px] uppercase font-semibold text-ink-faint block">
                  {row.label}
                </span>
                <span className="font-mono text-ink truncate block text-[11px]">
                  {row.val}
                </span>
              </div>
              <button
                type="button"
                onClick={() => copy(row.key, row.val!)}
                className="shrink-0 px-2 py-1 rounded bg-surface hover:bg-surface-muted text-[10px] font-medium text-ink-muted border border-border-subtle/60 transition-colors"
              >
                {copiedKey === row.key ? "✓ Copied" : "Copy"}
              </button>
            </div>
          ))
        )}

        <div className="pt-2 border-t border-border-subtle/40 flex items-center justify-between text-xs text-ink-muted">
          <span>Platform Escrow Fee</span>
          <span className="font-semibold text-ink">0.00 USD (0%)</span>
        </div>
      </div>
    </Card>
  );
}

function MilestonesReviewCard({
  deal,
  onResolved,
}: {
  deal: DealWithTimeline;
  onResolved: () => void;
}) {
  const t = useTranslations();
  return (
    <Card>
      <div className="flex items-center justify-between pb-3 border-b border-border-subtle/50">
        <div>
          <CardTitle>{t("milestones.title")}</CardTitle>
          <CardSubtitle>{t("milestones.subtitle")}</CardSubtitle>
        </div>
        <span className="text-xs font-semibold text-accent bg-accent-soft px-2.5 py-0.5 rounded-full">
          {deal.milestones.length} Stages
        </span>
      </div>
      <ul className="mt-4 space-y-4">
        {deal.milestones.map((milestone) => (
          <li key={milestone.id}>
            <MilestoneRow deal={deal} milestone={milestone} onResolved={onResolved} />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function MilestoneRow({
  deal,
  milestone,
  onResolved,
}: {
  deal: DealWithTimeline;
  milestone: Milestone;
  onResolved: () => void;
}) {
  const resolve = useResolveMilestoneDispute(deal.id, milestone.id);
  const report = milestone.verification_reports[milestone.verification_reports.length - 1];
  const style = statusStyle(milestone.state);

  return (
    <div className={cn("overflow-hidden rounded-card border", style.surface)}>
      <div className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-ink">
            {milestone.position + 1}. {milestone.title}
          </h3>
          {milestone.description ? (
            <p className="mt-1 text-sm text-ink-muted">{milestone.description}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <MoneyAmount amount={milestone.amount} currency={deal.currency} size="md" />
          <StatusBadge state={milestone.state} />
        </div>
      </div>

      {milestone.state === "DISPUTED" ? (
        <div className="border-t border-border-subtle/60 bg-surface p-4">
          {report ? (
            <div className="mb-4">
              <VerificationReport report={report} />
            </div>
          ) : null}
          <DecisionPanel
            dealAmount={milestone.amount}
            currency={deal.currency}
            onSubmit={async (values) => {
              await resolve.mutateAsync(values);
              onResolved();
            }}
            isSubmitting={resolve.isPending}
            error={resolve.error instanceof ApiError ? resolve.error.message : undefined}
          />
        </div>
      ) : null}
    </div>
  );
}

function DisputeCard({ deal, onResolved }: { deal: DealWithTimeline; onResolved: () => void }) {
  const t = useTranslations();
  const resolve = useResolveDispute(deal.id);
  const recommendation = useRecommendation(deal.id, true);

  return (
    <Card className="border-2 border-status-attention/60 bg-surface shadow-md">
      <div className="flex items-center justify-between pb-3 border-b border-border-subtle/50">
        <CardTitle className="text-status-attention flex items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-full bg-status-attention text-white text-xs font-bold">
            !
          </span>
          <span>{t("dispute.reviewerTitle")}</span>
        </CardTitle>
        <span className="text-[10px] font-bold uppercase tracking-wider bg-status-attention-soft text-status-attention px-2 py-0.5 rounded-full">
          Final Decision
        </span>
      </div>

      <div className="mt-4">
        <DecisionPanel
          dealAmount={deal.amount}
          currency={deal.currency}
          recommendation={recommendation.data}
          isLoadingRecommendation={recommendation.isPending}
          recommendationError={
            recommendation.isError ? t("dispute.recommendationFailed") : undefined
          }
          onSubmit={async (values) => {
            await resolve.mutateAsync(values);
            onResolved();
          }}
          isSubmitting={resolve.isPending}
          error={resolve.error instanceof ApiError ? resolve.error.message : undefined}
        />
      </div>
    </Card>
  );
}
