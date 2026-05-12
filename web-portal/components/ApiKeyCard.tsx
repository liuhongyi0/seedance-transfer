"use client";

import {useState} from "react";
import {useTranslations, useLocale} from "next-intl";
import type {ApiKey} from "@/types";
import {maskApiKey, formatDateTime, relativeTime} from "@/lib/utils";

interface ApiKeyCardProps {
  apiKey: ApiKey;
  onDelete: (id: string) => void;
  deleting: boolean;
}

export default function ApiKeyCard({
  apiKey,
  onDelete,
  deleting,
}: ApiKeyCardProps) {
  const t = useTranslations();
  const locale = useLocale();
  const [showConfirm, setShowConfirm] = useState(false);

  const handleDelete = () => {
    setShowConfirm(false);
    onDelete(apiKey.id);
  };

  return (
    <div className="bg-white rounded-card shadow-sm border border-gray-200 p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-gray-900">{apiKey.name}</h3>
          <code className="text-sm text-gray-500 mt-1 block font-mono">
            {maskApiKey(apiKey.keyPrefix)}
          </code>
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
            apiKey.isActive
              ? "bg-green-100 text-green-700"
              : "bg-gray-100 text-gray-500"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              apiKey.isActive ? "bg-green-500" : "bg-gray-400"
            }`}
          />
          {apiKey.isActive ? t("apiKey.active") : t("apiKey.disabled")}
        </span>
      </div>

      <div className="flex items-center justify-between text-xs text-gray-400">
        <div className="space-y-1">
          <p>
            {t("apiKey.createdAt")} {formatDateTime(apiKey.createdAt, locale)}
          </p>
          {apiKey.lastUsedAt && (
            <p>
              {t("apiKey.lastUsed")} {relativeTime(apiKey.lastUsedAt, locale)}
            </p>
          )}
        </div>

        {showConfirm ? (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowConfirm(false)}
              className="px-2 py-1 text-gray-500 hover:text-gray-700 text-xs"
            >
              {t("apiKey.cancel")}
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="px-2 py-1 bg-red-500 text-white rounded text-xs hover:bg-red-600 disabled:opacity-50"
            >
              {deleting ? t("apiKey.deleting") : t("apiKey.confirmDelete")}
            </button>
          </div>
        ) : (
          <button
            onClick={() => setShowConfirm(true)}
            className="text-red-500 hover:text-red-700 text-xs font-medium"
          >
            {t("apiKey.delete")}
          </button>
        )}
      </div>
    </div>
  );
}
