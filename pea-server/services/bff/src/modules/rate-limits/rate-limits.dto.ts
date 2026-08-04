import { IsBoolean, IsInt, IsOptional, IsString, MaxLength, Min } from 'class-validator';

/** 速率限制规则: 维度 (provider_id[, model_id][, tier]) + 配额 (limit_n / window_s)。 */
export class CreateRateLimitDto {
  @IsString()
  @MaxLength(64)
  provider_id: string;

  @IsOptional()
  @IsString()
  @MaxLength(64)
  model_id?: string;

  /** 图像档位 '4K'/'2K'/...; 不传 = 适用于该 provider/model 的任意档。 */
  @IsOptional()
  @IsString()
  @MaxLength(16)
  tier?: string;

  /** 每窗口允许请求数 (>=1)。 */
  @IsInt()
  @Min(1)
  limit_n: number;

  /** 窗口秒数 (>=1)。例如 4K 档 Agnes 限制 1 次/60s -> limit_n=1, window_s=60。 */
  @IsInt()
  @Min(1)
  window_s: number;

  @IsOptional()
  @IsBoolean()
  enabled?: boolean;
}

export class UpdateRateLimitDto {
  @IsOptional()
  @IsString()
  @MaxLength(64)
  provider_id?: string;

  @IsOptional()
  @IsString()
  @MaxLength(64)
  model_id?: string;

  @IsOptional()
  @IsString()
  @MaxLength(16)
  tier?: string;

  @IsOptional()
  @IsInt()
  @Min(1)
  limit_n?: number;

  @IsOptional()
  @IsInt()
  @Min(1)
  window_s?: number;

  @IsOptional()
  @IsBoolean()
  enabled?: boolean;
}
