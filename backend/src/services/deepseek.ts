// ─────────────────────────────────────────────
// DeepSeek 导演 — 自建 tool_call 循环（~300 行）
//
// 职责：
//   1. 作为视频创作导演，理解用户意图
//   2. 按需调用 Qwen VL 分析参考图
//   3. 按需调用 Flux 生成预览
//   4. 生成/迭代英文视频 Prompt
//   5. 与用户中文对话
//
// 关键技术：
//   - 使用 OpenAI SDK 兼容格式调用 DeepSeek API
//   - 自建 tool_call 执行循环（不依赖任何第三方 Agent 框架）
//   - 2 个 tools: analyze_image / finalize_prompt
// ─────────────────────────────────────────────

import OpenAI from 'openai';
import { config } from '../config';
import { analyzeImageForDirector } from './qwen';
import {
  ChatMessage,
  ToolCall,
  FilterParams,
  SuggestedOption,
} from '../types';

// ═══════════════════════════════════════════════
// DeepSeek 客户端
// ═══════════════════════════════════════════════

const deepseek = new OpenAI({
  apiKey: config.deepseekApiKey,
  baseURL: config.deepseekBaseUrl,
});

const MODEL = 'deepseek-chat';

// ═══════════════════════════════════════════════
// System Prompt
// ═══════════════════════════════════════════════

const SYSTEM_PROMPT = `You are a professional video content director for Seedance 2.0, an AI video generation system. Your role is to help Chinese-speaking creators produce compelling short videos by translating their ideas into detailed, cinematic English prompts.

## WORKFLOW
1. **Understand intent**: Parse the user's creative goal (product showcase, brand promo, social media, etc.)
2. **Analyze references**: If a reference image is provided, ALWAYS call analyze_image first to understand its visual content
3. **Suggest directions**: Based on analysis + intent, propose creative options — visual style, camera movement, color palette, lighting, composition
4. **Generate prompt**: Produce a detailed English video prompt optimized for Seedance
5. **Iterate**: Refine based on user feedback until satisfied
6. **Finalize**: Call finalize_prompt when the prompt is ready for video generation

## CRITICAL RULES
- Video prompts MUST be in ENGLISH (Seedance engine requirement)
- Communicate with users in CHINESE (they are Chinese-speaking creators)
- Prompts should be DETAILED and CINEMATIC: describe subject, setting, lighting, camera movement, mood, color palette, texture, depth of field
- When users provide CSS filter adjustments (warmth, brightness, blur, contrast, saturation), translate them into natural visual language descriptors in the prompt
- Keep prompts concise but vivid — focus on visual elements that Seedance can render
- Seedance works best with clear, directive, scene-description style prompts (not abstract artistic concepts)

## PROMPT STRUCTURE (for Seedance)
A good Seedance prompt includes:
1. **Subject**: What/who is in the frame (product, person, scene)
2. **Action/Movement**: What is happening, camera motion
3. **Setting**: Environment, background, context
4. **Lighting**: Light direction, quality, time of day, mood
5. **Color palette**: Dominant colors, saturation level, warmth
6. **Camera**: Angle, distance, lens type, depth of field
7. **Style**: Cinematic/commercial/documentary/social-media aesthetic

## OPTIONS FORMAT
When suggesting quick options for the user, include them as a JSON array at the END of your message:
[{"label":"温馨电商广告","value":"warm_ecommerce"},{"label":"品牌形象片","value":"brand_film"}]

Use short, actionable Chinese labels. Provide 2-4 options that represent distinct creative directions.`;

// ═══════════════════════════════════════════════
// Tool 定义（OpenAI function calling 格式）
// ═══════════════════════════════════════════════

const TOOLS: OpenAI.Chat.Completions.ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: 'analyze_image',
      description:
        'Analyze a reference image to understand its visual content, style, composition, and suitability for video creation. Call this whenever the user provides a reference image.',
      parameters: {
        type: 'object',
        properties: {
          image_b64: {
            type: 'string',
            description: 'The base64 encoded image data (include the data URI prefix)',
          },
          question: {
            type: 'string',
            description:
              'What specific aspects to analyze about the image (e.g., "Describe the product, its style, colors, and what kind of video this would suit")',
          },
        },
        required: ['image_b64', 'question'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'finalize_prompt',
      description:
        'Finalize the video prompt — mark the current prompt as ready for Seedance video generation. Call this when you believe the prompt is well-refined and the user is ready to generate the video.',
      parameters: {
        type: 'object',
        properties: {
          prompt: {
            type: 'string',
            description:
              'The final, polished English video prompt for Seedance 2.0',
          },
          summary: {
            type: 'string',
            description:
              'A brief Chinese summary explaining the creative choices made in the final prompt',
          },
        },
        required: ['prompt', 'summary'],
      },
    },
  },
];

// ═══════════════════════════════════════════════
// 工具执行器
// ═══════════════════════════════════════════════

interface ToolResult {
  tool_call_id: string;
  role: 'tool';
  content: string;
}

async function executeToolCall(
  toolCall: ToolCall
): Promise<ToolResult> {
  const { name, arguments: argsStr } = toolCall.function;
  let args: Record<string, any>;

  try {
    args = JSON.parse(argsStr);
  } catch {
    return {
      tool_call_id: toolCall.id,
      role: 'tool',
      content: JSON.stringify({ error: 'Invalid JSON arguments' }),
    };
  }

  console.log(`[DeepSeek Director] Executing tool: ${name}`);

  try {
    switch (name) {
      case 'analyze_image': {
        const imageB64 = args.image_b64 as string;
        const question = (args.question as string) ||
          '请详细描述这张图片的内容、风格和色调';
        const analysis = await analyzeImageForDirector(imageB64);
        return {
          tool_call_id: toolCall.id,
          role: 'tool',
          content: JSON.stringify({
            description: analysis.description,
            qwen_usage: analysis.usage || null,
          }),
        };
      }

      case 'finalize_prompt': {
        const prompt = args.prompt as string;
        const summary = (args.summary as string) || '视频 Prompt 已就绪';
        return {
          tool_call_id: toolCall.id,
          role: 'tool',
          content: JSON.stringify({
            finalized: true,
            prompt,
            summary,
          }),
        };
      }

      default:
        return {
          tool_call_id: toolCall.id,
          role: 'tool',
          content: JSON.stringify({ error: `Unknown tool: ${name}` }),
        };
    }
  } catch (err: any) {
    console.error(`[DeepSeek Director] Tool ${name} failed:`, err.message);
    return {
      tool_call_id: toolCall.id,
      role: 'tool',
      content: JSON.stringify({
        error: `Tool execution failed: ${err.message}`,
        fallback: true,
      }),
    };
  }
}

// ═══════════════════════════════════════════════
// Tool Loop 核心
// ═══════════════════════════════════════════════

interface ToolLoopResult {
  messages: ChatMessage[];
  directorMessage: string;
  currentPrompt: string | null;
  promptSummary: string | null;
  suggestedOptions: SuggestedOption[];
  imageAnalyzed: boolean;
  previewUrl: string | null;
  qwenTokens: number;
  tokenUsage: {
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
  };
}

/**
 * 执行 tool_call 循环
 * 持续调用 DeepSeek 直到不再产生 tool_calls
 */
async function runToolLoop(
  messages: ChatMessage[]
): Promise<ToolLoopResult> {
  const maxIterations = 10; // 防止无限循环
  let totalInputTokens = 0;
  let totalOutputTokens = 0;
  let totalQwenTokens = 0;
  let imageAnalyzed = false;
  let previewUrl: string | null = null;
  let currentPrompt: string | null = null;
  let promptSummary: string | null = null;

  for (let iteration = 0; iteration < maxIterations; iteration++) {
    console.log(
      `[DeepSeek Director] Iteration ${iteration + 1}/${maxIterations}, ` +
      `messages: ${messages.length}`
    );

    const response = await deepseek.chat.completions.create({
      model: MODEL,
      messages: messages as OpenAI.Chat.Completions.ChatCompletionMessageParam[],
      tools: TOOLS,
      tool_choice: 'auto',
      temperature: 0.7,
      max_tokens: 2000,
    });

    const usage = response.usage;
    if (usage) {
      totalInputTokens += usage.prompt_tokens || 0;
      totalOutputTokens += usage.completion_tokens || 0;
    }

    const choice = response.choices[0];
    if (!choice) {
      console.warn('[DeepSeek Director] Empty response choice');
      break;
    }

    const assistantMessage = choice.message;

    // 将 assistant 消息加入对话历史
    const msgToPush: ChatMessage = {
      role: 'assistant',
      content: assistantMessage.content,
    };

    // 处理 tool_calls
    if (assistantMessage.tool_calls && assistantMessage.tool_calls.length > 0) {
      msgToPush.tool_calls = assistantMessage.tool_calls.map((tc) => ({
        id: tc.id,
        type: 'function' as const,
        function: {
          name: tc.function.name,
          arguments: tc.function.arguments,
        },
      }));
    }

    messages.push(msgToPush);

    // 无 tool_calls → 正常回复，结束循环
    if (!assistantMessage.tool_calls || assistantMessage.tool_calls.length === 0) {
      console.log('[DeepSeek Director] No tool calls, ending loop');
      break;
    }

    // 执行所有 tool calls
    let finalized = false;

    for (const tc of assistantMessage.tool_calls) {
      const toolResult = await executeToolCall({
        id: tc.id,
        type: 'function',
        function: {
          name: tc.function.name,
          arguments: tc.function.arguments,
        },
      });

      messages.push(toolResult);

      // 跟踪状态
      if (tc.function.name === 'analyze_image') {
        imageAnalyzed = true;
        try {
          const result = JSON.parse(toolResult.content);
          if (result.qwen_usage && result.qwen_usage.totalTokens) {
            totalQwenTokens += result.qwen_usage.totalTokens;
          }
        } catch {}
      }

      if (tc.function.name === 'finalize_prompt') {
        finalized = true;
        try {
          const result = JSON.parse(toolResult.content);
          if (result.finalized) {
            currentPrompt = result.prompt;
            promptSummary = result.summary;
          }
        } catch {}
      }
    }

    // 如果调用了 finalize_prompt，结束循环
    if (finalized) {
      console.log('[DeepSeek Director] Prompt finalized, ending loop');
      break;
    }
  }

  // 提取最后的 assistant 消息作为 director_message
  let directorMessage = '';
  const assistantMessages = messages
    .filter((m) => m.role === 'assistant')
    .reverse();

  for (const msg of assistantMessages) {
    if (msg.content && msg.content.trim()) {
      directorMessage = msg.content;
      break;
    }
  }

  // 提取 suggested_options
  const suggestedOptions = extractOptions(directorMessage);

  // 如果 finalize 没有被调用，尝试从最后的 assistant 消息中提取 prompt
  if (!currentPrompt) {
    currentPrompt = extractPrompt(directorMessage);
  }

  return {
    messages,
    directorMessage,
    currentPrompt,
    promptSummary,
    suggestedOptions,
    imageAnalyzed,
    previewUrl,
    qwenTokens: totalQwenTokens,
    tokenUsage: {
      inputTokens: totalInputTokens,
      outputTokens: totalOutputTokens,
      totalTokens: totalInputTokens + totalOutputTokens,
    },
  };
}

// ═══════════════════════════════════════════════
// 选项提取
// ═══════════════════════════════════════════════

function extractOptions(message: string): SuggestedOption[] {
  try {
    // 查找 JSON 数组格式的选项: [{"label":...},{"label":...}]
    const regex = /\[\s*\{\s*"label"\s*:\s*"[^"]*"\s*,\s*"value"\s*:\s*"[^"]*"\s*\}[\s,]*\]/g;
    const match = message.match(regex);
    if (match) {
      const parsed = JSON.parse(match[0]);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed.filter(
          (o: any) =>
            typeof o.label === 'string' &&
            typeof o.value === 'string'
        );
      }
    }
  } catch {
    // 解析失败，返回空数组
  }

  return [];
}

// ═══════════════════════════════════════════════
// Prompt 提取（从普通消息中）
// ═══════════════════════════════════════════════

function extractPrompt(message: string): string | null {
  // 查找英文 prompt 模式：以英文大写字母开头，包含逗号分隔的细节描述
  // 简单策略：找第一个大于 50 字符的、主要是英文的段落
  const lines = message.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    // 跳过中文行、格式化行、markdown
    if (
      trimmed.length > 50 &&
      !/[一-鿿]/.test(trimmed) && // 不含中文
      !trimmed.startsWith('[') &&
      !trimmed.startsWith('{') &&
      !trimmed.startsWith('```') &&
      /^[A-Z]/.test(trimmed) // 以大写字母开头
    ) {
      return trimmed;
    }
  }
  return null;
}

// ═══════════════════════════════════════════════
// CSS 滤镜参数翻译
// ═══════════════════════════════════════════════

function translateCssParams(params: FilterParams): string {
  const parts: string[] = [];

  if (params.warmth !== undefined && params.warmth !== 0) {
    const level = Math.abs(params.warmth) > 0.5 ? 'strong' : 'subtle';
    if (params.warmth > 0) {
      parts.push(`warm color temperature (${level}, +${params.warmth.toFixed(1)})`);
    } else {
      parts.push(`cool color temperature (${level}, ${params.warmth.toFixed(1)})`);
    }
  }

  if (params.brightness !== undefined && params.brightness !== 0) {
    const level = Math.abs(params.brightness) > 0.5 ? 'significantly' : 'slightly';
    if (params.brightness > 0) {
      parts.push(`${level} brighter (${(params.brightness * 100).toFixed(0)}%)`);
    } else {
      parts.push(`${level} darker (${(params.brightness * 100).toFixed(0)}%)`);
    }
  }

  if (params.blur !== undefined && params.blur > 0) {
    const level = params.blur > 0.5 ? 'heavy' : 'light';
    parts.push(`${level} background blur / bokeh (${(params.blur * 100).toFixed(0)}%)`);
  }

  if (params.contrast !== undefined && params.contrast !== 0) {
    const level = Math.abs(params.contrast) > 0.5 ? 'high' : 'moderate';
    if (params.contrast > 0) {
      parts.push(`${level} contrast`);
    } else {
      parts.push(`reduced contrast (${level} flat look)`);
    }
  }

  if (params.saturation !== undefined && params.saturation !== 0) {
    const level = Math.abs(params.saturation) > 0.5 ? 'highly' : 'slightly';
    if (params.saturation > 0) {
      parts.push(`${level} saturated / vibrant colors`);
    } else {
      parts.push(`${level} desaturated / muted colors`);
    }
  }

  if (parts.length === 0) return '';

  return `[Current visual adjustments (translate these into the prompt's visual language): ${parts.join('; ')}]`;
}

// ═══════════════════════════════════════════════
// 公开 API
// ═══════════════════════════════════════════════

export interface DirectorResult {
  messages: ChatMessage[];
  directorMessage: string;
  currentPrompt: string | null;
  promptSummary: string | null;
  suggestedOptions: SuggestedOption[];
  imageAnalyzed: boolean;
  previewUrl: string | null;
  qwenTokens: number;
  tokenUsage: {
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
  };
}

/**
 * DeepSeek 导演类
 * 封装自建 tool_call 循环，管理视频创作向导对话
 */
export class DeepSeekDirector {
  /**
   * 开始新的向导会话
   *
   * @param userIntent  - 用户的创作意图（中文自然语言）
   * @param imageBase64 - 可选的参考图 base64
   * @returns 导演结果（含 messages 历史、当前 prompt、建议选项）
   */
  async startSession(
    userIntent: string,
    imageBase64?: string
  ): Promise<DirectorResult> {
    if (!config.deepseekApiKey) {
      throw new Error('DEEPSEEK_API_KEY 未配置，无法启动导演会话');
    }

    console.log(
      `[DeepSeek Director] Starting session, intent="${userIntent.substring(0, 80)}...", ` +
      `has_image=${!!imageBase64}`
    );

    const messages: ChatMessage[] = [
      { role: 'system', content: SYSTEM_PROMPT },
    ];

    // 构建用户初始消息
    let userContent = userIntent;

    if (imageBase64) {
      // 有参考图：告知 DeepSeek 需要分析
      userContent = `[用户提供了一张参考图]\n\n${userIntent}\n\n请先使用 analyze_image 工具分析这张参考图，然后根据分析结果和我的需求，为我建议视频创作方向并生成专业 Prompt。`;
    } else {
      userContent = `${userIntent}\n\n请根据我的需求，为我建议视频创作方向并生成专业 Prompt。`;
    }

    messages.push({ role: 'user', content: userContent });

    const result = await runToolLoop(messages);

    console.log(
      `[DeepSeek Director] Session started, ` +
      `tokens: ${result.tokenUsage.totalTokens}, ` +
      `prompt_len: ${result.currentPrompt?.length || 0}, ` +
      `image_analyzed: ${result.imageAnalyzed}`
    );

    return result;
  }

  /**
   * 继续对话
   *
   * @param existingMessages - 现有的对话历史
   * @param userMessage      - 用户的新消息
   * @param cssParams        - 可选的 CSS 滤镜参数
   * @returns 更新后的导演结果
   */
  async continueDialog(
    existingMessages: ChatMessage[],
    userMessage: string,
    cssParams?: FilterParams
  ): Promise<DirectorResult> {
    if (!config.deepseekApiKey) {
      throw new Error('DEEPSEEK_API_KEY 未配置，无法继续对话');
    }

    console.log(
      `[DeepSeek Director] Continuing dialog, ` +
      `history=${existingMessages.length} messages, ` +
      `has_css=${!!cssParams}`
    );

    const messages = [...existingMessages];

    // 构建用户消息（可能包含 CSS 滤镜翻译）
    let userContent = userMessage;

    if (cssParams) {
      const cssDescription = translateCssParams(cssParams);
      if (cssDescription) {
        userContent = `${userMessage}\n\n${cssDescription}`;
      }
    }

    messages.push({ role: 'user', content: userContent });

    const result = await runToolLoop(messages);

    console.log(
      `[DeepSeek Director] Dialog continued, ` +
      `tokens: ${result.tokenUsage.totalTokens}, ` +
      `prompt: ${result.currentPrompt?.substring(0, 60) || 'null'}...`
    );

    return result;
  }
}

// 单例导出
export const deepSeekDirector = new DeepSeekDirector();

// ═══════════════════════════════════════════════
// 结构化分析 — 新向导核心
// ═══════════════════════════════════════════════

import { PromptParams } from '../types';
import { defaultParams, validateAndNormalizeParams } from './promptComposer';

/**
 * 结构化分析结果
 */
export interface StructuredAnalysisResult {
  base_description: string;    // 精炼后的英文场景描述（用作 prompt 基底）
  creative_rationale: string;  // 创意说明（中文，向用户展示）
  initial_params: PromptParams;
  tokenUsage: { inputTokens: number; outputTokens: number; totalTokens: number };
}

/** DeepSeek 结构化分析专用系统 Prompt */
const ANALYSIS_SYSTEM_PROMPT = `You are a professional video prompt engineer for Seedance 2.0 AI video generation.

Your task: given (1) a detailed image description from a Vision model, and (2) a user's simple creative idea, produce a STRUCTURED creative brief for video generation.

You MUST call the \`structure_creative_params\` tool with your analysis result. Do not respond in plain text.

## Rules
- base_description: A concise, vivid ENGLISH description of the visual scene (2-4 sentences).
  Focus on: subject, setting, key visual elements, materials/textures, colors.
  Do NOT include motion, camera, or style directives here — those come from the params.
- creative_rationale: A brief CHINESE explanation (2-3 sentences) of why you chose these parameters.
- All param values must be chosen to best realize the user's creative idea.

## Parameter Guidelines
- style: 'cinematic' for drama/emotion; 'commercial' for product/brand; 'documentary' for real/authentic; 'social_media' for trendy/dynamic; 'artistic' for creative/experimental
- lighting: match the desired mood and time of day
- shot_type: choose based on subject and emotional impact
- mood: the dominant feeling the video should evoke
- color_tone: match the brand/aesthetic intent
- motion_intensity (0-100): 0=still photo feel, 50=gentle motion, 100=action
- depth_of_field (0-100): 0=everything sharp, 50=moderate bokeh, 100=extreme bokeh
- detail_richness (0-100): 0=minimalist clean, 50=balanced, 100=hyper-detailed
- saturation_level (0-100): 0=muted/desaturated, 50=natural, 100=hyper-vivid`;

/** 结构化参数工具定义 */
const STRUCTURE_TOOL: OpenAI.Chat.Completions.ChatCompletionTool = {
  type: 'function',
  function: {
    name: 'structure_creative_params',
    description: 'Output the structured creative brief for video prompt generation.',
    parameters: {
      type: 'object',
      properties: {
        base_description: {
          type: 'string',
          description: 'Concise vivid English scene description (2-4 sentences). Subject, setting, visual elements only — no style/motion/camera directives.',
        },
        creative_rationale: {
          type: 'string',
          description: '2-3 sentence Chinese explanation of the chosen creative direction and why it suits the user\'s idea.',
        },
        style:            { type: 'string', enum: ['cinematic', 'commercial', 'documentary', 'social_media', 'artistic'] },
        lighting:         { type: 'string', enum: ['bright_daylight', 'golden_hour', 'soft_diffused', 'dramatic_shadows', 'neon_night'] },
        shot_type:        { type: 'string', enum: ['close_up', 'medium_shot', 'wide_shot', 'aerial_view', 'low_angle'] },
        mood:             { type: 'string', enum: ['energetic', 'serene', 'mysterious', 'joyful', 'dramatic'] },
        color_tone:       { type: 'string', enum: ['warm', 'cool', 'vibrant', 'muted', 'monochrome'] },
        motion_intensity: { type: 'number', minimum: 0, maximum: 100 },
        depth_of_field:   { type: 'number', minimum: 0, maximum: 100 },
        detail_richness:  { type: 'number', minimum: 0, maximum: 100 },
        saturation_level: { type: 'number', minimum: 0, maximum: 100 },
      },
      required: [
        'base_description', 'creative_rationale',
        'style', 'lighting', 'shot_type', 'mood', 'color_tone',
        'motion_intensity', 'depth_of_field', 'detail_richness', 'saturation_level',
      ],
    },
  },
};

/**
 * 结构化分析入口
 *
 * @param imageDescription  - Qwen VL 返回的图片详细描述（英文）
 * @param userIdea          - 用户的简单想法（中文）
 * @returns StructuredAnalysisResult
 */
export async function analyzeAndStructure(
  imageDescription: string,
  userIdea: string
): Promise<StructuredAnalysisResult> {
  if (!config.deepseekApiKey) {
    throw new Error('DEEPSEEK_API_KEY 未配置');
  }

  console.log('[DeepSeek Analyzer] Starting structured analysis');

  const userMessage = `## Image Visual Description (from Vision AI):
${imageDescription}

## User's Creative Idea:
${userIdea}

Please analyze and call structure_creative_params with your creative brief.`;

  const messages: OpenAI.Chat.Completions.ChatCompletionMessageParam[] = [
    { role: 'system', content: ANALYSIS_SYSTEM_PROMPT },
    { role: 'user',   content: userMessage },
  ];

  let totalInputTokens = 0;
  let totalOutputTokens = 0;

  // DeepSeek 应在第一次响应中调用工具；最多重试两次
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await deepseek.chat.completions.create({
      model: MODEL,
      messages,
      tools: [STRUCTURE_TOOL],
      tool_choice: { type: 'function', function: { name: 'structure_creative_params' } },
      temperature: 0.5,
      max_tokens: 1500,
    });

    const usage = response.usage;
    if (usage) {
      totalInputTokens += usage.prompt_tokens || 0;
      totalOutputTokens += usage.completion_tokens || 0;
    }

    const choice = response.choices[0];
    const toolCalls = choice?.message?.tool_calls;

    if (toolCalls && toolCalls.length > 0) {
      const tc = toolCalls[0];
      if (tc.function.name === 'structure_creative_params') {
        try {
          const raw = JSON.parse(tc.function.arguments);

          const params = validateAndNormalizeParams({
            style:            raw.style,
            lighting:         raw.lighting,
            shot_type:        raw.shot_type,
            mood:             raw.mood,
            color_tone:       raw.color_tone,
            motion_intensity: raw.motion_intensity,
            depth_of_field:   raw.depth_of_field,
            detail_richness:  raw.detail_richness,
            saturation_level: raw.saturation_level,
          });

          console.log(
            `[DeepSeek Analyzer] Structured result obtained, ` +
            `tokens=${totalInputTokens + totalOutputTokens}`
          );

          return {
            base_description:  (raw.base_description as string) || imageDescription,
            creative_rationale: (raw.creative_rationale as string) || 'AI 已为您生成创作参数。',
            initial_params:    params,
            tokenUsage: {
              inputTokens:  totalInputTokens,
              outputTokens: totalOutputTokens,
              totalTokens:  totalInputTokens + totalOutputTokens,
            },
          };
        } catch (parseErr) {
          console.warn('[DeepSeek Analyzer] Failed to parse tool args, retrying...', parseErr);
        }
      }
    }

    // 没有拿到 tool call，将当前 assistant 消息加入并再次请求
    if (choice?.message) {
      messages.push(choice.message as OpenAI.Chat.Completions.ChatCompletionMessageParam);
      messages.push({
        role: 'user',
        content: '请务必调用 structure_creative_params 工具输出结构化结果，不要用普通文本回复。',
      });
    }
  }

  // 全部尝试失败 → 使用默认参数回退
  console.warn('[DeepSeek Analyzer] All attempts failed, using default params');
  return {
    base_description:  imageDescription,
    creative_rationale: '已使用默认创作参数，您可以在下方手动调整。',
    initial_params:    defaultParams(),
    tokenUsage: {
      inputTokens:  totalInputTokens,
      outputTokens: totalOutputTokens,
      totalTokens:  totalInputTokens + totalOutputTokens,
    },
  };
}
