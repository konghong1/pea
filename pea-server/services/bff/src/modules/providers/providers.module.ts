import { Module } from '@nestjs/common';
import { UsersModule } from '../users/users.module';
import { ProvidersService } from './providers.service';
import { ModelsService } from './models.service';
import { PricingService } from './pricing.service';
import { AdminProvidersController } from './admin-providers.controller';
import { AdminModelsController } from './admin-models.controller';
import { ModelsController } from './models.controller';
import { AdminGuard } from '../../common/guards/admin.guard';

/**
 * AI 提供商 / 模型 / 定价 域。
 *  - 管理员: 提供商 CRUD + 远端模型拉取 + 模型 CRUD (含动态定价)。
 *  - 用户侧: 可用模型列表 + 价格预估。
 *  - 对外导出 ModelsService / PricingService 供 Generation 域受理时算价与访问控制。
 */
@Module({
  imports: [UsersModule],
  controllers: [AdminProvidersController, AdminModelsController, ModelsController],
  providers: [ProvidersService, ModelsService, PricingService, AdminGuard],
  exports: [ProvidersService, ModelsService, PricingService],
})
export class ProvidersModule {}
