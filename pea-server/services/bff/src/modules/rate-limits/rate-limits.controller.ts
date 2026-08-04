import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Patch,
  Post,
  Query,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { AdminGuard } from '../../common/guards/admin.guard';
import { RateLimitsService } from './rate-limits.service';
import { CreateRateLimitDto, UpdateRateLimitDto } from './rate-limits.dto';

/** 管理员: 速率限制规则 CRUD (per-provider / per-model / per-tier)。 */
@Controller('admin/rate-limits')
@UseGuards(JwtAuthGuard, AdminGuard)
export class RateLimitsController {
  constructor(private readonly svc: RateLimitsService) {}

  @Get()
  list(
    @Query('providerId') providerId?: string,
    @Query('modelId') modelId?: string,
  ) {
    return this.svc.list({ providerId, modelId });
  }

  @Post()
  create(@Body() dto: CreateRateLimitDto) {
    return this.svc.create(dto);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateRateLimitDto) {
    return this.svc.update(id, dto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.svc.remove(id);
  }
}
