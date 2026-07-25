import { Injectable, BadRequestException } from '@nestjs/common';
import { BillingService } from '../billing/billing.service';
import { ModelsService } from '../providers/models.service';
import { OrchestratorHttpClient } from '../orchestrator-client/orchestrator-http.service';
import { AcceptGenerationDto } from './generation.dto';

/**
 * 生成受理 (T-GEN-02): 解析模型 + 访问控制 -> 服务端算价 -> 预扣 -> 交编排器 -> 返 jobId.
 *
 * 安全red线 (资深复核):
 *  - 价格一律由服务端按 模型 pricing_json + 请求参数计算, 忽略任何客户端传入金额。
 *  - 访问控制: 模型 min_plan_level 高于用户生效权益 -> 403, 不预扣。
 *  - 预扣成功但下游受理失败 -> 立即本地退款, 避免积分悬空。
 */
@Injectable()
export class GenerationService {
  constructor(
    private readonly billing: BillingService,
    private readonly models: ModelsService,
    private readonly orch: OrchestratorHttpClient,
  ) {}

  async accept(userId: number, dto: AcceptGenerationDto) {
    const params = dto.params ?? {};

    // 1) 解析模型 + 访问控制 (未解锁模型/停用模型/停用提供商在此抛错, 不进入扣费)
    const { model } = await this.models.resolveForGeneration(userId, dto.model, dto.type);

    // 2) 服务端权威算价 (按参数动态计价)
    const cost = this.models.computeCost(model.pricing_json, params);
    if (!Number.isFinite(cost) || cost <= 0) {
      throw new BadRequestException('invalid computed cost');
    }

    const idem =
      dto.idempotencyKey ??
      `${userId}:${Date.now()}:${Math.random().toString(36).slice(2)}`;

    // 3) 预扣 (强一致, 幂等). 必须 await.
    await this.billing.preauthorize(userId, cost, `${idem}:preauth`);

    // 4) 受理 (交编排器落库+入队). 传 model.id 供编排器从 DB 解析提供商密钥与真实模型名.
    try {
      const job = await this.orch.acceptJob({
        user_id: userId,
        type: dto.type,
        prompt: dto.prompt,
        model: model.id,
        params,
        priority: dto.priority ?? 'normal',
        idempotency_key: idem,
        cost_tapies: cost,
      });

      return {
        jobId: job.jobId,
        status: job.status,
        costTapies: cost,
        model: { id: model.id, name: model.display_name, modelName: model.model_name },
      };
    } catch (err) {
      await this.billing.refund(userId, cost, `${idem}:refund`);
      throw err;
    }
  }

  async getStatus(jobId: string) {
    return this.orch.getJob(jobId);
  }

  async listJobs(userId: number, limit = 20, cursor: string | number = 0) {
    if (limit > 100) throw new BadRequestException('limit too large');
    return this.orch.listJobs(userId, limit, cursor);
  }
}
