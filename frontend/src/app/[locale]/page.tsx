"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

import successAnim from "@/animations/success.json";
import { LottieAnimation } from "@/components/ui/lottie";
import { useSession } from "@/hooks/use-session";
import { locales } from "@/lib/i18n";
import { cn } from "@/lib/utils";

// A gentle fade-up, staggered, for the hero.
const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: "easeOut" },
  }),
};

/**
 * The public landing page — Waseet's front door. Navy identity, honest claims
 * (it is a sandbox prototype), and the same lifecycle and guardrail content
 * the Explore page uses, so the story stays consistent in and out of the app.
 */
export default function LandingPage() {
  const t = useTranslations();
  const locale = useLocale();
  const { user } = useSession();

  const appHref = `/${locale}/deals`;
  const signInHref = `/${locale}/login`;
  const primaryHref = user ? appHref : signInHref;

  const steps = ["create", "fund", "deliver", "settle"] as const;
  const pillars = ["decide", "gate", "failsafe", "bounded"] as const;

  return (
    <div className="flex min-h-dvh flex-col">
      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-border-subtle/60 bg-surface/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
          <Link href={`/${locale}`} className="flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" className="h-6 w-auto" aria-hidden />
            <span className="text-lg font-bold tracking-tight text-ink">{t("app.name")}</span>
          </Link>

          <div className="ms-auto flex items-center gap-3">
            <LanguageToggle />
            <Link
              href={primaryHref}
              className="inline-flex h-9 items-center rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
            >
              {user ? t("landing.openApp") : t("landing.signIn")}
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-accent-soft/60 to-transparent" />
          <div className="relative mx-auto w-full max-w-4xl px-4 py-16 text-center sm:px-6 sm:py-24">
            <motion.div
              custom={0}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="mb-6 flex justify-center"
            >
              <span className="flex size-24 items-center justify-center rounded-full bg-surface shadow-sheet ring-1 ring-border-subtle/60">
                <LottieAnimation
                  animationData={successAnim}
                  loop
                  className="size-16"
                  ariaLabel={t("landing.title")}
                />
              </span>
            </motion.div>
            <motion.span
              custom={1}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="inline-flex items-center gap-2 rounded-full border border-border-subtle/70 bg-surface px-3 py-1 text-xs font-medium text-ink-muted shadow-xs"
            >
              <span className="size-1.5 rounded-full bg-status-paid" />
              {t("landing.badge")}
            </motion.span>
            <motion.h1
              custom={2}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="mt-5 text-balance text-4xl font-bold leading-tight tracking-tight text-ink sm:text-5xl"
            >
              {t("landing.title")}
            </motion.h1>
            <motion.p
              custom={3}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="mx-auto mt-5 max-w-2xl text-pretty text-lg leading-relaxed text-ink-muted"
            >
              {t("landing.subtitle")}
            </motion.p>
            <motion.div
              custom={4}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="mt-8 flex flex-wrap items-center justify-center gap-3"
            >
              <Link
                href={primaryHref}
                className="inline-flex h-12 items-center rounded-xl bg-accent px-6 text-base font-medium text-white shadow-sheet transition-colors hover:bg-accent-hover"
              >
                {user ? t("landing.openApp") : t("landing.ctaPrimary")}
              </Link>
              <Link
                href={`/${locale}/explore`}
                className="inline-flex h-12 items-center rounded-xl border border-border-subtle bg-surface px-6 text-base font-medium text-ink transition-colors hover:bg-surface-muted"
              >
                {t("landing.ctaSecondary")}
              </Link>
            </motion.div>
          </div>
        </section>

        {/* Trust strip */}
        <section className="mx-auto w-full max-w-5xl px-4 pb-4 sm:px-6">
          <div className="grid gap-4 sm:grid-cols-3">
            {(["ai", "policy", "sandbox"] as const).map((key) => (
              <div
                key={key}
                className="rounded-card border border-border-subtle/60 bg-surface p-5 text-center shadow-sheet"
              >
                <p className="text-2xl font-bold text-accent">{t(`landing.stats.${key}.value`)}</p>
                <p className="mt-1 text-sm text-ink-muted">{t(`landing.stats.${key}.label`)}</p>
              </div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section className="mx-auto w-full max-w-5xl px-4 py-16 sm:px-6">
          <h2 className="text-center text-2xl font-bold tracking-tight text-ink">
            {t("explore.stepsTitle")}
          </h2>
          <ol className="mt-8 grid gap-4 sm:grid-cols-2">
            {steps.map((key, index) => (
              <li
                key={key}
                className="flex gap-4 rounded-card border border-border-subtle/60 bg-surface p-5 shadow-sheet"
              >
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-bold text-accent">
                  {index + 1}
                </span>
                <div>
                  <h3 className="font-semibold text-ink">{t(`explore.steps.${key}.title`)}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-muted">
                    {t(`explore.steps.${key}.body`)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* What makes it safe */}
        <section className="bg-surface-muted/50 py-16">
          <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
            <h2 className="text-center text-2xl font-bold tracking-tight text-ink">
              {t("explore.safeTitle")}
            </h2>
            <div className="mt-8 grid gap-4 sm:grid-cols-2">
              {pillars.map((key) => (
                <div
                  key={key}
                  className="rounded-card border border-border-subtle/60 bg-surface p-5 shadow-sheet"
                >
                  <h3 className="font-semibold text-ink">{t(`explore.safe.${key}.title`)}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-muted">
                    {t(`explore.safe.${key}.body`)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="mx-auto w-full max-w-4xl px-4 py-16 sm:px-6">
          <div className="overflow-hidden rounded-card bg-accent px-6 py-12 text-center text-white shadow-sheet">
            <h2 className="text-2xl font-bold tracking-tight">{t("landing.finalTitle")}</h2>
            <p className="mx-auto mt-2 max-w-xl text-white/85">{t("landing.finalSubtitle")}</p>
            <Link
              href={primaryHref}
              className="mt-6 inline-flex h-12 items-center rounded-xl bg-white px-6 text-base font-medium text-accent transition-colors hover:bg-white/90"
            >
              {user ? t("landing.openApp") : t("landing.ctaPrimary")}
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-border-subtle/60 py-6">
        <p className="mx-auto w-full max-w-6xl px-4 text-center text-xs text-ink-faint sm:px-6">
          {t("landing.footer")}
        </p>
      </footer>
    </div>
  );
}

function LanguageToggle() {
  const locale = useLocale();
  return (
    <nav className="flex items-center gap-1" aria-label="Language">
      {locales.map((option) => (
        <Link
          key={option}
          href={`/${option}`}
          aria-current={locale === option ? "true" : undefined}
          className={cn(
            "rounded px-2 py-1 text-xs font-medium uppercase transition-colors",
            locale === option
              ? "bg-accent text-white"
              : "text-ink-muted hover:bg-surface-muted hover:text-ink",
          )}
        >
          {option}
        </Link>
      ))}
    </nav>
  );
}
