// ─────────────────────────────────────────────
// 视频生成路由: /api/video
// POST /api/video/generate        — 提交视频生成任务
// GET  /api/video/:taskId/status  — 查询任务状态
// GET  /api/video/:taskId/result  — 获取视频结果
// ─────────────────────────────────────────────

import { Router, Request, Response, NextFunction } from 'express';
import { submitT2V, submitI2V, pollTask } from '../services/seedance';
import { estimateVideoCost, fenToYuan } from '../services/pricing';
import { query as dbQuery } from '../db/pool';
import {
  getWizardSession,
  updateWizardLastTask,
  createUsageLog,
  updateUsageLogStatus,
  deductBalance,
  refundBalance,
  getBalance,
  createVideoTask,
  updateVideoTask,
  getVideoTask,
  getVideoTasksByStatus,
} from '../db/queries';
import { config } from '../config';
import {
  VideoGenerateRequest,
  VideoGenerateResponse,
  VideoTaskStatus,
  VideoTaskResult,
  VideoMode,
  Quality,
  AspectRatio,
} from '../types';
import { AppError } from '../middleware/errorHandler';

const router = Router();

// ═══════════════════════════════════════════════
// 后台轮询管理器
// ═══════════════════════════════════════════════

interface PollEntry {
  intervalId: NodeJS.Timeout;
  startTime: number;
  upstreamTaskId: string;
  dbTaskId: string;
  userId: string;
  usageLogId: string;
  mode: VideoMode;
  quality: Quality;
}

const activePolls = new Map<string, PollEntry>();

/**
 * 启动后台轮询
 */
function startBackgroundPoll(
  dbTaskId: string,
  upstreamTaskId: string,
  userId: string,
  usageLogId: string,
  mode: VideoMode,
  quality: Quality
): void {
  const startTime = Date.now();
  let pollCount = 0;

  const intervalId = setInterval(async () => {
    pollCount++;

    // 超时检查
    if (Date.now() - startTime > config.maxPollTimeMs) {
      console.error(`[Video] Poll timeout for task ${dbTaskId} (upstream: ${upstreamTaskId})`);

      await updateVideoTask(dbTaskId, {
        status: 'failed',
        errorMessage: '视频生成超时，请重试',
      });

      await refundBalance(userId, 0, usageLogId);
      await updateUsageLogStatus(usageLogId, 'refunded', 0, 'Polling timeout');

      clearInterval(intervalId);
      activePolls.delete(dbTaskId);
      return;
    }

    try {
      const result = await pollTask(upstreamTaskId);

      // 更新进度
      if (result.progress > 0) {
        await updateVideoTask(dbTaskId, {
          status: 'processing',
          progress: result.progress,
        });
      }

      if (result.status === 'completed' && result.videoUrl) {
        console.log(
          `[Video] Task ${dbTaskId} completed after ${pollCount} polls ` +
          `(${((Date.now() - startTime) / 1000).toFixed(0)}s)`
        );

        // 计算实际费用（基于原始预估，实际可能需要根据真实时长调整）
        // 此处简化：按预估费用结算
        const task = await getVideoTask(dbTaskId);

        const actualCost = task?.estimated_cost_fen || 0;

        await updateVideoTask(dbTaskId, {
          status: 'completed',
          progress: 100,
          videoUrl: result.videoUrl,
          actualCostFen: actualCost,
        });

        // 写入实际费用（之前 cost_fen 以 0 pending，此处结算）
        await updateUsageLogStatus(usageLogId, 'success', actualCost);

        clearInterval(intervalId);
        activePolls.delete(dbTaskId);
        return;
      }

      if (result.status === 'failed') {
        console.error(
          `[Video] Task ${dbTaskId} failed: ${result.error || 'unknown'}`
        );

        const task = await getVideoTask(dbTaskId);
        const refundAmount = task?.estimated_cost_fen || 0;

        await updateVideoTask(dbTaskId, {
          status: 'failed',
          errorMessage: result.error || 'Seedance 生成失败',
        });

        await refundBalance(userId, refundAmount, usageLogId);
        await updateUsageLogStatus(
          usageLogId,
          'refunded',
          0,
          result.error || 'Seedance generation failed'
        );

        clearInterval(intervalId);
        activePolls.delete(dbTaskId);
        return;
      }
    } catch (err: any) {
      console.warn(
        `[Video] Poll #${pollCount} for task ${dbTaskId} error: ${err.message}`
      );
      // 继续轮询，不中断
    }
  }, config.pollIntervalMs);

  activePolls.set(dbTaskId, {
    intervalId,
    startTime,
    upstreamTaskId,
    dbTaskId,
    userId,
    usageLogId,
    mode,
    quality,
  });
}

/**
 * 恢复上次运行遗留的未完成轮询（server 启动时调用）
 * - 仍在超时窗口内: 恢复后台轮询
 * - 已超时: 标记失败 + 退款
 * 返回恢复的数量
 */
export async function recoverOrphanedPolls(): Promise<number> {
  try {
    const tasks = await getVideoTasksByStatus(['queued', 'processing']);
    if (tasks.length === 0) return 0;

    const now = Date.now();
    let recovered = 0;

    for (const task of tasks) {
      const createdAt = task.created_at ? new Date(task.created_at).getTime() : 0;
      const elapsed = now - createdAt;

      if (elapsed > config.maxPollTimeMs) {
        // 已超时: 标记失败并退款
        console.log(`[Video] Orphan task ${task.id} timed out (${(elapsed / 1000).toFixed(0)}s), refunding...`);
        await updateVideoTask(task.id, {
          status: 'failed',
          errorMessage: '服务器重启，任务超时自动取消',
        });
        if (task.usage_log_id) {
          await refundBalance(task.user_id, task.estimated_cost_fen, task.usage_log_id);
        }
      } else if (task.upstream_task_id && task.usage_log_id) {
        // 仍在窗口内: 恢复轮询
        console.log(`[Video] Recovering orphan poll for task ${task.id} (elapsed: ${(elapsed / 1000).toFixed(0)}s)`);
        startBackgroundPoll(
          task.id,
          task.upstream_task_id,
          task.user_id,
          task.usage_log_id,
          task.mode as VideoMode,
          task.quality as Quality
        );
        recovered++;
      }
    }

    return recovered;
  } catch (err: any) {
    console.error('[Video] Failed to recover orphaned polls:', err.message);
    return 0;
  }
}

// ═══════════════════════════════════════════════
// POST /api/video/generate — 提交视频生成
// ═══════════════════════════════════════════════

router.post('/generate', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const {
      session_id,
      mode,
      prompt_override,
      image_b64,
      aspect_ratio,
      duration,
      quality,
    }: VideoGenerateRequest = req.body;

    // 参数验证
    const validModes: VideoMode[] = ['text_to_video', 'image_to_video'];
    if (!mode || !validModes.includes(mode)) {
      throw AppError.badRequest('请指定生成模式: text_to_video 或 image_to_video');
    }

    if (!session_id) {
      throw AppError.badRequest('缺少 session_id');
    }

    const userId = req.user!.userId;
    const apiKeyId = req.user!.apiKeyId;

    // 1. 获取 Prompt
    const session = await getWizardSession(session_id);
    if (!session) {
      throw AppError.notFound('会话不存在或已过期');
    }

    if (session.user_id !== userId) {
      throw AppError.unauthorized('无权访问此会话');
    }

    const prompt = prompt_override || session.current_prompt;
    if (!prompt) {
      throw AppError.badRequest('暂无可用 Prompt。请先在向导中生成视频 Prompt。');
    }

    // 2. 参数校验
    const ratio: AspectRatio = aspect_ratio || '16:9';
    const validRatios: AspectRatio[] = ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9'];
    if (!validRatios.includes(ratio)) {
      throw AppError.badRequest(`无效的宽高比: ${ratio}`);
    }

    const dur = duration || 5;
    if (dur < 4 || dur > 15) {
      throw AppError.badRequest('视频时长需在 4-15 秒之间');
    }

    const qual: Quality = quality || 'high';
    if (qual !== 'basic' && qual !== 'high') {
      throw AppError.badRequest('画质参数无效');
    }

    // 2. I2V 模式需要图片
    if (mode === 'image_to_video' && !image_b64) {
      throw AppError.badRequest('image_to_video 模式需要提供 image_b64');
    }

    // 3. 预估费用
    const estimatedCostFen = await estimateVideoCost(mode, dur, qual);

    // 4. 检查余额并预扣
    const deducted = await deductBalance(userId, estimatedCostFen);
    if (!deducted) {
      throw AppError.insufficientBalance(
        `余额不足。预估费用 ${fenToYuan(estimatedCostFen)} 元，当前余额不足。`
      );
    }

    // 5. 创建用量日志（pending 状态，预扣费用）
    const usageLogId = await createUsageLog({
      userId,
      apiKeyId,
      service: mode === 'text_to_video' ? 'seedance_t2v' : 'seedance_i2v',
      units: dur,
      costFen: 0, // 实际费用等完成后结算
      preCostFen: estimatedCostFen,
      status: 'pending',
      requestMeta: {
        mode,
        duration: dur,
        quality: qual,
        aspect_ratio: ratio,
        prompt_length: prompt.length,
        session_id,
      },
    });

    // 6. 提交 Seedance 任务
    let upstreamTaskId: string;

    if (mode === 'text_to_video') {
      const result = await submitT2V(prompt, ratio, dur, qual);
      upstreamTaskId = result.taskId;
    } else {
      const result = await submitI2V(prompt, image_b64!, ratio, dur, qual);
      upstreamTaskId = result.taskId;
    }

    // 7. 创建视频任务记录
    const videoTask = await createVideoTask({
      userId,
      usageLogId,
      upstreamTaskId,
      mode,
      prompt,
      aspectRatio: ratio,
      durationSeconds: dur,
      quality: qual,
      estimatedCostFen,
    });

    // 8. 更新向导会话的 last_task_id
    await updateWizardLastTask(session_id, videoTask.id);

    // 9. 将 upstream_task_id 关联到已有的用量日志
    await dbQuery(
      `UPDATE usage_logs SET upstream_task_id = $1 WHERE id = $2`,
      [upstreamTaskId, usageLogId]
    );

    // 10. 启动后台轮询
    startBackgroundPoll(
      videoTask.id,
      upstreamTaskId,
      userId,
      usageLogId,
      mode,
      qual
    );

    // 11. 查询扣费后余额
    const balanceAfter = await getBalance(userId);

    console.log(
      `[Video] Task ${videoTask.id} submitted (upstream: ${upstreamTaskId}), ` +
      `mode=${mode}, cost=${estimatedCostFen}fen, balance=${balanceAfter}fen`
    );

    const estimatedSeconds = Math.ceil(dur * 15); // 粗略估计：每秒约 15 秒生成时间

    const response: VideoGenerateResponse = {
      task_id: videoTask.id,
      estimated_cost_fen: estimatedCostFen,
      estimated_seconds: estimatedSeconds,
      balance_after: balanceAfter,
    };

    res.status(202).json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// GET /api/video/:taskId/status — 查询任务状态
// ═══════════════════════════════════════════════

router.get('/:taskId/status', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const taskId = req.params.taskId as string;
    const userId = req.user!.userId;

    const task = await getVideoTask(taskId);
    if (!task) {
      throw AppError.notFound('任务不存在');
    }

    if (task.user_id !== userId) {
      throw AppError.unauthorized('无权访问此任务');
    }

    const response: VideoTaskStatus = {
      task_id: task.id,
      status: task.status,
      progress: task.progress,
      video_url: task.video_url,
      estimated_cost_fen: task.estimated_cost_fen,
      actual_cost_fen: task.actual_cost_fen,
      created_at: task.created_at,
      completed_at: task.completed_at,
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// GET /api/video/:taskId/result — 获取视频结果
// ═══════════════════════════════════════════════

router.get('/:taskId/result', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const taskId = req.params.taskId as string;
    const userId = req.user!.userId;

    const task = await getVideoTask(taskId);
    if (!task) {
      throw AppError.notFound('任务不存在');
    }

    if (task.user_id !== userId) {
      throw AppError.unauthorized('无权访问此任务');
    }

    if (task.status !== 'completed') {
      throw AppError.badRequest(
        `任务尚未完成（当前状态: ${task.status}），请等待生成完成后再获取结果`
      );
    }

    if (!task.video_url) {
      throw AppError.internal('任务已完成但视频地址缺失，请联系客服');
    }

    const response: VideoTaskResult = {
      video_url: task.video_url,
      duration_ms: task.duration_seconds * 1000,
      actual_cost_fen: task.actual_cost_fen || task.estimated_cost_fen,
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

export default router;
