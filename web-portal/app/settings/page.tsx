"use client";

import {useTranslations, useLocale} from "next-intl";
import ProtectedRoute from "@/components/ProtectedRoute";
import Navbar from "@/components/Navbar";
import Sidebar from "@/components/Sidebar";
import {useAuth} from "@/lib/auth";
import {maskPhone} from "@/lib/utils";

export default function SettingsPage() {
  return (
    <ProtectedRoute>
      <SettingsContent />
    </ProtectedRoute>
  );
}

function SettingsContent() {
  const t = useTranslations();
  const locale = useLocale();
  const {user} = useAuth();

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <Sidebar />

      <main className="pt-14 lg:pl-[220px]">
        <div className="p-4 lg:p-6 max-w-2xl mx-auto space-y-6">
          {/* Page title */}
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t("settings.title")}
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              {t("settings.subtitle")}
            </p>
          </div>

          {/* Account info */}
          <section className="bg-white rounded-card border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t("settings.accountInfo")}
            </h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-gray-600">
                  {t("settings.phone")}
                </span>
                <span className="text-sm font-medium text-gray-900">
                  {user ? maskPhone(user.phone) : ""}
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-gray-600">
                  {t("settings.userId")}
                </span>
                <span className="text-sm font-mono text-gray-500">
                  {user?.id || ""}
                </span>
              </div>
            </div>
          </section>

          {/* Change password */}
          <section className="bg-white rounded-card border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t("settings.changePassword")}
            </h2>
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="oldPassword"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  {t("settings.oldPassword")}
                </label>
                <input
                  id="oldPassword"
                  type="password"
                  disabled
                  placeholder={t("settings.oldPasswordPlaceholder")}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm bg-gray-50 text-gray-400 cursor-not-allowed"
                />
              </div>
              <div>
                <label
                  htmlFor="newPassword"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  {t("settings.newPassword")}
                </label>
                <input
                  id="newPassword"
                  type="password"
                  disabled
                  placeholder={t("settings.newPasswordPlaceholder")}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm bg-gray-50 text-gray-400 cursor-not-allowed"
                />
              </div>
              <div>
                <label
                  htmlFor="confirmNewPassword"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  {t("settings.confirmNewPassword")}
                </label>
                <input
                  id="confirmNewPassword"
                  type="password"
                  disabled
                  placeholder={t("settings.confirmNewPasswordPlaceholder")}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm bg-gray-50 text-gray-400 cursor-not-allowed"
                />
              </div>
              <button
                disabled
                className="w-full py-2.5 bg-gray-300 text-gray-500 rounded-lg text-sm font-medium cursor-not-allowed"
              >
                {t("settings.passwordButtonDisabled")}
              </button>
            </div>
          </section>

          {/* Language switcher */}
          <section className="bg-white rounded-card border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t("settings.languageSettings")}
            </h2>
            <p className="text-sm text-gray-500 mb-3">
              {locale === "zh-CN" ? t("settings.chinese") : t("settings.english")}
              {" — "}
              {t("settings.languageComingSoon")}
            </p>
            <div className="flex items-center gap-4">
              <button
                disabled={locale !== "zh-CN"}
                onClick={() => {}}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  locale === "zh-CN"
                    ? "bg-primary text-white"
                    : "bg-gray-100 text-gray-500 cursor-not-allowed"
                }`}
              >
                {t("settings.chinese")}
              </button>
              <button
                disabled={locale !== "en-US"}
                onClick={() => {}}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  locale === "en-US"
                    ? "bg-primary text-white"
                    : "bg-gray-100 text-gray-500 cursor-not-allowed"
                }`}
              >
                {t("settings.english")}
              </button>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
