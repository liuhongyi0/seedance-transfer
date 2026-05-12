export interface User {
  id: string;
  phone: string;
  displayName?: string;
  balanceFen: number;
}

export interface ApiKey {
  id: string;
  name: string;
  keyPrefix: string;
  isActive: boolean;
  createdAt: string;
  lastUsedAt?: string;
}

export interface Balance {
  amountFen: number;
  amountYuan: number;
  currency?: string;   // "CNY" 国内版 / "USD" 海外版
}

export type ServiceType =
  | "deepseek"
  | "qwen_vl"
  | "flux_preview"
  | "seedance_t2v"
  | "seedance_i2v";

export const SERVICE_LABELS: Record<ServiceType, string> = {
  deepseek: "DeepSeek导演",
  qwen_vl: "Qwen看图",
  flux_preview: "Flux预览",
  seedance_t2v: "Seedance文生视频",
  seedance_i2v: "Seedance图生视频",
};

export interface UsageLog {
  id: string;
  service: ServiceType;
  units: number;
  costFen: number;
  status: "success" | "failed" | "refunded" | "pending";
  createdAt: string;
}

export const STATUS_LABELS: Record<string, string> = {
  success: "成功",
  failed: "失败",
  refunded: "退款",
  pending: "处理中",
};

export const STATUS_COLORS: Record<string, string> = {
  success: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  refunded: "bg-yellow-100 text-yellow-800",
  pending: "bg-blue-100 text-blue-800",
};

export interface Package {
  key: string;
  name: string;
  priceYuan: number;
  fenAmount: number;
  recommended?: boolean;
  description?: string;
}

export const RECHARGE_PACKAGES: Package[] = [
  {
    key: "lite",
    name: "体验包",
    priceYuan: 9.9,
    fenAmount: 1000,
    description: "适合初次体验",
  },
  {
    key: "standard",
    name: "标准包",
    priceYuan: 49,
    fenAmount: 6000,
    description: "约 38 个 5s 视频",
  },
  {
    key: "pro",
    name: "专业包",
    priceYuan: 99,
    fenAmount: 15000,
    recommended: true,
    description: "约 96 个 5s 视频",
  },
  {
    key: "max",
    name: "旗舰包",
    priceYuan: 299,
    fenAmount: 50000,
    description: "约 322 个 5s 视频",
  },
];

export interface PaymentMethod {
  type: 'alipay' | 'wechat';
  name: string;
  icon: string;
  enabled: boolean;
}

export interface CreateOrderResponse {
  order_id: string;
  pay_url: string;
  qr_code: string | null;
  amount: number;
  fen_amount: number;
  currency: string;
}

export interface UsageListParams {
  service?: ServiceType;
  page?: number;
  pageSize?: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}
