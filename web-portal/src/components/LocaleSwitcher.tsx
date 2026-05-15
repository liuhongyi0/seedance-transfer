'use client';

import { useLocale } from 'next-intl';
import { locales } from '@/i18n';
import { useRouter } from '@/navigation';

export default function LocaleSwitcher() {
  const locale = useLocale();
  const router = useRouter();

  const nextLocale = locale === 'zh-CN' ? 'en-US' : 'zh-CN';
  const label = locale === 'zh-CN' ? 'EN' : '中';

  function switchLocale() {
    document.cookie = `NEXT_LOCALE=${nextLocale};path=/;max-age=31536000;SameSite=Lax`;
    router.refresh();
  }

  return (
    <button
      onClick={switchLocale}
      style={{
        background: 'rgba(255,255,255,0.1)',
        border: '1px solid rgba(255,255,255,0.2)',
        color: '#fff',
        padding: '4px 10px',
        borderRadius: 6,
        cursor: 'pointer',
        fontSize: 13,
        fontWeight: 600,
      }}
      title={locale === 'zh-CN' ? 'Switch to English' : '切换到中文'}
    >
      {label}
    </button>
  );
}
