"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import type { Role } from "@/lib/types";

const STEPS = ["create", "fund", "deliver", "settle"] as const;
const DISMISS_KEY = "waseet.onboarding.dismissed";

/**
 * First-run onboarding: the empty-state a new user lands on. Explains the whole
 * deal lifecycle in four steps, is role-aware (a buyer is nudged to create the
 * first deal; a seller is told what to expect), and can be dismissed — the
 * choice is remembered per browser.
 */
export function GettingStarted({ role }: { role: Role }) {
  const t = useTranslations();
  const locale = useLocale();
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    try {
      setDismissed(window.localStorage.getItem(DISMISS_KEY) === "1");
    } catch {
      // No storage (private mode) — just show it.
    }
  }, []);

  const dismiss = () => {
    setDismissed(true);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Best effort; the panel still hides for this view.
    }
  };

  const isBuyer = role === "buyer";

  if (dismissed) {
    return (
      <Card>
        <p className="text-sm font-medium text-ink">{t("deals.empty")}</p>
        <p className="mt-1 text-sm text-ink-muted">
          {isBuyer ? t("deals.emptyBuyer") : t("deals.emptySeller")}
        </p>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden p-0">
      {/* Welcome header, in the navy identity. */}
      <div className="bg-accent px-5 py-6 text-white sm:px-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{t("onboarding.welcomeTitle")}</h2>
            <p className="mt-1 max-w-prose text-sm leading-relaxed text-white/85">
              {isBuyer ? t("onboarding.welcomeBuyer") : t("onboarding.welcomeSeller")}
            </p>
          </div>
          <button
            type="button"
            onClick={dismiss}
            className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-white/80 transition-colors hover:bg-white/10 hover:text-white"
          >
            {t("onboarding.dismiss")}
          </button>
        </div>
      </div>

      {/* The four steps. */}
      <ol className="grid gap-px bg-border-subtle/60 sm:grid-cols-2">
        {STEPS.map((key, index) => (
          <li key={key} className="flex gap-3 bg-surface p-4 sm:p-5">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent">
              {index + 1}
            </span>
            <div>
              <h3 className="text-sm font-semibold text-ink">
                {t(`onboarding.steps.${key}.title`)}
              </h3>
              <p className="mt-0.5 text-sm leading-relaxed text-ink-muted">
                {t(`onboarding.steps.${key}.body`)}
              </p>
            </div>
          </li>
        ))}
      </ol>

      {/* Primary action for a buyer; sellers just wait for a deal. */}
      {isBuyer ? (
        <div className="border-t border-border-subtle/60 bg-surface p-5 sm:p-6">
          <Link
            href={`/${locale}/deals/new`}
            className="inline-flex h-11 items-center rounded-lg bg-accent px-5 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
          >
            {t("onboarding.createFirst")}
          </Link>
        </div>
      ) : null}
    </Card>
  );
}
