import { Injectable, Logger, BadRequestException } from '@nestjs/common';
import { BillingService } from '../billing/billing.service';
import { ModelsService } from '../providers/models.service';
import { UsageService } from '../usage/usage.service';
import { LlmStreamClient } from './llm-stream.client';
import { ChatStreamDto } from './chat.dto';

export type Emit = (event: string, data: any) => void;

/**
 * 文本节点的系统指令（服务端权威，不信任前端传入）。
 * 核心职责：把用户在文本节点里输入的简短描述，改写/扩写为更饱满、更适合作为
 * AI 绘图 / 视频生成提示词的描述。它【绝不】负责生成图片/视频本身，
 * 因此绝不能出现「我无法生成图像」这类拒答——只做文字层面的润色与扩写。
 */
const TEXT_NODE_SYSTEM = `你是一个专业的「提示词润色与扩写助手」，服务于一个 AI 创意画布工具。
用户在文本节点里会输入一句简短的描述或想法（例如「生成一只猫」「赛博朋克城市」）。
你的唯一任务：把用户输入改写成一段更丰富、更具体、更有画面感、更适合直接作为 AI 绘图 / 视频生成提示词的描述。

重要原则（务必遵守）：
1. 你绝不负责「生成图片 / 视频」本身，也绝不要说「我无法生成图像 / 图片」之类的话。你只做文字层面的润色与扩写。
2. 保留用户原意的核心主体，补齐缺失维度：主体姿态 / 环境氛围 / 光影 / 构图 / 风格 / 质感 / 情绪。
3. 默认用中文输出；仅当用户明确要求英文时才用英文。
4. 直接输出润色后的提示词正文，不要加「这是改写后的提示词：」之类的前缀或解释性废话，也不要用 Markdown 代码块包裹。
5. 若用户已给出较完整的提示词，则在其基础上精炼、增强、补全缺失维度，而非推倒重来。`;

/**
 * 节点聊天受理 (文本节点, 轻量 SSE 路径):
 *   解析模型 -> 服务端算价 -> 预扣(preauth) -> 流式调 LLM -> 逐 delta 回流
 *   -> 成功: 预扣即计费(流式无法预知精确 token) -> 失败: 退款(refund)。
 *
 * 设计要点 (对应已确认决策):
 *  - 文本节点 = 轻量、非任务式 -> 走 SSE, 不经 Orchestrator 重任务队列。
 *  - 预扣/退款复用现有双记账本, txn_id = `${idem}:preauth` / `${idem}:refund`, 幂等。
 *  - image/video (Phase 2) 才走 Orchestrator + 提示词构造层 (PromptConstructionLayer)。
 */
@Injectable()
export class ChatService {
  private readonly logger = new Logger(ChatService.name);

  constructor(
    private readonly billing: BillingService,
    private readonly models: ModelsService,
    private readonly usage: UsageService,
    private readonly llm: LlmStreamClient,
  ) {}

  async streamChat(userId: number, dto: ChatStreamDto, emit: Emit) {
    if (dto.kind !== 'text') {
      // Phase 2 才会实现图片/视频节点的提示词构造 + 生成任务。
      throw new BadRequestException(
        `节点类型 '${dto.kind}' 的聊天生成将在 Phase 2 支持 (本期仅 text)`,
      );
    }

    // 1) 解析模型 + 访问控制 (未解锁/停用 -> 抛错, 不进入扣费)
    const { model, provider } = await this.models.resolveForGeneration(
      userId,
      dto.model,
      'text',
    );

    // 2) 服务端权威算价 (文本按 base 估算; token 精确计费留 Phase 3)
    const cost = this.models.computeCost(model.pricing_json, {});
    if (!Number.isFinite(cost) || cost <= 0) {
      throw new BadRequestException('invalid computed cost');
    }

    const idem =
      dto.idempotencyKey ??
      `${userId}:chat:${Date.now()}:${Math.random().toString(36).slice(2)}`;

    // 3) 预扣 (强一致, 幂等)。聊天预扣即最终计费。
    await this.billing.preauthorize(userId, cost, `${idem}:preauth`);

    emit('meta', {
      nodeId: dto.nodeId,
      conversationId: dto.conversationId ?? idem,
      txnId: `${idem}:preauth`,
      costTapies: cost,
      model: { id: model.id, name: model.display_name, modelName: model.model_name },
    });

    try {
      let full = '';
      let usageCaptured: any = undefined;
      const isMock = provider.provider_type === 'mock' || !provider.base_url;

      for await (const chunk of this.llm.stream({
        baseUrl: provider.base_url,
        apiKey: provider.api_key,
        model: model.model_name,
        prompt: dto.prompt,
        // 文本节点的固定角色：提示词润色助手（避免模型把输入误当成「生成图片」而拒答）
        system: TEXT_NODE_SYSTEM,
        mock: isMock,
      })) {
        if (chunk.delta) {
          full += chunk.delta;
          emit('delta', { text: chunk.delta });
        }
        if (chunk.usage) usageCaptured = chunk.usage;
      }

      emit('done', { text: full, usage: usageCaptured ?? null });

      // Phase3: 文本聊天 token 用量计量落库 (审计/统计, 不改计费公式)
      if (usageCaptured && (usageCaptured.total_tokens || usageCaptured.prompt_tokens)) {
        await this.usage.record({
          userId,
          nodeType: 'text',
          model: model.id,
          provider: provider.provider_name ?? provider.provider_type,
          jobId: null,
          inputTokens: usageCaptured.prompt_tokens ?? 0,
          outputTokens: usageCaptured.completion_tokens ?? 0,
          totalTokens: usageCaptured.total_tokens ?? (usageCaptured.prompt_tokens ?? 0) + (usageCaptured.completion_tokens ?? 0),
        });
      }
      // 成功: 不需额外确认 (预扣即费)。
    } catch (err: any) {
      this.logger.warn(`chat stream failed, refunding txn ${idem}: ${err?.message}`);
      await this.billing.refund(userId, cost, `${idem}:refund`);
      emit('error', { message: err?.message ?? 'generation failed', refunded: true });
    }
  }
}
