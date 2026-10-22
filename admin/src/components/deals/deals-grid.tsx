"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { MoneyAmount } from "@/components/deals/money-amount";
import { StatusBadge } from "@/components/deals/status-badge";
import type { DealSummaryWithParties } from "@/lib/types";
import { cn } from "@/lib/utils";

type SortKey = "title" | "amount" | "state" | "updated_at";
type SortDir = "asc" | "desc";

/**
 * The reviewer's deals grid, after the Behance dashboard's data table: a
 * dense, sortable table with a dark header band and status pills. Each row
 * links to the full deal. Rendered in Waseet's navy, not the reference teal.
 */
export function DealsGrid({
  deals,
  locale,
}: {
  deals: DealSummaryWithParties[];
  locale: string;
}) {
  const t = useTranslations();
  const format = useFormatter();
  const [sortKey, setSortKey] = useState<SortKey>("updated_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    const rows = [...deals];
    rows.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "amount") cmp = Number(a.amount) - Number(b.amount);
      else if (sortKey === "updated_at")
        cmp = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
      else cmp = String(a[sortKey]).localeCompare(String(b[sortKey]));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [deals, sortKey, sortDir]);

  const toggle = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(key === "title" ? "asc" : "desc");
    }
  };

  const header = (key: SortKey, label: string, align: "start" | "end" = "start") => (
    <th
      scope="col"
      aria-sort={sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      className={cn("px-4 py-3 font-medium", align === "end" ? "text-end" : "text-start")}
    >
      <button
        type="button"
        onClick={() => toggle(key)}
        className="inline-flex items-center gap-1 text-white/90 transition-colors hover:text-white"
      >
        {label}
        <span aria-hidden className="text-[10px] text-white/60">
          {sortKey === key ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );

  return (
    <div className="overflow-hidden rounded-card border border-border-subtle/60 bg-surface shadow-sheet">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-accent text-xs uppercase tracking-wide">
            <tr>
              {header("title", t("grid.deal"))}
              <th scope="col" className="px-4 py-3 text-start font-medium text-white/90">
                {t("grid.parties")}
              </th>
              {header("amount", t("grid.amount"), "end")}
              {header("state", t("grid.state"))}
              {header("updated_at", t("grid.updated"), "end")}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle/70">
            {sorted.map((deal) => (
              <tr key={deal.id} className="group transition-colors hover:bg-surface-muted">
                <td className="px-4 py-3">
                  <Link
                    href={`/${locale}/deals/${deal.id}`}
                    className="font-medium text-ink group-hover:text-accent"
                  >
                    {deal.title}
                  </Link>
                </td>
                <td className="px-4 py-3 text-ink-muted">
                  <span className="whitespace-nowrap">
                    {deal.buyer.full_name || deal.buyer.email}
                    <span className="mx-1.5 text-ink-faint">→</span>
                    {deal.seller.full_name || deal.seller.email}
                  </span>
                </td>
                <td className="px-4 py-3 text-end">
                  <MoneyAmount amount={deal.amount} currency={deal.currency} size="sm" />
                </td>
                <td className="px-4 py-3">
                  <StatusBadge state={deal.state} />
                </td>
                <td className="px-4 py-3 text-end text-xs text-ink-faint">
                  {format.dateTime(new Date(deal.updated_at), {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
