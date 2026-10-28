"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { MoneyAmount } from "@/components/deals/money-amount";
import { Button } from "@/components/ui/button";
import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { useCreateDeal } from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const CURRENCIES = ["USD", "EUR", "GBP"] as const;

const amountRule = z
  .string()
  .trim()
  .regex(/^\d+(\.\d{1,2})?$/, "format")
  .refine((value) => {
    const amount = Number(value);
    return amount >= 1 && amount <= 10000;
  }, "range");

/** Mirrors the backend's own limits, so the user hears about a problem
 * before a round trip rather than after one. A deal is either a single
 * payment or two-or-more milestones — the amount rules differ per mode. */
const schema = z
  .object({
    seller_email: z.string().email(),
    title: z.string().trim().min(1).max(200),
    description: z.string().trim().min(20).max(5000),
    currency: z.enum(CURRENCIES),
    mode: z.enum(["single", "milestones"]),
    amount: z.string().trim().optional(),
    // Items are kept lenient at the base level; the real per-mode rules run in
    // superRefine, so the two empty default milestone rows never block a
    // single-payment submit.
    milestones: z
      .array(
        z.object({
          title: z.string().trim().max(200),
          description: z.string().trim().max(5000).optional(),
          amount: z.string().trim().optional(),
        }),
      )
      .optional(),
  })
  .superRefine((value, ctx) => {
    if (value.mode === "single") {
      if (!amountRule.safeParse(value.amount ?? "").success) {
        ctx.addIssue({ code: "custom", path: ["amount"], message: "amount" });
      }
      return;
    }
    // Milestones mode: at least two, each with a title and a valid amount.
    const milestones = value.milestones ?? [];
    if (milestones.length < 2) {
      ctx.addIssue({ code: "custom", path: ["milestones"], message: "min" });
    }
    milestones.forEach((m, index) => {
      if (!m.title || m.title.trim().length === 0) {
        ctx.addIssue({ code: "custom", path: ["milestones", index, "title"], message: "required" });
      }
      if (!amountRule.safeParse(m.amount ?? "").success) {
        ctx.addIssue({ code: "custom", path: ["milestones", index, "amount"], message: "range" });
      }
    });
  });

type FormValues = z.infer<typeof schema>;

export default function NewDealPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const params = useSearchParams();
  const { user, isLoading } = useRequireSession(locale);
  const createDeal = useCreateDeal();
  const [failure, setFailure] = useState<string | null>(null);

  // Prefill from a marketplace offer (?seller=&title=&amount=&currency=&desc=).
  const prefillCurrency = params.get("currency");
  const prefill = {
    seller_email: params.get("seller") ?? "",
    title: params.get("title") ?? "",
    description: params.get("desc") ?? "",
    amount: params.get("amount") ?? "",
    currency:
      prefillCurrency && (CURRENCIES as readonly string[]).includes(prefillCurrency)
        ? (prefillCurrency as (typeof CURRENCIES)[number])
        : ("USD" as const),
  };

  const {
    register,
    handleSubmit,
    control,
    watch,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      seller_email: prefill.seller_email,
      title: prefill.title,
      description: prefill.description,
      currency: prefill.currency,
      mode: "single",
      amount: prefill.amount,
      milestones: [
        { title: "", description: "", amount: "" },
        { title: "", description: "", amount: "" },
      ],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "milestones" });
  const mode = watch("mode");
  const currency = watch("currency");
  const milestoneAmounts = watch("milestones");

  const total = (milestoneAmounts ?? []).reduce((sum, m) => {
    const value = Number(m?.amount);
    return sum + (Number.isFinite(value) ? value : 0);
  }, 0);

  if (isLoading || !user) {
    return <div className="h-64 animate-pulse rounded-card bg-surface" aria-busy="true" />;
  }

  const onSubmit = async (values: FormValues) => {
    setFailure(null);
    try {
      const base = {
        seller_email: values.seller_email,
        title: values.title,
        description: values.description,
        currency: values.currency,
      };
      const deal = await createDeal.mutateAsync(
        values.mode === "milestones"
          ? {
              ...base,
              milestones: (values.milestones ?? []).map((m) => ({
                title: m.title,
                description: m.description ?? "",
                amount: m.amount ?? "",
              })),
            }
          : { ...base, amount: values.amount },
      );
      router.replace(`/${locale}/deals/${deal.id}`);
    } catch (error) {
      if (error instanceof ApiError) {
        setFailure(error.code === "ai_error" ? t("create.aiUnavailable") : error.message);
      } else {
        setFailure(t("create.failed"));
      }
    }
  };

  const amountError = errors.amount ? t("validation.amountRange") : undefined;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Link href={`/${locale}/deals`} className="text-sm text-ink-muted hover:text-ink">
        ← {t("common.back")}
      </Link>

      <Card>
        <CardTitle>{t("create.title")}</CardTitle>
        <CardSubtitle>{t("create.subtitle")}</CardSubtitle>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <Field
            label={t("create.dealTitle")}
            error={errors.title ? t("validation.titleRequired") : undefined}
          >
            {(props) => (
              <Input {...props} {...register("title")} placeholder={t("create.titlePlaceholder")} />
            )}
          </Field>

          <Field
            label={t("create.sellerEmail")}
            error={errors.seller_email ? t("validation.emailInvalid") : undefined}
          >
            {(props) => (
              <Input {...props} {...register("seller_email")} type="email" inputMode="email" />
            )}
          </Field>

          <Field
            label={t("create.description")}
            hint={t("create.descriptionHint")}
            error={errors.description ? t("validation.descriptionShort") : undefined}
          >
            {(props) => (
              <Textarea
                {...props}
                {...register("description")}
                rows={4}
                placeholder={t("create.descriptionPlaceholder")}
              />
            )}
          </Field>

          {/* Payment structure: one payment, or milestone-based releases. */}
          <div className="space-y-2">
            <span className="text-sm font-medium text-ink">{t("create.structure")}</span>
            <div role="radiogroup" aria-label={t("create.structure")} className="grid grid-cols-2 gap-2">
              {(["single", "milestones"] as const).map((option) => {
                const selected = mode === option;
                return (
                  <button
                    key={option}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setValue("mode", option, { shouldValidate: false })}
                    className={cn(
                      "flex items-start gap-2.5 rounded-control border px-3 py-2.5 text-start text-sm transition-colors",
                      selected
                        ? "border-accent bg-accent-soft text-accent"
                        : "border-border-subtle bg-surface text-ink-muted hover:bg-surface-muted",
                    )}
                  >
                    {/* A radio dot, filled when selected, so the choice is unmistakable. */}
                    <span
                      aria-hidden
                      className={cn(
                        "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border",
                        selected ? "border-accent" : "border-border-subtle",
                      )}
                    >
                      {selected ? <span className="size-2 rounded-full bg-accent" /> : null}
                    </span>
                    <span>
                      <span className={cn("block font-medium", selected ? "text-accent" : "text-ink")}>
                        {option === "single" ? t("create.modeSingle") : t("create.modeMilestones")}
                      </span>
                      <span className="mt-0.5 block text-xs text-ink-faint">
                        {option === "single"
                          ? t("create.modeSingleHint")
                          : t("create.modeMilestonesHint")}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {mode === "single" ? (
            <div className="grid gap-4 sm:grid-cols-[2fr_1fr]">
              <Field label={t("create.amount")} error={amountError}>
                {(props) => (
                  <Input
                    {...props}
                    {...register("amount")}
                    inputMode="decimal"
                    placeholder="250.00"
                    className="tabular"
                  />
                )}
              </Field>

              <Field label={t("create.currency")}>
                {(props) => (
                  <Select {...props} {...register("currency")}>
                    {CURRENCIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-ink">{t("create.milestones")}</span>
                <Select
                  {...register("currency")}
                  aria-label={t("create.currency")}
                  className="h-9 w-24 py-0 text-sm"
                >
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </Select>
              </div>
              <p className="text-xs text-ink-faint">{t("create.milestonesHint")}</p>

              {errors.milestones && !Array.isArray(errors.milestones) ? (
                <p role="alert" className="text-sm text-status-attention">
                  {t("create.milestonesMin")}
                </p>
              ) : null}

              <ul className="space-y-3">
                {fields.map((field, index) => (
                  <li
                    key={field.id}
                    className="rounded-card border border-border-subtle/70 bg-surface-muted/40 p-4 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                        {t("create.milestone")} {index + 1}
                      </span>
                      {fields.length > 2 ? (
                        <button
                          type="button"
                          onClick={() => remove(index)}
                          className="text-xs text-ink-muted hover:text-status-attention"
                        >
                          {t("create.removeMilestone")}
                        </button>
                      ) : null}
                    </div>

                    <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
                      <Field
                        label={t("create.milestoneTitle")}
                        error={
                          errors.milestones?.[index]?.title
                            ? t("validation.titleRequired")
                            : undefined
                        }
                      >
                        {(props) => (
                          <Input
                            {...props}
                            {...register(`milestones.${index}.title` as const)}
                            placeholder={t("create.milestoneTitlePlaceholder")}
                          />
                        )}
                      </Field>
                      <Field
                        label={t("create.milestoneAmount")}
                        error={
                          errors.milestones?.[index]?.amount
                            ? t("validation.amountRange")
                            : undefined
                        }
                      >
                        {(props) => (
                          <Input
                            {...props}
                            {...register(`milestones.${index}.amount` as const)}
                            inputMode="decimal"
                            placeholder="150.00"
                            className="tabular"
                          />
                        )}
                      </Field>
                    </div>

                    <Field label={t("create.milestoneDesc")}>
                      {(props) => (
                        <Input
                          {...props}
                          {...register(`milestones.${index}.description` as const)}
                          placeholder={t("create.milestoneDescPlaceholder")}
                        />
                      )}
                    </Field>
                  </li>
                ))}
              </ul>

              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => append({ title: "", description: "", amount: "" })}
                  className="text-sm font-medium text-accent hover:text-accent-hover"
                >
                  + {t("create.addMilestone")}
                </button>
                <span className="flex items-baseline gap-2 text-sm text-ink-muted">
                  {t("create.total")}
                  <MoneyAmount amount={total.toFixed(2)} currency={currency} size="md" />
                </span>
              </div>
            </div>
          )}

          {failure ? (
            <p role="alert" className="text-sm text-status-attention">
              {failure}
            </p>
          ) : null}

          <Button type="submit" disabled={createDeal.isPending} size="lg">
            {createDeal.isPending ? (
              <>
                <Spinner label={t("create.submitting")} />
                {t("create.submitting")}
              </>
            ) : (
              t("create.submit")
            )}
          </Button>
        </form>
      </Card>
    </div>
  );
}
