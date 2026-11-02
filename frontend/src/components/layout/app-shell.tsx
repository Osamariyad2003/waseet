"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { AppSidebar } from "@/components/sidebar/app-sidebar";
import { useSession } from "@/hooks/use-session";
import { cn } from "@/lib/utils";

export function AppShell({
  children,
  locale,
}: {
  children: React.ReactNode;
  locale: string;
}) {
  const t = useTranslations();
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useSession();

  const isAuthPage =
    pathname === `/${locale}/login` ||
    pathname.endsWith("/login") ||
    pathname === `/${locale}/signup` ||
    pathname.endsWith("/signup");

  // The public landing page owns its whole layout (its own top bar, no
  // sidebar), so the shell just hands it the canvas.
  const isLandingPage = pathname === `/${locale}` || pathname === `/${locale}/`;
  if (isLandingPage) {
    return (
      <div className="min-h-dvh bg-canvas" suppressHydrationWarning>
        {children}
      </div>
    );
  }

  // The public proof-of-escrow certificate is shareable and viewable without
  // signing in, so it owns its whole layout — no sidebar, no session.
  if (pathname.includes(`/${locale}/verify/`)) {
    return (
      <div className="min-h-dvh bg-canvas" suppressHydrationWarning>
        {children}
      </div>
    );
  }

  if (isAuthPage) {
    return (
      <div className="min-h-dvh flex flex-col bg-gradient-to-br from-accent-soft/40 via-canvas to-canvas" suppressHydrationWarning>
        <header className="bg-accent text-white px-4 py-3 sm:px-6">
          <div className="mx-auto flex w-full max-w-3xl items-center justify-between">
            <Link
              href={`/${locale}/deals`}
              className="flex items-baseline gap-2 font-semibold text-white"
            >
              {t("app.name")}
              <span className="hidden text-xs font-normal text-white/70 sm:inline">
                {t("app.tagline")}
              </span>
            </Link>

            <div className="flex items-center gap-3">
              <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-medium text-white">
                {t("app.sandboxNotice")}
              </span>
            </div>
          </div>
        </header>
        <main className="flex-1 flex items-center justify-center p-4 sm:p-6">
          {children}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-dvh flex flex-col md:flex-row bg-canvas" suppressHydrationWarning>
      {/* Mobile-only top header */}
      <header className="md:hidden bg-surface border-b border-border-subtle/70 px-4 py-2.5 flex items-center justify-between sticky top-0 z-30 shadow-xs">
        <Link
          href={`/${locale}/deals`}
          className="flex items-center gap-2 font-bold text-ink"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="" className="h-5 w-auto" aria-hidden />
          <span className="text-base font-bold">{t("app.name")}</span>
        </Link>

        <div className="flex items-center gap-2">
          <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-medium text-ink-muted border border-border-subtle/40">
            Sandbox
          </span>

          {user ? (
            <button
              type="button"
              onClick={() => {
                signOut();
                router.replace(`/${locale}/login`);
              }}
              className="text-xs text-ink-muted hover:text-status-attention ps-1"
            >
              {t("nav.signOut")}
            </button>
          ) : null}
        </div>
      </header>

      {/* Sidebar navigation */}
      <AppSidebar locale={locale} />

      {/* Main content area */}
      <main className="flex-1 min-w-0 px-4 py-6 sm:px-6 sm:py-8 pb-24 md:pb-10 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
