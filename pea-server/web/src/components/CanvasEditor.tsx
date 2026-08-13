import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import ReactFlow, {
  Background,
  BackgroundVariant,
  ReactFlowProvider,
  useReactFlow,
  useStoreApi,
  useViewport,
  type Node,
  type Edge,
  Connection,
  ConnectionMode,
  MiniMap,
  SelectionMode,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { App, Input, Modal, Select, Tooltip, ConfigProvider, theme as antdTheme } from 'antd';
import {
  ShareAltOutlined,
  WalletOutlined,
  CloseOutlined,
  CompassOutlined,
  PlayCircleOutlined,
  TrophyOutlined,
  EditOutlined,
  PlusOutlined,
  DeleteOutlined,
  SearchOutlined,
  FolderOutlined,
  AppstoreOutlined,
  CommentOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import { toast } from '../store/toast';
import { api } from '../api/client';
import { useCanvas, PeaNodeData, cleanGraph } from '../store/canvas';
import { getNodeSize } from '../lib/nodeSize';
import { useUi } from '../store/ui';
import { useAuth } from '../store/auth';
import { useCreatorDesign } from '../store/creatorDesign';
import { canvasesApi } from '../api/canvases';
import PeaNode from './PeaNode';
import GroupNode from './GroupNode';
import NodeIcon from './NodeIcon';

// dev/E2E 钩子：暴露 zustand store 到 window，方便 verify 脚本注入测试数据。
// - dev 模式始终暴露；
// - prod 模式仅在 localStorage.__peaDevHooks === '1' 时暴露，便于自动化验证生产构建。
// 不影响任何业务行为。
if (typeof window !== 'undefined' && (import.meta.env.DEV || localStorage.getItem('__peaDevHooks') === '1')) {
  // @ts-ignore
  window.__canvas = useCanvas;
  // @ts-ignore
  window.__ui = useUi;
  // ReactFlow 内部 store 暴露（用于框选 DOM 二次校正读 userSelectionRect）
  // 通过 useStoreApi hook 在 CanvasEditor 内部组件里赋值
}
import PeaEdge from './PeaEdge';
import CanvasErrorBoundary from './ErrorBoundary';
import SidePanel from './SidePanel';
import MaterialPanel from './MaterialPanel';
import NodeChatPrompt from './NodeChatPrompt';
import MultiSelectToolbar from './MultiSelectToolbar';
import SelectionBoundsBox from './SelectionBoundsBox';
import SearchPopover from './SearchPopover';
import MiniMapNode from './MiniMapNode';
import { kindColor } from './NodeIcon';
import { acceptsUpstreamInput } from '../lib/nodeSemantics';
import { resolveConnection } from '../lib/connectionOrientation';
import {
  NODE_DEF_OF,
  PeaNodeKind,
} from '../constants/nodeTypes';

const nodeTypes = { pea: PeaNode, group: GroupNode };
const edgeTypes = { pea: PeaEdge };

/**
 * 把当前画布缩放的倒数(1/zoom)写入全局 CSS 变量 --pea-inv-zoom。
 * 节点上的编辑框/功能条用 transform: scale(var(--pea-inv-zoom)) 抵消画布缩放，
 * 使它们随节点平移、但屏幕大小恒定（不随放大缩小而变形）。
 * 仅在 zoom 变化时写一次变量，节点本身不因此重渲，性能无忧。
 */
function ZoomVarSync() {
  const { zoom } = useViewport();
  useEffect(() => {
    document.documentElement.style.setProperty('--pea-inv-zoom', String(1 / zoom));
  }, [zoom]);
  return null;
}

interface MenuState {
  x: number;
  y: number;
  nodeId: string | null;
}

function relTime(ts: number | null): string {
  if (!ts) return '尚未保存';
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return '刚刚';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

/** MiniMap 节点着色：优先使用节点 data.kind 对应的品牌色。 */
function minimapNodeColor(node: Node<PeaNodeData>): string {
  return kindColor(node.data?.kind ?? 'prompt');
}

/** 画布左上角：pea logo 圆形按钮（hover 提示画布名 + 修改时间，点击展开下拉）。 */
function CanvasHeader({
  onClose,
}: {
  onClose: () => void;
}) {
  const title = useCanvas((s) => s.title);
  const lastSavedAt = useCanvas((s) => s.lastSavedAt);
  const canvasId = useCanvas((s) => s.canvasId);
  const { design: creatorDesign, setDesign: setCreatorDesign } = useCreatorDesign();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!(e.target instanceof Node) || !wrapRef.current?.contains(e.target)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('mousedown', onDocClick);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDocClick);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const displayTitle = title || '未命名画布';
  // Tooltip 内容：「画布名 · 上次修改于 X 分钟前」，居中显示（多行）
  const tipTitle = (
    <div className="text-center leading-tight">
      <div className="font-medium">{displayTitle}</div>
      <div className="text-[11px] opacity-80 mt-0.5">上次修改于 {relTime(lastSavedAt)}</div>
    </div>
  );

  return (
    <div ref={wrapRef} className="pea-canvas-header">
      <Tooltip title={tipTitle} placement="bottom" mouseEnterDelay={0.15}>
        <button
          type="button"
          className="pea-canvas-header-trigger"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={`画布：${displayTitle}，点击打开画布菜单`}
          onClick={() => setOpen((v) => !v)}
        >
          <img src="/logo.svg" alt="pea" className="pea-canvas-header-logo" />
        </button>
      </Tooltip>

      {open && (
        <div role="menu" className="pea-canvas-dropdown">
          <div className="pea-canvas-dropdown-head">
            <img src="/logo.svg" alt="pea" className="h-7 w-7 shrink-0 rounded-lg shadow-sm" />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{title || '未命名画布'}</div>
              <div className="truncate text-[11px] text-pea-text-muted">
                上次修改于 {relTime(lastSavedAt)}
              </div>
            </div>
          </div>
          <div className="pea-canvas-dropdown-divider" />
          <button
            type="button"
            role="menuitem"
            className="pea-canvas-dropdown-item"
            onClick={() => {
              setOpen(false);
              onClose();
            }}
          >
            ← 返回工作空间
          </button>
          <div className="pea-canvas-dropdown-group">探索</div>
          <button
            type="button"
            role="menuitem"
            className="pea-canvas-dropdown-item muted"
            onClick={() => {
              setOpen(false);
              toast.info('探索即将开放');
            }}
          >
            <CompassOutlined /> 探索
          </button>
          <button
            type="button"
            role="menuitem"
            className="pea-canvas-dropdown-item"
            onClick={() => {
              setOpen(false);
              const { setActive } = useUi.getState();
              setActive('tvtv');
            }}
          >
            <PlayCircleOutlined /> TapTV
          </button>
          <button
            type="button"
            role="menuitem"
            className="pea-canvas-dropdown-item"
            onClick={() => {
              setOpen(false);
              const { setActive } = useUi.getState();
              setActive('arena');
            }}
          >
            <TrophyOutlined /> 竞技场
          </button>
          <div className="pea-canvas-dropdown-divider" />
          <div className="pea-canvas-dropdown-group">项目</div>
          <RenameItem id={canvasId} title={title} onDone={() => setOpen(false)} />
          <NewProjectItem onDone={() => setOpen(false)} />
          <div className="pea-canvas-dropdown-divider" />
          <DeleteItem id={canvasId} title={title} onDone={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}

function RenameItem({
  id,
  title,
  onDone,
}: {
  id: number | null;
  title: string;
  onDone: () => void;
}) {
  const { message } = App.useApp();
  const renameInline = useCallback(
    async (newTitle: string) => {
      if (id == null) return;
      const t = newTitle.trim();
      if (!t || t === title) return;
      try {
        await canvasesApi.update(id, { title: t });
        const s = useCanvas.getState();
        // 重命名后立刻同步本地标题
        s.setCanvasMeta(id, s.version, t);
        toast.success('已重命名');
        onDone();
      } catch {
        toast.error('重命名失败');
      }
    },
    [id, title, onDone],
  );

  const onClick = () => {
    let inputValue = title;
    Modal.confirm({
      title: '重命名项目',
      content: (
        <Input
          defaultValue={title}
          autoFocus
          onChange={(e) => (inputValue = e.target.value)}
          onPressEnter={(e) => {
            // antd Modal.confirm 不响应表单回车；自定义输入处理
            e.preventDefault();
          }}
        />
      ),
      okText: '保存',
      cancelText: '取消',
      onOk: async () => {
        await renameInline(inputValue);
      },
    });
    void message;
  };

  return (
    <button type="button" role="menuitem" className="pea-canvas-dropdown-item" onClick={onClick}>
      <EditOutlined /> 重命名
    </button>
  );
}

function NewProjectItem({ onDone }: { onDone: () => void }) {
  return (
    <button
      type="button"
      role="menuitem"
      className="pea-canvas-dropdown-item"
      onClick={async () => {
        onDone();
        try {
          const { id } = await canvasesApi.create('未命名画布', 'personal');
          await useCanvas.getState().openCanvas(id);
          useUi.getState().setActive('canvas');
          toast.success('已创建并打开新画布');
        } catch {
          toast.error('新建失败');
        }
      }}
    >
      <PlusOutlined /> 新建项目
    </button>
  );
}

function DeleteItem({
  id,
  title,
  onDone,
}: {
  id: number | null;
  title: string;
  onDone: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      className="pea-canvas-dropdown-item danger"
      onClick={() => {
        if (id == null) {
          toast.error('画布不存在');
          return;
        }
        Modal.confirm({
          title: '删除项目',
          content: (
            <span>
              确认删除 <b>{title || '未命名画布'}</b>？当前为物理删除（不可恢复）。
            </span>
          ),
          okText: '删除',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: async () => {
            try {
              await canvasesApi.remove(id);
              toast.success('已删除');
              onDone();
              useUi.getState().setActive('workspace');
            } catch {
              toast.error('删除失败');
            }
          },
        });
      }}
    >
      <DeleteOutlined /> 删除
    </button>
  );
}

/** 画布右上角：创作主题切换 + Tapies 余额 + 社区 + 分享 */
function CanvasActions() {
  const balance = useAuth((s) => s.balance);
  const refreshBalance = useAuth((s) => s.refreshBalance);
  const { design: creatorDesign, setDesign: setCreatorDesign } = useCreatorDesign();
  const [shareBusy, setShareBusy] = useState(false);
  const { message } = App.useApp();

  const onShare = async () => {
    const url = window.location.href;
    setShareBusy(true);
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(url);
      } else {
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        if (!document.execCommand('copy')) throw new Error('copy failed');
        document.body.removeChild(ta);
      }
      toast.success('链接已复制到剪贴板');
    } catch {
      toast.error('复制失败，请手动复制');
      message.info(url);
    } finally {
      setShareBusy(false);
    }
  };

  return (
    <div className="pea-canvas-actions">
      {/* 创作主题切换（下拉选择） */}
      <Select
        size="small"
        value={creatorDesign}
        onChange={(v) => setCreatorDesign(v as 'runway' | 'figma')}
        popupClassName="pea-canvas-theme-dropdown"
        variant="borderless"
        className="pea-canvas-theme-select"
        options={[
          { value: 'runway', label: '🎬 暗调电影感' },
          { value: 'figma', label: '✨ 明亮创作' },
        ]}
        aria-label="创作端设计主题"
      />

      <Tooltip title="账户余额 (Tapies) — 点击查看订阅套餐">
        <button
          type="button"
          className="pea-canvas-tapies"
          aria-label={`Tapies 余额 ${balance}，点击查看订阅套餐`}
          onClick={() => useUi.getState().setActive('plans')}
        >
          {/* 能量光球图标（圆形） */}
          <svg className="pea-balance-gem" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
            <defs>
              <radialGradient id="gemBg" cx="40%" cy="35%" r="60%">
                <stop offset="0%" stopColor="#c4b5fd"/>
                <stop offset="50%" stopColor="#a78bfa"/>
                <stop offset="100%" stopColor="#5B7BF5"/>
              </radialGradient>
              <linearGradient id="gemShine" x1="6" y1="4" x2="18" y2="16">
                <stop offset="0%" stopColor="rgba(255,255,255,0.75)"/>
                <stop offset="100%" stopColor="rgba(255,255,255,0)"/>
              </linearGradient>
              <filter id="gemGlow">
                <feGaussianBlur stdDeviation="1" result="blur"/>
                <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
            </defs>
            {/* 外层光晕 */}
            <circle cx="14" cy="14" r="12" fill="url(#gemBg)" filter="url(#gemGlow)" opacity="0.3"/>
            {/* 主球体 */}
            <circle cx="14" cy="14" r="10" fill="url(#gemBg)"/>
            {/* 上方高光弧 */}
            <path d="M7 11A7 7 0 0 1 21 11" stroke="url(#gemShine)" strokeWidth="2" strokeLinecap="round" fill="none"/>
            {/* 左上小高光点 */}
            <circle cx="10" cy="9.5" r="1.8" fill="rgba(255,255,255,0.55)"/>
            {/* 中心星芒 */}
            <path d="M14 7L14.8 10.2L18 11L14.8 11.8L14 15L13.2 11.8L10 11L13.2 10.2Z" fill="rgba(255,255,255,0.9)"/>
          </svg>
          <span className="pea-balance-num">{balance}</span>
        </button>
      </Tooltip>
      <button
        type="button"
        className="pea-canvas-community"
        onClick={() => toast.info('社区功能即将开放')}
      >
        ✦ 社区
      </button>
      <Tooltip title="复制分享链接">
        <button
          type="button"
          className="pea-canvas-iconbtn"
          aria-label="复制分享链接"
          onClick={onShare}
          disabled={shareBusy}
        >
          <ShareAltOutlined />
        </button>
      </Tooltip>
    </div>
  );
}

/** 双击画布弹出的"添加节点"菜单（对齐参考图） */
function NodeLibrary({
  at,
  onPick,
  onClose,
}: {
  at: { x: number; y: number };
  onPick: (k: PeaNodeKind) => void;
  onClose: () => void;
}) {
  const [hover, setHover] = useState<PeaNodeKind | 'upload' | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const items: Array<
    | { group: '添加节点'; kind: PeaNodeKind; icon: React.ReactNode; label: string; sub?: string; dot?: boolean; tag?: string }
    | { group: '辅助工具'; kind: PeaNodeKind; icon: React.ReactNode; label: string; sub?: string; tag?: string }
    | { group: '添加资源'; action: 'upload'; icon: React.ReactNode; label: string }
  > = [
    { group: '添加节点', kind: 'text', icon: <NodeIcon kind="text" size={16} />, label: '文本' },
    { group: '添加节点', kind: 'image', icon: <NodeIcon kind="image" size={16} />, label: '图片', sub: '宣传图、海报、封面' },
    { group: '添加节点', kind: 'video', icon: <NodeIcon kind="video" size={16} />, label: '视频' },
    { group: '添加节点', kind: 'audio', icon: <NodeIcon kind="audio" size={16} />, label: '音频', dot: true },
    { group: '添加节点', kind: 'world3d', icon: <NodeIcon kind="world3d" size={16} />, label: '3D 世界', tag: 'Beta' },
    { group: '辅助工具', kind: 'playlist', icon: <NodeIcon kind="playlist" size={16} />, label: '播放列表', tag: 'Beta' },
    { group: '添加资源', action: 'upload', icon: <NodeIcon kind="image" size={16} />, label: '上传' },
  ];

  const groups = ['添加节点', '辅助工具', '添加资源'] as const;

  const menuStyle: React.CSSProperties = {
    position: 'fixed',
    left: Math.min(Math.max(at.x - 150, 12), window.innerWidth - 320),
    top: Math.min(at.y + 8, window.innerHeight - 420),
    zIndex: 50,
  };

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="pea-add-menu" style={menuStyle} onClick={(e) => e.stopPropagation()} role="menu">
        <div className="pea-add-menu-title">添加节点</div>
        {groups.map((g) => {
          const list = items.filter((it) => (it as any).group === g);
          if (!list.length) return null;
          return (
            <div key={g} className="pea-add-menu-section">
              {g !== '添加节点' && <div className="pea-add-menu-group">{g}</div>}
              {list.map((it: any) => {
                const isUpload = it.action === 'upload';
                const key = isUpload ? 'upload' : it.kind;
                const hl = hover === key;
                return (
                  <button
                    key={key}
                    className={`pea-add-menu-item ${hl ? 'hl' : ''}`}
                    onMouseEnter={() => setHover(key as any)}
                    onMouseLeave={() => setHover(null)}
                    onClick={() => {
                      if (isUpload) {
                        toast.info('请使用节点上方的"上传"按钮上传资源');
                      } else {
                        onPick(it.kind);
                      }
                      onClose();
                    }}
                    role="menuitem"
                  >
                    <span className="pea-add-menu-icon" aria-hidden>
                      {it.icon}
                    </span>
                    <span className="pea-add-menu-text">
                      <span className="pea-add-menu-label">
                        {it.label}
                        {it.dot && <span className="pea-add-menu-dot" aria-hidden />}
                        {it.tag && <span className="pea-add-menu-tag">{it.tag}</span>}
                      </span>
                      {it.sub && <span className="pea-add-menu-sub">{it.sub}</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
    </>
  );
}

/** 连线末端释放到空白处时弹出的节点选择菜单（对齐截图3） */
function EdgeNodeMenu({
  at,
  onPick,
  onClose,
}: {
  at: { x: number; y: number };
  onPick: (k: PeaNodeKind) => void;
  onClose: () => void;
}) {
  const [hover, setHover] = useState<PeaNodeKind | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const items: { kind: PeaNodeKind; label: string; sub?: string; tag?: string; icon: React.ReactNode }[] = [
    {
      kind: 'text',
      label: '文本生成',
      sub: '脚本、广告词、品牌文案',
      icon: <NodeIcon kind="text" size={18} />,
    },
    {
      kind: 'image',
      label: '图片生成',
      icon: <NodeIcon kind="image" size={18} />,
    },
    {
      kind: 'video',
      label: '视频生成',
      icon: <NodeIcon kind="video" size={18} />,
    },
    {
      kind: 'audio',
      label: '音频',
      icon: <NodeIcon kind="audio" size={18} />,
    },
    {
      kind: 'world3d',
      label: '3D 世界',
      tag: 'Beta',
      icon: <NodeIcon kind="world3d" size={18} />,
    },
  ];

  const menuStyle: React.CSSProperties = {
    position: 'fixed',
    left: Math.min(Math.max(at.x - 140, 12), window.innerWidth - 300),
    top: Math.min(Math.max(at.y - 60, 12), window.innerHeight - 360),
    zIndex: 50,
  };

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="pea-edge-menu" style={menuStyle} onClick={(e) => e.stopPropagation()} role="menu">
        {items.map((it) => {
          const hl = hover === it.kind;
          return (
            <button
              key={it.kind}
              className={`pea-edge-menu-item ${hl ? 'hl' : ''}`}
              onMouseEnter={() => setHover(it.kind)}
              onMouseLeave={() => setHover(null)}
              onClick={() => {
                onPick(it.kind);
                onClose();
              }}
              role="menuitem"
            >
              <span className="pea-edge-menu-icon" aria-hidden>
                {it.icon}
              </span>
              <span className="pea-edge-menu-text">
                <span className="pea-edge-menu-label">
                  {it.label}
                  {it.tag && <span className="pea-edge-menu-tag">{it.tag}</span>}
                </span>
                {it.sub && <span className="pea-edge-menu-sub">{it.sub}</span>}
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}

/** 画布左侧工具栏（对齐 pea-canvas-v12 .toolbar-left）
 * 设计要点（taste-skill / anti-slop）：
 * - 用 antd 图标替代 emoji，保证整应用图标家族一致；
 * - 每个按钮有清晰的 hover/active 反馈，active 状态与对应面板开关联动；
 * - 去掉无意义的装饰性小红点，减少视觉噪音；
 * - 头像使用品牌色渐变，与整体 token 系统统一。
 */
function LeftToolbar({
  onAdd,
  onSearch,
  onFiles,
  onComments,
  onHistory,
  onLibrary,
  onAvatar,
  libraryOpen,
  searchOpen,
  filesOpen,
}: {
  onAdd: () => void;
  onSearch: () => void;
  onFiles: () => void;
  onComments: () => void;
  onHistory: () => void;
  onLibrary: () => void;
  onAvatar: () => void;
  libraryOpen: boolean;
  searchOpen: boolean;
  filesOpen: boolean;
}) {
  return (
    <aside className="pea-toolbar" aria-label="画布工具栏">
      <Tooltip title="添加节点（双击画布也可打开）" placement="right">
        <button
          type="button"
          className={`pea-tlb-btn${libraryOpen ? ' active' : ''}`}
          aria-label="添加节点"
          onClick={onAdd}
        >
          <PlusOutlined aria-hidden />
        </button>
      </Tooltip>
      <Tooltip title="搜索" placement="right">
        <button
          type="button"
          className={`pea-tlb-btn${searchOpen ? ' active' : ''}`}
          aria-label="搜索"
          onClick={onSearch}
        >
          <SearchOutlined aria-hidden />
        </button>
      </Tooltip>
      <Tooltip title="收藏夹" placement="right">
        <button
          type="button"
          className={`pea-tlb-btn${filesOpen ? ' active' : ''}`}
          aria-label="收藏夹"
          onClick={onFiles}
        >
          <FolderOutlined aria-hidden />
        </button>
      </Tooltip>
      <Tooltip title="节点库" placement="right">
        <button
          type="button"
          className={`pea-tlb-btn${libraryOpen ? ' active' : ''}`}
          aria-label="节点库"
          onClick={onLibrary}
        >
          <AppstoreOutlined aria-hidden />
        </button>
      </Tooltip>
      <Tooltip title="评论" placement="right">
        <button
          type="button"
          className="pea-tlb-btn"
          aria-label="评论"
          onClick={onComments}
        >
          <CommentOutlined aria-hidden />
        </button>
      </Tooltip>
      <Tooltip title="历史记录" placement="right">
        <button
          type="button"
          className="pea-tlb-btn"
          aria-label="历史记录"
          onClick={onHistory}
        >
          <HistoryOutlined aria-hidden />
        </button>
      </Tooltip>
      <div className="pea-toolbar-bottom">
        <Tooltip title="账户" placement="right">
          <button
            type="button"
            className="pea-tlb-avatar"
            aria-label="打开账户菜单"
            onClick={onAvatar}
          >
            W
          </button>
        </Tooltip>
      </div>
    </aside>
  );
}

/**
 * 自定义画布控件（对齐图1）：
 * - 深色圆角胶囊容器，底部左侧
 * - 缩略图、网格、适配视图、缩放滑块
 * - 右侧独立圆形帮助按钮
 */
function CanvasControls({
  showMinimap,
  setShowMinimap,
  showGrid,
  setShowGrid,
}: {
  showMinimap: boolean;
  setShowMinimap: (v: boolean) => void;
  showGrid: boolean;
  setShowGrid: (v: boolean) => void;
}) {
  const { fitView, getZoom, setViewport, getViewport } = useReactFlow();
  const rfStoreApi = useStoreApi();
  const [zoom, setZoom] = useState(() => getZoom());

  useEffect(() => {
    const t = setInterval(() => setZoom(getZoom()), 80);
    return () => clearInterval(t);
  }, [getZoom]);

  const minZoom = 0.25;
  const maxZoom = 3;
  const logMin = Math.log(minZoom);
  const logMax = Math.log(maxZoom);
  const ratio = (Math.log(zoom) - logMin) / (logMax - logMin);
  const sliderValue = Math.max(0, Math.min(100, Math.round(ratio * 100)));

  const setZoomFromSlider = (v: number) => {
    const r = Math.max(0, Math.min(1, v / 100));
    const next = Math.exp(logMin + r * (logMax - logMin));
    const vp = getViewport();
    const { width, height } = rfStoreApi.getState();
    const w2 = width / 2;
    const h2 = height / 2;
    // 关键修复：以当前可视窗口中心为锚点缩放。
    // ReactFlow 视口变换：screen = flow * zoom + translate，
    // 因此窗口中心对应的 flow 坐标为 center = (size/2 - translate) / zoom。
    // 缩放后保持 center 不变：translate' = size/2 - center * zoom'。
    // 原实现把 x 的符号弄反，导致点击缩放条画布向反方向跳飞。
    const cx = (w2 - vp.x) / vp.zoom;
    const cy = (h2 - vp.y) / vp.zoom;
    setViewport(
      {
        x: w2 - cx * next,
        y: h2 - cy * next,
        zoom: next,
      },
      { duration: 0 },
    );
  };

  return (
    <div className="pea-canvas-controls" role="toolbar" aria-label="画布视图控制">
      <div className="pea-canvas-controls-pill">
        <button
          type="button"
          className={`pea-canvas-controls-btn ${showMinimap ? 'active' : ''}`}
          aria-label="切换缩略图"
          title="切换缩略图"
          onClick={() => setShowMinimap(!showMinimap)}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </button>
        <button
          type="button"
          className={`pea-canvas-controls-btn ${showGrid ? 'active' : ''}`}
          aria-label="切换网格"
          title="切换网格"
          onClick={() => setShowGrid(!showGrid)}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
        </button>
        <button
          type="button"
          className="pea-canvas-controls-btn"
          aria-label="适配视图"
          title="适配视图 (F)"
          onClick={() => fitView({ duration: 240, padding: 0.2, maxZoom: 1 })}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 9V5a1 1 0 0 1 1-1h4" />
            <path d="M20 9V5a1 1 0 0 0-1-1h-4" />
            <path d="M4 15v4a1 1 0 0 0 1 1h4" />
            <path d="M20 15v4a1 1 0 0 1-1 1h-4" />
          </svg>
        </button>
        <div className="pea-canvas-controls-slider-wrap">
          <input
            type="range"
            min={0}
            max={100}
            value={sliderValue}
            aria-label="画布缩放"
            onChange={(e) => setZoomFromSlider(Number(e.target.value))}
          />
        </div>
      </div>
      <button
        type="button"
        className="pea-canvas-controls-help"
        aria-label="快捷键帮助"
        title="快捷键帮助"
        onClick={() =>
          toast.info(
            '快捷键：Ctrl+S 保存 / Ctrl+Z 撤销 / Ctrl+Shift+Z 重做 / Delete 删除 / Esc 取消选中 / 双击空白添加节点 / 左键拖拽框选 / 右键拖拽平移画布',
          )
        }
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </button>
    </div>
  );
}

/** 画布右下角 Brainstorm 提示 + 头像（对齐图1） */
function BottomPrompt() {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <div className="pea-canvas-bottom-prompt" role="complementary">
      <span className="pea-canvas-bottom-prompt-text">体验 Brainstorm 模式打开故事方向</span>
      <button
        type="button"
        className="pea-canvas-bottom-prompt-close"
        aria-label="关闭"
        onClick={() => setDismissed(true)}
      >
        <CloseOutlined />
      </button>
      <div className="pea-canvas-bottom-prompt-avatar" aria-hidden>
        W
      </div>
    </div>
  );
}

/**
 * 自接管选区渲染：因为 .react-flow__selection 在本应用 viewport transform 下被截断（CSS 已隐藏），
 * 我们用原始 pointer 事件算出的屏幕坐标重新画一个 blue rect。
 * - 仅在 __lastSelRect 存在且非「上一拖拽的遗留」时显示（dragging=true 时），
 *   拖拽结束（mouseup）后 250ms 自动 fade 消失（用 style.opacity 控制）。
 * - 用 position: fixed 直接锚定屏幕坐标，不需要考虑 viewport transform。
 */
function SelectionOverlay() {
  const [rect, setRect] = useState<{
    l: number; t: number; w: number; h: number;
    active: boolean;
  } | null>(null);
  // rAF 循环在挂载时只创建一次，必须读 ref 才能拿到最新 rect，否则闭包里的 rect 永远是 null，
  // 导致拖拽结束后无法进入 fade-out 分支，选区 overlay 永久残留。
  const rectRef = useRef(rect);
  useEffect(() => {
    rectRef.current = rect;
  }, [rect]);

  useEffect(() => {
    let raf = 0;
    let hideTimer: ReturnType<typeof setTimeout> | null = null;

    const tick = () => {
      const w = window as any;
      const last = w.__lastSelRect as
        | { screenLeft: number; screenTop: number; screenRight: number; screenBottom: number; timestamp: number }
        | null;
      const flag = !!w.__selDragging;
      const currentRect = rectRef.current;

      if (flag && last) {
        if (hideTimer) {
          clearTimeout(hideTimer);
          hideTimer = null;
        }
        const wpx = last.screenRight - last.screenLeft;
        const hpx = last.screenBottom - last.screenTop;
        if (wpx >= 2 && hpx >= 2) {
          setRect({
            l: last.screenLeft,
            t: last.screenTop,
            w: wpx,
            h: hpx,
            active: true,
          });
        }
      } else if (currentRect && currentRect.active) {
        // 刚停止拖拽：保留最后一次绘制但置 inactive（触发 CSS opacity 过渡），随后移除 DOM
        setRect({ ...currentRect, active: false });
        if (!hideTimer) {
          hideTimer = setTimeout(() => {
            setRect(null);
            hideTimer = null;
          }, 120);
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      if (hideTimer) clearTimeout(hideTimer);
    };
  }, []);

  if (!rect) return null;
  if (typeof document === 'undefined') return null;
  return createPortal(
    <div
      className="pea-selection-overlay"
      data-testid="pea-selection-overlay"
      style={{
        left: rect.l,
        top: rect.t,
        width: rect.w,
        height: rect.h,
        opacity: rect.active ? 1 : 0,
      }}
    />,
    document.body,
  );
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 画布视口持久化（修复"每次进入画布都回到初始状态"）
 *   - 按 canvasId 隔离 localStorage key，记录 {x, y, zoom}（即 ReactFlow viewport）。
 *   - 进入画布：若存过视口 → setViewport 恢复；否则 fitView 自适应。
 *   - 平移/缩放时（onMove）防抖写入；卸载时立即落地（不等防抖）。
 *   - 只存视口，不动 graph_json，避免版本号无谓自增。
 * ═════════════════════════════════════════════════════════════════════════════ */
type Viewport = { x: number; y: number; zoom: number };
const vpKey = (canvasId: string | number) => `pea_canvas_vp_${canvasId}`;

function loadViewport(key: string): Viewport | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const v = JSON.parse(raw);
    if (typeof v?.x === 'number' && typeof v?.y === 'number' && typeof v?.zoom === 'number') {
      return { x: v.x, y: v.y, zoom: v.zoom };
    }
  } catch {
    /* 解析失败忽略，回落到 fitView */
  }
  return null;
}

function saveViewportNow(key: string, vp: Viewport) {
  try {
    localStorage.setItem(key, JSON.stringify({ x: vp.x, y: vp.y, zoom: vp.zoom }));
  } catch {
    /* 配额/隐私模式忽略 */
  }
}

// 模块级节流：同一时刻只有一个画布挂载，按 key 隔离足够；用 rAF 替代 250ms setTimeout，
// 缩短写入间隔（~16ms/帧），大幅降低"放大后快速刷新丢失最后zoom"的概率。
let vpSaveTimer: number | undefined;
function saveViewportThrottled(key: string, vp: Viewport) {
  if (vpSaveTimer != null) cancelAnimationFrame(vpSaveTimer);
  vpSaveTimer = requestAnimationFrame(() => saveViewportNow(key, vp));
}

function Flow() {
  const rfStoreApi = useStoreApi();
  // 暴露 ReactFlow 内部 store 到 window（仅 DEV 或 __peaDevHooks flag），供调试/E2E 验证使用。
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!(import.meta.env.DEV || localStorage.getItem('__peaDevHooks') === '1')) return;
    (window as any).__rfStore = rfStoreApi;
  }, [rfStoreApi]);
  // ── 框选 rect 追踪：直接用原始 pointer 事件计算选区矩形 ──
  // 关键发现：本应用 viewport 为 translate(150px,-102px)，ReactFlow 渲染的 .react-flow__selection
  // 选区 DOM 在框选时会「截断」（实测只画到约 40% 宽度），导致读该 DOM 的校正也只选左列。
  // 故不再依赖 RF 的选区 DOM，而是直接记录 pane 上的 mousedown 起点 + mousemove/mouseup 终点，
  // 用原始 clientX/Y 计算完整选区 rect（屏幕坐标 → 画布坐标），100% 可靠。
  // 选区结束后保留最近一次 rect 约 150ms（让 onNodesChange 的 setTimeout(0) 校正能读到），随后清空。
  useEffect(() => {
    if (typeof document === 'undefined' || typeof window === 'undefined') return;
    const w = window as any;
    if (w.__lastSelRect === undefined) w.__lastSelRect = null;

    const toCanvasRect = (x1: number, y1: number, x2: number, y2: number) => {
      const vp = document.querySelector<HTMLElement>('.react-flow__viewport');
      const cnr = document.querySelector<HTMLElement>('.react-flow__pane');
      let tx = 0, ty = 0, ts = 1;
      if (vp) {
        const m = /translate\(\s*(-?[\d.]+)px,\s*(-?[\d.]+)px\)\s*scale\(\s*([\d.]+)\s*\)/.exec(vp.style.transform);
        if (m) {
          tx = parseFloat(m[1]);
          ty = parseFloat(m[2]);
          ts = parseFloat(m[3]);
        }
      }
      const cnrR = cnr ? cnr.getBoundingClientRect() : { left: 0, top: 0 } as DOMRect;
      const left = Math.min(x1, x2);
      const top = Math.min(y1, y2);
      const right = Math.max(x1, x2);
      const bottom = Math.max(y1, y2);
      w.__lastSelRect = {
        x: (left - cnrR.left - tx) / ts,
        y: (top - cnrR.top - ty) / ts,
        width: (right - left) / ts,
        height: (bottom - top) / ts,
        screenLeft: left,
        screenTop: top,
        screenRight: right,
        screenBottom: bottom,
        timestamp: performance.now(),
      };
    };

    let dragging = false;
    let startX = 0, startY = 0, curX = 0, curY = 0;
    let moved = false;

    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null;
      // 仅在画布 pane / renderer 上启动框选；点节点或边由各自处理。
      if (t && (t.classList.contains('react-flow__pane') || t.classList.contains('react-flow__renderer'))) {
        dragging = true;
        w.__selDragging = true;
        moved = false;
        startX = e.clientX; startY = e.clientY;
        curX = e.clientX; curY = e.clientY;
        // 下一次按下清空上一帧的"残留 rect"，让 overlay 不被旧 rect 重影。
        w.__lastSelRect = null;
      }
    };
    const onMove = (e: MouseEvent) => {
      if (!dragging) return;
      curX = e.clientX; curY = e.clientY;
      moved = true;
      // 用屏幕坐标算 rect（不动 RF DOM，overlay 渲染直接用 screenLeft/Top/...）。
      toCanvasRect(startX, startY, curX, curY);
    };
    const onUp = (e?: MouseEvent) => {
      if (!dragging) return;
      dragging = false;
      w.__selDragging = false; // overlay 转入 fade-out 模式
      // 用 mouseup 事件自身的 clientX/Y 作为终点（不依赖 curX/curY — 真实浏览器里
      // 最后一次 mousemove 可能晚于 mouseup 到达，导致 curX/curY 滞后于鼠标指针）。
      const endX = e ? e.clientX : curX;
      const endY = e ? e.clientY : curY;
      curX = endX; curY = endY;
      toCanvasRect(startX, startY, endX, endY); // 最终一次
      if (moved) {
        // 触发「覆盖即选中」二次校正：setTimeout(0) 让 RF 先完成 mouseup 定稿（选中集合已确定），
        // 此刻 window.__lastSelRect 是完整选区矩形 → 把被覆盖但 RF 漏选的节点补进 selectedIds。
        setTimeout(() => {
          try {
            useCanvas.getState().correctBoxSelection();
          } catch (e) {
            /* noop */
          }
        }, 0);
      }
    };

    window.addEventListener('mousedown', onDown, true);
    window.addEventListener('mousemove', onMove, true);
    window.addEventListener('mouseup', onUp, true);
    return () => {
      window.removeEventListener('mousedown', onDown, true);
      window.removeEventListener('mousemove', onMove, true);
      window.removeEventListener('mouseup', onUp, true);
    };
  }, []);
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    select,
    setSelection,
    clearSelection,
    selectedIds,
    canvasId,
    version,
    dirty,
    markSaved,
    removeNode,
    removeEdge,
    duplicateNode,
    addConnected,
    copySelected,
    pasteNode,
  } = useCanvas();

  // 保存前清洗节点：只持久化必要字段（id/type/position/data），丢弃 ReactFlow 运行时字段
  // （width/height/positionAbsolute/selected/dragging/measured 等），避免脏字段写回导致
  // 重新加载时视口/布局抖动、表现为「同一画布数据不一致」。
  // cleanGraph 现复用 store 中的实现（见 canvas.ts 的 cleanGraph），
  // 与 store.saveCanvasNow / openCanvas 口径一致，避免序列化逻辑分叉。

  // 离开画布前（返回工作空间 / 刷新 / 关闭）确保未保存的改动落地。
  // 用 getState() 读最新，避免闭包陈旧；幂等（version 乐观锁，重复 PUT 第二次 409 被忽略）。
  const flushSave = useCallback(async () => {
    const s = useCanvas.getState();
    if (!s.dirty || s.canvasId == null) return;
    try {
      const { data } = await api.put(`/canvases/${s.canvasId}`, {
        graph_json: cleanGraph(s.nodes, s.edges),
        version: s.version,
      });
      useCanvas.getState().markSaved(data.version);
    } catch {
      /* 画布可能已删除或网络异常，忽略 */
    }
  }, []);

  // 卸载兜底：覆盖任何未显式 flush 的卸载路径（含浏览器刷新 / 关闭）。
  // 关键修复：原实现用 axios 异步 PUT，页面卸载时请求常被浏览器中止而丢弃 ->
  // 最后一段编辑（含视频/图片节点的提示词 editorText）只存在于内存 + localStorage，
  // 一旦标签页被异常关闭/崩溃，且用户换设备/清缓存后重进，提示词永久丢失（"重启容器后丢失"的元凶之一）。
  // 改用 fetch(keepalive:true)：keepalive 请求不受页面卸载影响，能可靠送达后端落库。
  const flushSaveKeepalive = () => {
    const s = useCanvas.getState();
    if (!s.dirty || s.canvasId == null) return;
    const token = localStorage.getItem('pea_token');
    try {
      fetch(`/api/canvases/${s.canvasId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          graph_json: cleanGraph(s.nodes, s.edges),
          version: s.version,
        }),
        keepalive: true,
      }).catch(() => {});
    } catch {
      /* keepalive 不被支持时退化为不落库（极少数环境），不阻断卸载 */
    }
  };

  useEffect(() => {
    return () => {
      flushSaveKeepalive();
    };
  }, []);

  // 标签页隐藏/挂起时立即落库：比 beforeunload 更可靠地覆盖
  // 「切走/锁屏/后台被杀」等不会触发 beforeunload 的场景，确保提示词在任何退出路径都不丢。
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === 'hidden') flushSaveKeepalive();
    };
    document.addEventListener('visibilitychange', onHide);
    window.addEventListener('pagehide', flushSaveKeepalive);
    return () => {
      document.removeEventListener('visibilitychange', onHide);
      window.removeEventListener('pagehide', flushSaveKeepalive);
    };
  }, []);

  const { screenToFlowPosition, fitView, getViewport, setViewport } = useReactFlow();
  // dev/E2E 钩子：暴露一个设置 zoom 的函数，方便验证脚本在任意缩放级别测试连接点位置。
  useEffect(() => {
    if (typeof window !== 'undefined' && (import.meta.env.DEV || localStorage.getItem('__peaDevHooks') === '1')) {
      // @ts-ignore
      window.__peaSetZoom = (z: number) => {
        const vp = getViewport();
        setViewport({ ...vp, zoom: Math.max(0.25, Math.min(3, z)) }, { duration: 0 });
      };
      // @ts-ignore
      window.__peaFitView = (opts?: { padding?: number; maxZoom?: number }) => {
        fitView({ duration: 0, padding: opts?.padding ?? 0.2, maxZoom: opts?.maxZoom ?? 1 });
      };
      // @ts-ignore
      // 直接设置视口（x,y,zoom），用于 E2E 验证"退出画布后视口持久化恢复"。
      window.__peaSetViewport = (x: number, y: number, z: number) => {
        setViewport({ x, y, zoom: Math.max(0.25, Math.min(3, z)) }, { duration: 0 });
      };
    }
  }, [getViewport, setViewport, fitView]);

  // 搜索弹层点击结果 → 移动视口到目标节点中心。
  // 通过 window CustomEvent 解耦：弹层只 dispatch，由 CanvasEditor 唯一一处 useReactFlow 持有者执行 setViewport。
  // 这样无论弹层在 Portal 哪个 DOM 子树都能复用同一份 ReactFlow 实例。
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onFocus = (e: Event) => {
      const id = (e as CustomEvent).detail?.id as string | undefined;
      if (!id) return;
      const target = useCanvas.getState().nodes.find((n) => n.id === id);
      if (!target) return;
      const w = (target as any).width ?? 260;
      const h = (target as any).height ?? 160;
      const cx = target.position.x + w / 2;
      const cy = target.position.y + h / 2;
      // 计算把节点中心挪到视口中心所需的偏移；
      // 公式：viewport.x = -cx * zoom + containerWidth/2 - (w/2)*zoom  → 这里用 transform 反推即可。
      const vp = getViewport();
      const zoom = vp.zoom;
      const container = flowRef.current;
      const cw = container?.clientWidth ?? window.innerWidth;
      const ch = container?.clientHeight ?? window.innerHeight;
      const nextX = cw / 2 - cx * zoom;
      const nextY = ch / 2 - cy * zoom;
      setViewport({ x: nextX, y: nextY, zoom }, { duration: 320 });
    };
    window.addEventListener('pea:focus-node', onFocus as EventListener);
    return () => window.removeEventListener('pea:focus-node', onFocus as EventListener);
  }, [getViewport, setViewport]);

  // 图片裁剪：点击「裁剪」后把目标节点居中并放大到合适尺寸。
  // 由 PeaNode 发起 CustomEvent，CanvasEditor 作为唯一 useReactFlow 持有者执行视口动画。
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onCenter = (e: Event) => {
      const detail = (e as CustomEvent).detail as { id?: string; zoom?: number; mode?: string } | undefined;
      const id = detail?.id;
      if (!id) return;
      const target = useCanvas.getState().nodes.find((n) => n.id === id);
      if (!target) return;
      const { width, height } = getNodeSize(target.data.aspectRatio, target.data.kind);
      const cx = target.position.x + width / 2;
      const cy = target.position.y + height / 2;
      const container = flowRef.current;
      const cw = container?.clientWidth ?? window.innerWidth;
      const ch = container?.clientHeight ?? window.innerHeight;
      // 角度魔方模式：节点下方约 300px 面板需要留在视口内，
      // 因此节点放在视口偏上（垂直 ~38%），并限制画布缩放让节点+面板都完整可见。
      const cubeMode = detail?.mode === 'cube';
      let zoom: number;
      let centerYRatio = 0.5;
      if (cubeMode) {
        // 节点显示高度不超过视口 42%，给下方角度魔方面板留足空间；
        // 同时限制最大 1.2，避免节点被放得过大。
        zoom = Math.min(1.2, (ch * 0.42) / height, (cw * 0.6) / width);
        centerYRatio = 0.38;
      } else {
        zoom = detail?.zoom ?? Math.min(2, Math.min((cw * 0.8) / width, (ch * 0.8) / height));
      }
      const nextX = cw / 2 - cx * zoom;
      const nextY = ch * centerYRatio - cy * zoom;
      setViewport({ x: nextX, y: nextY, zoom }, { duration: 320 });
    };
    window.addEventListener('pea:center-node', onCenter as EventListener);
    return () => window.removeEventListener('pea:center-node', onCenter as EventListener);
  }, [setViewport]);

  const { message } = App.useApp();
  const saveTimer = useRef<number>();
  const [sideOpen, setSideOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [materialOpen, setMaterialOpen] = useState(false);
  const [libAt, setLibAt] = useState<{ x: number; y: number } | null>(null);
  // 节点落点（独立于弹窗锚点 libAt）：从工具栏/右键打开库时留空 → 走"视口中心 + 避让"，
  // 从双击/某点打开时设为该屏幕坐标 → 节点落在鼠标处。拆开后弹窗定位不再污染节点落点。
  const [spawnAt, setSpawnAt] = useState<{ x: number; y: number } | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [edgeMenu, setEdgeMenu] = useState<{ x: number; y: number; sourceId: string; handleType: 'source' | 'target'; spawn: { x: number; y: number } } | null>(null);
  const [showMinimap, setShowMinimap] = useState(false);
  const [showGrid, setShowGrid] = useState(true);

  /** 点击 MiniMap 节点：聚焦到该节点并把缩略图关闭。 */
  const focusNodeFromMinimap = useCallback(
    (_event: React.MouseEvent, node: Node<PeaNodeData>) => {
      window.dispatchEvent(new CustomEvent('pea:focus-node', { detail: { id: node.id } }));
      setShowMinimap(false);
    },
    [setShowMinimap],
  );
  const pendingEdge = useRef<{ source: string | null; handleId: string | null; handleType: 'source' | 'target' | null } | null>(null);
  // 连线起点坐标：用于区分「单击连接点」与「拖拽连线」（位移阈值判定）。
  const startPosRef = useRef<{ x: number; y: number } | null>(null);
  // 本次拖拽是否已由 onConnect 真正建边：用于防止 onConnectEnd 对「本体落点」重复建边。
  const connectedThisDrag = useRef<boolean>(false);
  // 框选进行中标记：用于抑制拖动经过节点时的 hover 手柄显示与节点弹框（需求2）。
  const [selecting, setSelecting] = useState(false);
  const selectingRef = useRef(false);
  // 多选状态：selectedIds.length > 1 时给画布容器加类，用于抑制单个节点的功能条/上传条
  const isMultiSelect = selectedIds.length > 1;
  // 拖动 vs 单击判定：在 ReactFlow 的 onNodeDragStart 处记录按下坐标
  // （此处不受节点内部 stopPropagation 影响），onNodeClick 时比较位移。
  const downPosRef = useRef<{ x: number; y: number } | null>(null);

  // 右键拖拽平移画布：仅当右键在空白画布区按下时启动，拖动超过阈值即平移视口；
  // 松开后抑制随之而来的 contextmenu，使"右键单击=菜单 / 右键拖拽=平移"两者并存，
  // 且不与左键框选(selectionOnDrag)冲突。
  const flowRef = useRef<HTMLDivElement>(null);
  const panRef = useRef<{ active: boolean; moved: boolean; startX: number; startY: number; vx: number; vy: number } | null>(null);
  const suppressCtxRef = useRef(false);
  // 最近一次视口：onMove 实时写入，卸载时立即落地（不等防抖），保证恢复准确。
  const lastVpRef = useRef<Viewport | null>(null);
  // 【修复】ReactFlow 实例引用，用于 onInit 回调中可靠地恢复视口
  const rfInstanceRef = useRef<any>(null);
  // 【修复】待恢复的视口缓存：canvasId 异步到达时先存，onInit 就绪后消费
  const pendingVpRef = useRef<Viewport | null>(null);
  // 裁切模式锁定：裁切打开时禁止画布缩放/平移/框选
  const cropActiveRef = useRef(false);
  // 退出画布时立即持久化视口（不等 onMove 防抖），下次进入原样恢复，不再回到初始态。
  useEffect(() => {
    return () => {
      const s = useCanvas.getState();
      const id = s.canvasId;
      if (id != null && lastVpRef.current) {
        saveViewportNow(vpKey(id), lastVpRef.current);
      }
    };
  }, []);
  // 页面刷新/关闭前立即落盘（不等防抖 timer），解决 F5 刷新丢失最后视口的问题。
  useEffect(() => {
    const flush = () => {
      const s = useCanvas.getState();
      const id = s.canvasId;
      if (id != null && lastVpRef.current) {
        saveViewportNow(vpKey(id), lastVpRef.current);
      }
    };
    window.addEventListener('beforeunload', flush);
    window.addEventListener('pagehide', flush);
    return () => {
      window.removeEventListener('beforeunload', flush);
      window.removeEventListener('pagehide', flush);
    };
  }, []);

  // ── 裁切模式锁定：监听 ImageCropOverlay 派发的 crop-mode-change 事件 ──
  // 裁切打开时禁止画布的所有交互（缩放/平移/框选/拖拽），防止误操作
  // 通过在画布容器上添加 .pea-canvas-locked 类，CSS 层禁用所有 pointer 事件
  useEffect(() => {
    const onCropModeChange = (e: Event) => {
      const active = (e as CustomEvent).detail?.active === true;
      cropActiveRef.current = active;
      const el = flowRef.current;
      if (!el) return;
      if (active) {
        el.classList.add('pea-canvas-locked');
      } else {
        el.classList.remove('pea-canvas-locked');
      }
    };
    window.addEventListener('crop-mode-change', onCropModeChange);
    return () => window.removeEventListener('crop-mode-change', onCropModeChange);
  }, []);

  useEffect(() => {
    // 进入画布必须经由「新建项目」或「打开项目」显式创建/加载，
    // 这里不再自动创建画布，避免每次加载都产生游离画布。
    // canvasId 为 null 时由下方空状态提示用户。
  }, [canvasId]);

  useEffect(() => {
    if (!dirty || canvasId == null) return;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(async () => {
      // 实时读 store，避免 effect 闭包拿到陈旧的 nodes/edges/version。
      // 这是关键：flushSaveKeepalive（卸载/切走/visibilitychange）会 fire-and-forget 写入，
      // 服务端 version+1 但本地无回调；下一次 autosave 必须用最新本地 version 才不会 409。
      // 见 saveCanvasNow 的 409 重试模式（[store/canvas.ts]）。
      const s = useCanvas.getState();
      if (s.canvasId == null) return;
      const doPut = (v: number) =>
        api.put(`/canvases/${s.canvasId}`, { graph_json: { nodes: s.nodes, edges: s.edges }, version: v });
      try {
        const { data } = await doPut(s.version);
        useCanvas.getState().markSaved(data.version);
      } catch (e: any) {
        if (e?.response?.status === 409) {
          // 乐观锁冲突（最常见元凶：之前有 keepalive/multiple-tab 保存已让服务端 version+1，但本地未同步）。
          // 自动拉取权威 version 后重试一次 — 单用户画布下 last-write-wins 安全。
          try {
            const g = await api.get(`/canvases/${s.canvasId}`);
            const serverVersion: number = g.data.version;
            useCanvas.setState({ version: serverVersion });
            const { data } = await doPut(serverVersion);
            useCanvas.getState().markSaved(data.version);
            // 静默成功：不弹 toast 打扰用户；这是版本号自愈，不是真正的"被人改了"
            return;
          } catch {
            // 重试仍失败 → 降级提示（不要再说"被别人更新"——单用户场景下基本是网络/服务异常）
            message.warning('画布保存冲突，已自动重试，请稍后再试');
            return;
          }
        }
        message.error('保存失败');
      }
    }, 1000);
    return () => window.clearTimeout(saveTimer.current);
  }, [nodes, edges, dirty, canvasId, version, markSaved]);

  // 进入画布时从 localStorage 读取上次视口。
  // 注意：canvasId 是异步到达的（刷新时先挂载组件、后加载画布），
  // defaultViewport 只在首次渲染读一次，此时 canvasId 仍为 null，
  // 所以这里只做缓存；真正的恢复由下方 useEffect(canvasId) 通过 setViewport 执行。
  const initialVp = useMemo<Viewport | null>(
    () => (canvasId != null ? loadViewport(vpKey(canvasId)) : null),
    [canvasId],
  );

  // 视口恢复：当 canvasId 从 null 变为有值时，如果有保存的视口则用 setViewport 恢复；
  // 否则 fitView 自适应。这修复了"刷新页面后画布回到初始状态"的问题。
  //
  // 【修复】三阶段恢复策略：
  //   阶段1（此处）：canvasId 就绪后读取存档 → 缓存到 pendingVpRef + 尝试 RAF 恢复
  //   阶段2（onInit）：ReactFlow 实例就绪后，若 pendingVpRef 有值且阶段1未成功则再次恢复
  //   阶段3（兜底）：若两阶段都失败且 nodes 已加载，fitView 自适应
  const didFit = useRef(false);
  const vpRestored = useRef(false); // 【新增】标记视口是否已成功恢复
  useEffect(() => {
    if (canvasId == null) return;
    const saved = loadViewport(vpKey(canvasId));
    if (saved) {
      // 有存档：缓存待恢复视口
      pendingVpRef.current = saved;
      lastVpRef.current = saved;

      if (!didFit.current) {
        didFit.current = true;
        // 尝试立即恢复（ReactFlow 可能已就绪）
        requestAnimationFrame(() => {
          try {
            setViewport({ x: saved.x, y: saved.y, zoom: saved.zoom }, { duration: 0 });
            vpRestored.current = true;
          } catch {
            // RAF 时实例可能未就绪，由 onInit 兜底恢复
            vpRestored.current = false;
          }
        });
        return;
      }
    }

    // 无存档或已尝试过：fallback 到 fitView
    if (!didFit.current && nodes.length > 0) {
      didFit.current = true;
      // 默认 fitView 后把画布整体向下偏移一点，让节点内容在视口中显示在中间偏上位置
      const t2 = window.setTimeout(() => {
        fitView({ duration: 0, padding: 0.2, maxZoom: 1 });
        requestAnimationFrame(() => {
          const vp = getViewport();
          setViewport({ ...vp, y: vp.y + 80 }, { duration: 0 });
        });
      }, 100);
      return () => window.clearTimeout(t2);
    }
  }, [canvasId, nodes.length, fitView, setViewport]);

  const saveNow = async () => {
    if (canvasId == null) return;
    try {
      const { data } = await api.put(`/canvases/${canvasId}`, { graph_json: cleanGraph(nodes, edges), version });
      markSaved(data.version);
      message.success('已保存');
    } catch {
      message.error('保存失败');
    }
  };

  const add = (kind: PeaNodeKind, label: string, opts?: { prompt?: string }) => {
    // 落点优先用 spawnAt（双击/某点打开时设置）；为空（工具栏/右键打开库）则落视口中心。
    const anchor = spawnAt ?? { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    setSpawnAt(null); // 落点一次性消费，避免污染后续弹窗打开
    let pos = screenToFlowPosition({ x: anchor.x, y: anchor.y });
    const existing = nodes.map((n) => {
      const w = (n as any).width ?? 260;
      const h = (n as any).height ?? 160;
      return { x: n.position.x, y: n.position.y, w, h };
    });
    let step = 0;
    while (
      existing.some(
        (e) =>
          pos.x < e.x + e.w &&
          pos.x + 260 > e.x &&
          pos.y < e.y + e.h &&
          pos.y + 160 > e.y,
      )
    ) {
      step += 1;
      pos = screenToFlowPosition({ x: anchor.x + step * 40, y: anchor.y + step * 30 });
      if (step > 10) break;
    }
    // 新建节点时根据类型写入默认画幅比例（空白节点框按此比例展示）
    const store = useCanvas.getState();
    const ratio = kind === 'image'
      ? store.defaultAspectRatio   // 图片：跟随编辑框比例选择器（默认 9:16）
      : kind === 'video'
        ? '16:9'                   // 视频：固定横屏（无比例选择器）
        : undefined;               // 文本/音频：不设比例
    addNode({
      kind,
      label,
      prompt: opts?.prompt,
      aspectRatio: ratio,
      meta: {
        error: false,
        // 图片节点同步写入 genParams.aspectRatio，使重新选中编辑器时还原到同一比例（而非 1:1）
        ...(kind === 'image' ? { genParams: { aspectRatio: ratio, resolution: '2k' } } : {}),
      },
    } as PeaNodeData, pos);
  };

  const addConnectedAt = (kind: PeaNodeKind, sourceId: string, screenPos: { x: number; y: number }, handleType: 'source' | 'target' = 'source') => {
    const pos = screenToFlowPosition({ x: screenPos.x, y: screenPos.y });
    const label = kind === 'text' ? '文本生成' : kind === 'image' ? '图片生成' : kind === 'video' ? '视频生成' : kind === 'audio' ? '音频' : '3D 世界';
    const store = useCanvas.getState();
    const ratio = kind === 'image'
      ? store.defaultAspectRatio
      : kind === 'video'
        ? '16:9'
        : undefined;
    const newId = addNode({
      kind,
      label,
      aspectRatio: ratio,
      meta: {
        error: false,
        ...(kind === 'image' ? { genParams: { aspectRatio: ratio, resolution: '2k' } } : {}),
      },
    } as PeaNodeData, pos);
    if (newId) {
      // 单击连接点 → 新建并连接（与拖拽连线是不同的交互）：
      // 单击源(out)连接点：新节点作为下游(target)；单击目标(in)连接点：新节点作为上游(source)喂我。
      // 该语义独立于拖拽连线的「起拉节点恒为 source」规则，保持原 handleType 分支，避免回归。
      if (handleType === 'target') {
        onConnect({ source: newId, target: sourceId, sourceHandle: null, targetHandle: 'in' });
      } else {
        onConnect({ source: sourceId, target: newId, sourceHandle: null, targetHandle: 'in' });
      }
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const editing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
      const sel = useCanvas.getState().selectedId;

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        saveNow();
        return;
      }
      // 撤销 / 重做（Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y）。
      // 焦点在文本输入框 / contentEditable 内时，放行给浏览器原生撤销，不拦截画布撤销。
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        if (editing) return;
        e.preventDefault();
        const st = useCanvas.getState();
        if (e.shiftKey) {
          if (st.future.length === 0) { toast.info('没有可重做的操作'); return; }
          st.redo();
        } else {
          if (st.past.length === 0) { toast.info('没有可撤销的操作'); return; }
          st.undo();
        }
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        if (editing) return;
        e.preventDefault();
        const st = useCanvas.getState();
        if (st.future.length === 0) { toast.info('没有可重做的操作'); return; }
        st.redo();
        return;
      }
      // 特例: 选中节点后 NodeChatPrompt 会自动聚焦其 contentEditable 输入栏,
      // 导致 editing 恒为 true, Delete 永远删不掉节点 (用户反复报障)。
      // 规则: 焦点在节点输入栏内且输入栏为空 → Delete 键仍视为「删除节点」;
      // Backspace 不放行 (留给文本编辑, 防连按退格误删节点)。
      const inEmptyPromptEditor =
        editing &&
        e.key === 'Delete' &&
        !!(el.closest && el.closest('.node-prompt-input-wrap')) &&
        (el.textContent ?? '').trim() === '' &&
        !el.querySelector?.('[data-pea-ref]');

      if ((e.key === 'Delete' || e.key === 'Backspace') && (!editing || inEmptyPromptEditor)) {
        // 在输入框/文本域/可编辑元素内时, 退格/删除只用于编辑文本, 不删图元 (修复: 输入框退格误删节点)
        // 优先删除选中的边，再删除选中的节点
        // 注: ReactFlow v11 的连线 <g> 元素没有 data-id 属性, 直接读 DOM 取不到 id。
        //     改为从 store 读取已标记 selected 的连线 (onEdgesChange 已写入 selected 字段)。
        const selEdge = useCanvas.getState().edges.find((ed) => ed.selected);
        if (selEdge) {
          e.preventDefault();
          removeEdge(selEdge.id);
          return;
        }
        // 多选状态：一次性删除所有选中节点（合并为单条撤销项，与工具条"删除"行为一致）
        const selIds = useCanvas.getState().selectedIds;
        if (selIds.length > 1) {
          e.preventDefault();
          useCanvas.getState().removeNodes(selIds);
          return;
        }
        // 单选状态：删除当前选中节点
        if (sel) {
          e.preventDefault();
          // 先检查节点是否存在于 nodes 中，避免删除已不存在的节点
          const nodes = useCanvas.getState().nodes;
          if (nodes.some((n) => n.id === sel)) {
            removeNode(sel);
          }
          return;
        }
      }
      if (e.key === 'Escape' && sel) {
        e.preventDefault();
        clearSelection();
        return;
      }
      if (editing) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
        copySelected();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
        pasteNode();
      } else if (e.key.toLowerCase() === 'f') {
        fitView();
      }
    };
    // 使用 capture 阶段确保尽早捕获 Delete 键，防止被其他组件拦截
    window.addEventListener('keydown', onKey, { capture: true });
    return () => window.removeEventListener('keydown', onKey, { capture: true });
  }, [removeNode, removeEdge, copySelected, pasteNode, fitView, saveNow, clearSelection]);

  const onNodeCtx = (e: React.MouseEvent, node: Node) => {
    e.preventDefault();
    // 若刚发生了右键拖拽平移，抑制随之触发的节点菜单（保留纯右键单击的菜单）
    if (suppressCtxRef.current) {
      suppressCtxRef.current = false;
      return;
    }
    setMenu({ x: e.clientX, y: e.clientY, nodeId: node.id });
  };
  const onPaneCtx = (e: React.MouseEvent) => {
    e.preventDefault();
    // 若刚发生了右键拖拽平移，则抑制随之触发的画布菜单（保留纯右键单击的菜单）
    if (suppressCtxRef.current) {
      suppressCtxRef.current = false;
      return;
    }
    setMenu({ x: e.clientX, y: e.clientY, nodeId: null });
  };

  // —— 右键拖拽平移画布（与左键框选、右键菜单互不冲突）——
  const isCanvasBackground = (t: EventTarget | null): boolean => {
    const el = t as HTMLElement | null;
    if (!el || !el.closest) return false;
    // 命中节点/手柄/各类浮层控件时不启动平移，留给各自的交互
    return !el.closest(
      '.react-flow__node, .react-flow__handle, .pea-canvas-controls, .pea-toolbar, .pea-canvas-header, .pea-canvas-actions, .pea-canvas-bottom-prompt, .pea-add-menu, .pea-edge-menu, .pea-canvas-dropdown, .fixed.inset-0',
    );
  };

  const onFlowPointerDown = (e: React.PointerEvent) => {
    // 右键拖拽平移已迁移至 window 捕获阶段监听（覆盖节点/浮层，见下方 right-drag pan effect），
    // 此处仅处理左键在空白画布的框选。
    if (e.button === 0 && isCanvasBackground(e.target)) {
      // 左键在空白画布按下并拖拽 = 框选：标记进行中，抑制经过节点的 hover 手柄/弹框
      selectingRef.current = true;
      setSelecting(true);
    }
  };

  const onFlowPointerMove = (_e: React.PointerEvent) => {
    // 平移逻辑已迁移至 window 级监听（见下方 right-drag pan effect），此处不再处理。
  };

  const onFlowPointerUp = (_e: React.PointerEvent) => {
    // 框选结束：延迟一帧关闭标记，避免与框选提交的选中态竞争导致手柄/弹框瞬时闪现。
    if (selectingRef.current) {
      selectingRef.current = false;
      window.setTimeout(() => setSelecting(false), 0);
    }
  };

  // 以光标为锚点缩放画布（用于落在 portal/浮层上的 Ctrl+滚轮，ReactFlow 收不到该事件）。
  const zoomCanvasAtPointer = useCallback(
    (clientX: number, clientY: number, deltaY: number) => {
      const container = flowRef.current;
      if (!container) return;
      const vp = getViewport();
      const rect = container.getBoundingClientRect();
      const px = clientX - rect.left;
      const py = clientY - rect.top;
      const minZoom = 0.25;
      const maxZoom = 3;
      // 与 ReactFlow d3-zoom 一致的缩放曲线：上滚(deltaY<0)放大，下滚缩小。
      const factor = Math.pow(2, -deltaY * 0.0015);
      const next = Math.min(maxZoom, Math.max(minZoom, vp.zoom * factor));
      // 保持光标下的画布坐标不变：flow = (p - translate) / zoom
      const fx = (px - vp.x) / vp.zoom;
      const fy = (py - vp.y) / vp.zoom;
      setViewport({ x: px - fx * next, y: py - fy * next, zoom: next }, { duration: 0 });
    },
    [getViewport, setViewport],
  );

  // 修复：Ctrl/⌘ + 滚轮会触发浏览器整页缩放，而非画布缩放。
  // 根因：原 guard 只挂在 flowRef（画布容器内）。但节点编辑框浮层、antd Select 下拉、
  // 节点参数弹层等会被 createPortal 渲染到 document.body，不在 flowRef 子树内，
  // 其 wheel 事件冒泡不到 flowRef → 不被 preventDefault → 浏览器执行整页缩放。
  // 修复：改为在 window 捕获阶段 + 非 passive 监听 wheel：
  //  - 命中 Ctrl/⌘ 且目标处于画布范围内（.pea-canvas-host 或其 portal 后代）时，
  //    preventDefault() 拦截浏览器整页缩放；
  //  - 目标若在 ReactFlow 的 pane 子树内（含节点内联编辑框）→ 交给 ReactFlow 自身缩放，
  //    不重复缩放；否则（落在 portal/浮层上）以光标为锚点手动驱动画布缩放，
  //    满足"只要在画布中，Ctrl+滚轮只控制画布缩放"。
  //  - 普通滚轮（无 Ctrl）不拦截，保留 panOnScroll 的画布平移手势。
  //  - 裁切模式（cropActiveRef）下：完全阻止所有 wheel，锁定画布。
  useEffect(() => {
    const onWheelCapture = (e: WheelEvent) => {
      if (cropActiveRef.current) {
        e.stopPropagation();
        e.preventDefault();
        return;
      }
      if (!(e.ctrlKey || e.metaKey)) return;
      const t = e.target as HTMLElement | null;
      if (!t || !t.closest) return;
      const inCanvas =
        !!t.closest('.pea-canvas-host') ||
        !!t.closest('[data-pea-canvas-portal]') ||
        !!t.closest('.pea-canvas-portal');
      if (!inCanvas) return;
      // 拦截浏览器整页缩放（关键：必须在捕获阶段 + 非 passive 才能生效）
      e.preventDefault();
      // 区分「空白画布区」与「节点/浮层」：
      //  - 命中 pane/viewport/renderer 且【不在节点内】→ ReactFlow 自身已接管缩放，直接放行避免重复；
      //  - 命中节点内部或 portal 浮层 → ReactFlow 不会对该目标缩放，拦截并手动以光标为锚点缩放。
      const inNode = !!t.closest('.react-flow__node');
      const inPaneArea =
        !!t.closest('.react-flow__pane') ||
        !!t.closest('.react-flow__viewport') ||
        !!t.closest('.react-flow__renderer');
      if (inPaneArea && !inNode) return; // 空白画布区：交给 ReactFlow 自身缩放
      // 节点内或浮层：阻止冒泡（避免 ReactFlow 重复缩放），手动以光标为锚点缩放画布
      e.stopPropagation();
      zoomCanvasAtPointer(e.clientX, e.clientY, e.deltaY);
    };
    window.addEventListener('wheel', onWheelCapture, { capture: true, passive: false });
    return () => window.removeEventListener('wheel', onWheelCapture, true);
  }, [zoomCanvasAtPointer]);

  // 右键拖拽平移画布（覆盖节点/功能条/浮层，不依赖 ReactFlow 的 panOnDrag）。
  // 用 window 捕获阶段监听：节点内部会 stopPropagation 阻止事件冒泡到 flowRef，
  // 捕获阶段可在其之前截获，从而保证「在画布任意位置（含节点上）右键拖拽都能平移」。
  // 纯右键单击（未拖动）仍触发节点/画布右键菜单；拖动超过阈值则抑制随之而来的菜单。
  useEffect(() => {
    const EXCLUDE = 'input, textarea, [contenteditable="true"], .ant-dropdown, .pea-ctx-menu, .pea-canvas-controls, .pea-canvas-header, .pea-canvas-actions, .pea-canvas-bottom-prompt, .pea-add-menu, .pea-edge-menu, .pea-canvas-dropdown, .react-flow__minimap, .react-flow__controls, .react-flow__panel';
    const onDown = (e: PointerEvent) => {
      if (e.button !== 2) return; // 仅右键
      const t = e.target as HTMLElement | null;
      if (!t || !t.closest) return;
      if (!t.closest('.pea-canvas-host')) return; // 必须在画布范围内
      // 排除需要自身右键交互的控件（菜单/输入框/画布工具等），这些保持原生行为
      if (t.closest(EXCLUDE)) return;
      // 注意： deliberately 不排除 .react-flow__node —— 节点上也允许右键拖拽平移
      suppressCtxRef.current = false; // 每次右键交互重置抑制标记
      const vp = getViewport();
      panRef.current = {
        active: true,
        moved: false,
        startX: e.clientX,
        startY: e.clientY,
        vx: vp.x,
        vy: vp.y,
      };
      e.preventDefault(); // 阻止原生文本选择/图片拖拽，不影响随后的 contextmenu
    };
    const onMove = (e: PointerEvent) => {
      const p = panRef.current;
      if (!p || !p.active) return;
      const dx = e.clientX - p.startX;
      const dy = e.clientY - p.startY;
      if (!p.moved) {
        if (Math.hypot(dx, dy) < 4) return; // 拖动阈值：区分"单击"与"拖拽"
        p.moved = true;
        flowRef.current?.classList.add('pea-panning');
      }
      // 视口 translate 为屏幕像素，平移量 = 指针位移（与 ReactFlow 平移一致）
      setViewport({ x: p.vx + dx, y: p.vy + dy, zoom: getViewport().zoom }, { duration: 0 });
    };
    const onUp = () => {
      const p = panRef.current;
      if (p && p.active) {
        if (p.moved) {
          suppressCtxRef.current = true; // 拖动过 → 抑制随之触发的右键菜单
          flowRef.current?.classList.remove('pea-panning');
        }
        panRef.current = null;
      }
    };
    window.addEventListener('pointerdown', onDown, true); // 捕获阶段：早于节点 stopPropagation
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointerdown', onDown, true);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [getViewport, setViewport]);

  return (
    <div
      className={`pea-canvas-host${materialOpen ? ' pea-material-open' : ''}`}
      onContextMenu={(e) => e.preventDefault()}
      onDoubleClick={(e) => {
        const t = e.target as HTMLElement;
        const onPane =
          t.classList.contains('react-flow__pane') ||
          t.classList.contains('react-flow__viewport') ||
          t.classList.contains('react-flow__renderer');
        if (onPane) { setLibAt({ x: e.clientX, y: e.clientY }); setSpawnAt({ x: e.clientX, y: e.clientY }); }
      }}
    >
      <CanvasHeader
        onClose={async () => {
          await flushSave();
          useUi.getState().setActive('workspace');
        }}
      />
      <CanvasActions />
      <BottomPrompt />

      <LeftToolbar
        onAdd={() => { setLibAt({ x: (window.innerWidth - 300) / 2, y: window.innerHeight / 2 - 220 }); setSpawnAt(null); }}
        onSearch={() => setSearchOpen((s) => !s)}
        onFiles={() => setMaterialOpen((s) => !s)}
        onComments={() => toast.info('评论功能即将开放')}
        onHistory={() => toast.info('历史记录功能即将开放')}
        onLibrary={() => { setLibAt({ x: (window.innerWidth - 300) / 2, y: window.innerHeight / 2 - 220 }); setSpawnAt(null); }}
        onAvatar={() => {
          const av = document.querySelector<HTMLElement>('.pea-user-trigger');
          av?.click();
        }}
        libraryOpen={!!libAt}
        searchOpen={searchOpen}
        filesOpen={materialOpen}
      />

      {canvasId == null && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 text-center text-pea-text-secondary">
          <div className="text-5xl opacity-40">🎨</div>
          <div className="text-base font-medium text-pea-text">还没有打开画布</div>
          <div className="text-sm">在「工作空间」中新建或打开一个项目，即可进入画布。</div>
        </div>
      )}

      {sideOpen && <SidePanel onClose={() => setSideOpen(false)} />}
      {searchOpen && <SearchPopover onClose={() => setSearchOpen(false)} />}
      {materialOpen && <MaterialPanel onClose={() => setMaterialOpen(false)} />}
      {libAt && (
        <NodeLibrary
          at={libAt}
          onPick={(k) => add(k, NODE_DEF_OF(k).label)}
          onClose={() => { setLibAt(null); setSpawnAt(null); }}
        />
      )}
      {edgeMenu && (
        <EdgeNodeMenu
          at={{ x: edgeMenu.x, y: edgeMenu.y }}
          onPick={(k) => addConnectedAt(k, edgeMenu.sourceId, edgeMenu.spawn, edgeMenu.handleType)}
          onClose={() => setEdgeMenu(null)}
        />
      )}

      <div
        ref={flowRef}
        className={`pea-canvas-flow${selecting ? ' pea-selecting' : ''}${isMultiSelect ? ' pea-multi-select' : ''}`}
        onPointerDown={onFlowPointerDown}
        onPointerMove={onFlowPointerMove}
        onPointerUp={onFlowPointerUp}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultEdgeOptions={{ type: 'pea' }}
          connectionMode={ConnectionMode.Loose}
          connectionRadius={40}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={(conn: Connection) => {
            const pending = pendingEdge.current;
            pendingEdge.current = null;
            if (!pending?.source) return;
            if (!conn.source || !conn.target || conn.source === conn.target) return;
            // 关键修复：连线方向只由「起拉手柄类型」决定，与几何位置/落点命中哪个手柄无关。
            // 落点节点 = conn 中不是起拉节点的那个端点（ReactFlow 在 onConnect 里已填好两端 id）。
            const dropNode = conn.source === pending.source ? conn.target : conn.source;
            const edge = resolveConnection(pending, dropNode);
            const tNode = useCanvas.getState().nodes.find((n) => n.id === edge.target);
            // 用户上传的素材节点没有 target handle，不接受连线入边。
            // 统一走 lib/nodeSemantics.acceptsUpstreamInput（此前只判 kind==='image'，
            // 视频/音频上传节点虽隐藏 handle 仍能被 Loose 模式连上，是真实缺陷）。
            if (tNode && !acceptsUpstreamInput(tNode.data)) return;
            connectedThisDrag.current = true;
            onConnect(edge);
          }}
          // 【修复】onInit：ReactFlow 内部 d3-zoom 实例就绪后触发。
          // 此处是恢复视口的最佳时机——比 RAF 更可靠（保证实例已完全初始化）。
          // 若 RAF 阶段已成功恢复（vpRestored=true），跳过；否则用实例 API 直接设置视口。
          onInit={(instance: any) => {
            rfInstanceRef.current = instance;
            const pending = pendingVpRef.current;
            if (pending && !vpRestored.current) {
              try {
                instance.setViewport({ x: pending.x, y: pending.y, zoom: pending.zoom }, { duration: 0 });
                vpRestored.current = true;
                lastVpRef.current = pending;
              } catch {
                setViewport({ x: pending.x, y: pending.y, zoom: pending.zoom }, { duration: 0 });
                vpRestored.current = true;
              }
            }
          }}
          onConnectStart={(_evt: any, params: any) => {
            const me = _evt as MouseEvent | undefined;
            startPosRef.current = me ? { x: me.clientX, y: me.clientY } : null;
            pendingEdge.current = { source: params.nodeId ?? null, handleId: params.handleId ?? null, handleType: params.handleType ?? 'source' };
            connectedThisDrag.current = false;
          }}
          onConnectEnd={(evt: any) => {
            const e = evt as MouseEvent;
            const tgt = e.target as HTMLElement;
            const nodeEl = tgt.closest('.react-flow__node') as HTMLElement | null;
            const targetId = nodeEl ? nodeEl.getAttribute('data-id') : null;
            const onPane =
              tgt.classList.contains('react-flow__pane') ||
              tgt.classList.contains('react-flow__renderer') ||
              tgt.classList.contains('react-flow__viewport');

            const pending = pendingEdge.current;
            pendingEdge.current = null;

            // 已由 onConnect 建边 → 不重复处理。
            if (connectedThisDrag.current) {
              connectedThisDrag.current = false;
              return;
            }

            const ht: 'source' | 'target' = pending?.handleType === 'target' ? 'target' : 'source';
            // 位移判定：按下即松开、几乎未移动 = 单击；否则视为拖拽连线。
            const moved = startPosRef.current
              ? Math.hypot(e.clientX - startPosRef.current.x, e.clientY - startPosRef.current.y)
              : 999;
            const releasedOnOtherNode = !!targetId && targetId !== pending?.source;

            // 单击连接点（鼠标放在连接点上，或连接点跟随鼠标时点在圆点上）→ 弹出"新建并连接"菜单。
            // 手柄命中区随视觉一起移动，故两种场景都能命中。新节点按连线方向偏移出原节点外侧，避免压住原节点。
            if (pending?.source && !releasedOnOtherNode && moved < 6) {
              const dir = ht === 'target' ? -1 : 1;
              setEdgeMenu({
                x: e.clientX,
                y: e.clientY,
                sourceId: pending.source,
                handleType: ht,
                spawn: { x: e.clientX + dir * 280, y: e.clientY },
              });
              return;
            }

            // 兜底：onConnect 未触发（鼠标释放在其它节点本体，但不在任何手柄 connectionRadius 内），
            // 仍按统一规则建边。方向与 onConnect 完全一致——只由「起拉手柄类型」决定，与几何无关。
            if (releasedOnOtherNode && pending?.source) {
              const edge = resolveConnection(pending, targetId as string);
              const tNode = useCanvas.getState().nodes.find((n) => n.id === edge.target);
              // 同 onConnect：所有类型的上传素材节点都拒绝入边（不止图片）。
              if (!tNode || acceptsUpstreamInput(tNode.data)) {
                onConnect(edge);
              }
              return;
            }
            // 拖拽连线释放到空白 → 弹出"新建并连接"菜单（落点为新节点位置）
            if (pending?.source && onPane) {
              setEdgeMenu({
                x: e.clientX,
                y: e.clientY,
                sourceId: pending.source,
                handleType: ht,
                spawn: { x: e.clientX, y: e.clientY },
              });
            }
          }}
          onNodeClick={(e, n) => {
            // 仅在真实拖动（位移>4px）时抑制随后的 click；纯单击正常选中+弹框
            if (downPosRef.current) {
              const dx = e.clientX - downPosRef.current.x;
              const dy = e.clientY - downPosRef.current.y;
              if (Math.hypot(dx, dy) > 4) {
                downPosRef.current = null;
                return;
              }
            }
            // Shift+点击 多选交给 ReactFlow（multiSelectionKeyCode="Shift"）处理：
            // 若这里再调 toggleSelect，会与 ReactFlow 自身发出的 select change 在
            // onNodesChange 的 hasSelectChanges 分支互相覆盖，导致 selectedIds=[]。
            // 所以 Shift 时直接放行，让 ReactFlow 负责多选取并同步到 selectedIds。
            if (e.shiftKey) return;
            select(n.id);
          }}
          onNodeDragStart={(e) => {
            // 记录按下坐标（用于区分单击/拖动）；用原生事件坐标。
            // 注意：拖拽前快照改在 store.onNodesChange 的「首次 dragging 位移」处记录，
            // 因为 onNodeDragStart 在 mousedown 即触发（纯点击也会触发），
            // 放这里会为每次点击产生一条无意义的撤销项。
            const me = e as unknown as MouseEvent;
            downPosRef.current = { x: me.clientX, y: me.clientY };
          }}
          onNodeDragStop={(_e, node) => {
            // 拖完一个节点：依据节点最终画布坐标中心判定它应当进入/离开哪个组。
            // - 当前无 parentNode 且中心点位于某组视觉边界内 → 入组（自动改 parentNode + 坐标转相对 + 扩组）
            // - 已有 parentNode 且中心点已落到父组边界外 → 离组（坐标转绝对 + 缩组）
            try {
              const result = useCanvas.getState().moveNodeToGroup(node.id);
              // 调试日志（仅 DEV / devhooks 开启），E2E 也通过此分支
              if (result && (import.meta.env.DEV || localStorage.getItem('__peaDevHooks') === '1')) {
                const w = window as any;
                w.__lastGroupMove = { nodeId: node.id, action: result, ts: Date.now() };
              }
            } catch (e) {
              /* noop */
            }
          }}
          onPaneClick={() => {
            clearSelection();
            setMenu(null);
          }}
          onNodeContextMenu={onNodeCtx}
          onPaneContextMenu={onPaneCtx}
          // 实时把画布缩放倒数(1/zoom)写入 --pea-inv-zoom，供节点上的编辑框/功能条/标识
          // 做 counter-scale（恒定屏幕大小）。用 onMove 直接拿到实时 viewport，不依赖 useViewport 的上下文，最稳妥。
          onMove={(_e: any, vp: any) => {
            if (vp && typeof vp.zoom === 'number') {
              document.documentElement.style.setProperty('--pea-inv-zoom', String(1 / vp.zoom));
            }
            // 视口持久化：平移/缩放后节流写入 localStorage（~16ms/帧），退出画布可原样恢复。
            if (vp && canvasId != null && typeof vp.x === 'number' && typeof vp.y === 'number' && typeof vp.zoom === 'number') {
              const v = { x: vp.x, y: vp.y, zoom: vp.zoom };
              lastVpRef.current = v;
              saveViewportThrottled(vpKey(canvasId), v);
            }
          }}
          zoomOnDoubleClick={false}
          // Figma 风格：滚轮平移，拖拽=框选，Space+拖拽=平移
          panOnDrag={false}
          panOnScroll
          selectionOnDrag
          selectionMode={SelectionMode.Partial}
          // 多选键：Shift+点击 节点 = 加入/移出多选集合（交给 ReactFlow 处理，
          // onNodeClick 在 shiftKey 时放行，不再调 toggleSelect，避免与 ReactFlow
          // 的 select change 在 onNodesChange 中互相覆盖）。框选仍走 selectionOnDrag。
          multiSelectionKeyCode="Shift"
          selectionKeyCode={null}
          // 禁用键盘删除：退格/Delete 只用于编辑输入框文本（如节点聊天输入框），
          // 不再误删选中的节点。节点删除统一走右键菜单 -> 删除。
          deleteKeyCode={null}
          defaultViewport={initialVp ?? { x: 0, y: 0, zoom: 1 }}
          minZoom={0.25}
          maxZoom={3}
          proOptions={{ hideAttribution: true }}
        >
          {showGrid && (
            <Background
              variant={BackgroundVariant.Dots}
              gap={22}
              size={1.2}
              color="var(--pea-edge-idle)"
            />
          )}
          {showMinimap && (
            <MiniMap
              nodeStrokeWidth={3}
              zoomable
              pannable
              position="top-left"
              style={{ top: 78, left: 68 }}
              nodeComponent={MiniMapNode}
              nodeColor={minimapNodeColor}
              onNodeClick={focusNodeFromMinimap}
            />
          )}
          <CanvasControls
            showMinimap={showMinimap}
            setShowMinimap={setShowMinimap}
            showGrid={showGrid}
            setShowGrid={setShowGrid}
          />
        </ReactFlow>
      </div>

      <ZoomVarSync />
      <NodeChatPrompt />
      <MultiSelectToolbar />
      <SelectionBoundsBox />

      {menu && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setMenu(null)} />
          <div
            className="fixed z-50 min-w-[140px] rounded-lg border border-black/10 bg-white py-1 text-sm shadow-xl dark:border-white/10 dark:bg-[#1c1c24]"
            style={{ left: menu.x, top: menu.y }}
          >
            {menu.nodeId ? (
              <>
                <button
                  className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10"
                  onClick={() => {
                    duplicateNode(menu.nodeId!);
                    setMenu(null);
                  }}
                >
                  📋 复制节点
                </button>
                <button
                  className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10"
                  onClick={() => {
                    addConnected(menu.nodeId!);
                    setMenu(null);
                  }}
                >
                  ➕ 添加并连接
                </button>
                <button
                  className="block w-full px-3 py-1.5 text-left text-red-500 hover:bg-red-500/10"
                  onClick={() => {
                    removeNode(menu.nodeId!);
                    setMenu(null);
                  }}
                >
                  🗑 删除节点
                </button>
              </>
            ) : (
              <>
                <button
                  className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10"
                  onClick={() => {
                    setLibAt({ x: window.innerWidth / 2 - 150, y: window.innerHeight / 2 - 200 }); setSpawnAt(null);
                    setMenu(null);
                  }}
                >
                  打开节点库
                </button>
                <button
                  className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10"
                  onClick={() => {
                    fitView();
                    setMenu(null);
                  }}
                >
                  适配视图
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function CanvasEditor() {
  // 画布 Antd 主题跟随创作设计：Runway=暗，Figma=亮（与各自 surface 一致）。
  const creatorDesign = useCreatorDesign((s) => s.design);
  const canvasDark = creatorDesign === 'runway';
  const canvasTokens = canvasDark
    ? {
        colorPrimary: '#f5f5f5', // 暗态主操作：浅药丸 + 深字（可见）
        colorInfo: '#a78bfa', // AI 紫（暗态提亮保证对比）
        colorText: '#f5f5f5',
        colorTextSecondary: '#a7a7a7',
        colorBgContainer: '#0a0a0a',
        colorBgElevated: '#1a1a1a',
        colorBorder: '#27272a',
        colorBorderSecondary: '#27272a',
      }
    : {
        colorPrimary: '#000000', // 亮态：黑药丸 + 白字
        colorInfo: '#8b5cf6',
        colorText: '#000000',
        colorTextSecondary: '#4d4d4d',
        colorBgContainer: '#ffffff',
        colorBgElevated: '#ffffff',
        colorBorder: '#e6e6e6',
        colorBorderSecondary: '#e6e6e6',
      };
  return (
    <ConfigProvider
      theme={{
        algorithm: canvasDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          ...canvasTokens,
          borderRadius: 6,
          fontFamily:
            "'Inter', 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Noto Sans CJK SC', sans-serif",
        },
      }}
    >
      <ReactFlowProvider>
        <CanvasErrorBoundary>
          <Flow />
          <SelectionOverlay />
        </CanvasErrorBoundary>
      </ReactFlowProvider>
    </ConfigProvider>
  );
}