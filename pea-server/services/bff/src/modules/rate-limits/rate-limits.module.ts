import { Module } from '@nestjs/common';
import { RateLimitsService } from './rate-limits.service';
import { RateLimitsController } from './rate-limits.controller';
import { AdminGuard } from '../../common/guards/admin.guard';

/**
 * 速率限制规则后台配置域。
 *  - 管理员: 规则 CRUD (per-provider / per-model / per-tier)。
 *  - 编排器以 TTL 缓存加载这些规则并驱动分布式令牌桶, 改完无需重启编排器。
 */
@Module({
  controllers: [RateLimitsController],
  providers: [RateLimitsService, AdminGuard],
  exports: [RateLimitsService],
})
export class RateLimitsModule {}
