"use client";

import {useState, useRef, useCallback} from "react";
import {useTranslations} from "next-intl";
import ProtectedRoute from "@/components/ProtectedRoute";
import Navbar from "@/components/Navbar";
import Sidebar from "@/components/Sidebar";
import BalanceCard from "@/components/BalanceCard";
import PackageCard from "@/components/PackageCard";
import {useToast} from "@/components/Toast";
import {useAuth} from "@/lib/auth";
import {api} from "@/lib/api";
import {RECHARGE_PACKAGES, type Package, type PaymentMethod} from "@/types";

const PAYMENT_METHODS: PaymentMethod[] = [
  {type: "alipay", name: "支付宝", icon: "💙", enabled: true},
  {type: "wechat", name: "微信支付", icon: "💚", enabled: true},
];

export default function RechargePage() {
  return (
    <ProtectedRoute>
      <RechargeContent />
    </ProtectedRoute>
  );
}

function RechargeContent() {
  const t = useTranslations();
  const {user, refreshBalance} = useAuth();
  const {showToast} = useToast();
  const [loading, setLoading] = useState(false);
  const [selectedPayType, setSelectedPayType] = useState<"alipay" | "wechat">("alipay");
  const [payConfigured, setPayConfigured] = useState(true);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPollingBalance = useCallback(() => {
    stopPolling();
    const beforeFen = user?.balanceFen ?? 0;
    let attempts = 0;
    const maxAttempts = 60; // 3 minutes max

    pollingRef.current = setInterval(async () => {
      attempts++;
      try {
        const balance = await api.getBalance();
        if (balance.amountFen > beforeFen) {
          stopPolling();
          await refreshBalance();
          showToast(
            t("recharge.paymentSuccess", {
              amount: ((balance.amountFen - beforeFen) / 100).toFixed(2),
            }),
            "success"
          );
        } else if (attempts >= maxAttempts) {
          stopPolling();
          showToast(t("recharge.paymentTimeout"), "info");
        }
      } catch {
        // ignore polling errors
      }
    }, 3000);
  }, [user?.balanceFen, refreshBalance, showToast, stopPolling, t]);

  const handlePurchase = async (pkg: Package) => {
    setLoading(true);
    try {
      const result = await api.createOrder(pkg.key, selectedPayType);
      // Open payment page in new tab
      window.open(result.pay_url, "_blank");
      showToast(t("recharge.paymentOpened"), "info");
      // Start polling for balance change
      startPollingBalance();
    } catch (err: any) {
      if (err.status === 501) {
        setPayConfigured(false);
        showToast(t("recharge.comingSoon"), "info");
      } else {
        showToast(err.message || t("recharge.orderFailed"), "error");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <Sidebar />

      <main className="pt-14 lg:pl-[220px]">
        <div className="p-4 lg:p-6 max-w-6xl mx-auto space-y-6">
          {/* Page title */}
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t("recharge.title")}
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              {t("recharge.subtitle")}
            </p>
          </div>

          {/* Balance card */}
          <BalanceCard balanceFen={user?.balanceFen ?? 0} />

          {/* Package grid */}
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t("recharge.packageSelection")}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {RECHARGE_PACKAGES.map((pkg) => (
                <PackageCard
                  key={pkg.key}
                  pkg={pkg}
                  onPurchase={handlePurchase}
                  disabled={!payConfigured || loading}
                />
              ))}
            </div>
          </div>

          {/* Payment methods */}
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t("recharge.paymentMethods")}
            </h2>
            <div className="bg-white rounded-card border border-gray-200 p-6">
              <div className="flex flex-wrap gap-6">
                {PAYMENT_METHODS.map((method) => (
                  <button
                    key={method.type}
                    disabled={!method.enabled || !payConfigured}
                    onClick={() => setSelectedPayType(method.type)}
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg border-2 transition-colors ${
                      selectedPayType === method.type && payConfigured
                        ? "border-primary bg-primary/5"
                        : "border-gray-200 bg-gray-50 opacity-50 cursor-not-allowed"
                    }`}
                  >
                    <span className="text-2xl">{method.icon}</span>
                    <span className="text-sm font-medium text-gray-700">
                      {method.name}
                    </span>
                    {selectedPayType === method.type && payConfigured && (
                      <span className="ml-1 w-2.5 h-2.5 rounded-full bg-primary" />
                    )}
                  </button>
                ))}
              </div>
              {!payConfigured && (
                <p className="mt-4 text-sm text-gray-400">
                  {t("recharge.comingSoon")}
                </p>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
