import {
  IsObject,
  IsInt,
  IsOptional,
  IsString,
  IsIn,
  IsNumber,
  Min,
  IsBoolean,
} from 'class-validator';
import { Type } from 'class-transformer';

export class CreateCanvasDto {
  @IsOptional()
  @IsString()
  title?: string;

  /** 范围：个人空间 / 团队空间 */
  @IsOptional()
  @IsIn(['personal', 'team'])
  scope?: 'personal' | 'team';

  /** 创建时直接放入的文件夹；NULL = 根目录 */
  @IsOptional()
  @IsNumber()
  @Min(1)
  folder_id?: number | null;
}

export class SaveCanvasDto {
  @IsObject()
  graph_json: Record<string, any>;

  /** 客户端当前版本号, 用于乐观锁冲突检测 */
  @IsInt()
  version: number;
}

/**
 * 部分更新 (PATCH /canvases/:id)。
 * 重命名 / 移动至团队 / 移动至文件夹 / 删缩略图等场景。
 */
export class UpdateCanvasDto {
  @IsOptional()
  @IsString()
  title?: string;

  @IsOptional()
  @IsIn(['personal', 'team'])
  scope?: 'personal' | 'team';

  @IsOptional()
  @IsNumber()
  @Min(1)
  folder_id?: number | null;

  @IsOptional()
  @IsString()
  thumbnail_url?: string | null;

  /** 软删除：true 移入回收站；false 从回收站恢复 */
  @IsOptional()
  @IsBoolean()
  deleted?: boolean;
}

/** GET /canvases 查询参数 */
export class ListCanvasesQueryDto {
  @IsOptional()
  @IsIn(['personal', 'team', 'trash', 'all'])
  scope?: 'personal' | 'team' | 'trash' | 'all';

  /** 指定文件夹；0 / 不传 = 根目录 */
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  folder_id?: number;

  @IsOptional()
  @IsString()
  q?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  limit?: number;
}

/** POST /canvases/folders 创建文件夹 */
export class CreateFolderDto {
  @IsString()
  name: string;

  @IsOptional()
  @IsIn(['personal', 'team'])
  scope?: 'personal' | 'team';

  @IsOptional()
  @IsNumber()
  @Min(1)
  parent_id?: number | null;
}

export class UpdateFolderDto {
  @IsOptional()
  @IsString()
  name?: string;

  @IsOptional()
  @IsNumber()
  @Min(1)
  parent_id?: number | null;
}