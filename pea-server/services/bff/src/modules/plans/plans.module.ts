import { Module } from '@nestjs/common';
import { PlansService } from './plans.service';
import { PlansController, AdminPlansController } from './plans.controller';
import { AdminGuard } from '../../common/guards/admin.guard';

/** 套餐售卖域: 用户购买 (原子到账) + 管理员 CRUD。RedisPubSub 由 InfraModule 全局提供。 */
@Module({
  controllers: [PlansController, AdminPlansController],
  providers: [PlansService, AdminGuard],
  exports: [PlansService],
})
export class PlansModule {}
