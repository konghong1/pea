import {
  IsString,
  IsOptional,
  IsInt,
  Min,
  IsBoolean,
  IsArray,
  MaxLength,
} from 'class-validator';

export class PurchaseDto {
  @IsString()
  planId: string;

  /** 支付幂等键: 同键重复提交不重复到账 */
  @IsOptional()
  @IsString()
  idempotencyKey?: string;
}

export class UpsertPlanDto {
  @IsString() @MaxLength(64)
  id: string;

  @IsOptional() @IsString() @MaxLength(120)
  name?: string;

  @IsOptional() @IsInt() @Min(0)
  planLevel?: number;

  @IsOptional() @IsInt() @Min(0)
  priceCents?: number;

  @IsOptional() @IsInt() @Min(0)
  tapies?: number;

  @IsOptional() @IsInt() @Min(0)
  durationDays?: number;

  @IsOptional() @IsBoolean()
  enabled?: boolean;

  @IsOptional() @IsInt()
  sortOrder?: number;

  @IsOptional() @IsArray()
  features?: string[];
}
