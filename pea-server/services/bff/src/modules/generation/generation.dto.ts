import {
  IsString,
  IsIn,
  IsOptional,
  MinLength,
  MaxLength,
  IsObject,
} from 'class-validator';

export class AcceptGenerationDto {
  @IsIn(['image', 'video', 'text'])
  type: 'image' | 'video' | 'text';

  @IsString()
  @MinLength(1)
  @MaxLength(4000)
  prompt: string;

  /** 模型 id (ai_models.id)。缺省时按类型取默认模型。 */
  @IsOptional()
  @IsString()
  model?: string;

  /** 生成参数 (size / duration / n / reference_images 等)。用于服务端算价与下游调用。 */
  @IsOptional()
  @IsObject()
  params?: Record<string, any>;

  @IsOptional()
  @IsIn(['normal', 'fast'])
  priority?: 'normal' | 'fast';

  /** 幂等键: 同键重复提交不重复扣费/生成 */
  @IsOptional()
  @IsString()
  idempotencyKey?: string;

  /** Phase2: 图片/视频节点所选平台配置 id (提示词构造层据此拼平台化提示词) */
  @IsOptional()
  @IsString()
  platformConfigId?: string;

  // 注意: 价格由服务端按 模型 + 参数 计算 (PricingService), 客户端不得指定 costTapies。
}

/**
 * 节点图片/视频生成专用 DTO — 与电商套图 AcceptGenerationDto 解耦。
 * 节点自身用「比例/分辨率」UI 拼参, 不携带 platformConfigId (编排器对 image/video 的 platform_config_id 为空则原样用 prompt)。
 */
export class AcceptNodeGenerationDto {
  @IsIn(['image', 'video'])
  type: 'image' | 'video';

  @IsString()
  @MinLength(1)
  @MaxLength(4000)
  prompt: string;

  /** 模型 id (ai_models.id)。缺省时按类型取默认模型。 */
  @IsOptional()
  @IsString()
  model?: string;

  /** 生成参数 (size / width / height / n 等)。节点已按比例·分辨率拼好。 */
  @IsOptional()
  @IsObject()
  params?: Record<string, any>;

  @IsOptional()
  @IsIn(['normal', 'fast'])
  priority?: 'normal' | 'fast';

  /** 幂等键: 同键重复提交不重复扣费/生成 */
  @IsOptional()
  @IsString()
  idempotencyKey?: string;
}
