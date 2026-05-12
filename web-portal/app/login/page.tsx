"use client";

import {useState, FormEvent} from "react";
import {useRouter} from "next/navigation";
import Link from "next/link";
import {useTranslations} from "next-intl";
import {useAuth} from "@/lib/auth";
import {isValidEmail, isValidPhone} from "@/lib/utils";

type LoginMode = "email" | "phone";

export default function LoginPage() {
  const t = useTranslations();
  const router = useRouter();
  const {login, emailLogin} = useAuth();

  const [mode, setMode] = useState<LoginMode>("email");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (!password) {
      setError(t("login.errorEmptyPassword"));
      return;
    }

    if (mode === "email") {
      if (!isValidEmail(email)) {
        setError(t("login.errorInvalidEmail"));
        return;
      }
    } else {
      if (!isValidPhone(phone)) {
        setError(t("login.errorInvalidPhone"));
        return;
      }
    }

    setLoading(true);
    try {
      if (mode === "email") {
        await emailLogin(email, password);
      } else {
        await login(phone, password);
      }
      router.replace("/dashboard");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : t("login.errorLoginFailed");
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2">
            <span className="text-3xl">{"🎬"}</span>
            <span className="text-2xl font-bold text-gray-900">
              {t("login.title")}
            </span>
          </Link>
          <p className="text-gray-500 mt-2">{t("login.subtitle")}</p>
        </div>

        {/* Form card */}
        <div className="bg-white rounded-card shadow-sm border border-gray-200 p-8">
          {/* Mode tabs */}
          <div className="flex mb-6 bg-gray-100 rounded-lg p-1">
            <button
              type="button"
              onClick={() => setMode("email")}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                mode === "email"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t("login.emailTab")}
            </button>
            <button
              type="button"
              onClick={() => setMode("phone")}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                mode === "phone"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t("login.phoneTab")}
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email or Phone field */}
            {mode === "email" ? (
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
                  {t("login.email")}
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t("login.emailPlaceholder")}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                  autoComplete="email"
                />
              </div>
            ) : (
              <div>
                <label htmlFor="phone" className="block text-sm font-medium text-gray-700 mb-1.5">
                  {t("login.phone")}
                </label>
                <input
                  id="phone"
                  type="tel"
                  maxLength={11}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
                  placeholder={t("login.phonePlaceholder")}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                  autoComplete="tel"
                />
              </div>
            )}

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
                {t("login.password")}
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t("login.passwordPlaceholder")}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                autoComplete="current-password"
              />
            </div>

            {/* Error */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2.5 rounded-lg text-sm">
                {error}
              </div>
            )}

            {/* Login button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-primary text-white rounded-lg font-semibold hover:bg-primary-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? t("login.loggingIn") : t("login.loginButton")}
            </button>
          </form>

          {/* Footer link */}
          <p className="mt-6 text-center text-sm text-gray-500">
            {t("login.noAccount")}
            <Link href="/register" className="text-primary hover:underline ml-1">
              {t("login.goRegister")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
