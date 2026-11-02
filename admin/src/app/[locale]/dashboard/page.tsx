"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Suspense, useEffect, useState } from "react";

import { DealsGrid } from "@/components/deals/deals-grid";
import { StatTile } from "@/components/deals/stat-tile";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useReviewerOverview } from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialFilterParam = searchParams.get("filter") === "DISPUTED" ? "DISPUTED" : "all";

  const { user, isLoading } = useRequireSession(locale);
  const { data, isPending, isError, error, refetch, isRefetching } = useReviewerOverview();
  const [filterMode, setFilterMode] = useState<"all" | "DISPUTED">(initialFilterParam);

  // Sync if URL query changes
  useEffect(() => {
    if (searchParams.get("filter") === "DISPUTED") {
      setFilterMode("DISPUTED");
    }
  }, [searchParams]);

  // Reviewers only
  useEffect(() => {
    if (!isLoading && user && user.role !== "reviewer") {
      router.replace(`/${locale}/login`);
    }
  }, [isLoading, user, router, locale]);

  if (isLoading || !user || user.role !== "reviewer") {
    return <DashboardSkeleton />;
  }

  const hasOpenDisputes = Boolean(data && data.open_disputes.count > 0);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Top Banner / Operations Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between pb-2 border-b border-border-subtle/50">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink flex items-center gap-2.5">
            <span>Operations Dashboard</span>
            <span className="rounded-full bg-accent-soft text-accent text-xs px-2.5 py-0.5 font-semibold">
              Reviewer Console
            </span>
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Manage escrow guarantees, adjudicate contested deliverables, and execute final PayPal payouts or refunds.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isRefetching}
            className="inline-flex items-center gap-2 rounded-lg border border-border-subtle bg-surface px-3.5 py-2 text-xs font-semibold text-ink shadow-2xs hover:bg-surface-muted transition-colors disabled:opacity-60"
          >
            <svg
              className={`size-3.5 text-accent ${isRefetching ? "animate-spin" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span>{isRefetching ? "Refreshing..." : "Refresh Queue"}</span>
          </button>
        </div>
      </div>

      {isPending ? (
        <DashboardSkeleton bare />
      ) : isError ? (
        <Card className="space-y-3">
          <p className="text-sm font-medium text-ink">{t("dashboard.loadFailed")}</p>
          <p className="text-sm text-ink-muted">{error.message}</p>
          <Button variant="secondary" onClick={() => void refetch()}>
            {t("common.retry")}
          </Button>
        </Card>
      ) : (
        <>
          {/* Urgent Dispute Alert Callout */}
          {hasOpenDisputes ? (
            <div className="rounded-card border border-status-attention/40 bg-status-attention-soft/30 p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-start gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-status-attention text-white text-base font-bold shadow-xs">
                  !
                </span>
                <div>
                  <h3 className="text-sm font-bold text-status-attention">
                    {data.open_disputes.count} Dispute{data.open_disputes.count > 1 ? "s" : ""} Pending Review
                  </h3>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    Seller deliverables failed AI criteria or were contested by buyers. Human reviewer decision is required to release, refund, or split PayPal funds.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setFilterMode("DISPUTED")}
                className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg bg-status-attention px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-status-attention/90 transition-all"
              >
                <span>Jump to Disputes</span>
                <span aria-hidden>↓</span>
              </button>
            </div>
          ) : null}

          {/* 4 Core KPI Stat Tiles */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile
              tile={data.held_in_escrow}
              label={t("dashboard.heldInEscrow")}
              glyph="●"
              tone="accent"
            />
            <StatTile
              tile={data.open_disputes}
              label={t("dashboard.openDisputes")}
              glyph="!"
              tone="attention"
            />
            <StatTile
              tile={data.released}
              label={t("dashboard.released")}
              glyph="✓"
              tone="paid"
            />
            <StatTile
              tile={data.refunded}
              label={t("dashboard.refunded")}
              glyph="↩"
              tone="returned"
            />
          </div>

          {/* Deals Grid with Filter Controls */}
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-ink">Escrow Deals Ledger</h2>
            </div>

            {data.deals.length === 0 ? (
              <Card>
                <p className="text-sm text-ink-muted">{t("dashboard.noDeals")}</p>
              </Card>
            ) : (
              <DealsGrid deals={data.deals} locale={locale} initialFilter={filterMode} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

function DashboardSkeleton({ bare = false }: { bare?: boolean }) {
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {!bare ? <div className="h-8 w-48 animate-pulse rounded bg-surface" /> : null}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-card bg-surface" />
        ))}
      </div>
      <div className="h-96 animate-pulse rounded-card bg-surface" />
    </div>
  );
}
