import { Module } from '@nestjs/common';
import { BillingModule } from '../billing/billing.module';
import { ProvidersModule } from '../providers/providers.module';
import { UsageModule } from '../usage/usage.module';
import { ChatService } from './chat.service';
import { ChatController } from './chat.controller';
import { LlmStreamClient } from './llm-stream.client';

@Module({
  imports: [BillingModule, ProvidersModule, UsageModule],
  controllers: [ChatController],
  providers: [ChatService, LlmStreamClient],
  exports: [ChatService],
})
export class ChatModule {}
