import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Patch,
  Post,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { AdminGuard } from '../../common/guards/admin.guard';
import { ProvidersService } from './providers.service';
import { CreateProviderDto, UpdateProviderDto } from './providers.dto';

/** 管理员: AI 提供商 CRUD + 远端模型拉取 (密钥对外脱敏)。 */
@Controller('admin/providers')
@UseGuards(JwtAuthGuard, AdminGuard)
export class AdminProvidersController {
  constructor(private readonly providers: ProvidersService) {}

  @Get()
  list() {
    return this.providers.listProviders();
  }

  @Post()
  create(@Body() dto: CreateProviderDto) {
    return this.providers.createProvider(dto);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateProviderDto) {
    return this.providers.updateProvider(id, dto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.providers.deleteProvider(id);
  }

  /** 拉取该提供商远端可用模型列表 (不落库, 供管理员挑选)。 */
  @Post(':id/fetch-models')
  fetchModels(@Param('id') id: string) {
    return this.providers.fetchRemoteModels(id);
  }
}
