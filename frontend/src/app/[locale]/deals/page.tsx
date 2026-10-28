"use client";

import Link from "next/link";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { MoneyAmount } from "@/components/deals/money-amount";
import { StatusBadge } from "@/components/deals/status-badge";
import { GettingStarted } from "@/components/onboarding/getting-started";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { useDeals } from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";
import { statusStyle } from "@/lib/status";
import { DEAL_STATES, type DealState } from "@/lib/types";
import { cn } from "@/lib/utils";

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

  return (
    <div className="mx-auto w-full max-w-4xl space-y-5">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-ink">{t("deals.title")}</h1>

        <div className="ms-auto flex items-center gap-2">
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
        stateFilter ? (
          <Card>
            <p className="text-sm font-medium text-ink">{t("deals.emptyFiltered")}</p>
          </Card>
        ) : (
          // First-run onboarding: the whole lifecycle, role-aware, dismissible.
          <GettingStarted role={user.role} />
        )
      ) : (
        // A sheet of rows, after the design file's "Latest payments" list: a
        // status glyph in a soft circle on the lead, title + time, then the
        // amount and state trailing.
        <ul className="divide-y divide-border-subtle/70 overflow-hidden rounded-card border border-border-subtle/60 bg-surface shadow-sheet">
          {data.map((deal) => {
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
      )}
    </div>
  );
}

function ListSkeleton() {
  return (
    <ul
      className="divide-y divide-border-subtle/70 overflow-hidden rounded-card border border-border-subtle/60 bg-surface shadow-sheet"
      aria-busy="true"
    >
      {[0, 1, 2].map((index) => (
        <li key={index} className="flex items-center gap-4 p-4 sm:p-5">
          <span className="size-10 shrink-0 animate-pulse rounded-full bg-surface-muted" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-40 animate-pulse rounded bg-surface-muted" />
            <div className="h-3 w-24 animate-pulse rounded bg-surface-muted" />
          </div>
          <div className="h-5 w-16 animate-pulse rounded bg-surface-muted" />
        </li>
      ))}
    </ul>
  );
}
