import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Post,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { AdminGuard } from '../../common/guards/admin.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { PlansService } from './plans.service';
import { PurchaseDto, UpsertPlanDto } from './plans.dto';

/** 用户侧: 套餐列表 + 购买。 */
@Controller('plans')
@UseGuards(JwtAuthGuard)
export class PlansController {
  constructor(private readonly plans: PlansService) {}

  @Get()
  list() {
    return this.plans.listPlans(false);
  }

  @Post('purchase')
  purchase(@CurrentUser() u: { sub: number }, @Body() dto: PurchaseDto) {
    return this.plans.purchase(u.sub, dto.planId, dto.idempotencyKey);
  }
}

/** 管理员: 套餐 CRUD。 */
@Controller('admin/plans')
@UseGuards(JwtAuthGuard, AdminGuard)
export class AdminPlansController {
  constructor(private readonly plans: PlansService) {}

  @Get()
  list() {
    return this.plans.listPlans(true);
  }

  @Post()
  upsert(@Body() dto: UpsertPlanDto) {
    return this.plans.upsertPlan(dto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.plans.deletePlan(id);
  }
}
