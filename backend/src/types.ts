// ─────────────────────────────────────────────
// Seedance Wizard — TypeScript Type Definitions
// 严格遵循 contract/api-spec.yaml
// ─────────────────────────────────────────────

// ── 通用 ──────────────────────────────────────

export interface ErrorResponse {
  code: string;
  message: string;
}

// ── 用户 & 认证 ────────────────────────────────

export interface User {
  id: string;
  phone?: string | null;
  email?: string | null;
  google_id?: string | null;
  avatar_url?: string | null;
  password_hash?: string;
  display_name?: string | null;
  auth_provider?: string;
  is_active: boolean;
  created_at: string;
}

/** Full user record matching the DB users table structure */
export type UserRecord = User;

export interface RegisterRequest {
  phone: string;
  password: string;
  sms_code: string;
}

export interface RegisterResponse {
  user_id: string;
  message: string;
}

export interface LoginRequest {
  phone: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'Bearer';
}

export interface SmsRequest {
  phone: string;
}

export interface SmsResponse {
  message: string;
}

export interface GoogleLoginRequest {
  id_token: string;
}

export interface EmailRegisterRequest {
  email: string;
  password: string;
}

export interface EmailLoginRequest {
  email: string;
  password: string;
}

// ── API Key ───────────────────────────────────

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface CreateKeyRequest {
  name?: string;
}

export interface CreateKeyResponse {
  key: string;
  detail: ApiKey;
}

export interface KeyListResponse {
  keys: ApiKey[];
}

// ── 余额 & 用量 ───────────────────────────────

export interface BalanceResponse {
  amount_fen: number;
  amount: number;
  currency: string;
}

export interface UsageLogItem {
  id: string;
  service: ServiceType;
  units: number;
  cost_fen: number;
  status: LogStatus;
  created_at: string;
}

export interface UsageListResponse {
  total: number;
  page: number;
  items: UsageLogItem[];
}

export type ServiceType =
  | 'deepseek'
  | 'qwen_vl'
  | 'flux_preview'
  | 'seedance_t2v'
  | 'seedance_i2v';

export type LogStatus = 'pending' | 'success' | 'failed' | 'refunded';

// ── 向导流程 ──────────────────────────────────

export interface FilterParams {
  warmth?: number;     // -1 ~ 1
  brightness?: number; // -1 ~ 1
  blur?: number;       //  0 ~ 1
  contrast?: number;   // -1 ~ 1
  saturation?: number; // -1 ~ 1
}

// ─── 结构化 Prompt 参数（新向导核心）────────────

export type PromptStyle = 'cinematic' | 'commercial' | 'documentary' | 'social_media' | 'artistic';
export type PromptLighting = 'bright_daylight' | 'golden_hour' | 'soft_diffused' | 'dramatic_shadows' | 'neon_night';
export type PromptShotType = 'close_up' | 'medium_shot' | 'wide_shot' | 'aerial_view' | 'low_angle';
export type PromptMood = 'energetic' | 'serene' | 'mysterious' | 'joyful' | 'dramatic';
export type PromptColorTone = 'warm' | 'cool' | 'vibrant' | 'muted' | 'monochrome';

export interface PromptParams {
  // 分类参数（下拉框）
  style: PromptStyle;
  lighting: PromptLighting;
  shot_type: PromptShotType;
  mood: PromptMood;
  color_tone: PromptColorTone;
  // 数值参数（滑块 0–100）
  motion_intensity: number;   // 0=static → 100=kinetic
  depth_of_field: number;     // 0=pan focus → 100=extreme bokeh
  detail_richness: number;    // 0=minimal → 100=hyperdetailed
  saturation_level: number;   // 0=desaturated → 100=hyper-vivid
}

// ─── 向导 — 分析请求 ────────────────────────────

export interface WizardAnalyzeRequest {
  image_b64: string;        // 原图 base64（含 data URI 前缀）
  user_idea: string;        // 用户的简单想法（中文）
  aspect_ratio?: '16:9' | '9:16' | '1:1' | '4:3' | '3:4';
}

export interface WizardAnalyzeResponse {
  session_id: string;
  base_description: string;   // Qwen VL 提炼的图片描述（英文）
  creative_rationale: string; // DeepSeek 创作思路说明（中文）
  initial_params: PromptParams;
  composed_prompt: string;    // 合成后的完整英文 prompt
  preview_url: string | null;  // Flux 预览图 URL（失败时为 null）
  cost_fen: number;
  balance_after: number;
}

// ─── 向导 — 参数预览请求（替换旧 preview）──────

export interface WizardParamPreviewRequest {
  session_id: string;
  params: PromptParams;
  aspect_ratio?: '16:9' | '9:16' | '1:1' | '4:3' | '3:4';
}

export interface WizardParamPreviewResponse {
  preview_url: string | null;  // Flux 预览图 URL（失败时为 null）
  composed_prompt: string;
  cost_fen: number;
  balance_after: number;
}

export interface WizardStartRequest {
  intent: string;
  image_b64?: string | null;
  language?: 'zh' | 'en';
}

export interface SuggestedOption {
  label: string;
  value: string;
}

export interface WizardStartResponse {
  session_id: string;
  director_message: string;
  suggested_options: SuggestedOption[];
  current_prompt: string;
  image_analyzed: boolean;
  balance_after: number;
}

export interface WizardMessageRequest {
  session_id: string;
  message: string;
  css_params?: FilterParams | null;
}

export interface WizardMessageResponse {
  director_message: string;
  current_prompt: string;
  suggested_options: SuggestedOption[];
}

export interface WizardPreviewRequest {
  session_id: string;
  prompt_override?: string | null;
  aspect_ratio?: '16:9' | '9:16' | '1:1' | '4:3' | '3:4';
}

export interface WizardPreviewResponse {
  preview_url: string | null;  // Flux 预览图 URL（失败时为 null）
  cost_fen: number;
  balance_after: number;
}

// ── 视频生成 ──────────────────────────────────

export type VideoMode = 'text_to_video' | 'image_to_video';
export type Quality = 'basic' | 'high';
export type AspectRatio = '16:9' | '9:16' | '1:1' | '4:3' | '3:4' | '21:9';
export type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed';

export interface VideoGenerateRequest {
  session_id: string;
  mode: VideoMode;
  prompt_override?: string | null;
  image_b64?: string | null;
  aspect_ratio?: AspectRatio;
  duration?: number;
  quality?: Quality;
}

export interface VideoGenerateResponse {
  task_id: string;
  estimated_cost_fen: number;
  estimated_seconds: number;
  balance_after: number;
}

export interface VideoTaskStatus {
  task_id: string;
  status: TaskStatus;
  progress: number;
  video_url: string | null;
  estimated_cost_fen: number;
  actual_cost_fen: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface VideoTaskResult {
  video_url: string;
  duration_ms: number;
  actual_cost_fen: number;
}

// ── 费用预估 ──────────────────────────────────

export interface EstimateRequest {
  mode: VideoMode;
  duration: number;
  quality: Quality;
}

export interface EstimateResponse {
  cost_fen: number;
  cost_yuan: number;
}

// ── 定价 ──────────────────────────────────────

export interface PricingConfig {
  // 国内版（fen）
  deepseek_input_per_1m_fen: number;
  deepseek_output_per_1m_fen: number;
  qwen_vl_per_1m_fen: number;
  flux_preview_per_image_fen: number;
  seedance_t2v_basic_per_sec_fen: number;
  seedance_t2v_high_per_sec_fen: number;
  seedance_i2v_basic_per_sec_fen: number;
  seedance_i2v_high_per_sec_fen: number;
  // 海外版（subunit，美分 cents）
  deepseek_input_per_1m_subunit?: number;
  deepseek_output_per_1m_subunit?: number;
  qwen_vl_per_1m_subunit?: number;
  flux_preview_per_image_subunit?: number;
  seedance_t2v_basic_per_sec_subunit?: number;
  seedance_t2v_high_per_sec_subunit?: number;
  seedance_i2v_basic_per_sec_subunit?: number;
  seedance_i2v_high_per_sec_subunit?: number;
  currency?: string;
}

// ── Express 扩展 ──────────────────────────────

export interface AuthenticatedUser {
  userId: string;
  apiKeyId?: string;
  balanceFen: number;
}

declare global {
  namespace Express {
    interface Request {
      user?: AuthenticatedUser;
      requestId?: string;
    }
  }
}

// ── DeepSeek 导演对话消息 ─────────────────────

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  name?: string;
  tool_call_id?: string;
  tool_calls?: ToolCall[];
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

// ── 向导会话（DB 记录）────────────────────────

export interface WizardSessionRecord {
  id: string;
  user_id: string;
  messages: ChatMessage[];
  current_prompt: string | null;
  image_ref: string | null;
  last_task_id: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
}

// ── 视频任务（DB 记录）────────────────────────

export interface VideoTaskRecord {
  id: string;
  user_id: string;
  usage_log_id: string | null;
  upstream_task_id: string;
  status: TaskStatus;
  progress: number;
  mode: VideoMode;
  prompt: string;
  aspect_ratio: string;
  duration_seconds: number;
  quality: string;
  video_url: string | null;
  error_message: string | null;
  estimated_cost_fen: number;
  actual_cost_fen: number | null;
  created_at: string;
  completed_at: string | null;
}
