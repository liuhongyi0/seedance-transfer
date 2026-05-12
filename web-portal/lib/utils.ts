/**
 * Convert fen (分) to yuan (元) string, 2 decimal places
 */
export function fenToYuan(fen: number): string {
  return (fen / 100).toFixed(2);
}

/**
 * Convert fen (分) to yuan (元) as number
 */
export function fenToYuanNum(fen: number): number {
  return Math.round(fen) / 100;
}

/**
 * Format ISO datetime string to locale-aware local string
 */
export function formatDateTime(isoStr: string, locale: string = "zh-CN"): string {
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(isoStr));
}

/**
 * Format ISO date string (date only, no time)
 */
export function formatDate(isoStr: string, locale: string = "zh-CN"): string {
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(isoStr));
}

/**
 * Mask API Key: show first 12 chars, rest replaced with ****
 * e.g. sk-seed-ab12cd34ef567890... -> sk-seed-ab12****
 */
export function maskApiKey(prefix: string): string {
  if (prefix.length <= 12) return prefix + "****";
  return prefix.slice(0, 12) + "****";
}

/**
 * Mask phone number: show first 3 and last 3 digits, middle ****
 */
export function maskPhone(phone: string): string {
  if (phone.length !== 11) return phone;
  return phone.slice(0, 3) + "****" + phone.slice(8);
}

/**
 * Translation maps for relative time (used when Intl not available or fallback)
 */
const RELATIVE_TIME_MAP: Record<string, {
  justNow: string;
  minutesAgo: (n: number) => string;
  hoursAgo: (n: number) => string;
  daysAgo: (n: number) => string;
}> = {
  "zh-CN": {
    justNow: "刚刚",
    minutesAgo: (n) => `${n} 分钟前`,
    hoursAgo: (n) => `${n} 小时前`,
    daysAgo: (n) => `${n} 天前`,
  },
  "en-US": {
    justNow: "just now",
    minutesAgo: (n) => `${n}m ago`,
    hoursAgo: (n) => `${n}h ago`,
    daysAgo: (n) => `${n}d ago`,
  },
};

/**
 * Get relative time description, locale-aware.
 */
export function relativeTime(isoStr: string, locale: string = "zh-CN"): string {
  const now = Date.now();
  const then = new Date(isoStr).getTime();
  const diffSec = Math.floor((now - then) / 1000);

  const map = RELATIVE_TIME_MAP[locale] || RELATIVE_TIME_MAP["zh-CN"];

  if (diffSec < 60) return map.justNow;
  if (diffSec < 3600) return map.minutesAgo(Math.floor(diffSec / 60));
  if (diffSec < 86400) return map.hoursAgo(Math.floor(diffSec / 3600));
  if (diffSec < 2592000) return map.daysAgo(Math.floor(diffSec / 86400));
  return formatDate(isoStr, locale);
}

/**
 * Validate phone number format: Chinese mobile (1[3-9] followed by 9 digits)
 * Matches backend validation: /^1[3-9]\d{9}$/
 */
export function isValidPhone(phone: string): boolean {
  return /^1[3-9]\d{9}$/.test(phone);
}

/**
 * Validate email format
 */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Get JWT token from localStorage
 */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("seedance_token");
}

/**
 * Set JWT token in localStorage
 */
export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("seedance_token", token);
}

/**
 * Clear JWT token and user from localStorage
 */
export function removeToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("seedance_token");
  localStorage.removeItem("seedance_user");
}

/**
 * Get stored user info
 */
export function getStoredUser(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("seedance_user");
}

/**
 * Store user info in localStorage
 */
export function setStoredUser(userJson: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("seedance_user", userJson);
}
