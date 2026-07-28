import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  Param,
  Patch,
  Post,
  Query,
  UploadedFile,
  UseGuards,
  UseInterceptors,
  BadRequestException,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { AssetsService } from './assets.service';
import {
  CreateAssetFolderDto,
  ListAssetsQueryDto,
  UpdateAssetDto,
  UpdateAssetFolderDto,
  UploadAssetQueryDto,
} from './assets.dto';

@Controller('assets')
@UseGuards(JwtAuthGuard)
export class AssetsController {
  constructor(private readonly assets: AssetsService) {}

  // -------- 文件夹 --------
  @Get('folders')
  listFolders(
    @CurrentUser() u: { sub: number },
    @Query('scope') scope?: 'personal' | 'team',
  ) {
    return this.assets.listFolders(u.sub, scope ?? 'personal');
  }

  @Post('folders')
  @HttpCode(201)
  createFolder(
    @CurrentUser() u: { sub: number },
    @Body() dto: CreateAssetFolderDto,
  ) {
    return this.assets.createFolder(u.sub, dto);
  }

  @Patch('folders/:id')
  updateFolder(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
    @Body() dto: UpdateAssetFolderDto,
  ) {
    return this.assets.updateFolder(u.sub, Number(id), dto);
  }

  @Delete('folders/:id')
  @HttpCode(200)
  deleteFolder(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
  ) {
    return this.assets.deleteFolder(u.sub, Number(id));
  }

  // -------- 资源 --------
  @Get()
  list(
    @CurrentUser() u: { sub: number },
    @Query() q: ListAssetsQueryDto,
  ) {
    return this.assets.list(u.sub, q);
  }

  @Post('upload')
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: 100 * 1024 * 1024 } }))
  async upload(
    @UploadedFile() file: any,
    @CurrentUser() u: { sub: number },
    @Query() q: UploadAssetQueryDto,
  ) {
    if (!file) throw new BadRequestException('file required');
    return this.assets.upload(
      u.sub,
      {
        originalname: file.originalname,
        mimetype: file.mimetype,
        size: file.size,
        buffer: file.buffer,
      },
      q.folder_id,
      q.scope ?? 'personal',
    );
  }

  @Patch(':id')
  update(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
    @Body() dto: UpdateAssetDto,
  ) {
    return this.assets.update(u.sub, Number(id), dto);
  }

  @Delete(':id')
  @HttpCode(200)
  delete(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
  ) {
    return this.assets.delete(u.sub, Number(id));
  }
}
