import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { EventsGateway } from './events.gateway';

@Module({
  imports: [JwtModule.register({})],
  providers: [EventsGateway],
})
export class GatewayModule {}
