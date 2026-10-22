"use client";

import { zodResolver } from "@hookform/resolvers/zod";
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
    if (user?.role === "reviewer") router.replace(`/${locale}/dashboard`);
  }, [user, router, locale]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = async (values: FormValues) => {
    setFailure(null);
    try {
      const signedIn = await signIn(values.email, values.password);
      // This platform is for reviewers only. A buyer or seller who signs in
      // here is turned away and pointed at the escrow app.
      if (signedIn.role !== "reviewer") {
        signOut();
        setFailure(t("login.notReviewer"));
        return;
      }
      router.replace(`/${locale}/dashboard`);
    } catch (error) {
      if (error instanceof ApiError && error.code === "network_error") {
        setFailure(t("login.unreachable"));
      } else {
        setFailure(t("login.failed"));
      }
    }
  };

  return (
    <div className="mx-auto max-w-sm">
      <Card>
        <CardTitle>{t("login.title")}</CardTitle>
        <CardSubtitle>{t("login.subtitle")}</CardSubtitle>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <Field
            label={t("login.email")}
            error={errors.email ? t("validation.emailInvalid") : undefined}
          >
            {(props) => (
              <Input {...props} {...register("email")} type="email" autoComplete="email" autoFocus />
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

        <p className="mt-4 text-xs text-ink-faint">{t("login.demoHint")}</p>
      </Card>
    </div>
  );
}
