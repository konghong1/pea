import { IsObject, IsInt, IsOptional, IsString } from 'class-validator';

export class CreateCanvasDto {
  @IsOptional()
  @IsString()
  title?: string;
}

export class SaveCanvasDto {
  @IsObject()
  graph_json: Record<string, any>;

  /** 客户端当前版本号, 用于乐观锁冲突检测 */
  @IsInt()
  version: number;
}
