import { Module, NestModule, MiddlewareConsumer } from '@nestjs/common';
import { ConfigModuleRoot } from './config/config.module';
import { DatabaseModule } from './database/database.module';
import { InfraModule } from './infra/infra.module';
import { AuthModule } from './modules/auth/auth.module';
import { UsersModule } from './modules/users/users.module';
import { BillingModule } from './modules/billing/billing.module';
import { GenerationModule } from './modules/generation/generation.module';
import { PlatformConfigsModule } from './modules/platform-configs/platform-configs.module';
import { UsageModule } from './modules/usage/usage.module';
import { ChatModule } from './modules/chat/chat.module';
import { FilesModule } from './modules/files/files.module';
import { AssetsModule } from './modules/assets/assets.module';
import { CanvasesModule } from './modules/canvases/canvases.module';
import { ProvidersModule } from './modules/providers/providers.module';
import { RateLimitsModule } from './modules/rate-limits/rate-limits.module';
import { PlansModule } from './modules/plans/plans.module';
import { OrdersModule } from './modules/orders/orders.module';
import { CommunityModule } from './modules/community/community.module';
import { GatewayModule } from './modules/gateway/gateway.module';
import { RateLimitMiddleware } from './common/rate-limit.middleware';

@Module({
  imports: [
    ConfigModuleRoot,
    DatabaseModule,
    InfraModule,
    AuthModule,
    UsersModule,
    BillingModule,
    GenerationModule,
    PlatformConfigsModule,
    UsageModule,
    ChatModule,
    FilesModule,
    AssetsModule,
    CanvasesModule,
    ProvidersModule,
    RateLimitsModule,
    PlansModule,
    OrdersModule,
    CommunityModule,
    GatewayModule,
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(RateLimitMiddleware).forRoutes('*');
  }
}
