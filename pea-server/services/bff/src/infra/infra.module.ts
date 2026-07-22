import { Global, Module } from '@nestjs/common';
import { RedisPubSubService } from './redis-pubsub.service';

@Global()
@Module({
  providers: [RedisPubSubService],
  exports: [RedisPubSubService],
})
export class InfraModule {}
