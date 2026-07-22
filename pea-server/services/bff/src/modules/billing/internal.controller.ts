import { Body, Controller, Post, UseGuards } from '@nestjs/common';
import { IsInt, IsString, IsOptional, Min } from 'class-validator';
import { InternalAuthGuard } from '../../common/internal-auth.guard';
import { BillingService } from './billing.service';

class RefundDto {
  @IsInt()
  userId: number;

  @IsInt()
  @Min(0)
  amount: number;

  @IsString()
  txnId: string;

  @IsOptional()
  @IsString()
  jobId?: string;
}

/** 内部接口: 仅 orchestrator 经 service token 调用, 用于生成失败补偿退款. */
@Controller('internal/billing')
@UseGuards(InternalAuthGuard)
export class InternalBillingController {
  constructor(private readonly billing: BillingService) {}

  @Post('refund')
  refund(@Body() dto: RefundDto) {
    return this.billing.refund(dto.userId, dto.amount, dto.txnId, dto.jobId);
  }
}
