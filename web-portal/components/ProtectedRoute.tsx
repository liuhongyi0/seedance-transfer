"use client";

import {useAuth} from "@/lib/auth";
import {useRouter} from "next/navigation";
import {useEffect} from "react";
import {useTranslations} from "next-intl";

export default function ProtectedRoute({
  children,
}: {
  children: React.ReactNode;
}) {
  const t = useTranslations();
  const {isAuthenticated, isLoading} = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-500 text-sm">{t("protectedRoute.loading")}</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
