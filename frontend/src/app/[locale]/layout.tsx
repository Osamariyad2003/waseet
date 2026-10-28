import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Providers } from "@/app/providers";
import { AppShell } from "@/components/layout/app-shell";
import { direction, isLocale, locales } from "@/lib/i18n";

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  setRequestLocale(locale);
  const messages = await getMessages();

  return (
    // dir is set here, on the server, so the first paint is already correct
    // in Arabic rather than flipping after hydration.
    <html lang={locale} dir={direction(locale)} suppressHydrationWarning>
      <body className="min-h-dvh antialiased" suppressHydrationWarning>
        <NextIntlClientProvider messages={messages}>
          <Providers>
            <AppShell locale={locale}>
              {children}
            </AppShell>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
