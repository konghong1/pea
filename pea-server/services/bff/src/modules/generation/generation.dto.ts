import {
  IsString,
  IsIn,
  IsOptional,
  MinLength,
  MaxLength,
  IsInt,
  Min,
} from 'class-validator';

export class AcceptGenerationDto {
  @IsIn(['image', 'video', 'text'])
  type: 'image' | 'video' | 'text';

  @IsString()
  @MinLength(1)
  @MaxLength(4000)
  prompt: string;

  @IsOptional()
  @IsString()
  model?: string;

  @IsOptional()
  @IsIn(['normal', 'fast'])
  priority?: 'normal' | 'fast';

  /** 幂等键: 同键重复提交不重复扣费/生成 */
  @IsOptional()
  @IsString()
  idempotencyKey?: string;

  @IsOptional()
  @IsInt()
  @Min(0)
  costTapies?: number;
}
