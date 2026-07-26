/**
 * PromptRewriter — 文本节点提示词改写与润色引擎
 *
 * 核心能力：
 * 1. 将用户的简单词语/短句扩写为高质量的图片/视频提示词
 * 2. 支持多种风格模板（写实、动漫、电影级、艺术等）
 * 3. 结构化的 prompt 构建器（主体 + 环境 + 风格 + 技术参数）
 * 4. 完全独立于 Agent 聊天框，走专用 API 路径
 */

// ─── 类型定义 ──────────────────────────────────────────────

export type PromptMediaType = 'image' | 'video';

export interface PromptRewriteOptions {
  /** 目标媒体类型 */
  mediaType?: PromptMediaType;
  /** 风格模板 */
  style?: StyleTemplate;
  /** 语言偏好 */
  language?: 'zh' | 'en';
  /** 是否自动增强细节 */
  autoEnhance?: boolean;
}

export interface PromptResult {
  /** 改写后的提示词（用户可直接复制使用） */
  rewritten: string;
  /** 原始输入 */
  original: string;
  /** 媒体类型 */
  mediaType: PromptMediaType;
  /** 使用的风格 */
  style: StyleTemplate;
  /** 结构化分段（用于展示） */
  segments?: PromptSegments;
}

export type StyleTemplate =
  | 'realistic'
  | 'anime'
  | 'cinematic'
  | 'artistic'
  | 'minimal'
  | 'cyberpunk'
  | 'fantasy'
  | 'watercolor'
  | '3d-render'
  | 'auto';

// ─── 风格模板库 ─────────────────────────────────────────────

interface StyleEntry {
  image: string[];
  video: string[];
}

const STYLE_PROMPTS: Record<StyleTemplate, StyleEntry> = {
  realistic: {
    image: [
      'Professional photography, ultra detailed, 8K resolution, natural lighting, shot on Canon EOS R5 with 85mm f/1.4 lens',
      'High-end photographic quality, sharp focus, cinematic depth of field, professional color grading, studio lighting setup',
    ],
    video: [
      'Cinematic video, 4K UHD, professional camera movement, smooth gimbal shots, natural ambient lighting, high frame rate',
      'Documentary style footage, crystal clear quality, dynamic range optimized, realistic motion blur, anamorphic lens flares',
    ],
  },
  anime: {
    image: [
      'Anime art style, vibrant colors, cel shading, Studio Ghibli inspired, detailed background art, beautiful line work',
      'Japanese animation style, expressive eyes, soft pastel color palette, manga aesthetics, detailed character design',
    ],
    video: [
      'Anime animation style, smooth frame interpolation, vibrant color grading, Katsuhiro Otomo inspired motion sequences',
      'Modern anime production quality, dynamic camera angles, fluid character animation, sakuga-style action moments',
    ],
  },
  cinematic: {
    image: [
      'Hollywood cinematography, anamorphic widescreen, dramatic chiaroscuro lighting, IMAX quality, color graded in DaVinci Resolve',
      'Epic cinematic composition, shot on ARRI Alexa 65, golden hour lighting, volumetric fog, film grain texture',
    ],
    video: [
      'Blockbuster cinematography, IMAX 65mm, sweeping crane shots, dramatic tracking sequences, Hans Zimmer-level atmosphere',
      'Cinematic storytelling, dynamic dolly movements, film noir lighting, anamorphic lens characteristics, widescreen 2.39:1',
    ],
  },
  artistic: {
    image: [
      'Contemporary digital art, intricate details, surrealist composition, ArtStation trending, masterpiece quality, ethereal glow',
      'Fantasy illustration style, rich oil painting textures, Rembrandt-inspired lighting, intricate ornamental details',
    ],
    video: [
      'Animated art piece, impressionist motion painting, flowing watercolor transitions, Monet-inspired color palettes',
      'Experimental animation style, mixed media compositing, hand-drawn elements over digital backgrounds, Tim Burton aesthetic',
    ],
  },
  minimal: {
    image: [
      'Minimalist composition, clean negative space, Scandinavian design principles, muted earth tones, modern and uncluttered',
      'Bauhaus-inspired minimalism, geometric precision, limited color palette, elegant simplicity, Swiss design typography feel',
    ],
    video: [
      'Minimalist motion design, clean geometric transitions, restrained color palette, modern branding aesthetic, smooth easing curves',
      'Contemporary motion graphics, Helvetica spacing, Swiss grid layout, quiet luxury visual language, deliberate pacing',
    ],
  },
  cyberpunk: {
    image: [
      'Cyberpunk aesthetic, neon-lit rain-slicked streets, synthwave color palette, Blade Runner inspired, holographic advertisements',
      'Dark futuristic cityscape, chromatic aberration, volumetric neon glow, dystopian architecture, retrowave atmosphere',
    ],
    video: [
      'Cyberpunk future world, neon-noir atmosphere, rain-soaked streets reflecting holographic billboards, Blade Runner 2049 vibe',
      'Futuristic urban chase scene, purple and teal color grade, flying vehicles, augmented reality overlays, high-tech low-life',
    ],
  },
  fantasy: {
    image: [
      'Epic high fantasy, enchanted forest setting, magical luminescence, ancient ruins, Lord of the Rings inspired worldbuilding',
      'Mythological realm, ethereal light rays, floating islands, dragon silhouette in clouds, J.R.R. Tolkien aesthetic',
    ],
    video: [
      'Epic fantasy world, sweeping landscape reveals, magical particle effects, ancient crystalline structures, Dragon Age atmosphere',
      'Mythological adventure, enchanted forest journey, spectral light through canopy, mystical creature encounters, dark souls aesthetic',
    ],
  },
  watercolor: {
    image: [
      'Delicate watercolor painting, wet-on-wet technique, translucent layers, soft pigment bleeding, Winsor & Newton palette',
      'Contemporary watercolor illustration, organic paper texture, botanical illustration detail, gentle wash gradients',
    ],
    video: [
      'Watercolor animation style, organic pigment diffusion, paper grain overlay, soft edge transitions, traditional media motion',
      'Fluid watercolor morphing, color blooming effects, hand-painted frames, Studio Ghibli background aesthetic, delicate brush strokes',
    ],
  },
  '3d-render': {
    image: [
      'Photorealistic 3D render, Octane Render engine, physically based materials, global illumination, ray-traced reflections',
      'Unreal Engine 5 cinematic, Lumen global illumination, Nanite geometry, volumetric lighting, hyper-realistic PBR materials',
    ],
    video: [
      '3D animated short, Pixar-quality character animation, subsurface scattering, physically accurate materials, Octane rendered',
      'Cinematic 3D animation, Houdini VFX simulation, fluid dynamics, destruction physics, Marvel-level compositing',
    ],
  },
  auto: {
    image: [
      'Professional quality artwork, masterful composition, museum-grade detail, trending on ArtStation, contemporary aesthetic',
    ],
    video: [
      'Professional quality animation, smooth motion design, contemporary visual style, broadcast-grade production, award-winning aesthetic',
    ],
  },
};

// ─── 扩写增强层 ─────────────────────────────────────────────

const ENHANCEMENT_LAYERS = {
  lighting: [
    'balanced ambient illumination, natural light flow',
    'soft diffused lighting, gentle gradients',
    'dramatic chiaroscuro lighting with defined shadows',
  ],
  composition: [
    'masterful composition following rule of thirds',
    'leading lines guiding the eye through the frame',
    'dynamic diagonal composition for visual tension',
  ],
  mood: [
    'evoking a sense of wonder and awe',
    'with emotionally resonant atmosphere',
    'capturing a transcendent moment of beauty',
  ],
  quality: [
    'award-winning quality, gallery-worthy',
    'museum-exhibition standard, timeless masterpiece',
    'commercial publication ready, professional finishing',
  ],
};

const VIDEO_MOTION_HINTS = [
  'slow cinematic pan across the scene',
  'gentle camera push-in with shallow depth of field',
  'smooth tracking shot following the main subject',
  'dynamic orbit around focal point revealing new angles',
  'establishing wide shot gradually tightening to intimate close-up',
];

// ─── 核心改写引擎 ─────────────────────────────────────────────

export class PromptRewriter {
  /**
   * 将用户的简短输入改写为结构化的高质量提示词
   */
  rewrite(input: string, options: PromptRewriteOptions = {}): PromptResult {
    const mediaType = options.mediaType ?? 'image';
    const style = options.style ?? 'auto';
    const language = options.language ?? 'zh';
    const autoEnhance = options.autoEnhance ?? true;

    const base = this.parseInput(input);
    const styleEntry = STYLE_PROMPTS[style];
    const styleArr = styleEntry?.[mediaType] ?? styleEntry?.image ?? [];
    const stylePart = styleArr.length > 0 ? styleArr[0] : '';

    // 构建结构化分段
    const segments: Partial<PromptSegments> = {
      subject: base.subject,
      description: base.description,
      style: stylePart,
    };

    if (autoEnhance) {
      Object.assign(segments, this.generateEnhancements(base, style, mediaType));
    }

    // 合并为最终提示词
    const rewritten = this.mergePrompt(segments as PromptSegments, mediaType, language);

    return {
      rewritten,
      original: input,
      mediaType,
      style,
      segments: segments as PromptSegments,
    };
  }

  /**
   * 解析用户输入，提取主体和描述
   */
  private parseInput(input: string): { subject: string; description: string } {
    const trimmed = input.trim();

    // 如果已经包含逗号或连接词，可能是复合描述
    if (trimmed.includes('，') || trimmed.includes(',') || trimmed.includes('的')) {
      const parts = trimmed.split(/[，,]/).map((p) => p.trim()).filter(Boolean);
      return {
        subject: parts[0] || trimmed,
        description: parts.slice(1).join(', ') || '',
      };
    }

    // 纯简单词语 → 主体就是输入本身
    return {
      subject: trimmed,
      description: '',
    };
  }

  /**
   * 根据主体自动生成增强层描述
   */
  private generateEnhancements(
    base: { subject: string; description: string },
    style: StyleTemplate,
    mediaType: PromptMediaType,
  ): Pick<PromptSegments, 'lighting' | 'composition' | 'mood' | 'quality'> {
    const subject = base.subject.toLowerCase();
    const extras: Partial<Pick<PromptSegments, 'lighting' | 'composition' | 'mood' | 'quality'>> = {};

    // 根据主体关键词智能推荐
    if (/女人|女性|女孩|girl|woman|lady/.test(subject)) {
      extras.lighting = 'soft beauty lighting, rim light separation, flattering portrait illumination';
      extras.composition = 'rule of thirds portrait framing, eye-level angle';
      extras.mood = 'confident yet approachable, authentic personality shining through';
    } else if (/男人|男性|男孩|man|boy|male/.test(subject)) {
      extras.lighting = 'dramatic side lighting, defined shadows, masculine tonal range';
      extras.composition = 'power pose, low angle authority framing';
      extras.mood = 'commanding presence, quiet confidence, grounded strength';
    } else if (/风景|nature|landscape|山|海|景|自然/.test(subject)) {
      extras.lighting = 'golden hour warmth, natural sky illumination, volumetric light rays';
      extras.composition = 'grand panoramic sweep, layered foreground-middle-ground-background';
      extras.mood = 'tranquil majesty, humbling vastness of the natural world';
    } else if (/城市|city|urban|建筑|building|街|street/.test(subject)) {
      extras.lighting = 'urban ambient glow, window light pools, street lamp pools';
      extras.composition = 'leading lines drawing eye through architectural elements';
      extras.mood = 'the energy of metropolitan life captured in a single frame';
    } else if (/动物|animal|pet|dog|cat|猫|狗|鸟|bird/.test(subject)) {
      extras.lighting = 'natural window light, soft catchlight in eyes';
      extras.composition = 'eye-level perspective, intimate framing';
      extras.mood = 'innocent charm, soulful expressiveness, personality in every detail';
    } else if (/食物|food|dish|餐|料理|蛋糕|cake/.test(subject)) {
      extras.lighting = 'warm food photography lighting, appetizing highlights';
      extras.composition = 'styled flat lay or 45-degree angle, generous negative space';
      extras.mood = 'inviting warmth, artisan craftsmanship, feast for the eyes';
    } else if (/科技|tech|digital|AI|computer|科技|未来|future/.test(subject)) {
      extras.lighting = 'cool LED accent lights, holographic glows';
      extras.composition = 'clean futuristic composition, geometric precision';
      extras.mood = 'sleek innovation, tomorrow\'s technology, today';
    } else if (/音乐|music|song|表演|perform/.test(subject)) {
      extras.lighting = 'stage spotlights, colored gels, atmospheric haze';
      extras.composition = 'dynamic action angle, candid performance capture';
      extras.mood = 'raw creative energy, electric audience connection';
    } else if (/车|car|vehicle|auto|automobile/.test(subject)) {
      extras.lighting = 'studio showroom lighting, flowing reflection strips';
      extras.composition = 'three-quarter front angle, low stance power pose';
      extras.mood = 'sleek engineering, automotive sculpture in motion';
    } else if (/儿童|child|baby|kid|婴儿/.test(subject)) {
      extras.lighting = 'soft diffused natural light, gentle wrap-around quality';
      extras.composition = 'close-up intimate framing, playful spontaneity';
      extras.mood = 'pure joy, innocent wonder, heartwarming authenticity';
    }

    // 默认增强层（从 ENHANCEMENT_LAYERS 中取第一项）
    if (!extras.lighting) extras.lighting = ENHANCEMENT_LAYERS.lighting[0]!;
    if (!extras.composition) extras.composition = ENHANCEMENT_LAYERS.composition[0]!;
    if (!extras.mood) extras.mood = ENHANCEMENT_LAYERS.mood[0]!;
    if (!extras.quality) extras.quality = ENHANCEMENT_LAYERS.quality[0]!;

    return extras as Pick<PromptSegments, 'lighting' | 'composition' | 'mood' | 'quality'>;
  }

  /**
   * 合并所有段落为最终提示词
   */
  private mergePrompt(
    segments: PromptSegments,
    mediaType: PromptMediaType,
    language: 'zh' | 'en',
  ): string {
    const parts = [segments.subject];

    if (segments.description) parts.push(segments.description);
    if (segments.lighting) parts.push(segments.lighting);
    if (segments.composition) parts.push(segments.composition);
    if (segments.style) parts.push(segments.style);
    if (segments.mood) parts.push(segments.mood);
    if (segments.quality) parts.push(segments.quality);

    let prompt = parts.join(', ');

    // 视频节点追加运动提示
    if (mediaType === 'video') {
      const motionHints = VIDEO_MOTION_HINTS;
      const randomHint = motionHints[Math.floor(Math.random() * motionHints.length)];
      prompt += `, ${randomHint}`;
    }

    return prompt;
  }
}

// ─── 导出单例 ──────────────────────────────────────────────

export const promptRewriter = new PromptRewriter();

// ─── 辅助类型 ──────────────────────────────────────────────

interface PromptSegments {
  subject: string;          // 主体描述
  description: string;      // 补充描述
  lighting: string;         // 光影设置
  composition: string;      // 构图手法
  style: string;            // 风格标签
  mood: string;             // 情绪氛围
  quality: string;          // 质量标准
}
