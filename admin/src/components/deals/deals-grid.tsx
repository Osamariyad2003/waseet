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
type FilterState = "all" | "DISPUTED" | "FUNDED" | "VERIFYING" | "RELEASED" | "REFUNDED" | "SPLIT";

export function DealsGrid({
  deals,
  locale,
  initialFilter = "all",
}: {
  deals: DealSummaryWithParties[];
  locale: string;
  initialFilter?: FilterState;
}) {
  const t = useTranslations();
  const format = useFormatter();
  const [sortKey, setSortKey] = useState<SortKey>("updated_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [filterState, setFilterState] = useState<FilterState>(initialFilter);
  const [searchQuery, setSearchQuery] = useState("");

  // Counts for each filter badge
  const counts = useMemo(() => {
    return {
      all: deals.length,
      disputed: deals.filter((d) => d.state === "DISPUTED").length,
      funded: deals.filter((d) => d.state === "FUNDED").length,
      verifying: deals.filter((d) => d.state === "VERIFYING" || d.state === "DELIVERED").length,
      completed: deals.filter((d) => ["RELEASED", "REFUNDED", "SPLIT"].includes(d.state)).length,
    };
  }, [deals]);

  // Filtering + Searching
  const filtered = useMemo(() => {
    return deals.filter((deal) => {
      // State filter
      if (filterState === "DISPUTED" && deal.state !== "DISPUTED") return false;
      if (filterState === "FUNDED" && deal.state !== "FUNDED") return false;
      if (
        filterState === "VERIFYING" &&
        deal.state !== "VERIFYING" &&
        deal.state !== "DELIVERED"
      )
        return false;
      if (
        filterState === "RELEASED" &&
        !["RELEASED", "REFUNDED", "SPLIT"].includes(deal.state)
      )
        return false;

      // Text query
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const title = deal.title.toLowerCase();
        const buyerName = (deal.buyer.full_name || "").toLowerCase();
        const buyerEmail = deal.buyer.email.toLowerCase();
        const sellerName = (deal.seller.full_name || "").toLowerCase();
        const sellerEmail = deal.seller.email.toLowerCase();
        const id = deal.id.toLowerCase();

        return (
          title.includes(query) ||
          buyerName.includes(query) ||
          buyerEmail.includes(query) ||
          sellerName.includes(query) ||
          sellerEmail.includes(query) ||
          id.includes(query)
        );
      }

      return true;
    });
  }, [deals, filterState, searchQuery]);

  // Sorting
  const sorted = useMemo(() => {
    const rows = [...filtered];
    rows.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "amount") cmp = Number(a.amount) - Number(b.amount);
      else if (sortKey === "updated_at")
        cmp = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
      else cmp = String(a[sortKey]).localeCompare(String(b[sortKey]));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [filtered, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
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
      className={cn("px-4 py-3.5 font-medium", align === "end" ? "text-end" : "text-start")}
    >
      <button
        type="button"
        onClick={() => toggleSort(key)}
        className="inline-flex items-center gap-1.5 text-white/90 transition-colors hover:text-white"
      >
        <span>{label}</span>
        <span aria-hidden className="text-[10px] text-white/60">
          {sortKey === key ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );

  return (
    <div className="space-y-4">
      {/* Search & Filter Toolbar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* State Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 p-1 rounded-xl bg-surface-muted/80 border border-border-subtle/60 text-xs">
          <button
            type="button"
            onClick={() => setFilterState("all")}
            className={cn(
              "px-3 py-1.5 rounded-lg font-medium transition-all",
              filterState === "all"
                ? "bg-surface text-ink font-semibold shadow-xs"
                : "text-ink-muted hover:text-ink hover:bg-surface/50",
            )}
          >
            All Deals ({counts.all})
          </button>

          <button
            type="button"
            onClick={() => setFilterState("DISPUTED")}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all",
              filterState === "DISPUTED"
                ? "bg-status-attention text-white font-semibold shadow-xs"
                : counts.disputed > 0
                  ? "bg-status-attention-soft text-status-attention font-semibold hover:bg-status-attention/20"
                  : "text-ink-muted hover:text-ink hover:bg-surface/50",
            )}
          >
            <span>Disputed</span>
            <span
              className={cn(
                "rounded-full px-1.5 py-0.2 text-[10px]",
                filterState === "DISPUTED" ? "bg-white/20 text-white" : "bg-status-attention text-white",
              )}
            >
              {counts.disputed}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setFilterState("FUNDED")}
            className={cn(
              "px-3 py-1.5 rounded-lg font-medium transition-all",
              filterState === "FUNDED"
                ? "bg-surface text-ink font-semibold shadow-xs"
                : "text-ink-muted hover:text-ink hover:bg-surface/50",
            )}
          >
            In Escrow ({counts.funded})
          </button>

          <button
            type="button"
            onClick={() => setFilterState("VERIFYING")}
            className={cn(
              "px-3 py-1.5 rounded-lg font-medium transition-all",
              filterState === "VERIFYING"
                ? "bg-surface text-ink font-semibold shadow-xs"
                : "text-ink-muted hover:text-ink hover:bg-surface/50",
            )}
          >
            Verifying ({counts.verifying})
          </button>

          <button
            type="button"
            onClick={() => setFilterState("RELEASED")}
            className={cn(
              "px-3 py-1.5 rounded-lg font-medium transition-all",
              filterState === "RELEASED"
                ? "bg-surface text-ink font-semibold shadow-xs"
                : "text-ink-muted hover:text-ink hover:bg-surface/50",
            )}
          >
            Completed ({counts.completed})
          </button>
        </div>

        {/* Live Search Input */}
        <div className="relative w-full sm:w-72">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-ink-faint pointer-events-none"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search deals, buyer, seller..."
            className="w-full rounded-lg border border-border-subtle bg-surface pl-9 pr-8 py-2 text-xs text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
          {searchQuery ? (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-ink-faint hover:text-ink"
            >
              ×
            </button>
          ) : null}
        </div>
      </div>

      {/* Main Table Container */}
      <div className="overflow-hidden rounded-card border border-border-subtle/70 bg-surface shadow-sheet">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-sm">
            <thead className="bg-[#16203a] text-xs uppercase tracking-wider text-white">
              <tr>
                {header("title", t("grid.deal"))}
                <th scope="col" className="px-4 py-3.5 text-start font-medium text-white/90">
                  {t("grid.parties")}
                </th>
                {header("amount", t("grid.amount"), "end")}
                {header("state", t("grid.state"))}
                {header("updated_at", t("grid.updated"), "end")}
                <th scope="col" className="px-4 py-3.5 text-end font-medium text-white/90">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle/70">
              {sorted.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-ink-muted">
                    <p className="text-sm font-medium">No deals match your criteria.</p>
                    <button
                      type="button"
                      onClick={() => {
                        setFilterState("all");
                        setSearchQuery("");
                      }}
                      className="mt-2 text-xs font-semibold text-accent hover:underline"
                    >
                      Clear filters and search
                    </button>
                  </td>
                </tr>
              ) : (
                sorted.map((deal) => {
                  const isDisputed = deal.state === "DISPUTED";
                  return (
                    <tr
                      key={deal.id}
                      className={cn(
                        "group transition-colors",
                        isDisputed ? "bg-status-attention-soft/15 hover:bg-status-attention-soft/25" : "hover:bg-surface-muted/60",
                      )}
                    >
                      {/* Deal Title & ID */}
                      <td className="px-4 py-3.5">
                        <Link
                          href={`/${locale}/deals/${deal.id}`}
                          className="font-semibold text-ink group-hover:text-accent transition-colors block"
                        >
                          {deal.title}
                        </Link>
                        <span className="font-mono text-[10px] text-ink-faint block mt-0.5 truncate max-w-[180px]">
                          {deal.id}
                        </span>
                      </td>

                      {/* Parties (Buyer -> Seller) */}
                      <td className="px-4 py-3.5 text-xs text-ink-muted">
                        <div className="flex flex-col gap-0.5">
                          <span className="truncate max-w-[190px]">
                            <strong className="text-ink-faint text-[10px] uppercase tracking-wide">Buyer:</strong>{" "}
                            {deal.buyer.full_name || deal.buyer.email}
                          </span>
                          <span className="truncate max-w-[190px]">
                            <strong className="text-ink-faint text-[10px] uppercase tracking-wide">Seller:</strong>{" "}
                            {deal.seller.full_name || deal.seller.email}
                          </span>
                        </div>
                      </td>

                      {/* Amount */}
                      <td className="px-4 py-3.5 text-end">
                        <MoneyAmount amount={deal.amount} currency={deal.currency} size="sm" className="font-bold text-ink" />
                      </td>

                      {/* State Badge */}
                      <td className="px-4 py-3.5">
                        <StatusBadge state={deal.state} />
                      </td>

                      {/* Timestamp */}
                      <td className="px-4 py-3.5 text-end text-xs text-ink-faint whitespace-nowrap">
                        {format.dateTime(new Date(deal.updated_at), {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>

                      {/* Direct Review Action */}
                      <td className="px-4 py-3.5 text-end">
                        <Link
                          href={`/${locale}/deals/${deal.id}`}
                          className={cn(
                            "inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold transition-all",
                            isDisputed
                              ? "bg-status-attention text-white hover:bg-status-attention/90 shadow-2xs"
                              : "bg-surface-muted text-ink-muted hover:bg-accent/10 hover:text-accent",
                          )}
                        >
                          {isDisputed ? "Review & Settle →" : "Inspect →"}
                        </Link>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Footer info bar */}
        <div className="flex items-center justify-between border-t border-border-subtle/60 bg-surface-muted/30 px-4 py-2.5 text-xs text-ink-faint">
          <span>Showing {sorted.length} of {deals.length} deals</span>
          <span className="text-[11px]">Audit-compliant escrow management</span>
        </div>
      </div>
    </div>
  );
}
