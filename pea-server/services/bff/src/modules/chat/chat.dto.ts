import {
  IsString,
  IsIn,
  IsOptional,
  MinLength,
  MaxLength,
} from 'class-validator';

/** 节点聊天流式请求体 (SSE: POST /chat/stream)。 */
export class ChatStreamDto {
  /** 发起聊天的节点 id (前端用于把回流文本写回对应节点)。 */
  @IsString()
  @MinLength(1)
  @MaxLength(128)
  nodeId: string;

  /** 节点类型: 本期仅 text; image/video 在 Phase 2 经提示词构造层。 */
  @IsIn(['text', 'image', 'video'])
  kind: 'text' | 'image' | 'video';

  /** 用户在该节点输入框的聊天内容。 */
  @IsString()
  @MinLength(1)
  @MaxLength(8000)
  prompt: string;

  /** 模型 id (ai_models.id)。缺省按 text 类型取默认模型。 */
  @IsOptional()
  @IsString()
  model?: string;

  /** Phase 2: 用户所选平台配置 id (图片/视频提示词构造用)。 */
  @IsOptional()
  @IsString()
  platformConfigId?: string;

  /** 幂等键: 同键重复提交不重复扣费。 */
  @IsOptional()
  @IsString()
  idempotencyKey?: string;

  /** 多轮会话 id (可选, 本期单轮即可)。 */
  @IsOptional()
  @IsString()
  conversationId?: string;
}
