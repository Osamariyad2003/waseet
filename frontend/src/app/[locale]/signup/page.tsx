"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardSubtitle, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { useSession } from "@/hooks/use-session";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const schema = z
  .object({
    full_name: z.string().trim().min(1, "Full name is required").max(200),
    email: z.string().trim().email(),
    role: z.enum(["buyer", "seller"]),
    paypal_account_ref: z
      .string()
      .trim()
      .email()
      .optional()
      .or(z.literal("")),
    password: z.string().min(8, "Password must be at least 8 characters").max(256),
    confirmPassword: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type FormValues = z.infer<typeof schema>;

export default function SignupPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { signUp, user } = useSession();
  const [failure, setFailure] = useState<string | null>(null);

  // If already signed in, navigate straight to deals
  useEffect(() => {
    if (user) router.replace(`/${locale}/deals`);
  }, [user, router, locale]);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: "",
      email: "",
      role: "buyer",
      paypal_account_ref: "",
      password: "",
      confirmPassword: "",
    },
  });

  const selectedRole = watch("role");

  const onSubmit = async (values: FormValues) => {
    setFailure(null);
    try {
      await signUp({
        email: values.email,
        password: values.password,
        full_name: values.full_name,
        role: values.role,
        paypal_account_ref: values.paypal_account_ref ? values.paypal_account_ref : undefined,
      });
      router.replace(`/${locale}/deals`);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 409 || error.code === "conflict") {
          setFailure(t("signup.conflict"));
        } else if (error.code === "network_error") {
          setFailure(t("signup.unreachable"));
        } else {
          setFailure(error.message || t("signup.failed"));
        }
      } else {
        setFailure(t("signup.failed"));
      }
    }
  };

  return (
    <div className="mx-auto w-full max-w-md">
      <Card>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.svg" alt="Waseet" className="mx-auto mb-3 h-12 w-auto" />
        <CardTitle className="text-center text-xl">{t("signup.title")}</CardTitle>
        <CardSubtitle className="text-center text-xs sm:text-sm">
          {t("signup.subtitle")}
        </CardSubtitle>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          {/* Full Name */}
          <Field
            label={t("signup.fullName")}
            error={errors.full_name ? t("common.required") : undefined}
          >
            {(props) => (
              <Input
                {...props}
                {...register("full_name")}
                type="text"
                autoComplete="name"
                placeholder={t("signup.fullNamePlaceholder")}
                autoFocus
              />
            )}
          </Field>

          {/* Email */}
          <Field
            label={t("signup.email")}
            error={errors.email ? t("validation.emailInvalid") : undefined}
          >
            {(props) => (
              <Input
                {...props}
                {...register("email")}
                type="email"
                autoComplete="email"
                placeholder="name@example.com"
              />
            )}
          </Field>

          {/* Role Selection */}
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-ink">
              {t("signup.role")}
            </label>
            <div className="grid grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => setValue("role", "buyer")}
                className={cn(
                  "flex flex-col items-start gap-1 p-3 rounded-lg border text-start transition-all",
                  selectedRole === "buyer"
                    ? "border-accent bg-accent/5 ring-1 ring-accent"
                    : "border-border-subtle bg-surface hover:border-border-subtle/80 hover:bg-surface-muted/40",
                )}
              >
                <div className="flex items-center gap-1.5 font-semibold text-sm text-ink">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className="h-4 w-4 text-accent"
                  >
                    <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" />
                    <path d="M3 6h18" />
                    <path d="M16 10a4 4 0 0 1-8 0" />
                  </svg>
                  <span>{t("signup.roleBuyer")}</span>
                </div>
                <span className="text-[11px] leading-tight text-ink-muted">
                  {t("signup.roleBuyerDesc")}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setValue("role", "seller")}
                className={cn(
                  "flex flex-col items-start gap-1 p-3 rounded-lg border text-start transition-all",
                  selectedRole === "seller"
                    ? "border-accent bg-accent/5 ring-1 ring-accent"
                    : "border-border-subtle bg-surface hover:border-border-subtle/80 hover:bg-surface-muted/40",
                )}
              >
                <div className="flex items-center gap-1.5 font-semibold text-sm text-ink">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className="h-4 w-4 text-accent"
                  >
                    <path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7" />
                    <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
                    <path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4" />
                    <path d="M2 7h20" />
                  </svg>
                  <span>{t("signup.roleSeller")}</span>
                </div>
                <span className="text-[11px] leading-tight text-ink-muted">
                  {t("signup.roleSellerDesc")}
                </span>
              </button>
            </div>
          </div>

          {/* PayPal Sandbox Email (Optional) */}
          <Field
            label={t("signup.paypalRef")}
            hint={t("signup.paypalRefHint")}
            error={errors.paypal_account_ref ? t("validation.emailInvalid") : undefined}
          >
            {(props) => (
              <Input
                {...props}
                {...register("paypal_account_ref")}
                type="email"
                placeholder={t("signup.paypalRefPlaceholder")}
              />
            )}
          </Field>

          {/* Password */}
          <Field
            label={t("signup.password")}
            error={errors.password ? t("signup.passwordMin") : undefined}
          >
            {(props) => (
              <Input
                {...props}
                {...register("password")}
                type="password"
                autoComplete="new-password"
              />
            )}
          </Field>

          {/* Confirm Password */}
          <Field
            label={t("signup.confirmPassword")}
            error={errors.confirmPassword ? t("signup.passwordMismatch") : undefined}
          >
            {(props) => (
              <Input
                {...props}
                {...register("confirmPassword")}
                type="password"
                autoComplete="new-password"
              />
            )}
          </Field>

          {/* Error notice */}
          {failure ? (
            <p role="alert" className="text-sm font-medium text-status-attention">
              {failure}
            </p>
          ) : null}

          {/* Submit Button */}
          <Button type="submit" disabled={isSubmitting} size="lg" className="w-full mt-2">
            {isSubmitting ? (
              <>
                <Spinner label={t("signup.submitting")} />
                {t("signup.submitting")}
              </>
            ) : (
              t("signup.submit")
            )}
          </Button>
        </form>

        {/* Link to Login */}
        <div className="mt-5 pt-4 border-t border-border-subtle/60 text-center text-sm text-ink-muted">
          <span>{t("signup.alreadyHaveAccount")} </span>
          <Link
            href={`/${locale}/login`}
            className="font-semibold text-accent hover:underline hover:text-accent/90"
          >
            {t("signup.signIn")}
          </Link>
        </div>
      </Card>
    </div>
  );
}
