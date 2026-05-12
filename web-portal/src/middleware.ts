import createMiddleware from 'next-intl/middleware';
import {locales} from './i18n';

// localePrefix: 'never' — no locale in URL, cookie-based only
export default createMiddleware({
  locales,
  defaultLocale: 'zh-CN',
  localePrefix: 'never'
});

export const config = {
  matcher: ['/((?!api|_next|.*\\..*).*)']
};
