"use client";

import {useTranslations, useLocale} from "next-intl";
import type {UsageLog} from "@/types";
import {SERVICE_LABELS, STATUS_COLORS} from "@/types";
import {fenToYuan, formatDateTime} from "@/lib/utils";

interface UsageTableProps {
  records: UsageLog[];
  loading: boolean;
}

export default function UsageTable({records, loading}: UsageTableProps) {
  const t = useTranslations();
  const locale = useLocale();

  if (loading) {
    return (
      <div className="bg-white rounded-card border border-gray-200 p-8 text-center">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-gray-500 text-sm">{t("table.loading")}</p>
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="bg-white rounded-card border border-gray-200 p-12 text-center">
        <div className="text-4xl mb-3">{"📋"}</div>
        <p className="text-gray-500">{t("table.empty")}</p>
        <p className="text-gray-400 text-xs mt-1">{t("table.emptyHint")}</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-card border border-gray-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-3 text-gray-600 font-medium whitespace-nowrap">
                {t("table.time")}
              </th>
              <th className="text-left px-4 py-3 text-gray-600 font-medium whitespace-nowrap">
                {t("table.serviceType")}
              </th>
              <th className="text-right px-4 py-3 text-gray-600 font-medium whitespace-nowrap">
                {t("table.usage")}
              </th>
              <th className="text-right px-4 py-3 text-gray-600 font-medium whitespace-nowrap">
                {t("table.costYuan")}
              </th>
              <th className="text-center px-4 py-3 text-gray-600 font-medium whitespace-nowrap">
                {t("table.status")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {records.map((record) => (
              <tr key={record.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                  {formatDateTime(record.createdAt, locale)}
                </td>
                <td className="px-4 py-3 text-gray-900 whitespace-nowrap">
                  {t(`services.${record.service}` as any) || SERVICE_LABELS[record.service] || record.service}
                </td>
                <td className="px-4 py-3 text-gray-900 text-right whitespace-nowrap">
                  {record.units}
                </td>
                <td className="px-4 py-3 text-gray-900 text-right whitespace-nowrap font-mono">
                  {fenToYuan(record.costFen)}
                </td>
                <td className="px-4 py-3 text-center whitespace-nowrap">
                  <span
                    className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                      STATUS_COLORS[record.status] || "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {t(`status.${record.status}` as any) || record.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
