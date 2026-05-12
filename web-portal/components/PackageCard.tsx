"use client";

import {useTranslations} from "next-intl";
import type {Package} from "@/types";

interface PackageCardProps {
  pkg: Package;
  onPurchase: (pkg: Package) => void;
  disabled?: boolean;
}

export default function PackageCard({pkg, onPurchase, disabled}: PackageCardProps) {
  const t = useTranslations();

  return (
    <div
      className={`relative bg-white rounded-card border-2 p-6 flex flex-col ${
        pkg.recommended
          ? "border-accent shadow-lg shadow-accent/10"
          : "border-gray-200 shadow-sm hover:shadow-md"
      } transition-shadow`}
    >
      {pkg.recommended && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-accent text-white text-xs font-bold px-4 py-1 rounded-full shadow">
            {t("recharge.recommended")}
          </span>
        </div>
      )}

      <h3 className="text-lg font-semibold text-gray-900 text-center mb-4">
        {t(`packages.${pkg.key}` as any) || pkg.name}
      </h3>

      <div className="text-center mb-4">
        <span className="text-3xl font-bold text-gray-900">
          ¥{pkg.priceYuan}
        </span>
      </div>

      <div className="bg-gray-50 rounded-lg p-4 mb-6 space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">{t("recharge.balanceAmount")}</span>
          <span className="font-semibold text-gray-900">
            {(pkg.fenAmount / 100).toFixed(2)} {t("recharge.yuan")}
          </span>
        </div>
        {pkg.description && (
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">{t("recharge.estimate")}</span>
            <span className="font-semibold text-gray-900">{pkg.description}</span>
          </div>
        )}
      </div>

      <button
        onClick={() => onPurchase(pkg)}
        disabled={disabled}
        className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-colors mt-auto ${
          disabled
            ? "bg-gray-300 text-gray-500 cursor-not-allowed"
            : pkg.recommended
              ? "bg-accent text-white hover:bg-accent-600"
              : "bg-primary text-white hover:bg-primary-600"
        }`}
      >
        {disabled ? t("recharge.comingSoon") : t("recharge.buyNow")}
      </button>
    </div>
  );
}
