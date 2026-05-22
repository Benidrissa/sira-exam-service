import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import { notFound } from "next/navigation";
import { Providers } from "@/providers";
import { NavBar } from "@/components/NavBar";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { Toaster } from "sonner";

const locales = ["fr", "en"];

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!locales.includes(locale)) notFound();

  const messages = await getMessages();

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <Providers>
        <div className="min-h-screen bg-background">
          <NavBar />
          <Breadcrumbs />
          {children}
          <Toaster richColors position="top-right" />
        </div>
      </Providers>
    </NextIntlClientProvider>
  );
}
