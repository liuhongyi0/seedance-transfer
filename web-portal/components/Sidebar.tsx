"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import {useTranslations} from "next-intl";

export default function Sidebar() {
  const t = useTranslations();
  const pathname = usePathname();

  const NAV_ITEMS = [
    {href: "/dashboard", label: t("nav.dashboard"), icon: "📊"},
    {href: "/keys", label: t("nav.keys"), icon: "🔑"},
    {href: "/usage", label: t("nav.usage"), icon: "📋"},
    {href: "/recharge", label: t("nav.recharge"), icon: "💰"},
    {href: "/settings", label: t("nav.settings"), icon: "⚙️"},
  ];

  return (
    <aside className="hidden lg:flex lg:flex-col lg:w-[220px] lg:fixed lg:left-0 lg:top-14 lg:bottom-0 bg-white border-r border-gray-200 z-30">
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-primary-50 text-primary font-medium"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Bottom brand */}
      <div className="px-3 py-4 border-t border-gray-100">
        <p className="text-xs text-gray-400 text-center">
          {t("layout.version")}
        </p>
      </div>
    </aside>
  );
}
