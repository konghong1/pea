import { Controller, Get, Patch, Param, Body, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { ProvidersService } from './providers.service';
import { UpdateProviderDto } from './providers.dto';

@Controller('providers')
@UseGuards(JwtAuthGuard)
export class ProvidersController {
  constructor(private readonly providers: ProvidersService) {}

  /** 列出当前用户的 AI Provider 配置 (首次访问自动种子). */
  @Get()
  list(@CurrentUser() u: { sub: number }) {
    return this.providers.list(u.sub);
  }

  /** 切换启用状态 / 设为默认 (FR-G7). */
  @Patch(':id')
  update(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
    @Body() dto: UpdateProviderDto,
  ) {
    return this.providers.update(u.sub, id, dto);
  }
}
