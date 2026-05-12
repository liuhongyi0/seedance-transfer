"use client";

import {useState, useRef, useEffect} from "react";
import Link from "next/link";
import {useTranslations} from "next-intl";
import {useAuth} from "@/lib/auth";
import {fenToYuan, maskPhone} from "@/lib/utils";

export default function Navbar() {
  const t = useTranslations();
  const {user, isAuthenticated, logout} = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Click outside to close dropdown
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!isAuthenticated) return null;

  return (
    <nav className="fixed top-0 left-0 right-0 z-40 bg-white border-b border-gray-200 h-14">
      <div className="flex items-center justify-between h-full px-4 lg:px-6">
        {/* Left: Logo + mobile hamburger */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="lg:hidden p-1 text-gray-600 hover:text-gray-900"
            aria-label={t("nav.menu")}
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              {mobileMenuOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              )}
            </svg>
          </button>
          <Link href="/dashboard" className="flex items-center gap-2">
            <span className="text-xl font-bold text-primary">{"🎬"}</span>
            <span className="text-lg font-bold text-gray-900 hidden sm:block">
              {t("common.brand")}
            </span>
          </Link>
        </div>

        {/* Right: balance + user menu */}
        <div className="flex items-center gap-4">
          {user && (
            <Link
              href="/recharge"
              className="hidden sm:flex items-center gap-1 text-sm"
            >
              <span className="text-gray-500">{t("nav.balanceLabel")}</span>
              <span className="font-semibold text-primary">
                ¥{fenToYuan(user.balanceFen)}
              </span>
            </Link>
          )}

          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <div className="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center text-sm font-medium">
                {user ? user.phone.slice(0, 1) : "?"}
              </div>
              <span className="text-sm text-gray-700 hidden sm:block">
                {user ? maskPhone(user.phone) : ""}
              </span>
              <svg
                className={`w-4 h-4 text-gray-400 transition-transform ${
                  dropdownOpen ? "rotate-180" : ""
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50">
                <div className="px-4 py-2 border-b border-gray-100">
                  <p className="text-sm font-medium text-gray-900">
                    {user ? maskPhone(user.phone) : ""}
                  </p>
                  <p className="text-xs text-gray-500">
                    {t("common.balance")} ¥{user ? fenToYuan(user.balanceFen) : "0.00"}
                  </p>
                </div>
                <Link
                  href="/settings"
                  onClick={() => setDropdownOpen(false)}
                  className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  {"⚙️ "}
                  {t("common.settings")}
                </Link>
                <button
                  onClick={() => {
                    setDropdownOpen(false);
                    logout();
                  }}
                  className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  {"🚪 "}
                  {t("common.logout")}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile menu overlay */}
      {mobileMenuOpen && (
        <div className="lg:hidden fixed inset-0 top-14 bg-black/50 z-30">
          <div className="bg-white w-56 h-full shadow-lg p-4">
            <MobileNavItems onClose={() => setMobileMenuOpen(false)} />
          </div>
        </div>
      )}
    </nav>
  );
}

function MobileNavItems({onClose}: {onClose: () => void}) {
  const t = useTranslations();
  const {logout} = useAuth();
  const items = [
    {href: "/dashboard", label: t("nav.dashboard"), icon: "📊"},
    {href: "/keys", label: t("nav.keys"), icon: "🔑"},
    {href: "/usage", label: t("nav.usage"), icon: "📋"},
    {href: "/recharge", label: t("nav.recharge"), icon: "💰"},
    {href: "/settings", label: t("nav.settings"), icon: "⚙️"},
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 space-y-1">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            onClick={onClose}
            className="block px-3 py-2.5 rounded-lg text-gray-700 hover:bg-gray-100 text-sm"
          >
            {item.icon} {item.label}
          </Link>
        ))}
      </div>
      <button
        onClick={logout}
        className="w-full px-3 py-2.5 text-left text-sm text-red-600 hover:bg-red-50 rounded-lg"
      >
        {"🚪 "}
        {t("common.logout")}
      </button>
    </div>
  );
}
