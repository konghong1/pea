import { Controller, Get, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { UsageService } from './usage.service';

@Controller('usage')
@UseGuards(JwtAuthGuard)
export class UsageController {
  constructor(private readonly svc: UsageService) {}

  @Get('summary')
  summary(@CurrentUser() u: { sub: number }) {
    return this.svc.summary(u.sub);
  }
}
