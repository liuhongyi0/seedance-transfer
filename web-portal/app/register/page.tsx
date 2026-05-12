"use client";

import {useState, FormEvent, useEffect, useRef} from "react";
import {useRouter} from "next/navigation";
import Link from "next/link";
import {useTranslations} from "next-intl";
import {useAuth} from "@/lib/auth";
import {api} from "@/lib/api";
import {isValidEmail, isValidPhone} from "@/lib/utils";

type RegisterMode = "email" | "phone";

export default function RegisterPage() {
  const t = useTranslations();
  const router = useRouter();
  const {register, emailRegister} = useAuth();

  const [mode, setMode] = useState<RegisterMode>("email");

  // Email fields
  const [email, setEmail] = useState("");
  const [emailCode, setEmailCode] = useState("");

  // Phone fields
  const [phone, setPhone] = useState("");
  const [smsCode, setSmsCode] = useState("");

  // Common fields
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (countdown > 0) {
      timerRef.current = setTimeout(() => setCountdown(countdown - 1), 1000);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [countdown]);

  const handleSendCode = async () => {
    setError("");
    if (mode === "email") {
      if (!isValidEmail(email)) {
        setError(t("register.errorInvalidEmail"));
        return;
      }
    } else {
      if (!isValidPhone(phone)) {
        setError(t("register.errorInvalidPhone"));
        return;
      }
    }
    setSendingCode(true);
    try {
      if (mode === "email") {
        await api.sendEmailCode(email);
      } else {
        await api.sendSms(phone);
      }
      setCountdown(60);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : t("register.errorSendCodeFailed");
      setError(message);
    } finally {
      setSendingCode(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    // Validate mode-specific fields
    if (mode === "email") {
      if (!isValidEmail(email)) {
        setError(t("register.errorInvalidEmailDetail"));
        return;
      }
      if (!emailCode || emailCode.length !== 6) {
        setError(t("register.errorEmptyCode"));
        return;
      }
    } else {
      if (!isValidPhone(phone)) {
        setError(t("register.errorInvalidPhoneDetail"));
        return;
      }
      if (!smsCode || smsCode.length !== 6) {
        setError(t("register.errorEmptySms"));
        return;
      }
    }

    if (password.length < 8) {
      setError(t("register.errorShortPassword"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("register.errorPasswordMismatch"));
      return;
    }

    setLoading(true);
    try {
      if (mode === "email") {
        await emailRegister(email, password, emailCode);
      } else {
        await register(phone, password, smsCode);
      }
      router.push("/login?registered=true");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : t("register.errorRegisterFailed");
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2">
            <span className="text-3xl">{"🎬"}</span>
            <span className="text-2xl font-bold text-gray-900">
              {t("register.title")}
            </span>
          </Link>
          <p className="text-gray-500 mt-2">{t("register.subtitle")}</p>
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
              {t("register.emailTab")}
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
              {t("register.phoneTab")}
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email or Phone */}
            {mode === "email" ? (
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
                  {t("register.email")}
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t("register.emailPlaceholder")}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                  autoComplete="email"
                />
              </div>
            ) : (
              <div>
                <label htmlFor="phone" className="block text-sm font-medium text-gray-700 mb-1.5">
                  {t("register.phone")}
                </label>
                <input
                  id="phone"
                  type="tel"
                  maxLength={11}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
                  placeholder={t("register.phonePlaceholder")}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                  autoComplete="tel"
                />
              </div>
            )}

            {/* Verification code */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                {t("register.verificationCode")}
              </label>
              <div className="flex gap-2">
                {mode === "email" ? (
                  <input
                    type="text"
                    maxLength={6}
                    value={emailCode}
                    onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, ""))}
                    placeholder={t("register.codePlaceholder")}
                    className="flex-1 px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    autoComplete="one-time-code"
                  />
                ) : (
                  <input
                    type="text"
                    maxLength={6}
                    value={smsCode}
                    onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, ""))}
                    placeholder={t("register.smsPlaceholder")}
                    className="flex-1 px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    autoComplete="one-time-code"
                  />
                )}
                <button
                  type="button"
                  onClick={handleSendCode}
                  disabled={sendingCode || countdown > 0}
                  className="px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  {countdown > 0
                    ? `${countdown}s`
                    : sendingCode
                    ? t("register.sendingCode")
                    : t("register.sendCode")}
                </button>
              </div>
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
                {t("register.password")}
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t("register.passwordPlaceholder")}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                autoComplete="new-password"
              />
            </div>

            {/* Confirm Password */}
            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1.5">
                {t("register.confirmPassword")}
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder={t("register.confirmPasswordPlaceholder")}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                autoComplete="new-password"
              />
            </div>

            {/* Error */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2.5 rounded-lg text-sm">
                {error}
              </div>
            )}

            {/* Register button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-primary text-white rounded-lg font-semibold hover:bg-primary-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? t("register.registering") : t("register.registerButton")}
            </button>
          </form>

          {/* Footer link */}
          <p className="mt-6 text-center text-sm text-gray-500">
            {t("register.haveAccount")}
            <Link href="/login" className="text-primary hover:underline ml-1">
              {t("register.goLogin")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
