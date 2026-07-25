import { Module } from '@nestjs/common';
import { BillingModule } from '../billing/billing.module';
import { ProvidersModule } from '../providers/providers.module';
import { OrchestratorHttpClient } from '../orchestrator-client/orchestrator-http.service';
import { GenerationService } from './generation.service';
import { GenerationController } from './generation.controller';

@Module({
  imports: [BillingModule, ProvidersModule],
  controllers: [GenerationController],
  providers: [GenerationService, OrchestratorHttpClient],
  exports: [GenerationService],
})
export class GenerationModule {}
