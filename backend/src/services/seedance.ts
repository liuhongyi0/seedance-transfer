// ─────────────────────────────────────────────
// Seedance 2.0 视频生成服务
// 通过 muapi.ai API 提交文生视频 / 图生视频任务
// ─────────────────────────────────────────────

import { config } from '../config';
import { AspectRatio, Quality, VideoMode } from '../types';

interface SeedancePreFlightResponse {
  success?: boolean;
  status_code?: number;
  id?: string;
  request_id?: string;
  status?: string;
  output?: string[];
  outputs?: string[];
  error?: string;
  progress?: number;
}

interface SeedanceSubmitParams {
  prompt: string;
  imageBase64?: string;
  aspectRatio: AspectRatio;
  duration: number;
  quality: Quality;
}

/**
 * 提交文生视频任务
 */
export async function submitT2V(
  prompt: string,
  aspectRatio: AspectRatio = '16:9',
  duration: number = 5,
  quality: Quality = 'high'
): Promise<{ taskId: string }> {
  console.log(
    `[Seedance T2V] Submitting task: duration=${duration}s, ` +
    `quality=${quality}, aspect=${aspectRatio}`
  );

  return submitTask(config.muapi.seedanceT2V, {
    prompt,
    aspectRatio,
    duration,
    quality,
  });
}

/**
 * 提交图生视频任务
 */
export async function submitI2V(
  prompt: string,
  imageBase64: string,
  aspectRatio: AspectRatio = '16:9',
  duration: number = 5,
  quality: Quality = 'high'
): Promise<{ taskId: string }> {
  console.log(
    `[Seedance I2V] Submitting task: duration=${duration}s, ` +
    `quality=${quality}, aspect=${aspectRatio}`
  );

  return submitTask(config.muapi.seedanceI2V, {
    prompt,
    imageBase64,
    aspectRatio,
    duration,
    quality,
  });
}

/**
 * 轮询任务状态
 */
export async function pollTask(
  taskId: string
): Promise<{
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress: number;
  videoUrl?: string;
  error?: string;
}> {
  try {
    const response = await fetch(config.muapi.predictionResult(taskId), {
      headers: { 'x-api-key': config.muapiKey },
    });

    if (!response.ok) {
      console.warn(
        `[Seedance Poll] HTTP ${response.status} for task ${taskId}`
      );
      return { status: 'processing', progress: 0 };
    }

    const data = await response.json() as SeedancePreFlightResponse;

    // 映射 muapi 状态到我们的状态
    const statusMap: Record<string, 'queued' | 'processing' | 'completed' | 'failed'> = {
      queued: 'queued',
      processing: 'processing',
      running: 'processing',
      completed: 'completed',
      succeeded: 'completed',
      success: 'completed',
      failed: 'failed',
      error: 'failed',
    };

    const status = statusMap[data.status || ''] || 'processing';

    const videoUrl = data.outputs?.[0] || data.output?.[0];
    return {
      status,
      progress: data.progress || (status === 'completed' ? 100 : 0),
      videoUrl,
      error: data.error,
    };
  } catch (err: any) {
    console.error(`[Seedance Poll] Error: ${err.message}`);
    return { status: 'processing', progress: 0 };
  }
}

// ── 内部实现 ──────────────────────────────────

async function submitTask(
  endpoint: string,
  params: SeedanceSubmitParams
): Promise<{ taskId: string }> {
  if (!config.muapiKey) {
    throw new Error('MUAPI_KEY 未配置，无法调用 Seedance');
  }

  const body: Record<string, any> = {
    prompt: params.prompt,
    aspect_ratio: params.aspectRatio,
    duration: params.duration,
    quality: params.quality,
    output_format: 'mp4',
  };

  // 图生视频：传递参考图
  // muapi.ai 接受纯 base64，去除 data URI 前缀（如有）
  if (params.imageBase64) {
    const raw = params.imageBase64;
    body.image = raw.includes(',') ? raw.split(',')[1] : raw;
  }

  const startTime = Date.now();

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': config.muapiKey,
      },
      body: JSON.stringify(body),
    });

    const responseText = await response.text();
    let data: SeedancePreFlightResponse;

    try {
      data = JSON.parse(responseText);
    } catch {
      throw new Error(
        `Seedance API 返回非 JSON (HTTP ${response.status}): ${responseText.substring(0, 200)}`
      );
    }

    const elapsed = Date.now() - startTime;

    if (!response.ok) {
      const errorMsg = `HTTP ${response.status}: ${responseText.substring(0, 200)}`;
      console.error(`[Seedance] Submit failed in ${elapsed}ms:`, errorMsg);
      throw new Error(`Seedance 提交失败: ${errorMsg}`);
    }

    const taskId = data.id || data.request_id;
    if (!taskId) {
      throw new Error(`Seedance 未返回 task_id (response: ${responseText.substring(0, 200)})`);
    }

    console.log(
      `[Seedance] Task submitted in ${elapsed}ms, task_id=${taskId}, status=${data.status}`
    );
    return { taskId };
  } catch (err: any) {
    if (err.message.startsWith('Seedance ')) {
      throw err;
    }
    throw new Error(`Seedance API 调用失败: ${err.message}`);
  }
}
