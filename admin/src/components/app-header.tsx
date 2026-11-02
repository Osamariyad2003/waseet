"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { useSession } from "@/hooks/use-session";
import { cn } from "@/lib/utils";

export function AppHeader({ locale }: { locale: string }) {
  const t = useTranslations();
  const { user, signOut } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  const isDashboard = pathname === `/${locale}/dashboard` || pathname.endsWith("/dashboard");

  return (
    <header className="sticky top-0 z-40 bg-[#16203a] border-b border-[#253358] text-white shadow-md">
      <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
        {/* Left: Brand & Nav Links */}
        <div className="flex items-center gap-6">
          <Link
            href={`/${locale}/dashboard`}
            className="flex items-center gap-2.5 font-bold tracking-tight text-white hover:opacity-95 transition-opacity"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" className="h-6 w-auto brightness-0 invert" aria-hidden />
            <span className="text-lg">{t("app.name")}</span>
            <span className="rounded-full bg-accent/30 border border-accent-bright/50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-blue-200">
              {t("app.adminBadge")}
            </span>
          </Link>

          {/* Quick Nav Links */}
          <nav className="hidden sm:flex items-center gap-1 text-xs font-medium">
            <Link
              href={`/${locale}/dashboard`}
              className={cn(
                "rounded-md px-3 py-1.5 transition-colors",
                isDashboard
                  ? "bg-white/10 text-white font-semibold"
                  : "text-white/70 hover:bg-white/5 hover:text-white",
              )}
            >
              Overview
            </Link>
            <Link
              href={`/${locale}/dashboard?filter=DISPUTED`}
              className="rounded-md px-3 py-1.5 text-white/70 hover:bg-white/5 hover:text-white transition-colors"
            >
              Dispute Queue
            </Link>
            <a
              href="http://localhost:3000"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-white/60 hover:bg-white/5 hover:text-white transition-colors"
              title="Open buyer/seller escrow application"
            >
              <span>Escrow App</span>
              <svg className="size-3 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </nav>
        </div>

        {/* Right: Live Status & User Info */}
        <div className="ms-auto flex items-center gap-3">
          {/* Live PayPal Sandbox Indicator */}
          <div className="hidden md:flex items-center gap-1.5 rounded-full bg-emerald-950/60 border border-emerald-600/40 px-3 py-1 text-[11px] font-medium text-emerald-300">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
            </span>
            <span>PayPal Sandbox Live</span>
          </div>

          {user ? (
            <div className="flex items-center gap-3 ps-2 border-s border-white/10">
              <div className="hidden lg:flex flex-col text-end">
                <span className="text-xs font-semibold text-white truncate max-w-[150px]">
                  {user.full_name || "Dispute Reviewer"}
                </span>
                <span className="text-[10px] text-white/60 truncate max-w-[150px]">
                  {user.email}
                </span>
              </div>

              <div className="flex size-8 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-white shadow-xs">
                REV
              </div>

              <button
                type="button"
                onClick={() => {
                  signOut();
                  router.replace(`/${locale}/login`);
                }}
                className="inline-flex items-center gap-1.5 rounded-md bg-white/10 px-2.5 py-1.5 text-xs text-white/80 hover:bg-rose-500/20 hover:text-rose-200 transition-colors"
                title={t("nav.signOut")}
              >
                <svg className="size-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
                <span className="hidden sm:inline">{t("nav.signOut")}</span>
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
