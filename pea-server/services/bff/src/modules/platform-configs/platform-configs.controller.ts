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
  HttpCode,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { PlatformConfigsService } from './platform-configs.service';
import {
  CreatePlatformConfigDto,
  UpdatePlatformConfigDto,
} from './platform-configs.dto';

@Controller('platform-configs')
@UseGuards(JwtAuthGuard)
export class PlatformConfigsController {
  constructor(private readonly svc: PlatformConfigsService) {}

  @Get()
  list(@CurrentUser() u: { sub: number }, @Query('kind') kind?: 'image' | 'video') {
    return this.svc.list(u.sub, kind);
  }

  @Post()
  @HttpCode(201)
  create(@CurrentUser() u: { sub: number }, @Body() dto: CreatePlatformConfigDto) {
    return this.svc.create(u.sub, dto);
  }

  @Get(':id')
  get(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.svc.get(u.sub, id);
  }

  @Patch(':id')
  update(@CurrentUser() u: { sub: number }, @Param('id') id: string, @Body() dto: UpdatePlatformConfigDto) {
    return this.svc.update(u.sub, id, dto);
  }

  @Post(':id/set-default')
  @HttpCode(200)
  setDefault(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.svc.setDefault(u.sub, id);
  }

  @Delete(':id')
  @HttpCode(200)
  remove(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.svc.remove(u.sub, id);
  }
}
