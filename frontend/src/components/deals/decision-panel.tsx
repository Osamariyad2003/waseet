"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { MoneyAmount } from "@/components/deals/money-amount";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import type { MediationRecommendation, SettlementAction } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACTIONS: SettlementAction[] = ["release", "refund", "split"];

interface DecisionPanelProps {
  dealAmount: string;
  currency: string;
  recommendation?: MediationRecommendation;
  isLoadingRecommendation?: boolean;
  recommendationError?: string;
  onSubmit: (values: {
    action: SettlementAction;
    reasoning: string;
    seller_amount?: string | null;
  }) => Promise<void>;
  isSubmitting?: boolean;
  error?: string;
}

/**
 * The reviewer's decision panel — the human in the loop.
 *
 * The AI's recommendation is shown first and labelled as advisory, but it
 * does not preselect the decision: a reviewer who only ever clicks the
 * recommendation is not a human in the loop, they are a rubber stamp. The
 * reasoning field is required because every settlement has to be backed by
 * stored, readable reasoning — the backend rejects an empty one too.
 */
export function DecisionPanel({
  dealAmount,
  currency,
  recommendation,
  isLoadingRecommendation,
  recommendationError,
  onSubmit,
  isSubmitting,
  error,
}: DecisionPanelProps) {
  const t = useTranslations();
  const max = Number(dealAmount);

  const schema = z
    .object({
      action: z.enum(["release", "refund", "split"]),
      reasoning: z.string().trim().min(1),
      seller_amount: z.string().trim().optional(),
    })
    .refine(
      (values) => {
        if (values.action !== "split") return true;
        const amount = Number(values.seller_amount);
        return Number.isFinite(amount) && amount > 0 && amount < max;
      },
      { path: ["seller_amount"], message: "range" },
    );

  type FormValues = z.infer<typeof schema>;

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { reasoning: "", seller_amount: "" },
  });

  const action = watch("action");

  return (
    <div className="space-y-5">
      {/* The recommendation, clearly marked as advice. */}
      <section
        aria-labelledby="recommendation-heading"
        className="rounded-lg border border-border-subtle bg-surface-muted p-4"
      >
        <h3
          id="recommendation-heading"
          className="text-xs font-medium uppercase tracking-wide text-ink-faint"
        >
          {t("dispute.recommendation")}
        </h3>

        {isLoadingRecommendation ? (
          <p className="mt-2 flex items-center gap-2 text-sm text-ink-muted">
            <Spinner label={t("dispute.recommendationLoading")} />
            {t("dispute.recommendationLoading")}
          </p>
        ) : recommendationError ? (
          <p className="mt-2 text-sm text-status-returned">{recommendationError}</p>
        ) : recommendation ? (
          <>
            <p className="mt-1 text-base font-semibold text-ink">
              {t(`dispute.actions.${recommendation.recommendation}`)}
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
              {recommendation.reasoning}
            </p>
            {recommendation.suggested_seller_amount ? (
              <p className="mt-2 text-sm text-ink-muted">
                {t("dispute.suggestedSplit")}:{" "}
                <MoneyAmount
                  amount={recommendation.suggested_seller_amount}
                  currency={currency}
                  size="sm"
                  className="inline-flex align-baseline"
                />
              </p>
            ) : null}
            <p className="mt-3 text-xs leading-relaxed text-ink-faint">
              {t("dispute.advisory")}
            </p>
          </>
        ) : null}
      </section>

      <form
        onSubmit={handleSubmit(async (values) =>
          onSubmit({
            action: values.action,
            reasoning: values.reasoning,
            seller_amount: values.action === "split" ? values.seller_amount : null,
          }),
        )}
        className="space-y-4"
        noValidate
      >
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-ink">{t("dispute.decision")}</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {ACTIONS.map((option) => (
              <label
                key={option}
                className={cn(
                  "cursor-pointer rounded-lg border p-3 text-sm transition-colors",
                  action === option
                    ? "border-accent bg-accent-soft"
                    : "border-border-subtle bg-surface hover:bg-surface-muted",
                )}
              >
                <span className="flex items-center gap-2">
                  <input
                    type="radio"
                    value={option}
                    {...register("action")}
                    className="size-4 accent-accent"
                  />
                  <span className="font-medium text-ink">
                    {t(`dispute.actions.${option}`)}
                  </span>
                </span>
                <span className="mt-1 block ps-6 text-xs leading-relaxed text-ink-muted">
                  {t(`dispute.actionHints.${option}`)}
                </span>
              </label>
            ))}
          </div>
          {errors.action ? (
            <p role="alert" className="text-sm text-status-attention">
              {t("common.required")}
            </p>
          ) : null}
        </fieldset>

        {action === "split" ? (
          <Field
            label={t("dispute.sellerAmount")}
            hint={t("dispute.sellerAmountHint", { amount: `${dealAmount} ${currency}` })}
            error={errors.seller_amount ? t("validation.sellerAmountRange") : undefined}
          >
            {(props) => (
              <Input
                {...props}
                {...register("seller_amount")}
                inputMode="decimal"
                placeholder="100.00"
              />
            )}
          </Field>
        ) : null}

        <Field
          label={t("dispute.reasoning")}
          hint={t("dispute.reasoningHint")}
          error={errors.reasoning ? t("validation.reasonRequired") : undefined}
        >
          {(props) => <Textarea {...props} {...register("reasoning")} rows={4} />}
        </Field>

        {error ? (
          <p role="alert" className="text-sm text-status-attention">
            {error}
          </p>
        ) : null}

        <Button type="submit" disabled={isSubmitting || !action} size="lg">
          {isSubmitting ? (
            <>
              <Spinner label={t("dispute.submitting")} />
              {t("dispute.submitting")}
            </>
          ) : (
            t("dispute.submit")
          )}
        </Button>
      </form>
    </div>
  );
}
