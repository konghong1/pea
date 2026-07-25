import { Module, NestModule, MiddlewareConsumer } from '@nestjs/common';
import { ConfigModuleRoot } from './config/config.module';
import { DatabaseModule } from './database/database.module';
import { InfraModule } from './infra/infra.module';
import { AuthModule } from './modules/auth/auth.module';
import { UsersModule } from './modules/users/users.module';
import { BillingModule } from './modules/billing/billing.module';
import { GenerationModule } from './modules/generation/generation.module';
import { FilesModule } from './modules/files/files.module';
import { CanvasesModule } from './modules/canvases/canvases.module';
import { ProvidersModule } from './modules/providers/providers.module';
import { PlansModule } from './modules/plans/plans.module';
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
    FilesModule,
    CanvasesModule,
    ProvidersModule,
    PlansModule,
    CommunityModule,
    GatewayModule,
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(RateLimitMiddleware).forRoutes('*');
  }
}
