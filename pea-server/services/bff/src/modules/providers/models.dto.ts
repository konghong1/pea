import {
  IsBoolean,
  IsOptional,
  IsString,
  IsIn,
  IsInt,
  Min,
  MaxLength,
  IsObject,
} from 'class-validator';

export class CreateModelDto {
  @IsString() @MaxLength(64)
  id: string;

  @IsString() @MaxLength(64)
  providerId: string;

  @IsString() @MaxLength(200)
  modelName: string;

  @IsOptional() @IsString() @MaxLength(200)
  displayName?: string;

  @IsOptional() @IsIn(['image', 'video', 'text'])
  modelType?: 'image' | 'video' | 'text';

  @IsOptional() @IsBoolean()
  enabled?: boolean;

  @IsOptional() @IsBoolean()
  isDefault?: boolean;

  @IsOptional() @IsInt() @Min(0)
  minPlanLevel?: number;

  @IsOptional()
  pricing?: any;

  @IsOptional()
  paramsSchema?: any;

  @IsOptional() @IsString() @MaxLength(500)
  description?: string;

  @IsOptional() @IsInt()
  sortOrder?: number;
}

export class UpdateModelDto {
  @IsOptional() @IsString() @MaxLength(64)
  providerId?: string;

  @IsOptional() @IsString() @MaxLength(200)
  modelName?: string;

  @IsOptional() @IsString() @MaxLength(200)
  displayName?: string;

  @IsOptional() @IsIn(['image', 'video', 'text'])
  modelType?: 'image' | 'video' | 'text';

  @IsOptional() @IsBoolean()
  enabled?: boolean;

  @IsOptional() @IsBoolean()
  isDefault?: boolean;

  @IsOptional() @IsInt() @Min(0)
  minPlanLevel?: number;

  @IsOptional()
  pricing?: any;

  @IsOptional()
  paramsSchema?: any;

  @IsOptional() @IsString() @MaxLength(500)
  description?: string;

  @IsOptional() @IsInt()
  sortOrder?: number;
}

export class EstimateDto {
  @IsString()
  modelId: string;

  @IsOptional() @IsObject()
  params?: Record<string, any>;
}
