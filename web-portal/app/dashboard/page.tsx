"use client";

import {useState, useEffect} from "react";
import Link from "next/link";
import {useTranslations} from "next-intl";
import ProtectedRoute from "@/components/ProtectedRoute";
import Navbar from "@/components/Navbar";
import Sidebar from "@/components/Sidebar";
import BalanceCard from "@/components/BalanceCard";
import UsageTable from "@/components/UsageTable";
import {useAuth} from "@/lib/auth";
import {api} from "@/lib/api";
import {fenToYuan} from "@/lib/utils";
import type {UsageLog, ApiKey} from "@/types";

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}

function DashboardContent() {
  const t = useTranslations();
  const {user} = useAuth();
  const [recentUsage, setRecentUsage] = useState<UsageLog[]>([]);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [usageLoading, setUsageLoading] = useState(true);
  const [stats, setStats] = useState({
    monthlyCalls: 0,
    monthlyCostFen: 0,
    activeKeys: 0,
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [usageRes, keysRes] = await Promise.all([
          api.getUsage({page: 1, pageSize: 5}),
          api.getKeys(),
        ]);

        setRecentUsage(usageRes.data);

        // Calculate this month's data
        const now = new Date();
        const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
        const thisMonth = usageRes.data.filter(
          (u) => new Date(u.createdAt) >= monthStart
        );
        const totalCost = thisMonth.reduce((sum, u) => sum + u.costFen, 0);

        setStats({
          monthlyCalls: thisMonth.length,
          monthlyCostFen: totalCost,
          activeKeys: keysRes.filter((k) => k.isActive).length,
        });
        setKeys(keysRes);
      } catch {
        // Silent fail
      } finally {
        setUsageLoading(false);
      }
    };

    fetchData();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <Sidebar />

      <main className="pt-14 lg:pl-[220px]">
        <div className="p-4 lg:p-6 max-w-6xl mx-auto space-y-6">
          {/* Welcome */}
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t("dashboard.welcomeBack")}
              {user
                ? `，${user.phone.slice(0, 3)}****${user.phone.slice(8)}`
                : ""}
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              {t("dashboard.overview")}
            </p>
          </div>

          {/* Balance card */}
          <BalanceCard balanceFen={user?.balanceFen ?? 0} />

          {/* Stats cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard
              icon="📞"
              label={t("dashboard.monthlyCalls")}
              value={stats.monthlyCalls.toString()}
            />
            <StatCard
              icon="💳"
              label={t("dashboard.monthlyCost")}
              value={`¥${fenToYuan(stats.monthlyCostFen)}`}
            />
            <StatCard
              icon="🔑"
              label={t("dashboard.activeKeys")}
              value={stats.activeKeys.toString()}
            />
          </div>

          {/* Quick actions */}
          <div className="flex flex-wrap gap-3">
            <Link
              href="/keys"
              className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-600 transition-colors"
            >
              {"🔑 "}
              {t("dashboard.createKey")}
            </Link>
            <Link
              href="/usage"
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:border-primary hover:text-primary transition-colors"
            >
              {"📋 "}
              {t("dashboard.viewUsage")}
            </Link>
            <Link
              href="/recharge"
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:border-primary hover:text-primary transition-colors"
            >
              {"💰 "}
              {t("dashboard.topUp")}
            </Link>
          </div>

          {/* Recent usage */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-gray-900">
                {t("dashboard.recentUsage")}
              </h2>
              <Link
                href="/usage"
                className="text-sm text-primary hover:underline"
              >
                {t("dashboard.viewAll")}
              </Link>
            </div>
            <UsageTable records={recentUsage} loading={usageLoading} />
          </div>
        </div>
      </main>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: string;
  label: string;
  value: string;
}) {
  return (
    <div className="bg-white rounded-card border border-gray-200 p-5 flex items-center gap-4">
      <div className="text-2xl">{icon}</div>
      <div>
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-xl font-bold text-gray-900">{value}</p>
      </div>
    </div>
  );
}
