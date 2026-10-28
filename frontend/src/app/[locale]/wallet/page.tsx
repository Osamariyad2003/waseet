"use client";

import Link from "next/link";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";

import { MoneyAmount } from "@/components/deals/money-amount";
import { StatusBadge } from "@/components/deals/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useDeals } from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";
import { statusStyle } from "@/lib/status";
import type { DealSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const HELD_STATES = new Set(["FUNDED", "DELIVERED", "VERIFYING", "DISPUTED"]);
const RELEASED_STATES = new Set(["RELEASED", "SPLIT"]);
const REFUNDED_STATES = new Set(["REFUNDED"]);
const PENDING_STATES = new Set(["DRAFT"]);

function sumAmounts(deals: DealSummary[]): string {
  const total = deals.reduce((acc, deal) => {
    const val = parseFloat(deal.amount);
    return acc + (isNaN(val) ? 0 : val);
  }, 0);
  return total.toFixed(2);
}

export default function WalletPage() {
  const t = useTranslations("wallet");
  const locale = useLocale();
  const format = useFormatter();
  const { user, isLoading: isSessionLoading } = useRequireSession(locale);

  const { data: deals = [], isPending, isError, error, refetch, isRefetching } = useDeals();

  const primaryCurrency = useMemo(() => {
    return deals[0]?.currency ?? "USD";
  }, [deals]);

  const stats = useMemo(() => {
    const held = deals.filter((d) => HELD_STATES.has(d.state));
    const released = deals.filter((d) => RELEASED_STATES.has(d.state));
    const refunded = deals.filter((d) => REFUNDED_STATES.has(d.state));
    const pending = deals.filter((d) => PENDING_STATES.has(d.state));

    return {
      held: { count: held.length, total: sumAmounts(held) },
      released: { count: released.length, total: sumAmounts(released) },
      refunded: { count: refunded.length, total: sumAmounts(refunded) },
      pending: { count: pending.length, total: sumAmounts(pending) },
    };
  }, [deals]);

  // Headline KPIs across all the user's deals.
  const kpis = useMemo(() => {
    const active = deals.filter((d) => HELD_STATES.has(d.state)).length;
    const completed = deals.filter(
      (d) => RELEASED_STATES.has(d.state) || REFUNDED_STATES.has(d.state),
    ).length;
    const volume = sumAmounts(deals);
    const releasedCount = deals.filter((d) => RELEASED_STATES.has(d.state)).length;
    const settled = deals.filter(
      (d) => RELEASED_STATES.has(d.state) || REFUNDED_STATES.has(d.state),
    ).length;
    const avg =
      deals.length > 0 ? (parseFloat(volume) / deals.length).toFixed(2) : "0.00";
    const successRate = settled > 0 ? Math.round((releasedCount / settled) * 100) : null;
    return { total: deals.length, active, completed, volume, avg, successRate };
  }, [deals]);

  if (isSessionLoading || !user) {
    return <WalletSkeleton />;
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-ink">
          {t("title")}
        </h1>
        <p className="text-base text-ink-muted leading-relaxed max-w-2xl">
          {t("subtitle")}
        </p>
      </div>

      {isPending ? (
        <WalletSkeleton />
      ) : isError ? (
        <Card className="space-y-3 p-6">
          <p className="text-sm font-medium text-ink">{t("loadFailed")}</p>
          <p className="text-sm text-ink-muted">{error.message}</p>
          <Button variant="secondary" onClick={() => void refetch()} disabled={isRefetching}>
            {t("retry")}
          </Button>
        </Card>
      ) : deals.length === 0 ? (
        <Card className="p-8 text-center space-y-4">
          <p className="text-base font-medium text-ink">{t("empty")}</p>
          <div>
            <Link
              href={`/${locale}/deals`}
              className="inline-flex h-9 items-center rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
            >
              {t("emptyCta")}
            </Link>
          </div>
        </Card>
      ) : (
        <>
          {/* Headline KPIs */}
          <section className="space-y-3">
            <h2 className="text-lg font-semibold text-ink">{t("kpiTitle")}</h2>
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-border-subtle/60 bg-border-subtle/60 shadow-sheet sm:grid-cols-3 lg:grid-cols-6">
              <KpiStat label={t("kpiTotal")} value={String(kpis.total)} />
              <KpiStat label={t("kpiActive")} value={String(kpis.active)} />
              <KpiStat label={t("kpiCompleted")} value={String(kpis.completed)} />
              <KpiStat
                label={t("kpiVolume")}
                money={{ amount: kpis.volume, currency: primaryCurrency }}
              />
              <KpiStat
                label={t("kpiAvg")}
                money={{ amount: kpis.avg, currency: primaryCurrency }}
              />
              <KpiStat
                label={t("kpiSuccess")}
                value={kpis.successRate === null ? "—" : `${kpis.successRate}%`}
              />
            </div>
          </section>

          {/* Summary Stat Tiles */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* 1. Held in Escrow */}
            <Card className="p-4 border-l-4 border-l-[#4060b2] space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
                {t("held")}
              </span>
              <div>
                <MoneyAmount
                  amount={stats.held.total}
                  currency={primaryCurrency}
                  size="lg"
                  className="font-bold text-ink"
                />
              </div>
              <p className="text-xs text-ink-faint">{t("heldHint")}</p>
              <p className="text-[11px] text-ink-muted pt-1">
                {stats.held.count} {stats.held.count === 1 ? "deal" : "deals"}
              </p>
            </Card>

            {/* 2. Released */}
            <Card className="p-4 border-l-4 border-l-[#1b8f63] space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-[#1b8f63]">
                {t("released")}
              </span>
              <div>
                <MoneyAmount
                  amount={stats.released.total}
                  currency={primaryCurrency}
                  size="lg"
                  className="font-bold text-[#1b8f63]"
                />
              </div>
              <p className="text-xs text-ink-faint">{t("releasedHint")}</p>
              <p className="text-[11px] text-ink-muted pt-1">
                {stats.released.count} {stats.released.count === 1 ? "deal" : "deals"}
              </p>
            </Card>

            {/* 3. Refunded */}
            <Card className="p-4 border-l-4 border-l-[#c77400] space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-[#c77400]">
                {t("refunded")}
              </span>
              <div>
                <MoneyAmount
                  amount={stats.refunded.total}
                  currency={primaryCurrency}
                  size="lg"
                  className="font-bold text-ink"
                />
              </div>
              <p className="text-xs text-ink-faint">{t("refundedHint")}</p>
              <p className="text-[11px] text-ink-muted pt-1">
                {stats.refunded.count} {stats.refunded.count === 1 ? "deal" : "deals"}
              </p>
            </Card>

            {/* 4. Pending */}
            <Card className="p-4 border-l-4 border-l-border-subtle space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
                {t("pending")}
              </span>
              <div>
                <MoneyAmount
                  amount={stats.pending.total}
                  currency={primaryCurrency}
                  size="lg"
                  className="font-bold text-ink"
                />
              </div>
              <p className="text-xs text-ink-faint">{t("pendingHint")}</p>
              <p className="text-[11px] text-ink-muted pt-1">
                {stats.pending.count} {stats.pending.count === 1 ? "deal" : "deals"}
              </p>
            </Card>
          </div>

          {/* Breakdown by Deals */}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-ink">{t("breakdown")}</h2>

            <ul className="divide-y divide-border-subtle/70 overflow-hidden rounded-card border border-border-subtle/60 bg-surface shadow-sheet">
              {deals.map((deal) => {
                const style = statusStyle(deal.state);
                return (
                  <li key={deal.id}>
                    <Link
                      href={`/${locale}/deals/${deal.id}`}
                      className="flex items-center gap-3 p-4 transition-colors hover:bg-surface-muted sm:gap-4 sm:p-5"
                    >
                      <span
                        aria-hidden
                        className={cn(
                          "flex size-10 shrink-0 items-center justify-center rounded-full text-base font-semibold",
                          style.badge,
                        )}
                      >
                        {style.glyph}
                      </span>

                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-ink">{deal.title}</p>
                        <p className="mt-0.5 text-xs text-ink-faint">
                          {format.dateTime(new Date(deal.updated_at), {
                            day: "numeric",
                            month: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </p>
                      </div>

                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <MoneyAmount amount={deal.amount} currency={deal.currency} />
                        <StatusBadge state={deal.state} />
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

function KpiStat({
  label,
  value,
  money,
}: {
  label: string;
  value?: string;
  money?: { amount: string; currency: string };
}) {
  return (
    <div className="bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</p>
      <div className="mt-1">
        {money ? (
          <MoneyAmount amount={money.amount} currency={money.currency} size="lg" />
        ) : (
          <span className="text-2xl font-bold tabular text-ink">{value}</span>
        )}
      </div>
    </div>
  );
}

function WalletSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-28 rounded-card bg-surface-muted animate-pulse p-4" />
        ))}
      </div>
      <div className="h-64 rounded-card bg-surface-muted animate-pulse" />
    </div>
  );
}
