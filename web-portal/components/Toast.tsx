"use client";

import {useState, useEffect, useCallback, createContext, useContext} from "react";
import {useTranslations} from "next-intl";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextType {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextType>({
  showToast: () => {},
});

let toastId = 0;

export function ToastProvider({children}: {children: React.ReactNode}) {
  const t = useTranslations();
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++toastId;
    setToasts((prev) => [...prev, {id, message, type}]);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{showToast}}>
      {children}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <ToastItem
            key={toast.id}
            toast={toast}
            onRemove={() => removeToast(toast.id)}
            closeLabel={t("toast.close")}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({
  toast,
  onRemove,
  closeLabel,
}: {
  toast: Toast;
  onRemove: () => void;
  closeLabel: string;
}) {
  useEffect(() => {
    const timer = setTimeout(onRemove, 3000);
    return () => clearTimeout(timer);
  }, [onRemove]);

  const bgColor = {
    success: "bg-green-500",
    error: "bg-red-500",
    info: "bg-blue-500",
  }[toast.type];

  const icon = {
    success: "✓",
    error: "✕",
    info: "ℹ",
  }[toast.type];

  return (
    <div
      className={`${bgColor} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 min-w-[280px] animate-slide-in`}
      role="alert"
    >
      <span className="text-lg font-bold">{icon}</span>
      <span className="flex-1 text-sm">{toast.message}</span>
      <button
        onClick={onRemove}
        className="text-white/80 hover:text-white ml-2"
        aria-label={closeLabel}
      >
        {"×"}
      </button>
    </div>
  );
}

export function useToast(): ToastContextType {
  return useContext(ToastContext);
}
