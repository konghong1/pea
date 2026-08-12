export type PeaNodeKind =
  | 'prompt'
  | 'text'
  | 'image'
  | 'generate'
  | 'video'
  | 'audio'
  | 'agent'
  | 'story'
  | 'ref'
  | 'world3d'
  | 'camera'
  | 'light'
  | 'playlist'
  | 'replace';

export interface PeaNodeTypeDef {
  kind: PeaNodeKind;
  label: string;
  icon: string;
  color: string;
  category: 'input' | 'generate' | 'structure' | 'smart';
  desc: string;
}

/** 节点库定义（对齐 pea-canvas-v12.html NODE_DEFS，12 类 + 4 分类）
 * 注：节点图标已迁移到 NodeIcon.tsx 统一 SVG 科技感图标系统，
 * 此处 icon 字段保留兼容但不再使用。 */
export const PEA_NODE_TYPES: PeaNodeTypeDef[] = [
  { kind: 'text', label: '文本', icon: '', color: '#34d399', category: 'input', desc: '文字内容节点' },
  { kind: 'image', label: '图片', icon: '', color: '#FD79A8', category: 'input', desc: '图片素材' },
  { kind: 'video', label: '视频', icon: '', color: '#8b5cf6', category: 'input', desc: '视频素材' },
  { kind: 'audio', label: '音频', icon: '', color: '#8b5cf6', category: 'input', desc: '音频素材' },
  { kind: 'ref', label: '参考', icon: '', color: '#64748b', category: 'input', desc: '参考素材' },
  { kind: 'generate', label: '生成', icon: '', color: '#8b5cf6', category: 'generate', desc: 'AI 生成图像' },
  { kind: 'agent', label: '智能体', icon: '', color: '#8b5cf6', category: 'generate', desc: 'AI 智能体' },
  { kind: 'story', label: '故事', icon: '', color: '#f59e0b', category: 'generate', desc: '叙事脚本' },
  { kind: 'world3d', label: '3D 世界', icon: '', color: '#6366f1', category: 'generate', desc: '3D 场景' },
  { kind: 'camera', label: '镜头', icon: '', color: '#ec4899', category: 'structure', desc: '摄像机节点' },
  { kind: 'light', label: '灯光', icon: '', color: '#fbbf24', category: 'structure', desc: '灯光节点' },
  { kind: 'playlist', label: '分镜列表', icon: '', color: '#22c55e', category: 'structure', desc: '分镜播放列表' },
  { kind: 'replace', label: '替换', icon: '', color: '#ef4444', category: 'smart', desc: '元素替换' },
];

export const PEA_NODE_MAP: Record<string, PeaNodeTypeDef> = Object.fromEntries(
  PEA_NODE_TYPES.map((t) => [t.kind, t]),
);

export const NODE_CATEGORY_LABEL: Record<string, string> = {
  input: '输入',
  generate: '生成',
  structure: '结构',
  smart: '智能',
};

/** 未知 / 旧 'prompt' 类型统一回退到 text 定义，保证旧画布数据不崩 */
export const NODE_DEF_OF = (kind: string): PeaNodeTypeDef =>
  PEA_NODE_MAP[kind] ?? PEA_NODE_MAP['text'];
