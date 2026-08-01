import {
  IsString,
  IsOptional,
  IsInt,
  IsBoolean,
  IsIn,
  MaxLength,
  Min,
} from 'class-validator';

export class CreateOrderDto {
  @IsString() @MaxLength(64)
  planId: string;
}

export class SubmitProofDto {
  /** 付款截图对象 key（先经 POST /files/upload 上传拿到）。 */
  @IsOptional() @IsString() @MaxLength(512)
  proofKey?: string;

  /** 付款备注：付款人昵称 / 转账单号后四位，便于管理员核对。 */
  @IsOptional() @IsString() @MaxLength(255)
  proofNote?: string;
}

export class ReviewOrderDto {
  @IsOptional() @IsString() @MaxLength(255)
  reviewNote?: string;

  /** 实收金额（分）。留空则按订单应付金额记账。 */
  @IsOptional() @IsInt() @Min(0)
  paidAmountCents?: number;
}

export class UpsertQrcodeDto {
  @IsOptional() @IsInt()
  id?: number;

  @IsOptional() @IsIn(['wechat', 'alipay', 'other'])
  channel?: string;

  @IsOptional() @IsString() @MaxLength(64)
  label?: string;

  @IsOptional() @IsString() @MaxLength(128)
  accountNote?: string;

  /** 二维码图片对象 key（管理员经 POST /files/upload 上传）。 */
  @IsOptional() @IsString() @MaxLength(512)
  imageKey?: string;

  @IsOptional() @IsBoolean()
  enabled?: boolean;

  @IsOptional() @IsInt()
  sortOrder?: number;
}
