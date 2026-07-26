import { Module } from '@nestjs/common';
import { DatabaseModule } from '../../database/database.module';
import { PlatformConfigsService } from './platform-configs.service';
import { PlatformConfigsController } from './platform-configs.controller';

@Module({
  imports: [DatabaseModule],
  controllers: [PlatformConfigsController],
  providers: [PlatformConfigsService],
  exports: [PlatformConfigsService],
})
export class PlatformConfigsModule {}
