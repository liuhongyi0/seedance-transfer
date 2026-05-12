"use client";

import {useEffect} from "react";
import {useRouter} from "next/navigation";
import Link from "next/link";
import {useTranslations} from "next-intl";
import {useAuth} from "@/lib/auth";

export default function HomePage() {
  const t = useTranslations();
  const {isAuthenticated, isLoading} = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (isAuthenticated) {
    return null;
  }

  const features = [
    {
      icon: "🧠",
      title: t("home.feature1Title"),
      desc: t("home.feature1Desc"),
    },
    {
      icon: "🎨",
      title: t("home.feature2Title"),
      desc: t("home.feature2Desc"),
    },
    {
      icon: "🎬",
      title: t("home.feature3Title"),
      desc: t("home.feature3Desc"),
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      {/* Nav */}
      <header className="fixed top-0 left-0 right-0 z-40 bg-white/80 backdrop-blur border-b border-gray-200">
        <div className="max-w-6xl mx-auto flex items-center justify-between h-14 px-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-2xl">{"🎬"}</span>
            <span className="text-lg font-bold text-gray-900">
              {t("common.brand")}
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="px-4 py-1.5 text-sm text-gray-600 hover:text-gray-900"
            >
              {t("home.login")}
            </Link>
            <Link
              href="/register"
              className="px-4 py-1.5 text-sm bg-primary text-white rounded-lg hover:bg-primary-600 transition-colors"
            >
              {t("home.register")}
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="pt-14">
        <section className="max-w-6xl mx-auto px-4 py-20 lg:py-32">
          <div className="text-center max-w-2xl mx-auto">
            <div className="text-5xl mb-6">{"🎥"}</div>
            <h1 className="text-4xl lg:text-5xl font-extrabold text-gray-900 mb-6 leading-tight">
              {t("home.heroTitle1")}
              <span className="text-primary"> {t("home.heroTitle2")} </span>
              {t("home.heroTitle3")}
            </h1>
            <p className="text-lg text-gray-600 mb-8 leading-relaxed">
              {t("home.heroDescription")}
            </p>
            <div className="flex items-center justify-center gap-4">
              <Link
                href="/register"
                className="px-8 py-3 bg-primary text-white rounded-lg font-semibold text-lg hover:bg-primary-600 transition-colors shadow-lg shadow-primary/25"
              >
                {t("home.ctaTry")}
              </Link>
              <Link
                href="/login"
                className="px-8 py-3 border-2 border-gray-300 text-gray-700 rounded-lg font-semibold text-lg hover:border-primary hover:text-primary transition-colors"
              >
                {t("home.ctaLogin")}
              </Link>
            </div>
          </div>

          {/* Feature highlights */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-20">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="bg-white rounded-card p-6 shadow-sm border border-gray-200 text-center"
              >
                <div className="text-3xl mb-3">{feature.icon}</div>
                <h3 className="font-semibold text-gray-900 mb-2">
                  {feature.title}
                </h3>
                <p className="text-sm text-gray-500">{feature.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-gray-200 py-8 text-center">
          <p className="text-sm text-gray-400">
            &copy; {new Date().getFullYear()} {t("home.copyright")}
          </p>
        </footer>
      </main>
    </div>
  );
}
