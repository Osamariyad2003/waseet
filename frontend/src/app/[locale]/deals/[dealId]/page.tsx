"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { CriteriaChecklist } from "@/components/deals/criteria-checklist";
import { DealTimeline } from "@/components/deals/deal-timeline";
import { DecisionPanel } from "@/components/deals/decision-panel";
import { DeliverableUploader } from "@/components/deals/deliverable-uploader";
import { MoneyAmount } from "@/components/deals/money-amount";
import { PayPalCheckoutButton } from "@/components/deals/paypal-checkout-button";
import { StatusBadge } from "@/components/deals/status-badge";
import {
  VerificationReport,
  VerificationRunning,
} from "@/components/deals/verification-report";
import { Button } from "@/components/ui/button";
import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import { Field, Textarea } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import {
  useConfirmCriteria,
  useContest,
  useDeal,
  useRecommendation,
  useResolveDispute,
  useSubmitDeliverable,
  useVerify,
} from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";
import { ApiError } from "@/lib/api";
import { statusStyle } from "@/lib/status";
import type { DealWithTimeline, Role } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function DealPage() {
  const t = useTranslations();
  const locale = useLocale();
  const params = useParams<{ dealId: string }>();
  const dealId = params.dealId;
  const { user, isLoading: isSessionLoading } = useRequireSession(locale);

  const { data: deal, isPending, isError, error, refetch } = useDeal(dealId);

  if (isSessionLoading || !user || isPending) {
    return <div className="h-96 animate-pulse rounded-card bg-surface" aria-busy="true" />;
  }

  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Card className="space-y-3">
        <CardTitle>{t("common.errorTitle")}</CardTitle>
        <CardSubtitle>{notFound ? t("deal.notFound") : t("deal.loadFailed")}</CardSubtitle>
        <div className="flex gap-2">
          {!notFound ? (
            <Button variant="secondary" onClick={() => void refetch()}>
              {t("common.retry")}
            </Button>
          ) : null}
          <Link
            href={`/${locale}/deals`}
            className="inline-flex h-11 items-center rounded-lg px-4 text-sm text-ink-muted hover:text-ink"
          >
            {t("common.back")}
          </Link>
        </div>
      </Card>
    );
  }

  const viewerRole: Role = user.role;
  const isBuyer = deal.buyer.id === user.id;
  const isSeller = deal.seller.id === user.id;
  const isReviewer = viewerRole === "reviewer";

  return (
    <div className="space-y-5">
      <Link href={`/${locale}/deals`} className="text-sm text-ink-muted hover:text-ink">
        ← {t("common.back")}
      </Link>

      <DealHero deal={deal} />

      <NextStep deal={deal} isBuyer={isBuyer} isSeller={isSeller} isReviewer={isReviewer} />

      {/* DRAFT: confirm the checklist, then fund. */}
      {deal.state === "DRAFT" ? (
        <>
          <Card>
            <CardTitle>{t("criteria.title")}</CardTitle>
            <CardSubtitle>{t("criteria.subtitle")}</CardSubtitle>
            <div className="mt-5">
              <ConfirmableCriteria deal={deal} isParty={isBuyer || isSeller} role={viewerRole} />
            </div>
          </Card>

          {isBuyer ? <FundingCard deal={deal} onFunded={() => void refetch()} /> : null}
        </>
      ) : (
        <Card>
          <CardTitle>{t("criteria.title")}</CardTitle>
          <div className="mt-4">
            <CriteriaChecklist
              criteria={deal.criteria}
              viewerRole={viewerRole}
              canConfirm={false}
            />
          </div>
        </Card>
      )}

      {/* FUNDED: the seller delivers. */}
      {deal.state === "FUNDED" && isSeller ? <DeliverCard deal={deal} /> : null}

      {/* DELIVERED: the deliverable, and the trigger to verify. */}
      {deal.deliverables.length > 0 ? <DeliverableCard deal={deal} /> : null}
      {deal.state === "DELIVERED" ? <VerifyCard deal={deal} canVerify={isBuyer || isSeller} /> : null}

      {/* VERIFYING: visible progress rather than a frozen screen. */}
      {deal.state === "VERIFYING" ? <VerificationRunning /> : null}

      {/* The report, once there is one. */}
      <ReportCard deal={deal} isBuyer={isBuyer} />

      {/* DISPUTED: the reviewer decides. */}
      {deal.state === "DISPUTED" ? (
        <DisputeCard deal={deal} isReviewer={isReviewer} />
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

/** The hero: large status, large money, nothing else competing. */
function DealHero({ deal }: { deal: DealWithTimeline }) {
  const t = useTranslations();
  const style = statusStyle(deal.state);

  const amountLabel =
    deal.state === "RELEASED"
      ? t("deal.amountReleased")
      : deal.state === "REFUNDED"
        ? t("deal.amountRefunded")
        : deal.state === "SPLIT"
          ? t("deal.amount")
          : deal.state === "DRAFT"
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
          {/* The release moment is the demo's payoff beat, so the number
              animates in once when the state becomes terminal. */}
          <motion.div
            key={deal.state}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <MoneyAmount
              amount={deal.amount}
              currency={deal.currency}
              size="hero"
              label={amountLabel}
            />
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Label/value rows, divider-separated, after the file's "Payment
          details" section: uppercase faint labels over the value. */}
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
        {deal.platform_fee && Number(deal.platform_fee) > 0 ? (
          <div className="flex items-baseline justify-between gap-4 py-2.5">
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              {t("deal.platformFee")}
            </dt>
            <dd className="tabular text-end text-ink">
              {deal.platform_fee} {deal.currency}
            </dd>
          </div>
        ) : null}
      </dl>
    </Card>
  );
}

/** One line telling the viewer what, if anything, is theirs to do. */
function NextStep({
  deal,
  isBuyer,
  isSeller,
  isReviewer,
}: {
  deal: DealWithTimeline;
  isBuyer: boolean;
  isSeller: boolean;
  isReviewer: boolean;
}) {
  const t = useTranslations();
  const bothConfirmed =
    deal.criteria.length > 0 &&
    deal.criteria.every((c) => c.confirmed_by_buyer && c.confirmed_by_seller);
  const viewerConfirmed = isBuyer
    ? deal.criteria.every((c) => c.confirmed_by_buyer)
    : deal.criteria.every((c) => c.confirmed_by_seller);

  let key: string;
  switch (deal.state) {
    case "DRAFT":
      key = bothConfirmed
        ? isBuyer
          ? "fund"
          : "waitingForFunding"
        : viewerConfirmed
          ? "waitingOtherParty"
          : "confirmCriteria";
      break;
    case "FUNDED":
      key = isSeller ? "deliver" : "waitingForDelivery";
      break;
    case "DELIVERED":
      key = "verifying";
      break;
    case "VERIFYING":
      key = "verifying";
      break;
    case "DISPUTED":
      key = isReviewer ? "reviewerAction" : "reviewerDeciding";
      break;
    default:
      key = "done";
  }

  return (
    <p className="rounded-lg bg-surface-muted px-4 py-3 text-sm text-ink">
      <span className="font-medium">{t("deal.nextStep")}: </span>
      {t(`deal.nextSteps.${key}`)}
    </p>
  );
}

function ConfirmableCriteria({
  deal,
  isParty,
  role,
}: {
  deal: DealWithTimeline;
  isParty: boolean;
  role: Role;
}) {
  const confirm = useConfirmCriteria(deal.id);
  return (
    <CriteriaChecklist
      criteria={deal.criteria}
      viewerRole={role}
      canConfirm={isParty}
      onConfirm={() => confirm.mutate()}
      isConfirming={confirm.isPending}
      error={confirm.error instanceof ApiError ? confirm.error.message : undefined}
    />
  );
}

function FundingCard({
  deal,
  onFunded,
}: {
  deal: DealWithTimeline;
  onFunded: () => void;
}) {
  const t = useTranslations();
  const bothConfirmed =
    deal.criteria.length > 0 &&
    deal.criteria.every((c) => c.confirmed_by_buyer && c.confirmed_by_seller);

  return (
    // The one place money is paid in, so it carries the file's navy payment
    // header to set it apart from the rest of the page.
    <div className="overflow-hidden rounded-card border border-border-subtle/60 bg-surface shadow-sheet">
      <div className="bg-accent px-5 py-4 text-white sm:px-6">
        <h2 className="text-base font-semibold">{t("funding.title")}</h2>
        <p className="mt-1 text-sm leading-relaxed text-white/80">{t("funding.subtitle")}</p>
      </div>
      <div className="p-5 sm:p-6">
        <PayPalCheckoutButton
          dealId={deal.id}
          onFunded={onFunded}
          disabled={!bothConfirmed}
          disabledReason={!bothConfirmed ? t("funding.notConfirmed") : undefined}
        />
      </div>
    </div>
  );
}

function DeliverCard({ deal }: { deal: DealWithTimeline }) {
  const t = useTranslations();
  const submit = useSubmitDeliverable(deal.id);

  return (
    <Card>
      <CardTitle>{t("deliverable.title")}</CardTitle>
      <CardSubtitle>{t("deliverable.subtitle")}</CardSubtitle>
      <div className="mt-5">
        <DeliverableUploader
          onSubmit={async (values) => {
            await submit.mutateAsync(values);
          }}
          isSubmitting={submit.isPending}
          error={submit.error instanceof ApiError ? submit.error.message : undefined}
        />
      </div>
    </Card>
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
          // Rendered as plain text, never as markup: the content is
          // untrusted and may be an injection attempt aimed at the verifier.
          <p className="whitespace-pre-line break-words rounded-lg bg-surface-muted p-3 text-sm text-ink">
            {latest.content_ref}
          </p>
        )}
        {latest.note ? (
          <p className="text-sm text-ink-muted">{latest.note}</p>
        ) : null}
      </div>
    </Card>
  );
}

function VerifyCard({ deal, canVerify }: { deal: DealWithTimeline; canVerify: boolean }) {
  const t = useTranslations();
  const verify = useVerify(deal.id);

  if (!canVerify) return null;

  return (
    <Card>
      <CardTitle>{t("verification.title")}</CardTitle>
      <CardSubtitle>{t("verification.runningDetail")}</CardSubtitle>
      <div className="mt-5 space-y-2">
        <Button onClick={() => verify.mutate()} disabled={verify.isPending} size="lg">
          {verify.isPending ? (
            <>
              <Spinner label={t("verification.running")} />
              {t("verification.running")}
            </>
          ) : (
            t("deliverable.submit")
          )}
        </Button>
        {verify.error instanceof ApiError ? (
          <p role="alert" className="text-sm text-status-attention">
            {verify.error.message}
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function ReportCard({ deal, isBuyer }: { deal: DealWithTimeline; isBuyer: boolean }) {
  const t = useTranslations();
  const report = deal.verification_reports[deal.verification_reports.length - 1];
  if (!report) return null;

  const canContest =
    isBuyer && (deal.state === "FUNDED" || deal.state === "DELIVERED");

  return (
    <Card>
      <CardTitle>{t("verification.title")}</CardTitle>

      {deal.state === "RELEASED" && report.decided_by === "ai" ? (
        <p className="mt-2 rounded-lg border border-status-paid/20 bg-status-paid-soft px-3 py-2 text-sm text-status-paid">
          {t("verification.autoReleased")}
        </p>
      ) : null}

      <div className="mt-5">
        <VerificationReport report={report} />
      </div>

      {canContest ? (
        <div className="mt-5 border-t border-border-subtle pt-5">
          <ContestForm dealId={deal.id} />
        </div>
      ) : null}
    </Card>
  );
}

function ContestForm({ dealId }: { dealId: string }) {
  const t = useTranslations();
  const contest = useContest(dealId);
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);

  const invalid = touched && reason.trim().length === 0;

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-ink">{t("verification.contestTitle")}</h3>
        <p className="mt-1 text-sm text-ink-muted">{t("verification.contestSubtitle")}</p>
      </div>

      <Field
        label={t("verification.contestReason")}
        error={invalid ? t("validation.reasonRequired") : undefined}
      >
        {(props) => (
          <Textarea
            {...props}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            onBlur={() => setTouched(true)}
            rows={3}
          />
        )}
      </Field>

      {contest.error instanceof ApiError ? (
        <p role="alert" className="text-sm text-status-attention">
          {contest.error.message}
        </p>
      ) : null}

      <Button
        variant="danger"
        disabled={contest.isPending || reason.trim().length === 0}
        onClick={() => contest.mutate(reason.trim())}
      >
        {contest.isPending ? (
          <>
            <Spinner label={t("verification.contestSubmitting")} />
            {t("verification.contestSubmitting")}
          </>
        ) : (
          t("verification.contestSubmit")
        )}
      </Button>
    </div>
  );
}

function DisputeCard({
  deal,
  isReviewer,
}: {
  deal: DealWithTimeline;
  isReviewer: boolean;
}) {
  const t = useTranslations();
  const resolve = useResolveDispute(deal.id);
  const recommendation = useRecommendation(deal.id, isReviewer);

  if (!isReviewer) {
    return (
      <Card className="border-status-attention/20 bg-status-attention-soft">
        <CardTitle>{t("dispute.title")}</CardTitle>
        <CardSubtitle>{t("dispute.waitingForReviewer")}</CardSubtitle>
      </Card>
    );
  }

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
          }}
          isSubmitting={resolve.isPending}
          error={resolve.error instanceof ApiError ? resolve.error.message : undefined}
        />
      </div>
    </Card>
  );
}
