import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Providers } from "@/app/providers";
import { AppHeader } from "@/components/app-header";
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
    <html lang={locale} dir={direction(locale)}>
      <body className="min-h-dvh antialiased">
        <NextIntlClientProvider messages={messages}>
          <Providers>
            <AppHeader locale={locale} />
            <main className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-10">
              {children}
            </main>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
