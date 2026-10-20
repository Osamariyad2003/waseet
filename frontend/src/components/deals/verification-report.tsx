"use client";

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { Spinner } from "@/components/ui/spinner";
import type { VerificationReport as Report } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * How sure the verifier was, shown as a meter.
 *
 * The threshold is drawn on the scale, because "0.62" means nothing on its
 * own — what matters is which side of the auto-release line it falls on.
 */
export function ConfidenceMeter({
  confidence,
  threshold = 0.8,
}: {
  confidence: string;
  threshold?: number;
}) {
  const t = useTranslations();
  const value = Number(confidence);
  const safe = Number.isFinite(value) ? Math.min(Math.max(value, 0), 1) : 0;
  const clears = safe >= threshold;
  const percent = Math.round(safe * 100);

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          {t("verification.confidence")}
        </span>
        <span className="tabular text-sm font-semibold text-ink">{percent}%</span>
      </div>
      <div
        role="meter"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t("verification.confidence")}
        className="relative h-2 w-full overflow-hidden rounded-full bg-surface-muted"
      >
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className={cn(
            "h-full rounded-full",
            clears ? "bg-status-paid" : "bg-status-returned",
          )}
        />
        {/* The auto-release line. */}
        <span
          aria-hidden
          className="absolute top-0 h-full w-0.5 bg-ink/35"
          style={{ insetInlineStart: `${threshold * 100}%` }}
        />
      </div>
    </div>
  );
}

interface VerificationReportProps {
  report: Report;
  /** Shown while the model is running, instead of a frozen screen. */
  isRunning?: boolean;
}

/** The verification report: per-criterion findings, verdict, confidence,
 * reasoning — and the plain statement that it is advisory. */
export function VerificationReport({ report, isRunning }: VerificationReportProps) {
  const t = useTranslations();

  const verdictTone =
    report.verdict === "pass"
      ? "text-status-paid bg-status-paid-soft border-status-paid/20"
      : report.verdict === "fail"
        ? "text-status-attention bg-status-attention-soft border-status-attention/20"
        : "text-status-returned bg-status-returned-soft border-status-returned/25";

  return (
    <div className="space-y-5">
      <div className={cn("rounded-lg border px-4 py-3", verdictTone)}>
        <p className="text-xs font-medium uppercase tracking-wide opacity-80">
          {t("verification.verdict")}
        </p>
        <p className="mt-0.5 text-base font-semibold">
          {t(`verification.verdicts.${report.verdict}`)}
        </p>
      </div>

      <ConfidenceMeter confidence={report.confidence} />

      {report.per_criterion.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            {t("verification.perCriterion")}
          </h3>
          <ul className="divide-y divide-border-subtle rounded-lg border border-border-subtle">
            {report.per_criterion.map((finding, index) => (
              <li key={`${finding.criterion_id}-${index}`} className="flex gap-3 p-3">
                <span
                  aria-hidden
                  className={cn(
                    "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                    finding.pass
                      ? "bg-status-paid-soft text-status-paid"
                      : "bg-status-attention-soft text-status-attention",
                  )}
                >
                  {finding.pass ? "✓" : "✕"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink">{finding.text}</p>
                  <p className="mt-0.5 text-sm text-ink-muted">
                    <span className="sr-only">
                      {finding.pass ? t("verification.pass") : t("verification.fail")}.{" "}
                    </span>
                    {finding.note}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="space-y-1.5">
        <h3 className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          {t("verification.reasoning")}
        </h3>
        <p className="whitespace-pre-line text-sm leading-relaxed text-ink">
          {report.reasoning}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
        <span>
          {report.decided_by === "ai"
            ? t("verification.decidedByAi")
            : t("verification.decidedByHuman")}
        </span>
        {isRunning ? <Spinner label={t("verification.running")} /> : null}
      </div>

      {/* The honesty requirement, stated in the UI rather than the README. */}
      {report.decided_by === "ai" ? (
        <p className="rounded-lg bg-surface-muted px-3 py-2.5 text-xs leading-relaxed text-ink-muted">
          {t("verification.advisory")}
        </p>
      ) : null}
    </div>
  );
}

/** The VERIFYING state: visible progress, not a frozen screen. */
export function VerificationRunning() {
  const t = useTranslations();
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-status-progress/20 bg-status-progress-soft px-4 py-8 text-center">
      <motion.span
        aria-hidden
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        className="size-3 rounded-full bg-status-progress"
      />
      <div>
        <p className="text-sm font-semibold text-ink">{t("verification.running")}</p>
        <p className="mt-1 text-sm text-ink-muted">{t("verification.runningDetail")}</p>
      </div>
      <Spinner className="text-status-progress" label={t("verification.running")} />
    </div>
  );
}
