"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { MoneyAmount } from "@/components/deals/money-amount";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { usePriceHistory, useProduct, useSimilarProducts } from "@/hooks/use-catalog";
import { useRequireSession } from "@/hooks/use-session";
import type { CatalogProduct, PriceHistoryData, ProductDetail, ProductOffer } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function ProductDetailPage() {
  const t = useTranslations("shop");
  const locale = useLocale();
  const params = useParams<{ productId: string }>();
  const productId = decodeURIComponent(params.productId);

  const { user, isLoading: sessionLoading } = useRequireSession(locale);
  const { data: product, isPending, isError } = useProduct(productId);
  const { data: similar = [] } = useSimilarProducts(productId);
  const { data: priceHistory } = usePriceHistory(productId);

  if (sessionLoading || !user) {
    return <div className="h-64 animate-pulse rounded-card bg-surface" aria-busy="true" />;
  }

  if (isPending) {
    return (
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="h-96 animate-pulse rounded-card bg-surface" aria-busy="true" />
      </div>
    );
  }

  if (isError || !product) {
    return (
      <div className="mx-auto max-w-5xl space-y-4">
        <Link href={`/${locale}/shop`} className="text-sm text-accent hover:underline">
          {t("backToShop")}
        </Link>
        <Card className="p-8 text-center text-ink-muted">Product not found.</Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <Link href={`/${locale}/shop`} className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
        <span aria-hidden>&larr;</span> {t("backToShop")}
      </Link>

      {/* Main product section */}
      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <ImageGallery images={product.images} title={product.title} />
        <ProductInfo product={product} locale={locale} />
      </div>

      {/* Offers comparison */}
      {product.offers.length > 0 && (
        <OffersSection offers={product.offers} />
      )}

      {/* Price history */}
      {priceHistory && priceHistory.history.length > 0 && (
        <PriceHistorySection history={priceHistory} />
      )}

      {/* Similar products */}
      {similar.length > 0 && (
        <SimilarSection products={similar} locale={locale} />
      )}

      <p className="text-xs text-ink-faint">{t("poweredBy")}</p>
    </div>
  );
}

/* ---------- Image gallery ---------- */

function ImageGallery({ images, title }: { images: ProductDetail["images"]; title: string }) {
  const [selected, setSelected] = useState(0);
  const current = images[selected];

  if (images.length === 0) {
    return (
      <div className="flex aspect-square items-center justify-center rounded-xl bg-surface-muted text-ink-faint">
        No image
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-xl bg-surface-muted">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={current?.cleaned_url || current?.url}
          alt={current?.alt_text || title}
          className="aspect-square w-full object-contain p-4"
        />
      </div>
      {images.length > 1 && (
        <div className="flex gap-2 overflow-x-auto">
          {images.map((img, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setSelected(i)}
              className={cn(
                "h-16 w-16 shrink-0 overflow-hidden rounded-lg border-2 bg-surface-muted transition-colors",
                i === selected ? "border-accent" : "border-transparent",
              )}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.cleaned_url || img.url}
                alt=""
                className="h-full w-full object-contain p-1"
                loading="lazy"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- Product info ---------- */

function ProductInfo({ product, locale }: { product: ProductDetail; locale: string }) {
  const t = useTranslations("shop");

  const dealHref = () => {
    const desc =
      `Deliver the following product to the buyer: ${product.title}` +
      (product.brand ? ` by ${product.brand}` : "") +
      (product.description ? `. ${product.description}` : "");
    const params = new URLSearchParams({
      title: product.title,
      desc,
      currency: product.currency || "USD",
    });
    if (product.price) params.set("amount", product.price);
    return `/${locale}/deals/new?${params.toString()}`;
  };

  return (
    <div className="space-y-5">
      {product.brand && (
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
          {product.brand}
        </span>
      )}

      <h1 className="text-2xl font-bold tracking-tight text-ink">{product.title}</h1>

      {product.category && (
        <div className="flex items-center gap-2 text-sm text-ink-muted">
          <span className="font-medium">{t("category")}:</span> {product.category}
        </div>
      )}

      <div className="flex items-baseline gap-3">
        {product.price ? (
          <MoneyAmount amount={product.price} currency={product.currency} className="text-2xl font-bold" />
        ) : (
          <span className="text-lg text-ink-faint">{t("noPrice")}</span>
        )}
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
            product.available
              ? "bg-status-paid-soft text-status-paid"
              : "bg-surface-muted text-ink-faint",
          )}
        >
          {product.available ? t("inStock") : t("outOfStock")}
        </span>
      </div>

      {product.description && (
        <p className="text-sm leading-relaxed text-ink-muted">{product.description}</p>
      )}

      {product.key_features.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
            {t("keyFeatures")}
          </h3>
          <ul className="list-disc space-y-1 ps-5 text-sm text-ink-muted">
            {product.key_features.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {product.materials.length > 0 && (
        <div className="flex items-center gap-2 text-sm text-ink-muted">
          <span className="font-medium">{t("materials")}:</span>
          {product.materials.join(", ")}
        </div>
      )}

      <Link
        href={dealHref()}
        className="inline-flex h-11 items-center rounded-lg bg-accent px-6 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
      >
        {t("startDeal")}
      </Link>
    </div>
  );
}

/* ---------- Offers comparison ---------- */

function OffersSection({ offers }: { offers: ProductOffer[] }) {
  const t = useTranslations("shop");

  return (
    <Card className="space-y-4 p-5">
      <h2 className="text-lg font-semibold text-ink">{t("offers")}</h2>
      <div className="divide-y divide-border-subtle">
        {offers.map((offer, i) => (
          <div key={i} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-ink">{offer.domain}</span>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  offer.available
                    ? "bg-status-paid-soft text-status-paid"
                    : "bg-surface-muted text-ink-faint",
                )}
              >
                {offer.available ? t("inStock") : t("outOfStock")}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-end">
                {offer.price && (
                  <MoneyAmount amount={offer.price} currency={offer.currency} className="font-semibold" />
                )}
                {offer.compare_at_price && (
                  <span className="ms-2 text-xs text-ink-faint line-through">
                    <MoneyAmount amount={offer.compare_at_price} currency={offer.currency} />
                  </span>
                )}
              </div>
              {offer.url && (
                <a
                  href={offer.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-8 items-center rounded-md border border-border-subtle px-3 text-xs font-medium text-accent transition-colors hover:bg-surface-muted"
                >
                  {t("buyFrom", { domain: offer.domain })}
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ---------- Price history ---------- */

function PriceHistorySection({ history }: { history: PriceHistoryData }) {
  const t = useTranslations("shop");

  const statusLabel =
    history.current_status === "low" ? t("priceLow")
    : history.current_status === "high" ? t("priceHigh")
    : t("priceTypical");

  const statusColor =
    history.current_status === "low" ? "text-status-paid"
    : history.current_status === "high" ? "text-status-error"
    : "text-ink-muted";

  const prices = history.history.map((p) => p.price);
  const minY = Math.min(...prices);
  const maxY = Math.max(...prices);
  const rangeY = maxY - minY || 1;

  const chartWidth = 600;
  const chartHeight = 120;
  const points = history.history.map((p, i) => {
    const x = (i / Math.max(history.history.length - 1, 1)) * chartWidth;
    const y = chartHeight - ((p.price - minY) / rangeY) * (chartHeight - 10) - 5;
    return `${x},${y}`;
  });
  const polyline = points.join(" ");

  return (
    <Card className="space-y-4 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">{t("priceHistory")}</h2>
        <span className={cn("text-sm font-medium", statusColor)}>{statusLabel}</span>
      </div>

      {/* Mini chart */}
      <div className="overflow-hidden rounded-lg bg-surface-muted p-4">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="h-28 w-full"
          preserveAspectRatio="none"
        >
          <polyline
            points={polyline}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </svg>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label={t("currentPrice")} value={history.current_price} currency={history.history[0]?.currency || "USD"} />
        <StatCard label={t("lowestPrice")} value={history.min_price} currency={history.history[0]?.currency || "USD"} highlight />
        <StatCard label={t("highestPrice")} value={history.max_price} currency={history.history[0]?.currency || "USD"} />
        <StatCard label={t("averagePrice")} value={history.mean_price} currency={history.history[0]?.currency || "USD"} />
      </div>
    </Card>
  );
}

function StatCard({ label, value, currency, highlight }: { label: string; value: number | null; currency: string; highlight?: boolean }) {
  return (
    <div className="rounded-lg bg-surface-muted px-3 py-2.5 text-center">
      <p className="text-xs text-ink-faint">{label}</p>
      {value != null ? (
        <p className={cn("text-sm font-semibold", highlight ? "text-status-paid" : "text-ink")}>
          {currency === "USD" ? "$" : currency}{value.toFixed(2)}
        </p>
      ) : (
        <p className="text-sm text-ink-faint">—</p>
      )}
    </div>
  );
}

/* ---------- Similar products ---------- */

function SimilarSection({ products, locale }: { products: CatalogProduct[]; locale: string }) {
  const t = useTranslations("shop");

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-ink">{t("similarProducts")}</h2>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {products.slice(0, 8).map((p) => (
          <li key={p.id}>
            <Link href={`/${locale}/shop/${encodeURIComponent(p.id)}`}>
              <Card className="flex h-full flex-col overflow-hidden p-0 transition-shadow hover:shadow-md">
                <div className="aspect-square w-full overflow-hidden bg-surface-muted">
                  {p.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={p.image_url}
                      alt=""
                      className="h-full w-full object-contain p-2"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-xs text-ink-faint">
                      {t("noImage")}
                    </div>
                  )}
                </div>
                <div className="flex flex-1 flex-col gap-1 p-3">
                  {p.brand && (
                    <span className="text-[10px] font-medium uppercase tracking-wide text-ink-faint">
                      {p.brand}
                    </span>
                  )}
                  <p className="line-clamp-2 text-sm font-medium text-ink">{p.title}</p>
                  {p.price && (
                    <MoneyAmount amount={p.price} currency={p.currency} className="text-sm font-semibold" />
                  )}
                </div>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
