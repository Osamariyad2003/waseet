"use client";

import { motion } from "framer-motion";
import { useFormatter, useTranslations } from "next-intl";

import { statusStyle } from "@/lib/status";
import type { AuditEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

interface DealTimelineProps {
  entries: AuditEntry[];
  isLoading?: boolean;
  error?: string;
  onRetry?: () => void;
}

/**
 * The deal's history — every state change and decision, with the AI's
 * reasoning and the PayPal reference that backs it.
 *
 * This is the audit trail made legible: the demo's closing beat is scrolling
 * this and seeing that nothing happened without a recorded reason.
 */
export function DealTimeline({ entries, isLoading, error, onRetry }: DealTimelineProps) {
  const t = useTranslations();
  const format = useFormatter();

  if (isLoading) {
    return (
      <ol className="space-y-4" aria-busy="true">
        {[0, 1, 2].map((index) => (
          <li key={index} className="flex gap-3">
            <div className="mt-1.5 size-2.5 shrink-0 animate-pulse rounded-full bg-border-subtle" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-24 animate-pulse rounded bg-border-subtle" />
              <div className="h-3 w-3/4 animate-pulse rounded bg-surface-muted" />
            </div>
          </li>
        ))}
      </ol>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-status-attention/25 bg-status-attention-soft p-4">
        <p className="text-sm text-ink">{error}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 text-sm font-medium text-accent underline"
          >
            {t("common.retry")}
          </button>
        ) : null}
      </div>
    );
  }

  if (entries.length === 0) {
    return <p className="text-sm text-ink-muted">{t("timeline.empty")}</p>;
  }

  return (
    <ol className="space-y-5">
      {entries.map((entry, index) => {
        const style = statusStyle(entry.to_state);
        const isLast = index === entries.length - 1;

        return (
          <motion.li
            key={entry.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: Math.min(index * 0.03, 0.2) }}
            className="relative flex gap-3"
          >
            {/* The connecting rail, drawn behind the dots. */}
            {!isLast ? (
              <span
                aria-hidden
                className="absolute start-[4.5px] top-4 h-[calc(100%+0.75rem)] w-px bg-border-subtle"
              />
            ) : null}

            <span
              aria-hidden
              className={cn("relative mt-1.5 size-2.5 shrink-0 rounded-full", style.dot)}
            />

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="text-sm font-semibold text-ink">
                  {t(`states.${entry.to_state}`)}
                </span>
                <span className="text-xs text-ink-faint">
                  {t(`timeline.actors.${entry.actor}`)}
                </span>
                <time
                  dateTime={entry.created_at}
                  className="text-xs text-ink-faint tabular ms-auto"
                >
                  {format.dateTime(new Date(entry.created_at), {
                    hour: "2-digit",
                    minute: "2-digit",
                    day: "numeric",
                    month: "short",
                  })}
                </time>
              </div>

              <p className="mt-1 text-sm leading-relaxed text-ink-muted">{entry.reason}</p>

              {entry.paypal_reference ? (
                <p className="mt-1.5 text-xs text-ink-faint">
                  {t("timeline.paypalReference")}:{" "}
                  <span className="tabular font-medium text-ink-muted">
                    {entry.paypal_reference}
                  </span>
                </p>
              ) : null}
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}
