import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender, type RenderResult } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import en from "@/messages/en.json";
import ar from "@/messages/ar.json";

/**
 * Render with the providers a component actually needs.
 *
 * Tests go through the real message catalogue rather than a stub, so a
 * missing or renamed translation key fails a test instead of shipping as a
 * raw key in the UI.
 */
export function render(
  ui: React.ReactNode,
  { locale = "en" }: { locale?: "en" | "ar" } = {},
): RenderResult {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return rtlRender(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale={locale} messages={locale === "ar" ? ar : en}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}
