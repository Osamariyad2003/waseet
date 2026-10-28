"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useFormatter, useLocale, useTranslations } from "next-intl";

import { ConfidenceMeter } from "@/components/deals/verification-report";
import { MoneyAmount } from "@/components/deals/money-amount";
import { Card } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import type { Certificate } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function CertificatePage() {
  const t = useTranslations("certificate");
  const locale = useLocale();
  const format = useFormatter();
  const params = useParams();
  const dealId = String(params.dealId);

  const {
    data: cert,
    isPending,
    isError,
    error,
  } = useQuery<Certificate, ApiError>({
    queryKey: ["certificate", dealId],
    queryFn: () => api.getCertificate(dealId),
    retry: (count, err) => !err.isPermanent && count < 2,
  });

  return (
    <div className="min-h-dvh bg-canvas">
      <header className="bg-accent px-4 py-3 text-white sm:px-6">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between">
          <Link href={`/${locale}/deals`} className="flex items-baseline gap-2 font-semibold">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" className="h-5 w-auto" aria-hidden />
            <span>Waseet</span>
          </Link>
          <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-medium">
            {t("sandbox")}
          </span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-2xl px-4 py-8 sm:px-6 sm:py-12">
        {isPending ? (
          <div className="h-80 animate-pulse rounded-card bg-surface" aria-busy="true" />
        ) : isError ? (
          <Card className="space-y-2 p-8 text-center">
            <h1 className="text-lg font-semibold text-ink">{t("notFoundTitle")}</h1>
            <p className="text-sm text-ink-muted">
              {error.status === 404 ? t("notFoundBody") : error.message}
            </p>
            <Link
              href={`/${locale}/deals`}
              className="inline-flex h-9 items-center rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
            >
              {t("back")}
            </Link>
          </Card>
        ) : (
          <Certificate cert={cert} format={format} />
        )}
      </main>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: Certificate["outcome"] }) {
  const t = useTranslations("certificate");
  const tone =
    outcome === "released"
      ? "bg-status-paid-soft text-status-paid border-status-paid/20"
      : outcome === "refunded"
        ? "bg-status-returned-soft text-status-returned border-status-returned/25"
        : "bg-status-progress-soft text-status-progress border-status-progress/20";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold",
        tone,
      )}
    >
      {t(`outcomes.${outcome}`)}
    </span>
  );
}

function Certificate({
  cert,
  format,
}: {
  cert: Certificate;
  format: ReturnType<typeof useFormatter>;
}) {
  const t = useTranslations("certificate");

  return (
    <Card className="overflow-hidden p-0">
      {/* Masthead */}
      <div className="border-b border-border-subtle/70 bg-surface-muted/50 px-6 py-6 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-ink-faint">
          {t("title")}
        </p>
        <h1 className="mt-2 text-xl font-bold text-ink">{cert.title}</h1>
        <p className="mt-1 font-mono text-xs text-ink-muted">{cert.seal}</p>
      </div>

      <div className="space-y-6 p-6">
        {/* Outcome + amount */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              {t("outcome")}
            </p>
            <div className="mt-1">
              <OutcomeBadge outcome={cert.outcome} />
            </div>
          </div>
          <div className="text-end">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              {t("amount")}
            </p>
            <MoneyAmount
              amount={cert.amount}
              currency={cert.currency}
              size="lg"
              className="font-bold text-ink"
            />
          </div>
        </div>

        {/* Verification block, when the deal was AI-verified */}
        {cert.verdict ? (
          <div className="space-y-4 rounded-lg border border-border-subtle/70 p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-ink">
                {t(`verdicts.${cert.verdict}`)}
              </span>
              <span className="text-xs text-ink-faint">
                {cert.decided_by === "human" ? t("decidedByHuman") : t("decidedByAi")}
              </span>
            </div>

            {cert.confidence ? <ConfidenceMeter confidence={cert.confidence} /> : null}

            {cert.verified_criteria.length > 0 ? (
              <AuditList tone="met" heading={t("met")} items={cert.verified_criteria} />
            ) : null}
            {cert.unmet_or_missing_criteria.length > 0 ? (
              <AuditList
                tone="unmet"
                heading={t("unmet")}
                items={cert.unmet_or_missing_criteria}
              />
            ) : null}
          </div>
        ) : null}

        {/* Footer: issue date + advisory */}
        <div className="space-y-2 border-t border-border-subtle/70 pt-4">
          <p className="text-xs text-ink-faint">
            {t("issued")}{" "}
            {format.dateTime(new Date(cert.decided_at ?? cert.created_at), {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </p>
          <p className="text-xs leading-relaxed text-ink-muted">{cert.advisory_notice}</p>
        </div>
      </div>
    </Card>
  );
}

function AuditList({
  tone,
  heading,
  items,
}: {
  tone: "met" | "unmet";
  heading: string;
  items: string[];
}) {
  const met = tone === "met";
  return (
    <div>
      <p
        className={cn(
          "text-xs font-semibold uppercase tracking-wide",
          met ? "text-status-paid" : "text-status-attention",
        )}
      >
        {heading} · {items.length}
      </p>
      <ul className="mt-2 space-y-1.5">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2 text-sm text-ink">
            <span aria-hidden className={met ? "text-status-paid" : "text-status-attention"}>
              {met ? "✓" : "✕"}
            </span>
            <span className="min-w-0 flex-1">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
