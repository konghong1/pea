import { IsString, IsArray, IsOptional, IsInt, MaxLength } from 'class-validator';

export class CreateWorkDto {
  @IsString()
  @MaxLength(2000)
  caption: string;

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  mediaUrls?: string[];
}

export class CommentDto {
  @IsString()
  @MaxLength(1000)
  content: string;
}
