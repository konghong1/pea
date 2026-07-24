import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  Param,
  Patch,
  Post,
  Put,
  Query,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { CanvasesService } from './canvases.service';
import {
  CreateCanvasDto,
  CreateFolderDto,
  ListCanvasesQueryDto,
  SaveCanvasDto,
  UpdateCanvasDto,
  UpdateFolderDto,
} from './canvases.dto';

@Controller('canvases')
@UseGuards(JwtAuthGuard)
export class CanvasesController {
  constructor(private readonly canvases: CanvasesService) {}

  @Post()
  @HttpCode(201)
  create(@CurrentUser() u: { sub: number }, @Body() dto: CreateCanvasDto) {
    return this.canvases.create(u.sub, dto);
  }

  @Get()
  list(@CurrentUser() u: { sub: number }, @Query() q: ListCanvasesQueryDto) {
    return this.canvases.list(u.sub, q);
  }

  @Get(':id')
  get(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.canvases.get(u.sub, Number(id));
  }

  @Put(':id')
  @HttpCode(200)
  save(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
    @Body() dto: SaveCanvasDto,
  ) {
    return this.canvases.save(u.sub, Number(id), dto.graph_json, dto.version);
  }

  @Patch(':id')
  @HttpCode(200)
  update(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
    @Body() dto: UpdateCanvasDto,
  ) {
    return this.canvases.update(u.sub, Number(id), dto);
  }

  @Delete(':id')
  @HttpCode(200)
  remove(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.canvases.hardDelete(u.sub, Number(id));
  }

  // -------- 分享 --------
  @Post(':id/share')
  @HttpCode(200)
  createShare(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.canvases.ensureShareToken(u.sub, Number(id));
  }

  @Delete(':id/share')
  @HttpCode(200)
  revokeShare(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.canvases.revokeShareToken(u.sub, Number(id));
  }

  // -------- 文件夹 --------
  @Get('folders/list')
  listFolders(
    @CurrentUser() u: { sub: number },
    @Query('scope') scope?: 'personal' | 'team',
  ) {
    return this.canvases.listFolders(u.sub, scope ?? 'personal');
  }

  @Post('folders')
  @HttpCode(201)
  createFolder(@CurrentUser() u: { sub: number }, @Body() dto: CreateFolderDto) {
    return this.canvases.createFolder(u.sub, dto);
  }

  @Patch('folders/:id')
  @HttpCode(200)
  updateFolder(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
    @Body() dto: UpdateFolderDto,
  ) {
    return this.canvases.updateFolder(u.sub, Number(id), dto);
  }

  @Delete('folders/:id')
  @HttpCode(200)
  deleteFolder(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.canvases.deleteFolder(u.sub, Number(id));
  }
}

/**
 * 公开分享只读端点 (无 JWT guard)。
 * 路径 /shared/:token 直接挂在 canvases controller 上但用不同前缀，便于前端走 /api 代理。
 * 单独再开一个 controller 以避免和受保护路由混在一起。
 */
@Controller('shared')
export class SharedCanvasController {
  constructor(private readonly canvases: CanvasesService) {}

  @Get(':token')
  getByToken(@Param('token') token: string) {
    return this.canvases.getByShareToken(token);
  }
}