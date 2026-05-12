"use client";

import Link from "next/link";
import {useTranslations} from "next-intl";
import {fenToYuan} from "@/lib/utils";

interface BalanceCardProps {
  balanceFen: number;
}

export default function BalanceCard({balanceFen}: BalanceCardProps) {
  const t = useTranslations();
  const yuan = fenToYuan(balanceFen);
  const [yuanPart, fenPart] = yuan.split(".");

  return (
    <div className="relative overflow-hidden rounded-card bg-gradient-to-br from-primary to-blue-700 p-6 text-white">
      {/* Decorative background circles */}
      <div className="absolute -top-6 -right-6 w-32 h-32 bg-white/10 rounded-full" />
      <div className="absolute -bottom-4 -left-4 w-24 h-24 bg-white/10 rounded-full" />

      <div className="relative">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-blue-200">
            {t("balanceCard.accountBalance")}
          </span>
          <Link
            href="/recharge"
            className="px-3 py-1 bg-white/20 hover:bg-white/30 rounded-full text-xs transition-colors"
          >
            {t("balanceCard.topUp")}
          </Link>
        </div>

        <div className="flex items-baseline gap-1">
          <span className="text-sm text-blue-200">¥</span>
          <span className="text-4xl font-bold">{yuanPart}</span>
          <span className="text-lg text-blue-200">.{fenPart}</span>
        </div>

        <p className="mt-2 text-xs text-blue-200">
          {t("balanceCard.balanceUnit")}
        </p>
      </div>
    </div>
  );
}
