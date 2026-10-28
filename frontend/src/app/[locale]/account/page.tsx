"use client";

import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";

import { AccountIcon } from "@/components/sidebar/sidebar-icons";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useRequireSession, useSession } from "@/hooks/use-session";
import { cn } from "@/lib/utils";

export default function AccountPage() {
  const t = useTranslations("account");
  const locale = useLocale();
  const router = useRouter();
  const { user, isLoading } = useRequireSession(locale);
  const { signOut } = useSession();

  if (isLoading || !user) {
    return (
      <div className="mx-auto max-w-xl space-y-4">
        <div className="h-10 w-48 rounded bg-surface-muted animate-pulse" />
        <div className="h-64 rounded-card bg-surface-muted animate-pulse" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-ink">
          {t("title")}
        </h1>
      </div>

      {/* User Information Card */}
      <Card className="p-6 space-y-5">
        <div className="flex items-center gap-4">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent font-bold text-lg uppercase">
            {user.email.slice(0, 2)}
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold text-ink truncate">
              {user.full_name || user.email}
            </h2>
            <p className="text-sm text-ink-muted truncate">{user.email}</p>
          </div>
          <span className="rounded-full bg-accent-soft text-accent px-3 py-1 text-xs font-semibold capitalize">
            {t(`roles.${user.role}`)}
          </span>
        </div>

        <div className="pt-4 border-t border-border-subtle/50 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-ink-muted">{t("roleLabel")}</span>
            <span className="font-medium text-ink capitalize">
              {t(`roles.${user.role}`)}
            </span>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-ink-muted">Account ID</span>
            <span className="font-mono text-xs text-ink-faint truncate max-w-[200px]">
              {user.id}
            </span>
          </div>
        </div>
      </Card>

      {/* Preferences Card: Language & Sandbox */}
      <Card className="p-6 space-y-5">
        <div className="flex items-center justify-between text-sm">
          <span className="font-semibold text-ink">{t("language")}</span>
          <span className="text-sm font-medium text-ink-muted bg-surface-muted px-2.5 py-1 rounded-md border border-border-subtle/50">
            English
          </span>
        </div>

        {/* Sandbox Notice Banner */}
        <div className="rounded-lg bg-surface-muted/80 p-3.5 border border-border-subtle/60 flex items-start gap-3">
          <span className="text-base leading-none pt-0.5">ℹ️</span>
          <p className="text-xs text-ink-muted leading-relaxed">{t("sandbox")}</p>
        </div>
      </Card>

      {/* Actions */}
      <Card className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-ink text-sm">{t("signOut")}</p>
            <p className="text-xs text-ink-faint">End your current session</p>
          </div>
          <Button
            variant="secondary"
            onClick={() => {
              signOut();
              router.replace(`/${locale}/login`);
            }}
            className="text-status-attention hover:text-status-attention hover:border-status-attention/40"
          >
            {t("signOut")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
