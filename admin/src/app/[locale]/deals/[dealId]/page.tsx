"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";

import { CriteriaChecklist } from "@/components/deals/criteria-checklist";
import { DealTimeline } from "@/components/deals/deal-timeline";
import { DecisionPanel } from "@/components/deals/decision-panel";
import { MoneyAmount } from "@/components/deals/money-amount";
import { StatusBadge } from "@/components/deals/status-badge";
import { VerificationReport } from "@/components/deals/verification-report";
import { Button } from "@/components/ui/button";
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
 * The reviewer's read-only view of a deal, plus the decision panel when it
 * is disputed. No buyer/seller actions live here — this is the admin
 * platform.
 */
export default function AdminDealPage() {
  const t = useTranslations();
  const locale = useLocale();
  const params = useParams<{ dealId: string }>();
  const dealId = params.dealId;
  const { user, isLoading } = useRequireSession(locale);

  const { data: deal, isPending, isError, error, refetch } = useDeal(dealId);

  if (isLoading || !user || isPending) {
    return <div className="mx-auto h-96 max-w-3xl animate-pulse rounded-card bg-surface" />;
  }

  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Card className="mx-auto max-w-3xl space-y-3">
        <CardTitle>{t("common.errorTitle")}</CardTitle>
        <CardSubtitle>{notFound ? t("deal.notFound") : t("deal.loadFailed")}</CardSubtitle>
        <Link
          href={`/${locale}/dashboard`}
          className="inline-flex h-11 items-center text-sm text-ink-muted hover:text-ink"
        >
          {t("common.back")}
        </Link>
      </Card>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href={`/${locale}/dashboard`} className="text-sm text-ink-muted hover:text-ink">
        ← {t("common.back")}
      </Link>

      <OutcomeConfirmation deal={deal} />
      <DealHero deal={deal} />

      <Card>
        <CardTitle>{t("criteria.title")}</CardTitle>
        <div className="mt-4">
          <CriteriaChecklist criteria={deal.criteria} viewerRole="reviewer" canConfirm={false} />
        </div>
      </Card>

      {deal.deliverables.length > 0 ? <DeliverableCard deal={deal} /> : null}

      {deal.verification_reports.length > 0 ? (
        <Card>
          <CardTitle>{t("verification.title")}</CardTitle>
          <div className="mt-5">
            <VerificationReport
              report={deal.verification_reports[deal.verification_reports.length - 1]!}
            />
          </div>
        </Card>
      ) : null}

      {deal.state === "DISPUTED" ? <DisputeCard deal={deal} onResolved={() => void refetch()} /> : null}

      {deal.milestones.length > 0 ? (
        <MilestonesReviewCard deal={deal} onResolved={() => void refetch()} />
      ) : null}

      <Card>
        <CardTitle>{t("timeline.title")}</CardTitle>
        <div className="mt-5">
          <DealTimeline entries={deal.timeline} />
        </div>
      </Card>
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
    <Card className={cn("border", style.surface)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-ink">{deal.title}</h1>
          <p className="mt-1 max-w-prose text-sm leading-relaxed text-ink-muted">
            {deal.description}
          </p>
        </div>
        <StatusBadge state={deal.state} size="lg" withMeaning />
      </div>

      <div className="mt-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={deal.state}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <MoneyAmount amount={deal.amount} currency={deal.currency} size="hero" label={label} />
          </motion.div>
        </AnimatePresence>
      </div>

      <dl className="mt-5 divide-y divide-border-subtle border-t border-border-subtle text-sm">
        <div className="flex items-baseline justify-between gap-4 py-2.5">
          <dt className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            {t("deal.buyer")}
          </dt>
          <dd className="truncate text-end text-ink">
            {deal.buyer.full_name || deal.buyer.email}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-4 py-2.5">
          <dt className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            {t("deal.seller")}
          </dt>
          <dd className="truncate text-end text-ink">
            {deal.seller.full_name || deal.seller.email}
          </dd>
        </div>
      </dl>
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
      className="overflow-hidden rounded-card shadow-sheet"
    >
      <div className="bg-accent px-6 py-8 text-center text-white">
        <span
          aria-hidden
          className={cn(
            "mx-auto flex size-16 items-center justify-center rounded-full bg-white text-2xl font-bold",
            style.text,
          )}
        >
          {style.glyph}
        </span>
        <h2 className="mt-4 text-lg font-semibold">{t(`confirmation.${deal.state}.title`)}</h2>
        <p className="mt-1 text-sm text-white/85">{t(`confirmation.${deal.state}.detail`)}</p>
      </div>
      {reference ? (
        <div className="flex items-center justify-between gap-4 bg-surface px-6 py-3 text-sm">
          <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            {t("timeline.paypalReference")}
          </span>
          <span className="tabular truncate font-medium text-ink-muted">{reference}</span>
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
      <CardTitle>{t("deal.deliverableTitle")}</CardTitle>
      <div className="mt-3 space-y-2">
        <p className="text-xs text-ink-faint">{t(`deliverable.types.${latest.type}`)}</p>
        {isLink ? (
          <a
            href={latest.content_ref}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="block break-all text-sm font-medium text-accent underline"
          >
            {latest.content_ref}
          </a>
        ) : (
          <p className="whitespace-pre-line break-words rounded-lg bg-surface-muted p-3 text-sm text-ink">
            {latest.content_ref}
          </p>
        )}
        {latest.note ? <p className="text-sm text-ink-muted">{latest.note}</p> : null}
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
      <CardTitle>{t("milestones.title")}</CardTitle>
      <CardSubtitle>{t("milestones.subtitle")}</CardSubtitle>
      <ul className="mt-5 space-y-4">
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
  const t = useTranslations();
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

      {/* Only a disputed milestone needs a decision. */}
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
    <Card>
      <CardTitle>{t("dispute.reviewerTitle")}</CardTitle>
      <div className="mt-5">
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
