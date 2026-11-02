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
      <header className="sticky top-0 z-30 border-b border-white/10 bg-accent/95 backdrop-blur-lg">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
          <Link href={`/${locale}`} className="flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" className="h-6 w-auto brightness-0 invert" aria-hidden />
            <span className="text-lg font-bold tracking-tight text-white">{t("app.name")}</span>
          </Link>

          <div className="ms-auto flex items-center gap-3">
            <LanguageToggle />
            <Link
              href={primaryHref}
              className="inline-flex h-9 items-center rounded-lg bg-white px-4 text-sm font-medium text-accent transition-colors hover:bg-white/90"
            >
              {user ? t("landing.openApp") : t("landing.signIn")}
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <section className="relative overflow-hidden bg-gradient-to-b from-accent via-accent to-accent-soft/30">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(255,255,255,0.15),transparent)]" />
          <div className="relative mx-auto w-full max-w-4xl px-4 py-20 text-center sm:px-6 sm:py-28">
            <motion.div
              custom={0}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="mb-6 flex justify-center"
            >
              <span className="flex size-20 items-center justify-center rounded-2xl bg-white/15 shadow-lg ring-1 ring-white/20 backdrop-blur-sm">
                <LottieAnimation
                  animationData={successAnim}
                  loop
                  className="size-12"
                  ariaLabel={t("landing.title")}
                />
              </span>
            </motion.div>
            <motion.span
              custom={1}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium text-white/90 backdrop-blur-sm"
            >
              <span className="size-1.5 rounded-full bg-emerald-400" />
              {t("landing.badge")}
            </motion.span>
            <motion.h1
              custom={2}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="mt-5 text-balance text-4xl font-bold leading-tight tracking-tight text-white sm:text-5xl"
            >
              {t("landing.title")}
            </motion.h1>
            <motion.p
              custom={3}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              className="mx-auto mt-5 max-w-2xl text-pretty text-lg leading-relaxed text-white/75"
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
                className="inline-flex h-12 items-center rounded-xl bg-white px-6 text-base font-semibold text-accent shadow-lg transition-all hover:bg-white/90 hover:shadow-xl"
              >
                {user ? t("landing.openApp") : t("landing.ctaPrimary")}
              </Link>
              <Link
                href={`/${locale}/explore`}
                className="inline-flex h-12 items-center rounded-xl border border-white/25 bg-white/10 px-6 text-base font-medium text-white backdrop-blur-sm transition-colors hover:bg-white/20"
              >
                {t("landing.ctaSecondary")}
              </Link>
            </motion.div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-5xl px-4 -mt-8 relative z-10 sm:px-6">
          <div className="grid gap-4 sm:grid-cols-3">
            {(["ai", "policy", "sandbox"] as const).map((key) => (
              <div
                key={key}
                className="rounded-card border border-border-subtle/40 bg-surface p-6 text-center shadow-card-hover"
              >
                <p className="text-2xl font-bold text-accent">{t(`landing.stats.${key}.value`)}</p>
                <p className="mt-1.5 text-sm text-ink-muted">{t(`landing.stats.${key}.label`)}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto w-full max-w-5xl px-4 py-20 sm:px-6">
          <p className="text-center text-sm font-semibold uppercase tracking-widest text-accent">
            How it works
          </p>
          <h2 className="mt-2 text-center text-2xl font-bold tracking-tight text-ink sm:text-3xl">
            {t("explore.stepsTitle")}
          </h2>
          <ol className="mt-10 grid gap-5 sm:grid-cols-2">
            {steps.map((key, index) => (
              <li
                key={key}
                className="group flex gap-4 rounded-card border border-border-subtle/40 bg-surface p-6 shadow-sheet transition-all duration-200 hover:shadow-card-hover hover:-translate-y-0.5"
              >
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent text-sm font-bold text-white">
                  {index + 1}
                </span>
                <div>
                  <h3 className="font-semibold text-ink">{t(`explore.steps.${key}.title`)}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
                    {t(`explore.steps.${key}.body`)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="bg-gradient-to-b from-surface-muted/50 to-canvas py-20">
          <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
            <p className="text-center text-sm font-semibold uppercase tracking-widest text-status-paid">
              Trust & safety
            </p>
            <h2 className="mt-2 text-center text-2xl font-bold tracking-tight text-ink sm:text-3xl">
              {t("explore.safeTitle")}
            </h2>
            <div className="mt-10 grid gap-5 sm:grid-cols-2">
              {pillars.map((key) => (
                <div
                  key={key}
                  className="group rounded-card border border-border-subtle/40 bg-surface p-6 shadow-sheet transition-all duration-200 hover:shadow-card-hover hover:-translate-y-0.5"
                >
                  <h3 className="font-semibold text-ink">{t(`explore.safe.${key}.title`)}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
                    {t(`explore.safe.${key}.body`)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-4xl px-4 py-20 sm:px-6">
          <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-accent to-accent-bright px-6 py-14 text-center text-white shadow-lg sm:px-12">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_80%_-20%,rgba(255,255,255,0.12),transparent)]" />
            <div className="relative">
              <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("landing.finalTitle")}</h2>
              <p className="mx-auto mt-3 max-w-xl text-white/80">{t("landing.finalSubtitle")}</p>
              <Link
                href={primaryHref}
                className="mt-8 inline-flex h-12 items-center rounded-xl bg-white px-8 text-base font-semibold text-accent shadow-lg transition-all hover:bg-white/90 hover:shadow-xl"
              >
                {user ? t("landing.openApp") : t("landing.ctaPrimary")}
              </Link>
            </div>
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
              ? "bg-white/20 text-white"
              : "text-white/60 hover:bg-white/10 hover:text-white",
          )}
        >
          {option}
        </Link>
      ))}
    </nav>
  );
}
