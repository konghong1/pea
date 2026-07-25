import {
  IsBoolean,
  IsOptional,
  IsString,
  IsIn,
  MaxLength,
} from 'class-validator';

export class CreateProviderDto {
  @IsString()
  @MaxLength(64)
  id: string;

  @IsString()
  @MaxLength(120)
  name: string;

  @IsOptional()
  @IsString()
  @MaxLength(40)
  providerType?: string;

  @IsOptional()
  @IsString()
  @MaxLength(500)
  baseUrl?: string;

  @IsOptional()
  @IsString()
  @MaxLength(500)
  apiKey?: string;

  @IsOptional()
  @IsIn(['image', 'video', 'text', 'audio'])
  kind?: 'image' | 'video' | 'text' | 'audio';

  @IsOptional()
  @IsBoolean()
  enabled?: boolean;

  @IsOptional()
  @IsBoolean()
  isDefault?: boolean;

  @IsOptional()
  config?: any;
}

export class UpdateProviderDto {
  @IsOptional() @IsString() @MaxLength(120)
  name?: string;

  @IsOptional() @IsString() @MaxLength(40)
  providerType?: string;

  @IsOptional() @IsString() @MaxLength(500)
  baseUrl?: string;

  @IsOptional() @IsString() @MaxLength(500)
  apiKey?: string;

  @IsOptional() @IsIn(['image', 'video', 'text', 'audio'])
  kind?: 'image' | 'video' | 'text' | 'audio';

  @IsOptional() @IsBoolean()
  enabled?: boolean;

  @IsOptional() @IsBoolean()
  isDefault?: boolean;

  @IsOptional()
  config?: any;
}
