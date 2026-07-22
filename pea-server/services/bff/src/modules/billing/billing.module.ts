import { Module } from '@nestjs/common';
import { BillingService } from './billing.service';
import { BillingController } from './billing.controller';
import { InternalBillingController } from './internal.controller';

@Module({
  controllers: [BillingController, InternalBillingController],
  providers: [BillingService],
  exports: [BillingService],
})
export class BillingModule {}
