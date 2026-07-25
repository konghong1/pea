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

  // 注意: 价格由服务端按 模型 + 参数 计算 (PricingService), 客户端不得指定 costTapies。
}
