"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { MoneyAmount } from "@/components/deals/money-amount";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/field";
import { useCatalogSearch } from "@/hooks/use-catalog";
import { useRequireSession } from "@/hooks/use-session";
import type { CatalogProduct } from "@/lib/types";

/** Build the new-deal link, pre-filled from a product. The buy link goes into
 * the description so the seller and the AI both see the original listing. */
function dealHref(locale: string, p: CatalogProduct): string {
  const desc =
    `Deliver the following product to the buyer: ${p.title}` +
    (p.brand ? ` by ${p.brand}` : "") +
    (p.buy_url ? `. Reference listing: ${p.buy_url}` : "") +
    (p.description ? `. ${p.description}` : "");
  const params = new URLSearchParams({
    title: p.title,
    desc,
    currency: p.currency || "USD",
  });
  if (p.price) params.set("amount", p.price);
  return `/${locale}/deals/new?${params.toString()}`;
}

export default function ShopPage() {
  const t = useTranslations("shop");
  const locale = useLocale();
  const { user, isLoading } = useRequireSession(locale);

  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const { data: products = [], isFetching, isError } = useCatalogSearch(query);

  if (isLoading || !user) {
    return <div className="h-64 animate-pulse rounded-card bg-surface" aria-busy="true" />;
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("title")}</h1>
        <p className="text-sm text-ink-muted">{t("subtitle")}</p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(draft.trim());
        }}
        className="flex gap-2"
        role="search"
      >
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("placeholder")}
          aria-label={t("searchLabel")}
          className="flex-1"
        />
        <Button type="submit" disabled={!draft.trim()}>
          {t("search")}
        </Button>
      </form>

      {!query ? (
        <Card className="p-8 text-center text-sm text-ink-muted">{t("empty")}</Card>
      ) : isFetching ? (
        <ProductGridSkeleton />
      ) : isError ? (
        <Card className="p-6 text-sm text-ink-muted">{t("failed")}</Card>
      ) : products.length === 0 ? (
        <Card className="p-8 text-center text-sm text-ink-muted">{t("noResults")}</Card>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => (
            <li key={p.id}>
              <Card className="flex h-full flex-col overflow-hidden p-0">
                <Link href={`/${locale}/shop/${encodeURIComponent(p.id)}`}>
                  <div className="aspect-[4/3] w-full overflow-hidden bg-surface-muted">
                    {p.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={p.image_url}
                        alt=""
                        className="h-full w-full object-contain p-2"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center text-ink-faint">
                        {t("noImage")}
                      </div>
                    )}
                  </div>
                </Link>
                <div className="flex flex-1 flex-col gap-2 p-4">
                  {p.brand ? (
                    <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                      {p.brand}
                    </span>
                  ) : null}
                  <Link href={`/${locale}/shop/${encodeURIComponent(p.id)}`} className="line-clamp-2 font-medium text-ink hover:text-accent">
                    {p.title}
                  </Link>
                  <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                    {p.price ? (
                      <MoneyAmount amount={p.price} currency={p.currency} className="font-semibold" />
                    ) : (
                      <span className="text-sm text-ink-faint">{t("noPrice")}</span>
                    )}
                    <div className="flex gap-1.5">
                      <Link
                        href={`/${locale}/shop/${encodeURIComponent(p.id)}`}
                        className="inline-flex h-9 items-center rounded-lg border border-border-subtle px-3 text-sm font-medium text-ink-muted transition-colors hover:bg-surface-muted"
                      >
                        {t("viewDetails")}
                      </Link>
                      <Link
                        href={dealHref(locale, p)}
                        className="inline-flex h-9 items-center rounded-lg bg-accent px-3 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
                      >
                        {t("startDeal")}
                      </Link>
                    </div>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-ink-faint">{t("poweredBy")}</p>
    </div>
  );
}

function ProductGridSkeleton() {
  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <li key={i} className="h-72 animate-pulse rounded-card bg-surface" aria-busy="true" />
      ))}
    </ul>
  );
}
