import { IsEmail, IsString, MinLength, MaxLength, IsOptional } from 'class-validator';

export class RegisterDto {
  @IsEmail()
  email: string;

  @IsString()
  @MinLength(8)
  @MaxLength(64)
  password: string;

  // 可选：注册时不强制填昵称。@IsOptional() 必须放在 @IsString() 之前，
  // 否则字段缺失(undefined)时 @IsString() 会校验 undefined 失败 → 400。
  @IsOptional()
  @IsString()
  @MaxLength(120)
  displayName?: string;
}

export class LoginDto {
  @IsEmail()
  email: string;

  @IsString()
  password: string;
}
