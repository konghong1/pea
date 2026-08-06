/**
 * 节点语义判定（单一事实来源 / Single Source of Truth）
 * ============================================================================
 * 背景：「这个节点是用户自己上传的素材，还是 AI 生成的结果？」这条判断此前在
 *   - PeaNode.tsx 顶层（左侧 target Handle 显隐）
 *   - PeaNode.tsx > NodeBadge（徽章文案 / 上传角标）
 *   - CanvasEditor.tsx onConnect（拒绝入边）
 *   - CanvasEditor.tsx onConnectEnd（拒绝入边兜底）
 * 各写了一遍，且实现并不一致（画布连线处只判了 kind === 'image'，导致视频/音频
 * 上传节点虽然隐藏了 Handle，仍能被 Loose 连线模式连上入边）。
 *
 * 任何"按节点状态区分行为"的逻辑都必须从这里取，禁止在组件内再写一遍表达式。
 */
import type { PeaNodeData } from '../store/canvas';

/**
 * 支持"用户直接上传素材"的节点类型。
 * - image / video / audio：PeaNode 内有隐藏 <input type="file">，上传后写 fileKey|url
 * - ref：参考素材节点，当前无上传入口，此处预留（将来接入时行为自动一致）
 */
export const UPLOADABLE_MEDIA_KINDS = ['image', 'video', 'audio', 'ref'] as const;

export function isUploadableMediaKind(kind?: string | null): boolean {
  return !!kind && (UPLOADABLE_MEDIA_KINDS as readonly string[]).includes(kind);
}

/** 节点是否已有 AI 生成结果（单图 resultUrl 或多图 resultUrls）。 */
export function hasGeneratedResult(data?: Partial<PeaNodeData> | null): boolean {
  return !!(data?.resultUrl || (data?.resultUrls && data.resultUrls.length > 0));
}

/**
 * 「用户自己上传的素材节点」：
 *   媒体类 kind + 有素材来源(fileKey|url) + 不是 AI 生成结果。
 *
 * 注意：不把 generating 纳入判断——生成中的节点语义由调用方自行叠加，
 * 因为不同场景对"生成中"的期望相反（连线要禁止、编辑框要显示）。
 */
export function isUserUploadedMediaNode(data?: Partial<PeaNodeData> | null): boolean {
  if (!data) return false;
  if (!isUploadableMediaKind(data.kind)) return false;
  if (!(data.fileKey || data.url)) return false;
  return !hasGeneratedResult(data);
}

/** 节点是否为 AI 生成出来的媒体结果（与上传素材互斥）。 */
export function isGeneratedMediaNode(data?: Partial<PeaNodeData> | null): boolean {
  if (!data) return false;
  if (!isUploadableMediaKind(data.kind)) return false;
  return hasGeneratedResult(data);
}

/**
 * 是否接受上游入边（= 是否渲染左侧 target Handle）。
 * 用户上传的素材节点内容由文件决定，不接受任何上游输入。
 */
export function acceptsUpstreamInput(data?: Partial<PeaNodeData> | null): boolean {
  return !isUserUploadedMediaNode(data);
}

/**
 * 选中该节点时，是否隐藏「节点下方编辑框」(NodeChatPrompt)。
 *
 * 规则：用户自己上传的素材节点 → 隐藏（上传的东西不是生成任务，不该弹输入框）。
 *
 * ⚠️ 必须保留的例外（历史回归，勿删）：
 *   generating === true 时一律显示。
 *   - v6：生成中编辑框是「停止」按钮的唯一入口，隐藏后无法取消任务；
 *   - v7/v8：生成开始瞬间 resultUrl 被清空，若此时按"上传态"隐藏，编辑框会被
 *     卸载并带走用户刚输入的提示词（用户连续两轮反馈"提示词消失"的直接原因）。
 *
 * 注意：裁切模式下的编辑框隐藏【不】在此处理，而是由 CSS
 * （.pea-node.is-cropping .pea-node-editor-anchor { display:none }）负责。
 * 该 class 由本地 cropOpen 实时驱动，不再读取会持久化写脏的 data.isCropping，
 * 避免「点过裁切的节点编辑框永远消失」这类回归。
 */
export function shouldHideNodeEditor(data?: Partial<PeaNodeData> | null): boolean {
  if (!data) return false;
  if (data.generating) return false;
  return isUserUploadedMediaNode(data);
}
