import {
  IsString,
  IsIn,
  IsOptional,
  IsBoolean,
  IsObject,
  MinLength,
  MaxLength,
} from 'class-validator';

export class CreatePlatformConfigDto {
  @IsString()
  @MinLength(1)
  @MaxLength(120)
  name: string;

  /** 平台标识: midjourney / dalle / sora / stable-diffusion / generic 等 */
  @IsOptional()
  @IsString()
  @MaxLength(64)
  platform?: string = 'generic';

  @IsIn(['image', 'video'])
  kind: 'image' | 'video';

  /** plain: 模板拼装 (零额外成本); llm: 先调文本 LLM 扩写 (需 expandModel) */
  @IsOptional()
  @IsIn(['plain', 'llm'])
  promptMode?: 'plain' | 'llm' = 'plain';

  /** { style_prefix, negative_prompt, aspect_ratio, quality, extra } */
  @IsOptional()
  @IsObject()
  presets?: Record<string, any>;

  /** llm 模式扩写所用模型 (ai_models.id); 空则自动回退 plain */
  @IsOptional()
  @IsString()
  expandModel?: string;

  @IsOptional()
  @IsBoolean()
  isDefault?: boolean = false;
}

export class UpdatePlatformConfigDto {
  @IsOptional()
  @IsString()
  @MinLength(1)
  @MaxLength(120)
  name?: string;

  @IsOptional()
  @IsString()
  @MaxLength(64)
  platform?: string;

  @IsOptional()
  @IsIn(['plain', 'llm'])
  promptMode?: 'plain' | 'llm';

  @IsOptional()
  @IsObject()
  presets?: Record<string, any>;

  @IsOptional()
  @IsString()
  expandModel?: string;

  @IsOptional()
  @IsBoolean()
  isDefault?: boolean;
}
