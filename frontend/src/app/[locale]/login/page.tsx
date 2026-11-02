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

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { signIn, signOut, user } = useSession();
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    if (user) router.replace(`/${locale}/deals`);
  }, [user, router, locale]);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = async (values: FormValues) => {
    setFailure(null);
    try {
      const signedIn = await signIn(values.email, values.password);
      if (signedIn.role === "reviewer") {
        signOut();
        setFailure(t("login.reviewerElsewhere"));
        return;
      }
      router.replace(`/${locale}/deals`);
    } catch (error) {
      if (error instanceof ApiError && error.code === "network_error") {
        setFailure(t("login.unreachable"));
      } else {
        setFailure(t("login.failed"));
      }
    }
  };

  const fillDemoBuyer = () => {
    setValue("email", "buyer@waseet.example.com");
    setValue("password", "demo-password-123");
  };

  const fillDemoSeller = () => {
    setValue("email", "seller@waseet.example.com");
    setValue("password", "demo-password-123");
  };

  return (
    <div className="mx-auto max-w-sm">
      <Card>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.svg" alt="Waseet" className="mx-auto mb-4 h-14 w-auto" />
        <CardTitle>{t("login.title")}</CardTitle>
        <CardSubtitle>{t("login.subtitle")}</CardSubtitle>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <Field
            label={t("login.email")}
            error={errors.email ? t("validation.emailInvalid") : undefined}
          >
            {(props) => (
              <Input
                {...props}
                {...register("email")}
                type="email"
                autoComplete="email"
                autoFocus
              />
            )}
          </Field>

          <Field
            label={t("login.password")}
            error={errors.password ? t("common.required") : undefined}
          >
            {(props) => (
              <Input
                {...props}
                {...register("password")}
                type="password"
                autoComplete="current-password"
              />
            )}
          </Field>

          {failure ? (
            <p role="alert" className="text-sm text-status-attention">
              {failure}
            </p>
          ) : null}

          <Button type="submit" disabled={isSubmitting} size="lg" className="w-full">
            {isSubmitting ? (
              <>
                <Spinner label={t("login.submitting")} />
                {t("login.submitting")}
              </>
            ) : (
              t("login.submit")
            )}
          </Button>
        </form>

        <div className="mt-5 pt-4 border-t border-border-subtle/60 text-center text-sm text-ink-muted">
          <span>{t("login.noAccount")} </span>
          <Link
            href={`/${locale}/signup`}
            className="font-semibold text-accent hover:underline hover:text-accent/90"
          >
            {t("login.signUp")}
          </Link>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={fillDemoBuyer}
            className="flex-1 rounded-lg border border-border-subtle px-3 py-2 text-xs font-medium text-ink-muted transition-colors hover:border-accent hover:text-accent"
          >
            {t("login.demoBuyer")}
          </button>
          <button
            type="button"
            onClick={fillDemoSeller}
            className="flex-1 rounded-lg border border-border-subtle px-3 py-2 text-xs font-medium text-ink-muted transition-colors hover:border-accent hover:text-accent"
          >
            {t("login.demoSeller")}
          </button>
        </div>

        <p className="mt-3 text-xs text-center text-ink-faint">{t("login.demoHint")}</p>
      </Card>
    </div>
  );
}
