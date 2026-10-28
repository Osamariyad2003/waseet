"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";

import {
  AccountIcon,
  ExploreIcon,
  HomeIcon,
  ShopIcon,
  WalletIcon,
} from "@/components/sidebar/sidebar-icons";
import { useSession } from "@/hooks/use-session";
import { cn } from "@/lib/utils";

interface NavItem {
  id: "home" | "explore" | "shop" | "wallet" | "account";
  labelKey: string;
  href: (locale: string) => string;
  isActive: (pathname: string, locale: string) => boolean;
  Icon: typeof HomeIcon;
}

export const NAV_ITEMS: NavItem[] = [
  {
    id: "home",
    labelKey: "nav.home",
    href: (locale) => `/${locale}/deals`,
    isActive: (pathname, locale) =>
      pathname === `/${locale}` ||
      pathname === `/${locale}/deals` ||
      pathname.startsWith(`/${locale}/deals/`),
    Icon: HomeIcon,
  },
  {
    id: "explore",
    labelKey: "nav.explore",
    href: (locale) => `/${locale}/explore`,
    isActive: (pathname, locale) => pathname.startsWith(`/${locale}/explore`),
    Icon: ExploreIcon,
  },
  {
    id: "shop",
    labelKey: "nav.shop",
    href: (locale) => `/${locale}/shop`,
    isActive: (pathname, locale) => pathname.startsWith(`/${locale}/shop`),
    Icon: ShopIcon,
  },
  {
    id: "wallet",
    labelKey: "nav.wallet",
    href: (locale) => `/${locale}/wallet`,
    isActive: (pathname, locale) => pathname.startsWith(`/${locale}/wallet`),
    Icon: WalletIcon,
  },
  {
    id: "account",
    labelKey: "nav.account",
    href: (locale) => `/${locale}/account`,
    isActive: (pathname, locale) => pathname.startsWith(`/${locale}/account`),
    Icon: AccountIcon,
  },
];

export function AppSidebar({ locale }: { locale: string }) {
  const t = useTranslations();
  const { user, signOut } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  return (
    <>
      {/* ========================================================= */}
      {/* DESKTOP SIDEBAR (Visible on medium & larger screens)      */}
      {/* ========================================================= */}
      <aside
        aria-label="Sidebar Navigation"
        className="hidden md:flex flex-col w-64 shrink-0 border-e border-border-subtle/70 bg-surface min-h-dvh sticky top-0 self-start p-4 z-30"
      >
        {/* Brand Header */}
        <div className="pb-5 pt-1 px-2 border-b border-border-subtle/50">
          <Link
            href={`/${locale}/deals`}
            className="group flex flex-col gap-0.5 focus:outline-none"
          >
            <div className="flex items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.svg" alt="" className="h-6 w-auto" aria-hidden />
              <span className="text-lg font-bold text-ink tracking-tight group-hover:text-accent transition-colors">
                {t("app.name")}
              </span>
            </div>
            <span className="text-xs text-ink-faint ps-9">
              {t("app.tagline")}
            </span>
          </Link>

          <div className="mt-3 ps-9">
            <span className="inline-block rounded-full bg-surface-muted px-2.5 py-0.5 text-[11px] font-medium text-ink-muted border border-border-subtle/40">
              {t("app.sandboxNotice")}
            </span>
          </div>
        </div>

        {/* Feature Navigation Links */}
        <nav className="flex-1 py-5 space-y-1.5" aria-label="Main Menu">
          {NAV_ITEMS.map(({ id, labelKey, href, isActive, Icon }) => {
            const active = isActive(pathname, locale);
            return (
              <Link
                key={id}
                href={href(locale)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
                  active
                    ? "bg-[#e7f5ef] text-[#1b8f63] font-semibold shadow-xs"
                    : "text-ink-muted hover:text-ink hover:bg-surface-muted",
                )}
              >
                <Icon
                  filled={active && id === "home"}
                  className={cn(
                    "size-5 shrink-0 transition-colors",
                    active ? "text-[#1b8f63]" : "text-ink-faint group-hover:text-ink",
                  )}
                />
                <span className="capitalize">{t(labelKey)}</span>
              </Link>
            );
          })}
        </nav>

        {/* User Session & Language Switcher (Footer) */}
        <div className="pt-4 border-t border-border-subtle/50 space-y-3">
          {user ? (
            <div className="flex items-center gap-3 px-2 py-1.5 rounded-lg bg-surface-muted/60">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent font-semibold text-xs uppercase">
                {user.email.slice(0, 2)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-ink">
                  {user.full_name || user.email}
                </p>
                <p className="text-[11px] font-medium text-ink-muted capitalize">
                  {user.role}
                </p>
              </div>
            </div>
          ) : null}

          {user ? (
            <div className="pt-1">
              <button
                type="button"
                onClick={() => {
                  signOut();
                  router.replace(`/${locale}/login`);
                }}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-medium text-ink-muted hover:text-status-attention hover:bg-status-attention-soft transition-colors border border-border-subtle/50"
              >
                <span>{t("nav.signOut")}</span>
              </button>
            </div>
          ) : null}
        </div>
      </aside>

      {/* ========================================================= */}
      {/* MOBILE BOTTOM NAVIGATION BAR                              */}
      {/* (Directly mirrors the tab layout in user's design image)  */}
      {/* ========================================================= */}
      <nav
        aria-label="Mobile Navigation"
        className="fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur-md border-t border-border-subtle/70 py-2 px-3 flex items-center justify-around md:hidden shadow-lg"
      >
        {NAV_ITEMS.map(({ id, labelKey, href, isActive, Icon }) => {
          const active = isActive(pathname, locale);
          return (
            <Link
              key={id}
              href={href(locale)}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex flex-col items-center justify-center gap-1 min-w-16 py-1 px-2 rounded-lg transition-colors focus:outline-none",
                active ? "text-[#1b8f63]" : "text-ink-faint hover:text-ink",
              )}
            >
              <Icon
                filled={active && id === "home"}
                className={cn(
                  "size-6 transition-colors",
                  active ? "text-[#1b8f63]" : "text-ink-faint",
                )}
              />
              <span
                className={cn(
                  "text-[11px] leading-tight",
                  active ? "font-semibold text-[#1b8f63]" : "font-normal text-ink-muted",
                )}
              >
                {t(labelKey)}
              </span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
