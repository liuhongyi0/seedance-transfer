// ─────────────────────────────────────────────
// Prompt Composer — 结构化参数 → 英文 Flux Prompt
//
// 职责：
//   将 PromptParams 中的分类参数和数值参数，
//   组合成一条完整的 Flux-schnell 英文 Prompt。
//
// 调用方：
//   - /api/wizard/analyze  (初始合成)
//   - /api/wizard/preview  (参数更新后重新合成)
// ─────────────────────────────────────────────

import {
  PromptParams,
  PromptStyle,
  PromptLighting,
  PromptShotType,
  PromptMood,
  PromptColorTone,
} from '../types';

// ═══════════════════════════════════════════════
// 分类参数映射表
// ═══════════════════════════════════════════════

const STYLE_MAP: Record<PromptStyle, string> = {
  cinematic:    'cinematic film style, 4K ultra-detailed, professional cinematography, film grain',
  commercial:   'high-end commercial photography, clean polished look, studio quality',
  documentary:  'documentary photography, natural authentic lighting, photojournalistic',
  social_media: 'trendy social media aesthetic, vibrant eye-catching composition',
  artistic:     'fine art photography, creative composition, artistic interpretation, painterly',
};

const LIGHTING_MAP: Record<PromptLighting, string> = {
  bright_daylight:   'bright natural daylight, crisp clean shadows, clear blue sky',
  golden_hour:       'warm golden hour light, long soft shadows, magical sunset glow',
  soft_diffused:     'soft diffused overcast light, no harsh shadows, gentle ethereal quality',
  dramatic_shadows:  'dramatic chiaroscuro lighting, deep moody shadows, high contrast',
  neon_night:        'neon-lit night scene, colorful reflections on wet surfaces, cyberpunk atmosphere',
};

const SHOT_MAP: Record<PromptShotType, string> = {
  close_up:    'tight close-up shot, subject fills the frame, intimate perspective',
  medium_shot: 'medium shot, subject from waist up, natural conversational framing',
  wide_shot:   'wide establishing shot, subject in full environment context',
  aerial_view: 'aerial bird\'s-eye view, top-down perspective, expansive overview',
  low_angle:   'dramatic low-angle shot, looking up at subject, powerful perspective',
};

const MOOD_MAP: Record<PromptMood, string> = {
  energetic:   'energetic dynamic atmosphere, high energy, lively and vibrant',
  serene:      'serene peaceful atmosphere, tranquil and calm, meditative quality',
  mysterious:  'mysterious atmospheric mood, enigmatic, slightly surreal undertone',
  joyful:      'joyful uplifting mood, warm positive emotion, celebratory feel',
  dramatic:    'dramatic intense mood, emotional weight, theatrical gravitas',
};

const COLOR_MAP: Record<PromptColorTone, string> = {
  warm:       'warm color palette, amber and golden tones, cozy inviting feel',
  cool:       'cool color palette, blue and silver tones, crisp refreshing feel',
  vibrant:    'vibrant saturated colors, rich hues, colorful and lively',
  muted:      'muted desaturated palette, earthy tones, understated elegance',
  monochrome: 'monochromatic color scheme, tonal harmony, unified visual feel',
};

// ═══════════════════════════════════════════════
// 数值参数映射
// ═══════════════════════════════════════════════

function motionFragment(v: number): string {
  if (v < 15) return 'completely static, no motion, still photograph quality';
  if (v < 35) return 'subtle gentle motion, slight organic movement';
  if (v < 60) return 'smooth flowing movement, graceful natural motion';
  if (v < 80) return 'dynamic active motion, energetic movement';
  return 'fast kinetic action, high-energy dynamic movement, blur trails';
}

function dofFragment(v: number): string {
  if (v < 15) return 'everything in crisp sharp focus, deep depth of field, pan focus';
  if (v < 40) return 'slight background softness, gentle depth separation';
  if (v < 65) return 'prominent background bokeh, shallow depth of field, subject isolation';
  if (v < 85) return 'beautiful creamy bokeh, razor-thin depth of field';
  return 'extreme lens blur bokeh, maximum subject isolation, f/1.2 effect';
}

function detailFragment(v: number): string {
  if (v < 15) return 'minimalist clean composition, uncluttered negative space';
  if (v < 40) return 'balanced natural detail level';
  if (v < 65) return 'rich detailed textures, fine surface details visible';
  if (v < 85) return 'highly detailed, intricate textures, meticulous rendering';
  return 'hyperdetailed 8K ultra-resolution, intricate microscopic detail, photorealistic';
}

function saturationFragment(v: number): string {
  if (v < 15) return 'desaturated near-monochrome palette, drained of color';
  if (v < 35) return 'natural muted color saturation, understated palette';
  if (v < 55) return 'balanced natural color reproduction';
  if (v < 75) return 'vivid enhanced saturation, punchy colors';
  return 'hyper-vivid ultra-saturated neon colors, maximum color intensity';
}

// ═══════════════════════════════════════════════
// 主合成函数
// ═══════════════════════════════════════════════

/**
 * 将 base_description（Qwen VL 描述）和 PromptParams 合成为完整英文 Flux Prompt。
 *
 * 输出格式：
 *   [scene description], [style], [lighting], [shot type], [mood],
 *   [color tone], [motion], [depth of field], [detail], [saturation].
 *   High quality, best quality.
 */
export function composePrompt(baseDescription: string, params: PromptParams): string {
  const clamp = (v: number) => Math.max(0, Math.min(100, Math.round(v)));

  const parts: string[] = [
    baseDescription.trim(),
    STYLE_MAP[params.style]        ?? STYLE_MAP['cinematic'],
    LIGHTING_MAP[params.lighting]  ?? LIGHTING_MAP['soft_diffused'],
    SHOT_MAP[params.shot_type]     ?? SHOT_MAP['medium_shot'],
    MOOD_MAP[params.mood]          ?? MOOD_MAP['serene'],
    COLOR_MAP[params.color_tone]   ?? COLOR_MAP['vibrant'],
    motionFragment(clamp(params.motion_intensity)),
    dofFragment(clamp(params.depth_of_field)),
    detailFragment(clamp(params.detail_richness)),
    saturationFragment(clamp(params.saturation_level)),
    'high quality, best quality, masterpiece',
  ];

  return parts.join(', ');
}

// ═══════════════════════════════════════════════
// 默认参数（DeepSeek 分析失败时的回退）
// ═══════════════════════════════════════════════

export function defaultParams(): PromptParams {
  return {
    style:            'cinematic',
    lighting:         'soft_diffused',
    shot_type:        'medium_shot',
    mood:             'serene',
    color_tone:       'vibrant',
    motion_intensity: 30,
    depth_of_field:   40,
    detail_richness:  55,
    saturation_level: 50,
  };
}

// ═══════════════════════════════════════════════
// 参数范围校验
// ═══════════════════════════════════════════════

const VALID_STYLES: PromptStyle[]     = ['cinematic', 'commercial', 'documentary', 'social_media', 'artistic'];
const VALID_LIGHTINGS: PromptLighting[] = ['bright_daylight', 'golden_hour', 'soft_diffused', 'dramatic_shadows', 'neon_night'];
const VALID_SHOTS: PromptShotType[]   = ['close_up', 'medium_shot', 'wide_shot', 'aerial_view', 'low_angle'];
const VALID_MOODS: PromptMood[]       = ['energetic', 'serene', 'mysterious', 'joyful', 'dramatic'];
const VALID_COLORS: PromptColorTone[] = ['warm', 'cool', 'vibrant', 'muted', 'monochrome'];

export function validateAndNormalizeParams(raw: Partial<PromptParams>): PromptParams {
  const defaults = defaultParams();
  const clamp = (v: unknown, def: number): number => {
    const n = typeof v === 'number' ? v : def;
    return Math.max(0, Math.min(100, Math.round(n)));
  };

  return {
    style:            VALID_STYLES.includes(raw.style as PromptStyle) ? raw.style as PromptStyle : defaults.style,
    lighting:         VALID_LIGHTINGS.includes(raw.lighting as PromptLighting) ? raw.lighting as PromptLighting : defaults.lighting,
    shot_type:        VALID_SHOTS.includes(raw.shot_type as PromptShotType) ? raw.shot_type as PromptShotType : defaults.shot_type,
    mood:             VALID_MOODS.includes(raw.mood as PromptMood) ? raw.mood as PromptMood : defaults.mood,
    color_tone:       VALID_COLORS.includes(raw.color_tone as PromptColorTone) ? raw.color_tone as PromptColorTone : defaults.color_tone,
    motion_intensity: clamp(raw.motion_intensity, defaults.motion_intensity),
    depth_of_field:   clamp(raw.depth_of_field, defaults.depth_of_field),
    detail_richness:  clamp(raw.detail_richness, defaults.detail_richness),
    saturation_level: clamp(raw.saturation_level, defaults.saturation_level),
  };
}
