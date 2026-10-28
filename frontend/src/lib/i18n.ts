/**
 * next-intl configuration. Arabic and English from day one, with RTL —
 * retrofitting direction later always means rewriting layout.
 */
import { getRequestConfig } from "next-intl/server";

export const locales = ["en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

export function isLocale(value: string): value is Locale {
  return value === "en";
}

export function direction(_locale?: Locale): "ltr" {
  return "ltr";
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = requested && isLocale(requested) ? requested : defaultLocale;
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
