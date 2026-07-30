import { useCanvas } from '../store/canvas';
import { toast } from '../store/toast';
import { acceptNodeGenerationJob } from '../api/catalog';
import { api } from '../api/client';

/**
 * 节点生成任务轮询兜底（从 NodeChatPrompt 抽离为共享模块）。
 * WS 的 job.updated 事件是 fire-and-forget：长任务（真实模型常 ~1-3 分钟）完成时，
 * 前端 WS 可能已不在监听窗口/断连，事件被丢弃，导致节点永远停在 generating。
 * 这里用轮询兜底：事件若先到，会从 jobNodeMap 移除 job，本函数随即终止；否则轮询负责回填。
 * 失败态会把 error 写回节点，供节点内失败卡展示与重试。
 */
export function pollNodeJobResult(jobId: string) {
  // 2026-07-28 修正: 视频出片真实耗时 5–10 分钟 (见 orchestrator config.video_poll_max_s=900s)。
  // 旧 MAX_ATTEMPTS=120 (3s 间隔 = 6min) 比视频出片还短 -> 后端仍在轮询时前端已判"超时"重置节点,
  // 造成"视频永远不出来"。与后端对齐放宽到 300 (3s 间隔 = 15min, 覆盖 video_poll_max_s)。
  const MAX_ATTEMPTS = 300;
  let attempt = 0;
  const tick = async () => {
    // 事件已处理 -> jobNodeMap 已无此 job -> 终止轮询（避免重复回填）
    if (!useCanvas.getState().jobNodeMap[jobId]) return;
    if (attempt++ >= MAX_ATTEMPTS) {
      useCanvas.getState().applyJobResult(jobId, { generating: false, error: '生成超时，请重试' });
      useCanvas.getState().removeJob(jobId);
      toast.error('生成超时，请稍后重试');
      return;
    }
    try {
      const { data } = await api.get<any>(`/generation/jobs/${jobId}`);
      const st = data?.status;
      if (st === 'done') {
        const url = data?.resultUrl ?? undefined;
        // 优先使用后端返回的多图数组，兼容单图
        const urls = data?.resultUrls ?? (url ? [url] : undefined);
        useCanvas.getState().applyJobResult(jobId, {
          generating: false,
          error: undefined,
          resultUrl: urls?.[0] ?? url,
          resultUrls: urls,
          resultIndex: 0,
          savedToLibrary: false,
        });
        useCanvas.getState().removeJob(jobId);
        const count = urls?.length ?? 1;
        toast.success(count > 1 ? `生成完成，共 ${count} 张图` : '生成完成');
        return;
      }
      if (st === 'failed' || st === 'refunded') {
        useCanvas.getState().applyJobResult(jobId, {
          generating: false,
          error: data?.error || '生成失败',
          // 失败时清理旧结果，避免旧 resultUrl 导致 broken image 覆盖失败卡
          resultUrl: undefined,
          resultUrls: undefined,
          resultIndex: 0,
          savedToLibrary: false,
        });
        useCanvas.getState().removeJob(jobId);
        toast.error(data?.error || '生成失败，已退款');
        return;
      }
    } catch {
      // 网络抖动忽略，继续轮询
    }
    setTimeout(tick, 3000);
  };
  setTimeout(tick, 3000);
}

/** kind -> 受理类型映射（仅 image/video/generate 走 WS 受理流）。 */
const RETRY_GEN_TYPE: Record<string, 'image' | 'video' | null> = {
  image: 'image',
  video: 'video',
  generate: 'image',
  audio: null,
  text: null,
};

/**
 * 节点失败重试：复用节点上已持久化的 prompt/params/meta.modelId 重新受理。
 * 不依赖编辑框状态，直接从画布 store 读取，保证重试稳健。
 */
export async function retryNodeGeneration(nodeId: string) {
  const node = useCanvas.getState().nodes.find((n) => n.id === nodeId);
  if (!node) return;
  const { kind, prompt, params, meta } = node.data;
  const type = RETRY_GEN_TYPE[kind] ?? null;
  if (!type) {
    toast.error('该节点类型暂不支持重试');
    return;
  }
  const model = (meta?.modelId as string) || '';
  if (!model) {
    toast.error('缺少模型信息，无法重试');
    return;
  }
  try {
    const res = await acceptNodeGenerationJob({
      type,
      prompt: prompt || '',
      model,
      params: params || {},
      priority: 'normal',
      idempotencyKey: `gen-${nodeId}-${Date.now()}`,
    });
    useCanvas.getState().registerJob(res.jobId, nodeId);
    // 重新进入 generating，并清除旧 error/旧结果，避免重试期间仍显示上次失败的图片
    // recordHistory=false：生成重试属于异步任务回写，不计入撤销历史（撤销只针对用户操作）
    useCanvas.getState().updateNodeData(nodeId, {
      generating: true,
      error: undefined,
      resultUrl: undefined,
      resultUrls: undefined,
      resultIndex: 0,
      savedToLibrary: false,
      lastJobId: res.jobId,
    }, false);
    toast.success('已重新发起生成');
    pollNodeJobResult(res.jobId);
  } catch (e: any) {
    toast.error(e?.response?.data?.message || '重试受理失败');
  }
}
