import { Module } from '@nestjs/common';
import { DatabaseModule } from '../../database/database.module';
import { UsageService } from './usage.service';
import { UsageController } from './usage.controller';

@Module({
  imports: [DatabaseModule],
  controllers: [UsageController],
  providers: [UsageService],
  exports: [UsageService],
})
export class UsageModule {}
