import { useEffect, useRef, useState, useCallback } from 'react';
import ReactFlow, {
  Background,
  BackgroundVariant,
  ReactFlowProvider,
  useReactFlow,
  type Node,
  type Edge,
  Connection,
  ConnectionMode,
  MiniMap,
  SelectionMode,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { App, Input, Modal, Select, Tooltip } from 'antd';
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
} from '@ant-design/icons';
import { toast } from '../store/toast';
import { api } from '../api/client';
import { useCanvas, PeaNodeData } from '../store/canvas';
import { useUi } from '../store/ui';
import { useAuth } from '../store/auth';
import { useTheme } from '../store/theme';
import { canvasesApi } from '../api/canvases';
import PeaNode from './PeaNode';
import PeaEdge from './PeaEdge';
import SidePanel from './SidePanel';
import NodeChatPrompt from './NodeChatPrompt';
import TextNodeToolbar from './TextNodeToolbar';
import {
  NODE_DEF_OF,
  PeaNodeKind,
} from '../constants/nodeTypes';

const nodeTypes = { pea: PeaNode };
const edgeTypes = { pea: PeaEdge };

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

/** 画布左上角：pea logo + 画布标题 + 上次修改时间（点击展开下拉）。 */
function CanvasHeader({
  onClose,
}: {
  onClose: () => void;
}) {
  const title = useCanvas((s) => s.title);
  const lastSavedAt = useCanvas((s) => s.lastSavedAt);
  const canvasId = useCanvas((s) => s.canvasId);
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

  return (
    <div ref={wrapRef} className="pea-canvas-header">
      <button
        type="button"
        className="pea-canvas-header-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`画布：${title}`}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="h-7 w-7 shrink-0 rounded-lg bg-gradient-to-br from-pea-purple via-pea-brand to-pea-lime shadow-sm" />
        <div className="min-w-0 text-left">
          <div className="truncate text-sm font-semibold leading-tight">{title || '未命名画布'}</div>
          <div className="truncate text-[11px] text-pea-text-muted leading-tight">
            上次修改于 {relTime(lastSavedAt)}
          </div>
        </div>
        <span className={`pea-canvas-caret ${open ? 'open' : ''}`} aria-hidden>
          ▾
        </span>
      </button>

      {open && (
        <div role="menu" className="pea-canvas-dropdown">
          <div className="pea-canvas-dropdown-head">
            <div className="h-7 w-7 shrink-0 rounded-lg bg-gradient-to-br from-pea-purple via-pea-brand to-pea-lime shadow-sm" />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{title || '未命名画布'}</div>
              <div className="truncate text-[11px] text-pea-text-muted">
                上次修改于 {relTime(lastSavedAt)}
              </div>
            </div>
          </div>
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

/** 画布右上角：Tapies 余额 + 社区 + 分享 */
function CanvasActions() {
  const balance = useAuth((s) => s.balance);
  const setBalance = useAuth((s) => s.setBalance);
  const { mode, setMode } = useTheme();
  const [shareBusy, setShareBusy] = useState(false);
  const { message } = App.useApp();

  const refreshBalance = async () => {
    try {
      const r = await api.get('/billing/balance');
      setBalance(r.data.balance);
    } catch {
      /* ignore */
    }
  };

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
      <Select
        className="pea-theme-select"
        value={mode}
        onChange={(v) => setMode(v)}
        suffixIcon={<span className="text-xs">▾</span>}
        options={[
          { label: '浅色', value: 'light' },
          { label: '深色', value: 'dark' },
          { label: '跟随系统', value: 'system' },
        ]}
      />
      <Tooltip title="账户余额 (Tapies)">
        <button
          type="button"
          className="pea-canvas-tapies"
          aria-label={`Tapies 余额 ${balance}`}
          onClick={refreshBalance}
        >
          <WalletOutlined />
          <span>{balance}</span>
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
    | { group: '添加节点'; kind: PeaNodeKind; icon: string; label: string; sub?: string; dot?: boolean; tag?: string }
    | { group: '辅助工具'; kind: PeaNodeKind; icon: string; label: string; sub?: string; tag?: string }
    | { group: '添加资源'; action: 'upload'; icon: string; label: string }
  > = [
    { group: '添加节点', kind: 'text', icon: '≡', label: '文本' },
    { group: '添加节点', kind: 'image', icon: '🖼', label: '图片', sub: '宣传图、海报、封面' },
    { group: '添加节点', kind: 'video', icon: '▷', label: '视频' },
    { group: '添加节点', kind: 'audio', icon: '♫', label: '音频', dot: true },
    { group: '添加节点', kind: 'world3d', icon: '🌐', label: '3D 世界', tag: 'Beta' },
    { group: '辅助工具', kind: 'playlist', icon: '▦', label: '播放列表', tag: 'Beta' },
    { group: '添加资源', action: 'upload', icon: '↑', label: '上传' },
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
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M4 6h16M4 12h10M4 18h7" />
        </svg>
      ),
    },
    {
      kind: 'image',
      label: '图片生成',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <circle cx="8.5" cy="9.5" r="1.5" />
          <path d="M3 16l5-5 4 4 3-3 6 6" />
        </svg>
      ),
    },
    {
      kind: 'video',
      label: '视频生成',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="M10 9l5 3-5 3z" fill="currentColor" stroke="none" />
        </svg>
      ),
    },
    {
      kind: 'audio',
      label: '音频',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M3 10v4" />
          <path d="M7 7v10" />
          <path d="M11 4v16" />
          <path d="M15 8v8" />
          <path d="M19 10v4" />
        </svg>
      ),
    },
    {
      kind: 'world3d',
      label: '3D 世界',
      tag: 'Beta',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M2 12h20" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
      ),
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

/** 画布左侧工具栏（对齐 pea-canvas-v12 .toolbar-left） */
function LeftToolbar({
  onAdd,
  onSearch,
  onFiles,
  onComments,
  onHistory,
  onLibrary,
  onAvatar,
}: {
  onAdd: () => void;
  onSearch: () => void;
  onFiles: () => void;
  onComments: () => void;
  onHistory: () => void;
  onLibrary: () => void;
  onAvatar: () => void;
}) {
  return (
    <aside className="pea-toolbar" aria-label="画布工具栏">
      <TooltipLite title="添加节点（双击画布也可打开）" onClick={onAdd}>
        <span aria-hidden>➕</span>
        <span className="pea-tlb-dot" />
      </TooltipLite>
      <TooltipLite title="搜索" onClick={onSearch}>
        <span aria-hidden>🔍</span>
      </TooltipLite>
      <TooltipLite title="文件" onClick={onFiles}>
        <span aria-hidden>📁</span>
        <span className="pea-tlb-dot" />
      </TooltipLite>
      <TooltipLite title="节点库" onClick={onLibrary}>
        <span aria-hidden>⊞</span>
      </TooltipLite>
      <TooltipLite title="评论" onClick={onComments}>
        <span aria-hidden>💬</span>
      </TooltipLite>
      <TooltipLite title="历史记录" onClick={onHistory}>
        <span aria-hidden>🕐</span>
      </TooltipLite>
      <div className="pea-toolbar-bottom">
        <button
          className="pea-tlb-avatar"
          title="账户"
          aria-label="打开账户菜单"
          onClick={onAvatar}
        >
          W
        </button>
      </div>
    </aside>
  );
}

function TooltipLite({
  title,
  onClick,
  children,
}: {
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button className="pea-tlb-btn" title={title} aria-label={title} onClick={onClick}>
      {children}
    </button>
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
    setViewport({ ...vp, zoom: next }, { duration: 0 });
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
            '快捷键：Ctrl+S 保存 / Delete 删除 / Esc 取消选中 / 双击空白添加节点 / Shift+拖拽框选',
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

function Flow() {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    select,
    toggleSelect,
    setSelection,
    clearSelection,
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
  const { screenToFlowPosition, fitView } = useReactFlow();
  const { message } = App.useApp();
  const saveTimer = useRef<number>();
  const [sideOpen, setSideOpen] = useState(false);
  const [libAt, setLibAt] = useState<{ x: number; y: number } | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [edgeMenu, setEdgeMenu] = useState<{ x: number; y: number; sourceId: string } | null>(null);
  const [showMinimap, setShowMinimap] = useState(false);
  const [showGrid, setShowGrid] = useState(true);
  const pendingEdge = useRef<{ source: string; handleId: string | null } | null>(null);
  // 拖动 vs 单击判定：在 ReactFlow 的 onNodeDragStart 处记录按下坐标
  // （此处不受节点内部 stopPropagation 影响），onNodeClick 时比较位移。
  const downPosRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    // 进入画布必须经由「新建项目」或「打开项目」显式创建/加载，
    // 这里不再自动创建画布，避免每次加载都产生游离画布。
    // canvasId 为 null 时由下方空状态提示用户。
  }, [canvasId]);

  useEffect(() => {
    if (!dirty || canvasId == null) return;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(async () => {
      try {
        const graph = { nodes, edges };
        const { data } = await api.put(`/canvases/${canvasId}`, { graph_json: graph, version });
        markSaved(data.version);
      } catch (e: any) {
        if (e?.response?.status === 409) {
          message.warning('画布已被他人更新，请刷新');
        } else {
          message.error('保存失败');
        }
      }
    }, 1000);
    return () => window.clearTimeout(saveTimer.current);
  }, [nodes, edges, dirty, canvasId, version, markSaved]);

  const didFit = useRef(false);
  useEffect(() => {
    if (didFit.current || nodes.length === 0) return;
    didFit.current = true;
    const t = window.setTimeout(() => fitView({ duration: 0, padding: 0.2, maxZoom: 1 }), 100);
    return () => window.clearTimeout(t);
  }, [nodes.length, fitView]);

  const saveNow = async () => {
    if (canvasId == null) return;
    try {
      const { data } = await api.put(`/canvases/${canvasId}`, { graph_json: { nodes, edges }, version });
      markSaved(data.version);
      message.success('已保存');
    } catch {
      message.error('保存失败');
    }
  };

  const add = (kind: PeaNodeKind, label: string, opts?: { prompt?: string }) => {
    const anchor = libAt ?? { x: window.innerWidth / 2, y: window.innerHeight / 2 };
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
    addNode({ kind, label, prompt: opts?.prompt, meta: { error: false } } as PeaNodeData, pos);
  };

  const addConnectedAt = (kind: PeaNodeKind, sourceId: string, screenPos: { x: number; y: number }) => {
    const pos = screenToFlowPosition({ x: screenPos.x, y: screenPos.y });
    const label = kind === 'text' ? '文本生成' : kind === 'image' ? '图片生成' : kind === 'video' ? '视频生成' : kind === 'audio' ? '音频' : '3D 世界';
    const newId = addNode({ kind, label, meta: { error: false } } as PeaNodeData, pos);
    if (newId) {
      onConnect({ source: sourceId, target: newId, sourceHandle: null, targetHandle: null });
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
      if (e.key === 'Delete' || e.key === 'Backspace') {
        // 优先删除选中的边，再删除选中的节点
        const selEdge = document.querySelector('.react-flow__edge.selected');
        if (selEdge) {
          e.preventDefault();
          const edgeId = selEdge.getAttribute('data-id');
          if (edgeId) removeEdge(edgeId);
          return;
        }
        if (sel) {
          e.preventDefault();
          removeNode(sel);
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
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [removeNode, removeEdge, copySelected, pasteNode, fitView, saveNow, clearSelection]);

  const onNodeCtx = (e: React.MouseEvent, node: Node) => {
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, nodeId: node.id });
  };
  const onPaneCtx = (e: React.MouseEvent) => {
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, nodeId: null });
  };

  return (
    <div
      className="pea-canvas-host"
      onContextMenu={(e) => e.preventDefault()}
      onDoubleClick={(e) => {
        const t = e.target as HTMLElement;
        const onPane =
          t.classList.contains('react-flow__pane') ||
          t.classList.contains('react-flow__viewport') ||
          t.classList.contains('react-flow__renderer');
        if (onPane) setLibAt({ x: e.clientX, y: e.clientY });
      }}
    >
      <CanvasHeader onClose={() => useUi.getState().setActive('workspace')} />
      <CanvasActions />
      <BottomPrompt />

      <LeftToolbar
        onAdd={() => setLibAt({ x: (window.innerWidth - 300) / 2, y: window.innerHeight / 2 - 220 })}
        onSearch={() => setSideOpen(true)}
        onFiles={() => setSideOpen(true)}
        onComments={() => toast.info('评论功能即将开放')}
        onHistory={() => toast.info('历史记录功能即将开放')}
        onLibrary={() => setLibAt({ x: (window.innerWidth - 300) / 2, y: window.innerHeight / 2 - 220 })}
        onAvatar={() => {
          const av = document.querySelector<HTMLElement>('.pea-user-trigger');
          av?.click();
        }}
      />

      {canvasId == null && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 text-center text-pea-text-secondary">
          <div className="text-5xl opacity-40">🎨</div>
          <div className="text-base font-medium text-pea-text">还没有打开画布</div>
          <div className="text-sm">在「工作空间」中新建或打开一个项目，即可进入画布。</div>
        </div>
      )}

      {sideOpen && <SidePanel onClose={() => setSideOpen(false)} />}
      {libAt && (
        <NodeLibrary
          at={libAt}
          onPick={(k) => add(k, NODE_DEF_OF(k).label)}
          onClose={() => setLibAt(null)}
        />
      )}
      {edgeMenu && (
        <EdgeNodeMenu
          at={{ x: edgeMenu.x, y: edgeMenu.y }}
          onPick={(k) => addConnectedAt(k, edgeMenu.sourceId, { x: edgeMenu.x, y: edgeMenu.y })}
          onClose={() => setEdgeMenu(null)}
        />
      )}

      <div className="pea-canvas-flow">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultEdgeOptions={{ type: 'pea' }}
          connectionMode={ConnectionMode.Loose}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={(conn: Connection) => {
            pendingEdge.current = null;
            onConnect(conn);
          }}
          onConnectStart={(_evt: any, params: any) => {
            pendingEdge.current = { source: params.nodeId ?? null, handleId: params.handleId ?? null };
          }}
          onConnectEnd={(evt: any) => {
            const pending = pendingEdge.current;
            pendingEdge.current = null;
            if (!pending?.source) return;
            const e = evt as MouseEvent;
            const tgt = e.target as HTMLElement;
            const nodeEl = tgt.closest('.react-flow__node') as HTMLElement | null;
            const onHandle = !!tgt.closest('.react-flow__handle');
            const onPane =
              tgt.classList.contains('react-flow__pane') ||
              tgt.classList.contains('react-flow__renderer') ||
              tgt.classList.contains('react-flow__viewport');
            if (onPane) {
              // 空白处释放 → 弹出"新建并连接"菜单
              setEdgeMenu({ x: e.clientX, y: e.clientY, sourceId: pending.source });
              return;
            }
            if (nodeEl && !onHandle) {
              // 释放在某节点内部（非手柄）→ 视为"从节点拖到节点即连线"，
              // 自动创建一条边（onConnect 已处理手柄路径，这里只补齐"落在节点本体"的情形）。
              const targetId = nodeEl.getAttribute('data-id');
              if (targetId && targetId !== pending.source) {
                onConnect({
                  source: pending.source,
                  target: targetId,
                  sourceHandle: null,
                  targetHandle: null,
                } as Connection);
              }
            }
            // 释放在手柄上：onConnect 已建边，这里无需处理。
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
            e.shiftKey ? toggleSelect(n.id) : select(n.id);
          }}
          onNodeDragStart={(e) => {
            // 记录按下坐标（用于区分单击/拖动）；用原生事件坐标
            const me = e as unknown as MouseEvent;
            downPosRef.current = { x: me.clientX, y: me.clientY };
          }}
          onPaneClick={() => {
            clearSelection();
            setMenu(null);
          }}
          onNodeContextMenu={onNodeCtx}
          onPaneContextMenu={onPaneCtx}
          zoomOnDoubleClick={false}
          // Figma 风格：滚轮平移，拖拽=框选，Space+拖拽=平移
          panOnDrag={false}
          panOnScroll
          selectionOnDrag
          selectionMode={SelectionMode.Partial}
          defaultViewport={{ x: 0, y: 0, zoom: 1 }}
          minZoom={0.25}
          maxZoom={3}
          proOptions={{ hideAttribution: true }}
        >
          {showGrid && (
            <Background
              variant={BackgroundVariant.Dots}
              gap={22}
              size={1.2}
              color="rgba(255,255,255,0.06)"
            />
          )}
          {showMinimap && (
            <MiniMap
              nodeStrokeWidth={3}
              zoomable
              pannable
              position="top-left"
              style={{ top: 78, left: 68 }}
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

      <TextNodeToolbar />
      <NodeChatPrompt />

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
                    setLibAt({ x: window.innerWidth / 2 - 150, y: window.innerHeight / 2 - 200 });
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
  return (
    <ReactFlowProvider>
      <Flow />
    </ReactFlowProvider>
  );
}