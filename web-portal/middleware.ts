import {NextRequest, NextResponse} from 'next/server';
import {locales, defaultLocale} from './src/i18n';

const COOKIE = 'NEXT_LOCALE';

function getLocale(request: NextRequest): string {
  const cookie = request.cookies.get(COOKIE)?.value;
  if (cookie && locales.includes(cookie as any)) return cookie;

  const accept = request.headers.get('accept-language') || '';
  for (const locale of locales) {
    if (accept.startsWith(locale) || accept.includes(',' + locale + ';')) return locale;
  }

  return defaultLocale;
}

export function middleware(request: NextRequest) {
  const locale = getLocale(request);
  request.headers.set('x-next-intl-locale', locale);

  const response = NextResponse.next();
  response.cookies.set(COOKIE, locale, {path: '/', sameSite: 'lax', maxAge: 31536000});
  response.headers.set('x-next-intl-locale', locale);
  return response;
}

export const config = {
  matcher: ['/((?!api|_next|.*\\..*).*)']
};
