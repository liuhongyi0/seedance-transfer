"use client";

import {useState, useEffect, useCallback} from "react";
import {useTranslations} from "next-intl";
import ProtectedRoute from "@/components/ProtectedRoute";
import Navbar from "@/components/Navbar";
import Sidebar from "@/components/Sidebar";
import ApiKeyCard from "@/components/ApiKeyCard";
import {useToast} from "@/components/Toast";
import {api} from "@/lib/api";
import type {ApiKey} from "@/types";

export default function KeysPage() {
  return (
    <ProtectedRoute>
      <KeysContent />
    </ProtectedRoute>
  );
}

function KeysContent() {
  const t = useTranslations();
  const {showToast} = useToast();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Create Key modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [creating, setCreating] = useState(false);

  // Show full Key modal
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [fullKey, setFullKey] = useState("");

  const fetchKeys = useCallback(async () => {
    try {
      const data = await api.getKeys();
      setKeys(data);
    } catch {
      showToast(t("keys.toastFetchFailed"), "error");
    } finally {
      setLoading(false);
    }
  }, [showToast, t]);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async () => {
    if (!newKeyName.trim()) {
      showToast(t("keys.toastNameRequired"), "error");
      return;
    }
    setCreating(true);
    try {
      const result = await api.createKey(newKeyName.trim());
      setShowCreateModal(false);
      setNewKeyName("");
      setFullKey(result.key);
      setShowKeyModal(true);
      await fetchKeys();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : t("keys.toastCreateFailed");
      showToast(message, "error");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await api.deleteKey(id);
      showToast(t("keys.toastDeleted"), "success");
      setKeys((prev) => prev.filter((k) => k.id !== id));
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : t("keys.toastDeleteFailed");
      showToast(message, "error");
    } finally {
      setDeletingId(null);
    }
  };

  const copyKey = () => {
    navigator.clipboard.writeText(fullKey).then(
      () => showToast(t("keys.toastCopied"), "success"),
      () => showToast(t("keys.toastCopyFailed"), "error")
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <Sidebar />

      <main className="pt-14 lg:pl-[220px]">
        <div className="p-4 lg:p-6 max-w-4xl mx-auto space-y-6">
          {/* Page title */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {t("keys.title")}
              </h1>
              <p className="text-gray-500 text-sm mt-1">
                {t("keys.subtitle")}
              </p>
            </div>
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-600 transition-colors"
            >
              {t("keys.createNew")}
            </button>
          </div>

          {/* Key list */}
          {loading ? (
            <div className="bg-white rounded-card border border-gray-200 p-8 text-center">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-gray-500 text-sm">{t("keys.loading")}</p>
            </div>
          ) : keys.length === 0 ? (
            <div className="bg-white rounded-card border border-gray-200 p-12 text-center">
              <div className="text-4xl mb-3">{"🔑"}</div>
              <p className="text-gray-500">{t("keys.empty")}</p>
              <p className="text-gray-400 text-xs mt-1">
                {t("keys.emptyHint")}
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="mt-4 px-4 py-2 bg-primary text-white rounded-lg text-sm hover:bg-primary-600 transition-colors"
              >
                {t("keys.createFirst")}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {keys.map((key) => (
                <ApiKeyCard
                  key={key.id}
                  apiKey={key}
                  onDelete={handleDelete}
                  deleting={deletingId === key.id}
                />
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Create Key modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-card shadow-xl p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t("keys.modalCreateTitle")}
            </h2>
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="keyName"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  {t("keys.nameLabel")}
                </label>
                <input
                  id="keyName"
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder={t("keys.namePlaceholder")}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  autoFocus
                />
              </div>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => {
                    setShowCreateModal(false);
                    setNewKeyName("");
                  }}
                  className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm hover:bg-gray-50 transition-colors"
                >
                  {t("common.cancel")}
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating}
                  className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-600 transition-colors disabled:opacity-50"
                >
                  {creating ? t("keys.creating") : t("keys.confirmCreate")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Show full Key modal */}
      {showKeyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-card shadow-xl p-6 w-full max-w-lg">
            <div className="text-center mb-4">
              <div className="text-3xl mb-2">{"⚠️"}</div>
              <h2 className="text-lg font-semibold text-gray-900">
                {t("keys.modalRevealTitle")}
              </h2>
              <p className="text-sm text-red-600 mt-1 font-medium">
                {t("keys.modalRevealWarning")}
              </p>
            </div>

            <div className="bg-gray-100 rounded-lg p-4 mb-4">
              <code className="text-sm text-gray-900 break-all font-mono">
                {fullKey}
              </code>
            </div>

            <div className="flex gap-3">
              <button
                onClick={copyKey}
                className="flex-1 px-4 py-2.5 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent-600 transition-colors"
              >
                {t("keys.copyToClipboard")}
              </button>
              <button
                onClick={() => {
                  setShowKeyModal(false);
                  setFullKey("");
                }}
                className="flex-1 px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors"
              >
                {t("keys.savedClose")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
