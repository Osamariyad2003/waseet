"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { useSession } from "@/hooks/use-session";

export function AppHeader({ locale }: { locale: string }) {
  const t = useTranslations();
  const { user, signOut } = useSession();
  const router = useRouter();

  return (
    <header className="bg-accent text-white">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
        <Link
          href={`/${locale}/dashboard`}
          className="flex items-baseline gap-2 font-semibold text-white"
        >
          {t("app.name")}
          <span className="rounded bg-white/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
            {t("app.adminBadge")}
          </span>
        </Link>

        <div className="ms-auto flex items-center gap-3">
          <span className="hidden rounded-full bg-white/15 px-2.5 py-1 text-xs font-medium text-white sm:inline">
            {t("app.sandboxNotice")}
          </span>

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
