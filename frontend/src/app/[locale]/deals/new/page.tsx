"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { useCreateDeal } from "@/hooks/use-deals";
import { useRequireSession } from "@/hooks/use-session";
import { ApiError } from "@/lib/api";

const CURRENCIES = ["USD", "EUR", "GBP"] as const;

/** Mirrors the backend's own limits, so the user hears about a problem
 * before a round trip rather than after one. */
const schema = z.object({
  seller_email: z.string().email(),
  title: z.string().trim().min(1).max(200),
  description: z.string().trim().min(20).max(5000),
  amount: z
    .string()
    .trim()
    .regex(/^\d+(\.\d{1,2})?$/, "format")
    .refine((value) => {
      const amount = Number(value);
      return amount >= 1 && amount <= 10000;
    }, "range"),
  currency: z.enum(CURRENCIES),
});

type FormValues = z.infer<typeof schema>;

export default function NewDealPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { user, isLoading } = useRequireSession(locale);
  const createDeal = useCreateDeal();
  const [failure, setFailure] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { seller_email: "", title: "", description: "", amount: "", currency: "USD" },
  });

  if (isLoading || !user) {
    return <div className="h-64 animate-pulse rounded-card bg-surface" aria-busy="true" />;
  }

  const onSubmit = async (values: FormValues) => {
    setFailure(null);
    try {
      const deal = await createDeal.mutateAsync(values);
      router.replace(`/${locale}/deals/${deal.id}`);
    } catch (error) {
      if (error instanceof ApiError) {
        // The criteria agent being down is its own message: nothing was
        // created, so "try again" is genuinely the right advice.
        setFailure(error.code === "ai_error" ? t("create.aiUnavailable") : error.message);
      } else {
        setFailure(t("create.failed"));
      }
    }
  };

  const amountError = errors.amount
    ? errors.amount.message === "range"
      ? t("validation.amountRange")
      : t("validation.amountInvalid")
    : undefined;

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
              <Input
                {...props}
                {...register("title")}
                placeholder={t("create.titlePlaceholder")}
              />
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
                  {CURRENCIES.map((currency) => (
                    <option key={currency} value={currency}>
                      {currency}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>

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
