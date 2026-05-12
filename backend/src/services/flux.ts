// ─────────────────────────────────────────────
// 预览图生成服务
// 主路由: 阿里云 DashScope 通义万象 (wanx2.1-t2i-turbo)
// 备用路由: fal.ai Flux-Schnell（当 DashScope 失败时）
// ─────────────────────────────────────────────

import { config } from '../config';

// ── DashScope Wanx 响应结构 ────────────────────

interface WanxSubmitResponse {
  request_id: string;
  output: {
    task_id: string;
    task_status: string;
  };
  code?: string;
  message?: string;
}

interface WanxPollResponse {
  request_id: string;
  output: {
    task_id: string;
    task_status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN';
    results?: Array<{ url: string; orig_url?: string }>;
    code?: string;
    message?: string;
  };
  usage?: { image_count: number };
}

// ── fal.ai 备用响应结构 ────────────────────────

interface FalResponse {
  images?: Array<{ url: string; width: number; height: number }>;
  request_id?: string;
  status?: string;
  detail?: string;
}

// ── 尺寸映射 ──────────────────────────────────

// DashScope Wanx: "宽*高"
const WANX_SIZE_MAP: Record<string, string> = {
  '16:9': '1280*720',
  '9:16': '720*1280',
  '1:1':  '1024*1024',
  '4:3':  '1024*768',
  '3:4':  '768*1024',
};

// fal.ai image_size 名称（备用）
const FAL_SIZE_MAP: Record<string, string> = {
  '16:9': 'landscape_16_9',
  '9:16': 'portrait_9_16',
  '1:1':  'square_hd',
  '4:3':  'landscape_4_3',
  '3:4':  'portrait_4_3',
};

// DashScope 图片生成接口地址
const WANX_SUBMIT_URL =
  'https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis';
const WANX_TASK_URL =
  'https://dashscope.aliyuncs.com/api/v1/tasks';

/**
 * 生成预览图
 * 主路由: 阿里云通义万象 wanx2.1-t2i-turbo
 * 备用路由: fal.ai Flux-Schnell
 */
export async function generatePreview(
  prompt: string,
  aspectRatio: string = '16:9'
): Promise<{ imageUrl: string }> {

  // ── 1. 主路由: DashScope Wanx ──────────────
  if (config.dashscopeApiKey) {
    try {
      return await generatePreviewViaWanx(prompt, aspectRatio);
    } catch (err: any) {
      console.warn(`[Preview] DashScope Wanx 失败，切换 fal.ai: ${err.message}`);
    }
  } else {
    console.warn('[Preview] DASHSCOPE_API_KEY 未配置，跳过 Wanx，尝试 fal.ai');
  }

  // ── 2. 备用路由: fal.ai ─────────────────────
  if (config.falKey) {
    return await generatePreviewViaFal(prompt, aspectRatio);
  }

  throw new Error('DASHSCOPE_API_KEY 和 FAL_KEY 均未配置，无法生成预览图');
}

// ══════════════════════════════════════════════
// 阿里云通义万象实现
// ══════════════════════════════════════════════

async function generatePreviewViaWanx(
  prompt: string,
  aspectRatio: string
): Promise<{ imageUrl: string }> {
  const size = WANX_SIZE_MAP[aspectRatio] || '1280*720';
  const startTime = Date.now();

  console.log(
    `[Preview/Wanx] Generating preview, size=${size}, prompt length=${prompt.length}`
  );

  // Step 1: 提交任务
  const submitResp = await fetch(WANX_SUBMIT_URL, {
    method: 'POST',
    headers: {
      'Content-Type':    'application/json',
      'Authorization':   `Bearer ${config.dashscopeApiKey}`,
      'X-DashScope-Async': 'enable',
    },
    body: JSON.stringify({
      model: 'wanx2.1-t2i-turbo',
      input: {
        prompt,
        negative_prompt: 'blurry, low quality, distorted, text, watermark',
      },
      parameters: {
        size,
        n: 1,
      },
    }),
  });

  if (!submitResp.ok) {
    const errText = await submitResp.text();
    console.error(`[Preview/Wanx] Submit HTTP ${submitResp.status}: ${errText.substring(0, 300)}`);
    throw new Error(`Wanx 提交失败 (HTTP ${submitResp.status}): ${errText.substring(0, 200)}`);
  }

  const submitData = await submitResp.json() as WanxSubmitResponse;

  if (submitData.code) {
    throw new Error(`Wanx 提交错误: ${submitData.code} — ${submitData.message}`);
  }

  const taskId = submitData.output?.task_id;
  if (!taskId) {
    throw new Error(`Wanx 未返回 task_id，响应: ${JSON.stringify(submitData).substring(0, 200)}`);
  }

  console.log(`[Preview/Wanx] Task submitted: ${taskId}`);

  // Step 2: 轮询结果（最多等 60s，每 3s 查一次）
  const imageUrl = await pollWanxTask(taskId);
  const elapsed  = Date.now() - startTime;

  console.log(`[Preview/Wanx] Ready in ${elapsed}ms → ${imageUrl.substring(0, 80)}...`);
  return { imageUrl };
}

async function pollWanxTask(
  taskId: string,
  maxWaitMs: number = 60_000,
  intervalMs: number = 3_000
): Promise<string> {
  const startTime = Date.now();

  while (Date.now() - startTime < maxWaitMs) {
    await sleep(intervalMs);

    const resp = await fetch(`${WANX_TASK_URL}/${taskId}`, {
      headers: { 'Authorization': `Bearer ${config.dashscopeApiKey}` },
    });

    if (!resp.ok) {
      console.warn(`[Preview/Wanx Poll] HTTP ${resp.status}, retrying...`);
      continue;
    }

    const data = await resp.json() as WanxPollResponse;
    const status = data.output?.task_status;

    console.log(`[Preview/Wanx Poll] task=${taskId} status=${status}`);

    if (status === 'SUCCEEDED') {
      const url = data.output?.results?.[0]?.url;
      if (url) return url;
      throw new Error(`Wanx SUCCEEDED 但未返回图片 URL，响应: ${JSON.stringify(data.output).substring(0, 200)}`);
    }

    if (status === 'FAILED') {
      const code = data.output?.code || 'unknown';
      const msg  = data.output?.message || 'unknown';
      throw new Error(`Wanx 任务失败: ${code} — ${msg}`);
    }

    // PENDING / RUNNING → 继续等待
  }

  throw new Error(`Wanx 预览超时: task ${taskId} 在 ${maxWaitMs}ms 内未完成`);
}

// ══════════════════════════════════════════════
// fal.ai 备用实现（保留，以防万一）
// ══════════════════════════════════════════════

async function generatePreviewViaFal(
  prompt: string,
  aspectRatio: string
): Promise<{ imageUrl: string }> {
  const imageSize = FAL_SIZE_MAP[aspectRatio] || 'landscape_16_9';
  const startTime = Date.now();

  console.log(
    `[Preview/fal.ai] Generating preview, size=${imageSize}, prompt length=${prompt.length}`
  );

  const response = await fetch('https://fal.run/fal-ai/flux/schnell', {
    method: 'POST',
    headers: {
      'Content-Type':  'application/json',
      'Authorization': `Key ${config.falKey}`,
    },
    body: JSON.stringify({
      prompt,
      image_size:             imageSize,
      num_images:             1,
      num_inference_steps:    4,
      enable_safety_checker:  false,
      sync_mode:              true,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error(`[Preview/fal.ai] HTTP ${response.status}: ${errorText.substring(0, 300)}`);
    throw new Error(`fal.ai HTTP ${response.status}: ${errorText.substring(0, 200)}`);
  }

  const data = await response.json() as FalResponse;
  const elapsed = Date.now() - startTime;

  if (data.images && data.images.length > 0 && data.images[0].url) {
    const imageUrl = data.images[0].url;
    console.log(`[Preview/fal.ai] Ready in ${elapsed}ms → ${imageUrl.substring(0, 80)}...`);
    return { imageUrl };
  }

  // 异步队列模式（sync_mode=false 时走这里）
  if (data.request_id) {
    const imageUrl = await pollFalResult(data.request_id);
    return { imageUrl };
  }

  throw new Error(
    `fal.ai 未返回有效图片，响应: ${JSON.stringify(data).substring(0, 200)}`
  );
}

async function pollFalResult(
  requestId: string,
  maxWaitMs: number = 30_000,
  intervalMs: number = 1_000
): Promise<string> {
  const startTime = Date.now();

  while (Date.now() - startTime < maxWaitMs) {
    await sleep(intervalMs);

    try {
      const response = await fetch(
        `https://queue.fal.run/fal-ai/flux/schnell/requests/${requestId}`,
        { headers: { 'Authorization': `Key ${config.falKey}` } }
      );
      if (!response.ok) continue;

      const data = await response.json() as FalResponse;
      if (data.images && data.images.length > 0 && data.images[0].url) {
        return data.images[0].url;
      }
      if (data.status === 'FAILED') {
        throw new Error(`fal.ai task ${requestId} failed: ${data.detail || 'unknown'}`);
      }
    } catch (err: any) {
      if (err.message.startsWith('fal.ai task')) throw err;
      console.warn(`[Preview/fal.ai Poll] ${err.message}`);
    }
  }

  throw new Error(`fal.ai 预览超时: request ${requestId} 在 ${maxWaitMs}ms 内未完成`);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
