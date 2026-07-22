import { Controller, Get, Query, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { BillingService } from './billing.service';

@Controller('billing')
@UseGuards(JwtAuthGuard)
export class BillingController {
  constructor(private readonly billing: BillingService) {}

  @Get('balance')
  balance(@CurrentUser() u: { sub: number }) {
    return this.billing.getBalance(u.sub);
  }

  @Get('ledger')
  ledger(
    @CurrentUser() u: { sub: number },
    @Query('page') page = 1,
    @Query('size') size = 20,
  ) {
    return this.billing.listLedger(u.sub, Number(page), Number(size));
  }
}
