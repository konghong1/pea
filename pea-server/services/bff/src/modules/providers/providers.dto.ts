import { IsBoolean, IsOptional } from 'class-validator';

export class UpdateProviderDto {
  @IsOptional()
  @IsBoolean()
  enabled?: boolean;

  @IsOptional()
  @IsBoolean()
  isDefault?: boolean;
}
