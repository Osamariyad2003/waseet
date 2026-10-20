"use client";

import Link from "next/link";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { MoneyAmount } from "@/components/deals/money-amount";
import { StatusBadge } from "@/components/deals/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { useDeals } from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";
import { DEAL_STATES, type DealState } from "@/lib/types";

export default function DealsPage() {
  const t = useTranslations();
  const locale = useLocale();
  const format = useFormatter();
  const { user, isLoading: isSessionLoading } = useRequireSession(locale);
  const [stateFilter, setStateFilter] = useState<DealState | "">("");

  const { data, isPending, isError, error, refetch, isRefetching } = useDeals(
    stateFilter || undefined,
  );

  if (isSessionLoading || !user) {
    return <ListSkeleton />;
  }

  const isReviewer = user.role === "reviewer";

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-ink">
          {isReviewer ? t("deals.reviewerTitle") : t("deals.title")}
        </h1>

        <div className="ms-auto flex items-center gap-2">
          {/* A reviewer's queue is defined by state, so the filter would
              only let them empty their own list. */}
          {!isReviewer ? (
            <Select
              aria-label={t("deals.filterAll")}
              value={stateFilter}
              onChange={(event) => setStateFilter(event.target.value as DealState | "")}
              className="h-9 w-auto py-0 text-sm"
            >
              <option value="">{t("deals.filterAll")}</option>
              {DEAL_STATES.map((state) => (
                <option key={state} value={state}>
                  {t(`states.${state}`)}
                </option>
              ))}
            </Select>
          ) : null}

          {user.role === "buyer" ? (
            <Link
              href={`/${locale}/deals/new`}
              className="inline-flex h-9 items-center rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
            >
              {t("deals.newDeal")}
            </Link>
          ) : null}
        </div>
      </header>

      {isPending ? (
        <ListSkeleton />
      ) : isError ? (
        <Card className="space-y-3">
          <p className="text-sm font-medium text-ink">{t("deals.loadFailed")}</p>
          <p className="text-sm text-ink-muted">{error.message}</p>
          <Button variant="secondary" onClick={() => void refetch()} disabled={isRefetching}>
            {t("deals.retry")}
          </Button>
        </Card>
      ) : data.length === 0 ? (
        <Card>
          <p className="text-sm font-medium text-ink">
            {stateFilter ? t("deals.emptyFiltered") : t("deals.empty")}
          </p>
          {!stateFilter ? (
            <p className="mt-1 text-sm text-ink-muted">
              {isReviewer
                ? t("deals.emptyReviewer")
                : user.role === "buyer"
                  ? t("deals.emptyBuyer")
                  : t("deals.emptySeller")}
            </p>
          ) : null}
        </Card>
      ) : (
        <ul className="space-y-3">
          {data.map((deal) => (
            <li key={deal.id}>
              <Link
                href={`/${locale}/deals/${deal.id}`}
                className="block rounded-card border border-border-subtle bg-surface p-4 transition-colors hover:bg-surface-muted sm:p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
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
                  <div className="flex items-center gap-3">
                    <MoneyAmount amount={deal.amount} currency={deal.currency} />
                    <StatusBadge state={deal.state} />
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ListSkeleton() {
  return (
    <ul className="space-y-3" aria-busy="true">
      {[0, 1, 2].map((index) => (
        <li
          key={index}
          className="h-[86px] animate-pulse rounded-card border border-border-subtle bg-surface"
        />
      ))}
    </ul>
  );
}
