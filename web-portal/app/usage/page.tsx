"use client";

import {useState, useEffect, useCallback} from "react";
import {useTranslations} from "next-intl";
import ProtectedRoute from "@/components/ProtectedRoute";
import Navbar from "@/components/Navbar";
import Sidebar from "@/components/Sidebar";
import UsageTable from "@/components/UsageTable";
import {useToast} from "@/components/Toast";
import {api} from "@/lib/api";
import type {UsageLog, ServiceType} from "@/types";
import {SERVICE_LABELS} from "@/types";

const PAGE_SIZE = 10;

export default function UsagePage() {
  return (
    <ProtectedRoute>
      <UsageContent />
    </ProtectedRoute>
  );
}

function UsageContent() {
  const t = useTranslations();
  const {showToast} = useToast();
  const [records, setRecords] = useState<UsageLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [filterService, setFilterService] = useState<ServiceType | "">("");

  const fetchUsage = useCallback(async () => {
    setLoading(true);
    try {
      const params: {page: number; pageSize: number; service?: ServiceType} = {
        page,
        pageSize: PAGE_SIZE,
      };
      if (filterService) {
        params.service = filterService as ServiceType;
      }
      const res = await api.getUsage(params);
      setRecords(res.data);
      setTotal(res.total);
      setTotalPages(res.totalPages);
    } catch {
      showToast(t("usage.toastFetchFailed"), "error");
    } finally {
      setLoading(false);
    }
  }, [page, filterService, showToast, t]);

  useEffect(() => {
    fetchUsage();
  }, [fetchUsage]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <Sidebar />

      <main className="pt-14 lg:pl-[220px]">
        <div className="p-4 lg:p-6 max-w-6xl mx-auto space-y-6">
          {/* Page title */}
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t("usage.title")}
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              {t("usage.subtitle")}
            </p>
          </div>

          {/* Filter bar */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label
                htmlFor="serviceFilter"
                className="text-sm text-gray-600"
              >
                {t("usage.serviceType")}
              </label>
              <select
                id="serviceFilter"
                value={filterService}
                onChange={(e) => {
                  setFilterService(e.target.value as ServiceType | "");
                  setPage(1);
                }}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary bg-white"
              >
                <option value="">{t("usage.allServices")}</option>
                {(
                  Object.entries(SERVICE_LABELS) as [
                    ServiceType,
                    string
                  ][]
                ).map(([key]) => (
                  <option key={key} value={key}>
                    {t(`services.${key}` as any)}
                  </option>
                ))}
              </select>
            </div>

            <span className="text-sm text-gray-400 ml-auto">
              {t("usage.totalRecords", {total})}
            </span>
          </div>

          {/* Usage table */}
          <UsageTable records={records} loading={loading} />

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t("usage.previousPage")}
              </button>

              {generatePageNumbers(page, totalPages).map((p, i) =>
                p === "..." ? (
                  <span key={`ellipsis-${i}`} className="px-2 text-gray-400">
                    ...
                  </span>
                ) : (
                  <button
                    key={p}
                    onClick={() => setPage(p as number)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      p === page
                        ? "bg-primary text-white"
                        : "border border-gray-300 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    {p}
                  </button>
                )
              )}

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t("usage.nextPage")}
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function generatePageNumbers(
  current: number,
  total: number
): (number | "...")[] {
  if (total <= 7) {
    return Array.from({length: total}, (_, i) => i + 1);
  }

  const pages: (number | "...")[] = [];

  if (current <= 3) {
    pages.push(1, 2, 3, 4, "...", total);
  } else if (current >= total - 2) {
    pages.push(1, "...", total - 3, total - 2, total - 1, total);
  } else {
    pages.push(
      1,
      "...",
      current - 1,
      current,
      current + 1,
      "...",
      total
    );
  }

  return pages;
}
