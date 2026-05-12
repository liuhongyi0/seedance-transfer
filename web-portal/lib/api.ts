import {getToken, removeToken} from "./utils";
import type {
  User,
  ApiKey,
  Balance,
  UsageLog,
  UsageListParams,
  PaginatedResponse,
} from "@/types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:3000";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Convert backend snake_case usage record to frontend camelCase */
function normalizeUsageLog(raw: any): UsageLog {
  return {
    id: raw.id,
    service: raw.service,
    units: raw.units,
    costFen: raw.cost_fen,
    status: raw.status,
    createdAt: raw.created_at,
  };
}

/** Convert backend snake_case ApiKey to frontend camelCase */
function normalizeApiKey(raw: any): ApiKey {
  return {
    id: raw.id,
    name: raw.name,
    keyPrefix: raw.key_prefix,
    isActive: raw.is_active,
    createdAt: raw.created_at,
    lastUsedAt: raw.last_used_at ?? undefined,
  };
}

/** Convert backend snake_case Balance to frontend camelCase */
function normalizeBalance(raw: any): Balance {
  return {
    amountFen: raw.amount_fen,
    amountYuan: raw.amount_yuan,
    currency: raw.currency,
  };
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    removeToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    // Throw with a key that components can use for i18n
    throw new ApiError("Authentication expired, please log in again", 401);
  }

  // 204 No Content — return empty object (e.g. DELETE /api/keys/:id)
  if (res.status === 204) {
    return {} as T;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message =
      body.message || body.error || `Request failed (${res.status})`;
    throw new ApiError(message, res.status);
  }

  return res.json();
}

export const api = {
  /** Login with phone + password, returns { access_token, token_type } */
  login(phone: string, password: string): Promise<{access_token: string; token_type: string}> {
    return request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({phone, password}),
    });
  },

  /** Register (backend expects snake_case: sms_code) */
  register(
    phone: string,
    password: string,
    smsCode: string
  ): Promise<{message: string}> {
    return request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({phone, password, sms_code: smsCode}),
    });
  },

  /** Send SMS verification code */
  sendSms(phone: string): Promise<{message: string}> {
    return request("/api/auth/sms", {
      method: "POST",
      body: JSON.stringify({phone}),
    });
  },

  /** Send email verification code */
  sendEmailCode(email: string): Promise<{message: string}> {
    return request("/api/auth/email/send-code", {
      method: "POST",
      body: JSON.stringify({email}),
    });
  },

  /** Login with email + password */
  emailLogin(email: string, password: string): Promise<{access_token: string; token_type: string}> {
    return request("/api/auth/email/login", {
      method: "POST",
      body: JSON.stringify({email, password}),
    });
  },

  /** Register with email + password + code */
  emailRegister(email: string, password: string, code: string): Promise<{user_id: string; message: string}> {
    return request("/api/auth/email/register", {
      method: "POST",
      body: JSON.stringify({email, password, code}),
    });
  },

  /** Get API key list (backend returns { keys: [...] } with snake_case fields) */
  async getKeys(): Promise<ApiKey[]> {
    const res = await request<{keys: any[]}>("/api/keys");
    return (res.keys || []).map(normalizeApiKey);
  },

  /** Create a new API key (backend returns { key, detail } with snake_case fields) */
  async createKey(name: string): Promise<ApiKey & {key: string}> {
    const res = await request<{key: string; detail: any}>("/api/keys", {
      method: "POST",
      body: JSON.stringify({name}),
    });
    return {...normalizeApiKey(res.detail), key: res.key};
  },

  /** Delete API key (backend returns 204 No Content) */
  async deleteKey(id: string): Promise<void> {
    await request(`/api/keys/${id}`, {method: "DELETE"});
  },

  /** Get balance (backend returns snake_case: amount_fen, amount_yuan, currency) */
  async getBalance(): Promise<Balance> {
    const raw = await request<any>("/api/balance");
    return normalizeBalance(raw);
  },

  /** Get usage log list (backend returns snake_case { total, page, items }) */
  async getUsage(
    params: UsageListParams = {}
  ): Promise<PaginatedResponse<UsageLog>> {
    const searchParams = new URLSearchParams();
    if (params.service) searchParams.set("service", params.service);
    if (params.page) searchParams.set("page", String(params.page));
    if (params.pageSize) searchParams.set("page_size", String(params.pageSize));
    const qs = searchParams.toString();
    const res = await request<{total: number; page: number; items: any[]}>(
      `/api/usage${qs ? `?${qs}` : ""}`
    );
    return {
      data: (res.items || []).map(normalizeUsageLog),
      total: res.total,
      page: res.page,
      pageSize: params.pageSize || 20,
      totalPages: Math.ceil(res.total / (params.pageSize || 20)),
    };
  },

  /** Get user profile (reuses balance endpoint for balance) */
  async getProfile(): Promise<User> {
    const raw = await request<any>("/api/balance");
    const balance = normalizeBalance(raw);
    const stored = localStorage.getItem("seedance_user");
    if (stored) {
      const user = JSON.parse(stored) as User;
      user.balanceFen = balance.amountFen;
      return user;
    }
    return {
      id: "",
      phone: "",
      balanceFen: balance.amountFen,
    };
  },

  /** Get recharge packages list */
  getPackages(): Promise<{packages: Array<{key: string; price: number; fenAmount: number; currency: string}>}> {
    return request("/api/payment/packages");
  },

  /** Create payment order */
  createOrder(
    packageKey: string,
    payType: 'alipay' | 'wechat'
  ): Promise<{
    order_id: string;
    pay_url: string;
    qr_code: string | null;
    amount: number;
    fen_amount: number;
    currency: string;
  }> {
    return request("/api/payment/create", {
      method: "POST",
      body: JSON.stringify({ package_key: packageKey, pay_type: payType }),
    });
  },
};
