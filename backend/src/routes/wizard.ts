// ─────────────────────────────────────────────
// 向导核心路由: /api/wizard/*
//
// POST /api/wizard/analyze  — 新向导: 图片+想法 → 结构化参数 + 预览图
// POST /api/wizard/preview  — 参数更新 → 合成 prompt → Flux 重新生成图
// POST /api/wizard/start    — 旧向导: 开始对话（保留兼容）
// POST /api/wizard/message  — 旧向导: 多轮对话
// ─────────────────────────────────────────────

import { Router, Request, Response, NextFunction } from 'express';
import { deepSeekDirector, analyzeAndStructure } from '../services/deepseek';
import { generatePreview } from '../services/flux';
import { composePrompt, validateAndNormalizeParams } from '../services/promptComposer';
import {
  calculateDeepseekCost,
  calculateQwenCost,
  calculateFluxPreviewCost,
  fenToYuan,
} from '../services/pricing';
import {
  createWizardSession,
  updateWizardSession,
  getWizardSession,
  createUsageLog,
  deductBalance,
  getBalance,
} from '../db/queries';
import { query } from '../db/pool';
import {
  WizardStartRequest,
  WizardStartResponse,
  WizardMessageRequest,
  WizardMessageResponse,
  WizardAnalyzeRequest,
  WizardAnalyzeResponse,
  WizardParamPreviewRequest,
  WizardParamPreviewResponse,
} from '../types';
import { analyzeImageForDirector } from '../services/qwen';
import { AppError } from '../middleware/errorHandler';

const router = Router();

// ═══════════════════════════════════════════════
// POST /api/wizard/analyze — 新向导: 一键分析
// 流程: Qwen VL (图像→文字) → DeepSeek 结构化 → Flux 预览
// ═══════════════════════════════════════════════

router.post('/analyze', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { image_b64, user_idea, aspect_ratio }: WizardAnalyzeRequest = req.body;

    if (!image_b64 || !image_b64.startsWith('data:')) {
      throw AppError.badRequest('请提供有效的 image_b64（data URI 格式）');
    }
    if (!user_idea || user_idea.trim().length === 0) {
      throw AppError.badRequest('请输入您的创作想法（user_idea）');
    }

    const userId   = req.user!.userId;
    const apiKeyId = req.user!.apiKeyId;
    const ratio    = aspect_ratio || '16:9';

    // ── 1. Qwen VL 分析图片（不扣费）─────────────
    console.log('[Wizard/Analyze] Step 1: Qwen VL image analysis');
    const qwenResult = await analyzeImageForDirector(image_b64);
    const imageDescription = qwenResult.description;
    const qwenTokens = qwenResult.usage?.totalTokens || 0;

    // ── 2. DeepSeek 结构化分析（不扣费）───────────
    console.log('[Wizard/Analyze] Step 2: DeepSeek structured analysis');
    const structuredResult = await analyzeAndStructure(imageDescription, user_idea.trim());

    // ── 3. 合成完整 Prompt ────────────────────────
    const composedPrompt = composePrompt(
      structuredResult.base_description,
      structuredResult.initial_params
    );

    // ── 4. 计算总费用 & 统一扣费 ──────────────────
    const qwenCostFen = qwenTokens > 0 ? await calculateQwenCost(qwenTokens) : 0;
    const deepseekCostFen = await calculateDeepseekCost(
      structuredResult.tokenUsage.inputTokens,
      structuredResult.tokenUsage.outputTokens
    );

    // 先检查余额是否足够 Qwen + DeepSeek（Flux 单独计算，失败不扣）
    const preFluxCost = qwenCostFen + deepseekCostFen;
    const currentBalance = await getBalance(userId);
    if (currentBalance < preFluxCost) {
      throw AppError.insufficientBalance(
        `余额不足。分析费用 ${fenToYuan(preFluxCost)} 元，当前余额 ${fenToYuan(currentBalance)} 元。`
      );
    }

    // 先扣 Qwen + DeepSeek
    if (preFluxCost > 0) {
      const deducted = await deductBalance(userId, preFluxCost);
      if (!deducted) {
        throw AppError.insufficientBalance('余额扣费失败，请稍后重试。');
      }
    }

    // ── 5. Flux 生成预览图（可降级）──────────────
    console.log('[Wizard/Analyze] Step 3: Flux preview generation');
    let previewUrl: string | null = null;
    let fluxCostFen = 0;
    let fluxFailed = false;

    try {
      fluxCostFen = await calculateFluxPreviewCost(1);
      const fluxDeducted = await deductBalance(userId, fluxCostFen);
      if (!fluxDeducted) {
        console.warn('[Wizard/Analyze] Flux deduction failed, skipping preview');
        fluxCostFen = 0;
        fluxFailed = true;
      } else {
        const { imageUrl } = await generatePreview(composedPrompt, ratio);
        previewUrl = imageUrl;
      }
    } catch (fluxErr: any) {
      console.warn(`[Wizard/Analyze] Flux failed (non-fatal): ${fluxErr.message}`);
      // 退还已扣的 Flux 费用
      if (fluxCostFen > 0) {
        try {
          await query(
            'UPDATE balances SET amount_fen = amount_fen + $1 WHERE user_id = $2',
            [fluxCostFen, userId]
          );
        } catch (_) { /* best-effort refund */ }
      }
      fluxCostFen = 0;
      fluxFailed = true;
    }

    // ── 6. 创建向导会话 ──────────────────────────
    const sessionId = await createWizardSession(
      userId,
      [],
      composedPrompt,
      image_b64
    );

    // ── 7. 记录用量日志 ──────────────────────────
    if (qwenCostFen > 0) {
      await createUsageLog({
        userId, apiKeyId,
        service: 'qwen_vl',
        units:   qwenTokens,
        costFen: qwenCostFen,
        status:  'success',
        requestMeta: { model: 'qwen-vl-max', session_id: sessionId },
      });
    }

    if (deepseekCostFen > 0) {
      await createUsageLog({
        userId, apiKeyId,
        service: 'deepseek',
        units:   structuredResult.tokenUsage.totalTokens,
        costFen: deepseekCostFen,
        status:  'success',
        requestMeta: {
          model:         'deepseek-chat',
          input_tokens:  structuredResult.tokenUsage.inputTokens,
          output_tokens: structuredResult.tokenUsage.outputTokens,
          session_id:    sessionId,
          mode:          'structured_analysis',
        },
      });
    }

    if (!fluxFailed && fluxCostFen > 0) {
      await createUsageLog({
        userId, apiKeyId,
        service: 'flux_preview',
        units:   1,
        costFen: fluxCostFen,
        status:  'success',
        requestMeta: {
          session_id:    sessionId,
          aspect_ratio:  ratio,
          prompt_length: composedPrompt.length,
        },
      });
    }

    const totalCostFen = qwenCostFen + deepseekCostFen + fluxCostFen;
    const balanceAfter = await getBalance(userId);

    console.log(
      `[Wizard/Analyze] Session ${sessionId} created, ` +
      `qwen=${qwenCostFen}fen, deepseek=${deepseekCostFen}fen, ` +
      `flux=${fluxCostFen}fen${fluxFailed ? ' (FAILED)' : ''}, total=${totalCostFen}fen`
    );

    const response: WizardAnalyzeResponse = {
      session_id:         sessionId,
      base_description:   structuredResult.base_description,
      creative_rationale: structuredResult.creative_rationale,
      initial_params:     structuredResult.initial_params,
      composed_prompt:    composedPrompt,
      preview_url:        previewUrl,
      cost_fen:           totalCostFen,
      balance_after:      balanceAfter,
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/wizard/preview — 参数驱动预览重新生成
// 用于用户调整参数后实时更新预览图
// ═══════════════════════════════════════════════

router.post('/preview', async (req: Request, res: Response, next: NextFunction) => {
  try {
    // 支持两种调用方式：
    //   新: { session_id, params }
    //   旧: { session_id, prompt_override, aspect_ratio }
    const body = req.body;
    const sessionId = body.session_id;

    if (!sessionId) {
      throw AppError.badRequest('缺少 session_id');
    }

    const userId   = req.user!.userId;
    const apiKeyId = req.user!.apiKeyId;

    // 1. 验证会话
    const session = await getWizardSession(sessionId);
    if (!session) throw AppError.notFound('会话不存在或已过期');
    if (session.user_id !== userId) throw AppError.unauthorized('无权访问此会话');

    const ratio = body.aspect_ratio || '16:9';
    const validRatios = ['16:9', '9:16', '1:1', '4:3', '3:4'];
    if (!validRatios.includes(ratio)) {
      throw AppError.badRequest(`无效的宽高比: ${ratio}`);
    }

    let finalPrompt: string;
    let composedPrompt: string | null = null;

    if (body.params) {
      // ── 新路径：params → compose → Flux ──────────
      const params = validateAndNormalizeParams(body.params);
      // base_description 优先从请求中获取，fallback 到 session.current_prompt
      const baseDesc = (body.base_description as string | undefined)
        || session.current_prompt
        || 'A beautiful scene';

      composedPrompt = composePrompt(baseDesc, params);
      finalPrompt    = composedPrompt;

      // 更新 session 中保存的 prompt
      await updateWizardSession(sessionId, session.messages, composedPrompt);
    } else {
      // ── 旧路径：prompt_override 或 session prompt ─
      finalPrompt = body.prompt_override || session.current_prompt;
      if (!finalPrompt) {
        throw AppError.badRequest('暂无可用 Prompt，请提供 params 或 prompt_override。');
      }
    }

    // 2. 扣费
    let costFen = await calculateFluxPreviewCost(1);
    const deducted = await deductBalance(userId, costFen);
    if (!deducted) {
      throw AppError.insufficientBalance(
        `余额不足。Flux 预览费用 ${fenToYuan(costFen)} 元，请充值后重试。`
      );
    }

    // 3. 调用 Flux（可降级）
    let imageUrl: string | null = null;
    let fluxFailed = false;

    try {
      const result = await generatePreview(finalPrompt, ratio);
      imageUrl = result.imageUrl;
    } catch (fluxErr: any) {
      console.warn(`[Wizard/Preview] Flux failed (non-fatal): ${fluxErr.message}`);
      if (costFen > 0) {
        try {
          await query(
            'UPDATE balances SET amount_fen = amount_fen + $1 WHERE user_id = $2',
            [costFen, userId]
          );
        } catch (_) { /* best-effort refund */ }
      }
      costFen = 0;
      fluxFailed = true;
    }

    // 4. 记录用量（仅成功时）
    if (!fluxFailed && costFen > 0) {
      await createUsageLog({
        userId, apiKeyId,
        service: 'flux_preview',
        units:   1,
        costFen,
        status:  'success',
        requestMeta: {
          session_id:    sessionId,
          aspect_ratio:  ratio,
          prompt_length: finalPrompt.length,
          mode:          body.params ? 'param_driven' : 'legacy',
        },
      });
    }

    const balanceAfter = await getBalance(userId);

    console.log(
      `[Wizard/Preview] Session ${sessionId}, cost=${costFen}fen` +
      `${fluxFailed ? ' (Flux failed, refunded)' : ''}`
    );

    // 新旧路径都能用的响应（新路径多返回 composed_prompt）
    const response: WizardParamPreviewResponse = {
      preview_url:     imageUrl,
      composed_prompt: composedPrompt || finalPrompt,
      cost_fen:        costFen,
      balance_after:   balanceAfter,
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/wizard/start — 旧向导（兼容保留）
// ═══════════════════════════════════════════════

router.post('/start', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { intent, image_b64, language }: WizardStartRequest = req.body;

    if (!intent || intent.trim().length === 0) {
      throw AppError.badRequest('请输入创作意图（intent）');
    }

    const userId   = req.user!.userId;
    const apiKeyId = req.user!.apiKeyId;

    const result = await deepSeekDirector.startSession(intent.trim(), image_b64 || undefined);

    const deepseekCostFen = await calculateDeepseekCost(
      result.tokenUsage.inputTokens,
      result.tokenUsage.outputTokens
    );

    let qwenCostFen = 0;
    if (result.imageAnalyzed && result.qwenTokens > 0) {
      qwenCostFen = await calculateQwenCost(result.qwenTokens);
    }

    const totalCostFen = deepseekCostFen + qwenCostFen;
    const deducted = await deductBalance(userId, totalCostFen);
    if (!deducted) {
      throw AppError.insufficientBalance(
        `余额不足。本次对话预估费用 ${fenToYuan(totalCostFen)} 元，请充值后重试。`
      );
    }

    const sessionId = await createWizardSession(
      userId, result.messages, result.currentPrompt || undefined, image_b64 || undefined
    );

    await createUsageLog({
      userId, apiKeyId,
      service: 'deepseek',
      units:   result.tokenUsage.totalTokens,
      costFen: deepseekCostFen,
      status:  'success',
      requestMeta: { model: 'deepseek-chat', session_id: sessionId },
    });

    if (result.imageAnalyzed && result.qwenTokens > 0) {
      await createUsageLog({
        userId, apiKeyId,
        service: 'qwen_vl',
        units:   result.qwenTokens,
        costFen: qwenCostFen,
        status:  'success',
        requestMeta: { model: 'qwen-vl-max', session_id: sessionId },
      });
    }

    const balanceAfter = await getBalance(userId);

    const response: WizardStartResponse = {
      session_id:       sessionId,
      director_message: result.directorMessage,
      suggested_options: result.suggestedOptions,
      current_prompt:   result.currentPrompt || '',
      image_analyzed:   result.imageAnalyzed,
      balance_after:    balanceAfter,
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/wizard/message — 旧向导多轮对话（兼容保留）
// ═══════════════════════════════════════════════

router.post('/message', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { session_id, message, css_params }: WizardMessageRequest = req.body;

    if (!session_id) throw AppError.badRequest('缺少 session_id');
    if (!message || message.trim().length === 0) throw AppError.badRequest('请输入反馈信息');

    const userId   = req.user!.userId;
    const apiKeyId = req.user!.apiKeyId;

    const session = await getWizardSession(session_id);
    if (!session) throw AppError.notFound('会话不存在或已过期');
    if (session.user_id !== userId) throw AppError.unauthorized('无权访问此会话');

    const result = await deepSeekDirector.continueDialog(
      session.messages, message.trim(), css_params || undefined
    );

    const costFen = await calculateDeepseekCost(
      result.tokenUsage.inputTokens,
      result.tokenUsage.outputTokens
    );

    const deducted = await deductBalance(userId, costFen);
    if (!deducted) {
      throw AppError.insufficientBalance(
        `余额不足。本次对话预估费用 ${fenToYuan(costFen)} 元，请充值后重试。`
      );
    }

    await updateWizardSession(session_id, result.messages, result.currentPrompt || undefined);

    await createUsageLog({
      userId, apiKeyId,
      service: 'deepseek',
      units:   result.tokenUsage.totalTokens,
      costFen,
      status:  'success',
      requestMeta: {
        model:         'deepseek-chat',
        input_tokens:  result.tokenUsage.inputTokens,
        output_tokens: result.tokenUsage.outputTokens,
        session_id,
      },
    });

    const response: WizardMessageResponse = {
      director_message: result.directorMessage,
      current_prompt:   result.currentPrompt || session.current_prompt || '',
      suggested_options: result.suggestedOptions,
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

export default router;
