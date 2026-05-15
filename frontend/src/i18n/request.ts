import { getRequestConfig } from "next-intl/server";
import { notFound } from "next/navigation";

const locales = ["fr", "en"] as const;

export default getRequestConfig(async ({ requestLocale }) => {
  // Fall back to default locale when next-intl middleware hasn't set requestLocale
  const locale = (await requestLocale) ?? "fr";
  if (!locales.includes(locale as (typeof locales)[number])) notFound();

  return {
    locale: locale as string,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
