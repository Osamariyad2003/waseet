"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";

import { useSession } from "@/hooks/use-session";
import { locales } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function AppHeader({ locale }: { locale: string }) {
  const t = useTranslations();
  const { user, signOut } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const activeLocale = useLocale();

  /** Switch language but stay on the same page. */
  const switchTo = (next: string) => {
    const rest = pathname.replace(/^\/[^/]+/, "");
    router.replace(`/${next}${rest || ""}`);
  };

  return (
    <header className="bg-accent text-white">
      <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
        <Link
          href={`/${locale}/deals`}
          className="flex items-baseline gap-2 font-semibold text-white"
        >
          {t("app.name")}
          <span className="hidden text-xs font-normal text-white/70 sm:inline">
            {t("app.tagline")}
          </span>
        </Link>

        {/* A reviewer has an operations dashboard; the parties do not. */}
        {user?.role === "reviewer" ? (
          <nav className="flex items-center gap-1 text-sm">
            <Link
              href={`/${locale}/dashboard`}
              className="rounded px-2 py-1 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
            >
              {t("dashboard.title")}
            </Link>
            <Link
              href={`/${locale}/deals`}
              className="rounded px-2 py-1 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
            >
              {t("dashboard.reviewQueue")}
            </Link>
          </nav>
        ) : null}

        <div className="ms-auto flex items-center gap-3">
          {/* Sandbox is stated in the chrome, so nobody watching the demo
              wonders whether real money is moving. */}
          <span className="hidden rounded-full bg-white/15 px-2.5 py-1 text-xs font-medium text-white sm:inline">
            {t("app.sandboxNotice")}
          </span>

          <nav aria-label={t("nav.language")} className="flex items-center gap-1">
            {locales.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => switchTo(option)}
                aria-current={activeLocale === option ? "true" : undefined}
                className={cn(
                  "rounded px-2 py-1 text-xs font-medium uppercase transition-colors",
                  activeLocale === option
                    ? "bg-white text-accent"
                    : "text-white/70 hover:text-white",
                )}
              >
                {option}
              </button>
            ))}
          </nav>

          {user ? (
            <button
              type="button"
              onClick={() => {
                signOut();
                router.replace(`/${locale}/login`);
              }}
              className="text-sm text-white/80 hover:text-white"
            >
              {t("nav.signOut")}
            </button>
          ) : null}
        </div>
      </div>
    </header>
  );
}
