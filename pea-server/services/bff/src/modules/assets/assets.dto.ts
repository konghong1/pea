import {
  IsString,
  IsOptional,
  IsIn,
  IsNumber,
  Min,
  IsBoolean,
} from 'class-validator';
import { Type } from 'class-transformer';

export class CreateAssetFolderDto {
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

export class UpdateAssetFolderDto {
  @IsOptional()
  @IsString()
  name?: string;

  @IsOptional()
  @IsNumber()
  @Min(1)
  parent_id?: number | null;
}

export class ListAssetsQueryDto {
  @IsOptional()
  @IsIn(['personal', 'team'])
  scope?: 'personal' | 'team';

  /** 指定文件夹 (>=1) 则按文件夹过滤; 不传则返回该 scope 下全部素材 (用于收藏跨文件夹聚合) */
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(1)
  folder_id?: number;

  @IsOptional()
  @IsString()
  q?: string;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(1)
  limit?: number;
}

export class UpdateAssetDto {
  @IsOptional()
  @IsString()
  name?: string;

  @IsOptional()
  @IsNumber()
  @Min(1)
  folder_id?: number | null;

  @IsOptional()
  @IsBoolean()
  is_favorite?: boolean;
}

export class UploadAssetQueryDto {
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(1)
  folder_id?: number;

  @IsOptional()
  @IsIn(['personal', 'team'])
  scope?: 'personal' | 'team';
}
