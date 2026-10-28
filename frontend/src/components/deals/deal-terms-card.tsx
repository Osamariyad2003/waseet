"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import type { DealTerms } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The Deal Terms Acknowledgment: a plain-language summary of what both parties
 * agreed to, pinned to the confirmed checklist with a SHA-256. Honest by
 * design — it states the process, shows the fingerprint, and preserves every
 * right. It is not a binding legal instrument.
 */
export function DealTermsCard({ dealId }: { dealId: string }) {
  const t = useTranslations("terms");
  const [open, setOpen] = useState(false);

  const { data: terms, isPending, isError } = useQuery<DealTerms, ApiError>({
    queryKey: ["terms", dealId],
    queryFn: () => api.getTerms(dealId),
    enabled: open,
  });

  return (
    <Card className="p-5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-3 text-start"
      >
        <span>
          <CardTitle>{t("title")}</CardTitle>
          <CardSubtitle>{t("subtitle")}</CardSubtitle>
        </span>
        <span aria-hidden className="mt-1 text-ink-faint">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open ? (
        isPending ? (
          <div className="mt-4 h-40 animate-pulse rounded-lg bg-surface-muted" aria-busy="true" />
        ) : isError || !terms ? (
          <p className="mt-4 text-sm text-ink-muted">{t("loadFailed")}</p>
        ) : (
          <div className="mt-4 space-y-5">
            {/* Confirmation state (the actual agreement) */}
            <div className="flex flex-wrap gap-2">
              <ConfirmBadge ok={terms.buyer_confirmed} label={t("buyer")} />
              <ConfirmBadge ok={terms.seller_confirmed} label={t("seller")} />
            </div>

            {/* The agreed checklist */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                {t("checklist")}
              </h4>
              <ol className="list-decimal space-y-1 ps-5 text-sm text-ink">
                {terms.criteria.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ol>
            </div>

            {/* The cryptographic fingerprint that pins the terms */}
            <div className="space-y-1">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                {t("fingerprint")}
              </h4>
              <p
                className="break-all rounded-lg bg-surface-muted px-3 py-2 font-mono text-xs text-ink-muted"
                title={terms.checklist_sha256}
              >
                sha256:{terms.checklist_sha256}
              </p>
            </div>

            {/* How the process works, stated plainly */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                {t("howItWorks")}
              </h4>
              <ol className="list-decimal space-y-1 ps-5 text-sm text-ink-muted">
                {terms.process_steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </div>

            {/* Rights preserved — the honest counterpart to a waiver */}
            <p className="rounded-lg border border-border-subtle/70 bg-surface-muted/50 px-3 py-2.5 text-xs leading-relaxed text-ink-muted">
              {terms.rights_notice}
            </p>
          </div>
        )
      ) : null}
    </Card>
  );
}

function ConfirmBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        ok
          ? "border-status-paid/20 bg-status-paid-soft text-status-paid"
          : "border-border-subtle bg-surface-muted text-ink-faint",
      )}
    >
      <span aria-hidden>{ok ? "✓" : "○"}</span>
      {label}
    </span>
  );
}
