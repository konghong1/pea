import { PeaNodeKind } from '../constants/nodeTypes';

export interface NodeIconProps {
  kind: PeaNodeKind | string;
  color?: string;
  size?: number;
  className?: string;
}

/**
 * 科技感节点图标系统
 * - 统一 24x24 视口，1.5px 描边，圆角端点
 * - 每种 kind 有独特语义图形，避免 emoji 在不同平台的差异
 * - 默认使用 kind 对应的品牌色，可通过 color 覆盖
 */
export default function NodeIcon({ kind, color, size = 14, className }: NodeIconProps) {
  const c = color || kindColor(kind);
  const svgProps = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: c,
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className: className ? `${className} pea-node-icon` : 'pea-node-icon',
    'aria-hidden': true,
  };

  switch (kind) {
    case 'text':
      return (
        <svg {...svgProps}>
          <path d="M4 7h16M8 7v10M16 7v10M6 17h12" />
        </svg>
      );
    case 'image':
      return (
        <svg {...svgProps}>
          <rect x="3" y="5" width="18" height="14" rx="2.5" />
          <circle cx="8" cy="10" r="1.5" fill={c} stroke="none" />
          <path d="M3 16l5-5 4 4 3-3 6 6" />
        </svg>
      );
    case 'video':
      return (
        <svg {...svgProps}>
          <rect x="2.5" y="6" width="19" height="12" rx="2.5" />
          <path d="M10 10l5 3-5 3V10z" fill={c} stroke="none" />
        </svg>
      );
    case 'audio':
      return (
        <svg {...svgProps}>
          <path d="M12 4v10" />
          <path d="M8 8v6" />
          <path d="M16 8v6" />
          <path d="M6 19a5 5 0 0 0 6 0 5 5 0 0 0 6 0" />
        </svg>
      );
    case 'ref':
      return (
        <svg {...svgProps}>
          <path d="M9.5 14.5l5-5" />
          <path d="M14.5 14.5v-5h-5" />
          <rect x="4" y="8" width="6" height="6" rx="1.5" />
          <rect x="14" y="4" width="6" height="6" rx="1.5" />
        </svg>
      );
    case 'generate':
      return (
        <svg {...svgProps}>
          <path d="M13 2L10 10l-8 3 8 3 3 8 3-8 8-3-8-3-3-8z" />
        </svg>
      );
    case 'agent':
      return (
        <svg {...svgProps}>
          <rect x="5" y="4" width="14" height="12" rx="3" />
          <circle cx="9" cy="10" r="1.2" fill={c} stroke="none" />
          <circle cx="15" cy="10" r="1.2" fill={c} stroke="none" />
          <path d="M9 15l3 4 3-4" />
          <path d="M12 4V2" />
        </svg>
      );
    case 'story':
      return (
        <svg {...svgProps}>
          <path d="M4 5h11a3 3 0 0 1 0 6H4" />
          <path d="M4 11h13a3 3 0 0 1 0 6H4" />
          <path d="M4 5v12" />
        </svg>
      );
    case 'world3d':
      return (
        <svg {...svgProps}>
          <path d="M12 2l9 5v10l-9 5-9-5V7l9-5z" />
          <path d="M12 12l9-5" />
          <path d="M12 12V2" />
          <path d="M12 12L3 7" />
        </svg>
      );
    case 'camera':
      return (
        <svg {...svgProps}>
          <rect x="4" y="7" width="16" height="11" rx="2.5" />
          <circle cx="12" cy="12.5" r="3.5" />
          <path d="M8 7V5.5A1.5 1.5 0 0 1 9.5 4h5A1.5 1.5 0 0 1 16 5.5V7" />
        </svg>
      );
    case 'light':
      return (
        <svg {...svgProps}>
          <path d="M12 3v2" />
          <path d="M12 19v2" />
          <path d="M5 12H3" />
          <path d="M21 12h-2" />
          <path d="M6.34 6.34L4.93 4.93" />
          <path d="M19.07 19.07l-1.41-1.41" />
          <path d="M6.34 17.66l-1.41 1.41" />
          <path d="M19.07 4.93l-1.41 1.41" />
          <circle cx="12" cy="12" r="4" />
        </svg>
      );
    case 'playlist':
      return (
        <svg {...svgProps}>
          <rect x="4" y="4" width="16" height="5" rx="1.5" />
          <rect x="4" y="12" width="12" height="4" rx="1.5" />
          <rect x="4" y="18" width="8" height="3" rx="1.5" />
          <path d="M17 14l4 2-4 2v-4z" fill={c} stroke="none" />
        </svg>
      );
    case 'replace':
      return (
        <svg {...svgProps}>
          <path d="M4 9V5h4" />
          <path d="M20 15v4h-4" />
          <path d="M4 9c0 3.5 3 6 8 6" />
          <path d="M20 15c0-3.5-3-6-8-6" />
        </svg>
      );
    case 'prompt':
    default:
      return (
        <svg {...svgProps}>
          <path d="M8 9h8M8 13h5" />
          <rect x="4" y="4" width="16" height="16" rx="3" />
        </svg>
      );
  }
}

/** 获取 kind 默认品牌色（与 nodeTypes.ts 中的 color 对齐） */
export function kindColor(kind: string): string {
  const map: Record<string, string> = {
    text: '#34d399',
    image: '#FD79A8',
    video: '#8b5cf6',
    audio: '#8b5cf6',
    ref: '#64748b',
    generate: '#8b5cf6',
    agent: '#8b5cf6',
    story: '#f59e0b',
    world3d: '#6366f1',
    camera: '#ec4899',
    light: '#fbbf24',
    playlist: '#22c55e',
    replace: '#ef4444',
    prompt: '#34d399',
  };
  return map[kind] || '#8b5cf6';
}

/** 生成态徽标：小闪电 */
export function GeneratingBadge({ size = 10 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className="pea-node-badge-generate-dot"
      aria-hidden
    >
      <path d="M13 2L10 10l-8 3 8 3 3 8 3-8 8-3-8-3-3-8z" />
    </svg>
  );
}

/** 上传态徽标：小箭头 */
export function UploadBadge({ size = 10 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="pea-node-badge-upload-dot"
      aria-hidden
    >
      <path d="M12 3v12" />
      <path d="M7 8l5-5 5 5" />
      <path d="M5 21h14" />
    </svg>
  );
}
