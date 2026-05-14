import {getRequestConfig} from 'next-intl/server';
import {notFound} from 'next/navigation';

export const locales = ['zh-CN', 'en-US'] as const;
export const defaultLocale = 'zh-CN';
export type Locale = (typeof locales)[number];

export default getRequestConfig(async ({requestLocale}) => {
  const locale = await requestLocale;
  if (!locale || !locales.includes(locale as Locale)) notFound();

  return {
    locale,
    messages: (await import(`../locales/${locale}.json`)).default
  };
});
