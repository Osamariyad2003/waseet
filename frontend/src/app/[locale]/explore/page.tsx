"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { MoneyAmount } from "@/components/deals/money-amount";
import { Button } from "@/components/ui/button";
import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { useCreateOffer, useDelistOffer, useMyOffers, useOffers } from "@/hooks/use-offers";
import { useRequireSession } from "@/hooks/use-session";
import { ApiError } from "@/lib/api";
import type { Offer } from "@/lib/types";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  "design",
  "development",
  "writing",
  "marketing",
  "consulting",
  "other",
] as const;
const CURRENCIES = ["USD", "EUR", "GBP"] as const;

export default function MarketplacePage() {
  const t = useTranslations();
  const locale = useLocale();
  const { user, isLoading } = useRequireSession(locale);

  const { data: offers = [], isPending } = useOffers();
  const [category, setCategory] = useState<string>("");

  if (isLoading || !user) {
    return <div className="h-64 animate-pulse rounded-card bg-surface" aria-busy="true" />;
  }

  const isSeller = user.role === "seller";
  const filtered = category ? offers.filter((o) => o.category === category) : offers;

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">{t("market.title")}</h1>
          <p className="mt-1 text-sm text-ink-muted">{t("market.subtitle")}</p>
        </div>
        <Link
          href={`/${locale}`}
          className="text-sm text-ink-muted underline-offset-2 hover:text-ink hover:underline"
        >
          {t("market.howItWorks")}
        </Link>
      </header>

      {/* A seller manages their own listings. */}
      {isSeller ? <SellerPanel /> : null}

      {/* Category filter. */}
      <div className="flex flex-wrap gap-2">
        <Chip active={category === ""} onClick={() => setCategory("")}>
          {t("market.all")}
        </Chip>
        {CATEGORIES.map((c) => (
          <Chip key={c} active={category === c} onClick={() => setCategory(c)}>
            {t(`market.categories.${c}`)}
          </Chip>
        ))}
      </div>

      {/* The marketplace grid. */}
      {isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-card bg-surface" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-sm text-ink-muted">{t("market.empty")}</p>
        </Card>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((offer) => (
            <li key={offer.id}>
              <OfferCard offer={offer} canStart={user.role === "buyer"} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function OfferCard({ offer, canStart }: { offer: Offer; canStart: boolean }) {
  const t = useTranslations();
  const locale = useLocale();

  const startHref =
    `/${locale}/deals/new?seller=${encodeURIComponent(offer.seller.email)}` +
    `&title=${encodeURIComponent(offer.title)}&amount=${encodeURIComponent(offer.amount)}` +
    `&currency=${encodeURIComponent(offer.currency)}&desc=${encodeURIComponent(offer.description)}`;

  return (
    <Card className="flex h-full flex-col gap-3 p-5">
      <div className="flex items-start justify-between gap-3">
        <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium capitalize text-accent">
          {CATEGORIES.includes(offer.category as (typeof CATEGORIES)[number])
            ? t(`market.categories.${offer.category}` as `market.categories.${(typeof CATEGORIES)[number]}`)
            : offer.category}
        </span>
        <MoneyAmount amount={offer.amount} currency={offer.currency} size="md" />
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="font-semibold text-ink">{offer.title}</h3>
        {offer.description ? (
          <p className="mt-1 line-clamp-3 text-sm text-ink-muted">{offer.description}</p>
        ) : null}
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-border-subtle/60 pt-3">
        <span className="truncate text-xs text-ink-faint">
          {offer.seller.full_name || offer.seller.email}
        </span>
        {canStart ? (
          <Link
            href={startHref}
            className="inline-flex h-9 items-center rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
          >
            {t("market.startDeal")}
          </Link>
        ) : null}
      </div>
    </Card>
  );
}

function SellerPanel() {
  const t = useTranslations();
  const { data: mine = [] } = useMyOffers();
  const createOffer = useCreateOffer();
  const delist = useDelistOffer();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "design",
    amount: "",
    currency: "USD",
  });
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (!form.title.trim() || !/^\d+(\.\d{1,2})?$/.test(form.amount)) {
      setError(t("market.formError"));
      return;
    }
    try {
      await createOffer.mutateAsync(form);
      setForm({ title: "", description: "", category: "design", amount: "", currency: "USD" });
      setOpen(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("market.formError"));
    }
  };

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <CardTitle>{t("market.yourOffers")}</CardTitle>
          <CardSubtitle>{t("market.yourOffersHint")}</CardSubtitle>
        </div>
        <Button variant={open ? "secondary" : "primary"} onClick={() => setOpen((v) => !v)}>
          {open ? t("common.cancel") : t("market.postOffer")}
        </Button>
      </div>

      {open ? (
        <div className="space-y-3 rounded-card border border-border-subtle/70 bg-surface-muted/40 p-4">
          <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
            <Field label={t("market.offerTitle")}>
              {(p) => (
                <Input
                  {...p}
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder={t("market.offerTitlePlaceholder")}
                />
              )}
            </Field>
            <Field label={t("market.category")}>
              {(p) => (
                <Select
                  {...p}
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {t(`market.categories.${c}`)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <Field label={t("market.offerDesc")}>
            {(p) => (
              <Textarea
                {...p}
                rows={2}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder={t("market.offerDescPlaceholder")}
              />
            )}
          </Field>
          <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
            <Field label={t("market.price")}>
              {(p) => (
                <Input
                  {...p}
                  inputMode="decimal"
                  className="tabular"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  placeholder="250.00"
                />
              )}
            </Field>
            <Field label={t("create.currency")}>
              {(p) => (
                <Select
                  {...p}
                  value={form.currency}
                  onChange={(e) => setForm({ ...form, currency: e.target.value })}
                >
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          {error ? (
            <p role="alert" className="text-sm text-status-attention">
              {error}
            </p>
          ) : null}
          <Button onClick={submit} disabled={createOffer.isPending}>
            {createOffer.isPending ? (
              <>
                <Spinner label={t("market.posting")} />
                {t("market.posting")}
              </>
            ) : (
              t("market.publish")
            )}
          </Button>
        </div>
      ) : null}

      {mine.length > 0 ? (
        <ul className="divide-y divide-border-subtle/60">
          {mine.map((offer) => (
            <li key={offer.id} className="flex items-center gap-3 py-2.5">
              <span className="min-w-0 flex-1 truncate text-sm text-ink">{offer.title}</span>
              <MoneyAmount amount={offer.amount} currency={offer.currency} size="sm" />
              {offer.active ? (
                <button
                  type="button"
                  onClick={() => delist.mutate(offer.id)}
                  className="text-xs text-ink-muted hover:text-status-attention"
                >
                  {t("market.delist")}
                </button>
              ) : (
                <span className="text-xs text-ink-faint">{t("market.delisted")}</span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-3 py-1 text-sm font-medium capitalize transition-colors",
        active
          ? "border-accent bg-accent text-white"
          : "border-border-subtle bg-surface text-ink-muted hover:bg-surface-muted",
      )}
    >
      {children}
    </button>
  );
}
