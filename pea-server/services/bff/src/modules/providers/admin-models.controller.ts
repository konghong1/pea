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
import { ModelsService } from './models.service';
import { CreateModelDto, UpdateModelDto } from './models.dto';

/** 管理员: 模型 CRUD (含动态定价 pricing / 门槛 min_plan_level)。 */
@Controller('admin/models')
@UseGuards(JwtAuthGuard, AdminGuard)
export class AdminModelsController {
  constructor(private readonly models: ModelsService) {}

  @Get()
  list(@Query('providerId') providerId?: string) {
    return this.models.listAll(providerId);
  }

  @Post()
  create(@Body() dto: CreateModelDto) {
    return this.models.createModel(dto);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateModelDto) {
    return this.models.updateModel(id, dto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.models.deleteModel(id);
  }
}
