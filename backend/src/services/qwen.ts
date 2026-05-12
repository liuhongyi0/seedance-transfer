// ─────────────────────────────────────────────
// Qwen VL 图像分析服务
// 通过阿里云 DashScope 兼容接口调用 qwen-vl-max
// 使用 OpenAI 兼容 SDK 格式
// ─────────────────────────────────────────────

import OpenAI from 'openai';
import { config } from '../config';

const openai = new OpenAI({
  apiKey: config.dashscopeApiKey,
  baseURL: config.dashscopeBaseUrl,
});

export interface QwenAnalysisResult {
  description: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
}

/**
 * Qwen VL 图像分析
 *
 * @param imageBase64 - 图片的 base64 编码（含 data URI 前缀，如 data:image/jpeg;base64,...）
 * @param question   - 分析问题，如 "详细描述这张图片的内容、风格和色调"
 * @returns 分析结果，包含文本描述和 token 用量
 */
export async function analyzeImage(
  imageBase64: string,
  question: string
): Promise<QwenAnalysisResult> {
  if (!config.dashscopeApiKey) {
    throw new Error('DASHSCOPE_API_KEY 未配置，无法调用 Qwen VL');
  }

  console.log('[Qwen VL] Sending image analysis request...');
  const startTime = Date.now();

  try {
    const response = await openai.chat.completions.create({
      model: 'qwen-vl-max',
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'image_url',
              image_url: {
                url: imageBase64,
              },
            },
            {
              type: 'text',
              text: question,
            },
          ],
        },
      ],
      max_tokens: 1000,
      temperature: 0.7,
    });

    const elapsed = Date.now() - startTime;
    const usage = response.usage;
    console.log(
      `[Qwen VL] Analysis complete in ${elapsed}ms, ` +
      `tokens: ${usage?.total_tokens || 'N/A'} ` +
      `(input: ${usage?.prompt_tokens}, output: ${usage?.completion_tokens})`
    );

    const content = response.choices[0]?.message?.content;
    if (!content) {
      throw new Error('Qwen VL 返回了空内容');
    }

    return {
      description: content,
      usage: usage ? {
        promptTokens: usage.prompt_tokens || 0,
        completionTokens: usage.completion_tokens || 0,
        totalTokens: usage.total_tokens || 0,
      } : undefined,
    };
  } catch (err: any) {
    const elapsed = Date.now() - startTime;
    console.error(`[Qwen VL] Error after ${elapsed}ms:`, err.message);

    if (err.status === 401 || err.status === 403) {
      throw new Error('DashScope API Key 无效或无权访问');
    }
    if (err.status === 429) {
      throw new Error('DashScope API 调用频率过高，请稍后重试');
    }
    throw new Error(`Qwen VL 分析失败: ${err.message}`);
  }
}

/**
 * 分析图片并返回结构化描述
 * 专门为导演模式设计 —— 分析更适合作为视频创作参考的细节
 */
export async function analyzeImageForDirector(
  imageBase64: string
): Promise<QwenAnalysisResult> {
  const question = `请详细分析这张图片，包括：
1. 主体内容：画面中有什么对象/产品/人物
2. 构图与布局：主体位置、视角、景深
3. 色彩与光线：主色调、光影方向、氛围
4. 风格：写实/插画/极简/奢华/科技感等
5. 背景与环境：场景类型、材质、纹理
6. 适合做成什么类型的视频：电商广告 / 品牌宣传 / 社交媒体 / 产品展示

请用中文输出分析结果，要具体、可用于指导视频创作。`;

  return analyzeImage(imageBase64, question);
}
