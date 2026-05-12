import type {Metadata} from 'next';
import './globals.css';
import {NextIntlClientProvider} from 'next-intl';
import {getLocale, getMessages} from 'next-intl/server';
import {AuthProvider} from '@/lib/auth';
import {ToastProvider} from '@/components/Toast';

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const messages = (await import(`../locales/${locale}.json`)).default;

  return {
    title: messages.layout?.title || 'Seedance Wizard',
    description:
      messages.layout?.description ||
      'Seedance Wizard AI Video Creation Platform',
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <AuthProvider>
            <ToastProvider>{children}</ToastProvider>
          </AuthProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
