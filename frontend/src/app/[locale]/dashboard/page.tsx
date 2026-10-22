"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { DealsGrid } from "@/components/deals/deals-grid";
import { StatTile } from "@/components/deals/stat-tile";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useReviewerOverview } from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";

/**
 * The reviewer dashboard — an admin/audit overview (the SRS's optional
 * AG-Grid view), in the Behance escrow dashboard's stat-tiles + data-grid
 * layout, rendered in Waseet's navy identity.
 */
export default function DashboardPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { user, isLoading } = useRequireSession(locale);

  // Only a reviewer has an operations view; a party is sent to their deals.
  useEffect(() => {
    if (!isLoading && user && user.role !== "reviewer") {
      router.replace(`/${locale}/deals`);
    }
  }, [isLoading, user, router, locale]);

  const { data, isPending, isError, error, refetch } = useReviewerOverview();

  if (isLoading || !user || user.role !== "reviewer") {
    return <DashboardSkeleton />;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink">{t("dashboard.title")}</h1>
        <Link href={`/${locale}/deals`} className="text-sm text-ink-muted hover:text-ink">
          {t("dashboard.reviewQueue")} →
        </Link>
      </div>

      {isPending ? (
        <DashboardSkeleton bare />
      ) : isError ? (
        <Card className="space-y-3">
          <p className="text-sm font-medium text-ink">{t("dashboard.loadFailed")}</p>
          <p className="text-sm text-ink-muted">{error.message}</p>
          <Button variant="secondary" onClick={() => void refetch()}>
            {t("common.retry")}
          </Button>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile
              tile={data.held_in_escrow}
              label={t("dashboard.heldInEscrow")}
              glyph="●"
              tone="accent"
            />
            <StatTile
              tile={data.open_disputes}
              label={t("dashboard.openDisputes")}
              glyph="!"
              tone="attention"
            />
            <StatTile
              tile={data.released}
              label={t("dashboard.released")}
              glyph="✓"
              tone="paid"
            />
            <StatTile
              tile={data.refunded}
              label={t("dashboard.refunded")}
              glyph="↩"
              tone="returned"
            />
          </div>

          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-ink">{t("dashboard.allDeals")}</h2>
            {data.deals.length === 0 ? (
              <Card>
                <p className="text-sm text-ink-muted">{t("dashboard.noDeals")}</p>
              </Card>
            ) : (
              <DealsGrid deals={data.deals} locale={locale} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

function DashboardSkeleton({ bare = false }: { bare?: boolean }) {
  return (
    <div className={bare ? "space-y-6" : "mx-auto max-w-6xl space-y-6"} aria-busy="true">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-card border border-border-subtle/60 bg-surface"
          />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-card border border-border-subtle/60 bg-surface" />
    </div>
  );
}
