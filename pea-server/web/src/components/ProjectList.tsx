import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  Input,
  Modal,
  Dropdown,
  App as AntApp,
  Empty,
  Tooltip,
  Spin,
  Segmented,
  Select,
} from 'antd';
import {
  PlusOutlined,
  SearchOutlined,
  FilterOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  MoreOutlined,
  FolderOpenOutlined,
  DeleteOutlined,
  ShareAltOutlined,
  CheckSquareOutlined,
  BorderOutlined,
  TeamOutlined,
  EditOutlined,
  FolderAddOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { canvasesApi, CanvasFolder, CanvasItem } from '../api/canvases';
import { useUi } from '../store/ui';
import { useCanvas } from '../store/canvas';
import { useAuth } from '../store/auth';
import { toast } from '../store/toast';
import { useTheme } from '../store/theme';

type Scope = 'personal' | 'team' | 'trash';
type View = 'grid' | 'list';

/* ---------------- helpers ---------------- */

/** 基于 canvas id 生成稳定的 CSS gradient（不依赖网络图片）。 */
function gradientFor(id: number): string {
  const palettes = [
    'linear-gradient(135deg,#7c5cff 0%,#1fa2dc 55%,#b6f09c 100%)',
    'linear-gradient(135deg,#1fa2dc 0%,#16a34a 70%,#b6f09c 100%)',
    'linear-gradient(135deg,#ff7eb3 0%,#7c5cff 60%,#1fa2dc 100%)',
    'linear-gradient(135deg,#f59e0b 0%,#ef4444 70%,#7c5cff 100%)',
    'linear-gradient(135deg,#0ea5e9 0%,#1fa2dc 60%,#7c5cff 100%)',
    'linear-gradient(135deg,#22d3ee 0%,#1fa2dc 55%,#16a34a 100%)',
    'linear-gradient(135deg,#f43f5e 0%,#7c5cff 70%,#1fa2dc 100%)',
    'linear-gradient(135deg,#a855f7 0%,#ec4899 60%,#f97316 100%)',
  ];
  // 简单稳定哈希
  let h = id | 0;
  h = (h * 2654435761) >>> 0;
  return palettes[h % palettes.length];
}

function relTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '';
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return '刚刚';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return new Date(iso).toLocaleDateString();
}

const SCOPE_LABEL: Record<Scope, string> = {
  personal: '我的',
  team: '团队',
  trash: '回收站',
};

/* ---------------- main page ---------------- */

export default function ProjectList() {
  const { message } = AntApp.useApp();
  const setActive = useUi((s) => s.setActive);
  const openCanvas = useCanvas((s) => s.openCanvas);
  const { user } = useAuth();
  const { mode } = useTheme();

  const [scope, setScope] = useState<Scope>('personal');
  const [items, setItems] = useState<CanvasItem[]>([]);
  const [folders, setFolders] = useState<CanvasFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>('grid');
  const [q, setQ] = useState('');
  // 默认按「最近创建」排序：顺序稳定，不会因为编辑某个项目导致它跳到列表最前，
  // 造成"点第一个卡片进去显示的却是刚编辑的项目"的错觉（2026-07-27 用户反馈的严重 bug）。
  // 用户手动切换排序后持久化到 localStorage。
  const [sortBy, setSortBy] = useState<'updated_at' | 'created_at' | 'name'>(() => {
    try {
      const v = localStorage.getItem('pea_projects_sort');
      if (v === 'updated_at' || v === 'created_at' || v === 'name') return v;
    } catch { /* ignore */ }
    return 'created_at';
  });
  const changeSortBy = (v: 'updated_at' | 'created_at' | 'name') => {
    setSortBy(v);
    try { localStorage.setItem('pea_projects_sort', v); } catch { /* ignore */ }
  };
  const [multiSelect, setMultiSelect] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Modals
  const [renameTarget, setRenameTarget] = useState<CanvasItem | null>(null);
  const [shareTarget, setShareTarget] = useState<CanvasItem | null>(null);
  const [moveTarget, setMoveTarget] = useState<CanvasItem | null>(null);
  const [bulkMoveOpen, setBulkMoveOpen] = useState(false);
  const [folderModalOpen, setFolderModalOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await canvasesApi.list({
        scope,
        q: q.trim() || undefined,
        limit: 100,
      });
      let arr = data ?? [];
      // 前端排序（也可由后端 ORDER BY，但前端更可控）
      arr = [...arr].sort((a, b) => {
        if (sortBy === 'name') return a.title.localeCompare(b.title, 'zh-Hans-CN');
        const ka = new Date(a[sortBy]).getTime();
        const kb = new Date(b[sortBy]).getTime();
        return kb - ka;
      });
      setItems(arr);
    } catch (e: any) {
      const code = e?.response?.status;
      if (code === 401) {
        toast.error('登录已过期，请重新登录');
      } else {
        toast.error(`加载项目失败 (${code ?? '网络错误'})`);
      }
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [scope, q, sortBy]);

  const refreshFolders = useCallback(async () => {
    if (scope === 'trash') {
      setFolders([]);
      return;
    }
    try {
      const fs = await canvasesApi.folders(scope);
      setFolders(fs);
    } catch {
      setFolders([]);
    }
  }, [scope]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    refreshFolders();
  }, [refreshFolders]);

  /* ----- actions ----- */

  const creatingRef = useRef(false);
  const newProject = async () => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    try {
      const { id } = await canvasesApi.create('未命名画布', scope === 'trash' ? 'personal' : scope);
      await openCanvas(id);
      setActive('canvas');
      toast.success('已创建并打开新画布');
    } catch (e: any) {
      toast.error('新建失败');
    } finally {
      creatingRef.current = false;
    }
  };

  const openProject = async (id: number) => {
    try {
      await openCanvas(id);
      setActive('canvas');
    } catch {
      toast.error('打开画布失败');
    }
  };

  const renameInline = async (item: CanvasItem, newTitle: string) => {
    const t = newTitle.trim();
    if (!t || t === item.title) return;
    try {
      await canvasesApi.update(item.id, { title: t });
      setItems((arr) => arr.map((x) => (x.id === item.id ? { ...x, title: t } : x)));
      toast.success('已重命名');
    } catch {
      toast.error('重命名失败');
    }
  };

  const moveToTeam = async (item: CanvasItem) => {
    const next: 'personal' | 'team' = item.scope === 'team' ? 'personal' : 'team';
    try {
      await canvasesApi.update(item.id, { scope: next });
      setItems((arr) => arr.map((x) => (x.id === item.id ? { ...x, scope: next } : x)));
      toast.success(next === 'team' ? '已移动至团队空间' : '已移动回个人空间');
      refresh();
    } catch {
      toast.error('移动失败');
    }
  };

  const doShare = async (item: CanvasItem) => {
    try {
      const { token } = await canvasesApi.share(item.id);
      const url = `${window.location.origin}/shared/${token}`;
      setShareTarget({ ...item, share_token: token });
      // 自动复制
      try {
        await navigator.clipboard.writeText(url);
        toast.success('分享链接已复制到剪贴板');
      } catch {
        toast.info('分享链接已生成');
      }
    } catch {
      toast.error('生成分享链接失败');
    }
  };

  const revokeShare = async (item: CanvasItem) => {
    try {
      await canvasesApi.revokeShare(item.id);
      setItems((arr) => arr.map((x) => (x.id === item.id ? { ...x, share_token: null } : x)));
      toast.success('已取消分享');
    } catch {
      toast.error('取消分享失败');
    }
  };

  const moveToFolder = async (item: CanvasItem, folderId: number | null) => {
    try {
      await canvasesApi.update(item.id, { folder_id: folderId });
      setItems((arr) => arr.map((x) => (x.id === item.id ? { ...x, folder_id: folderId } : x)));
      toast.success(folderId == null ? '已移至根目录' : '已移至文件夹');
      refresh();
    } catch {
      toast.error('移动失败');
    }
  };

  const deleteOne = (item: CanvasItem) => {
    Modal.confirm({
      title: '删除项目',
      content: (
        <span>
          确认删除 <b>{item.title}</b>？当前为物理删除（不可恢复）。
        </span>
      ),
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await canvasesApi.remove(item.id);
          setItems((arr) => arr.filter((x) => x.id !== item.id));
          toast.success('已删除');
        } catch {
          toast.error('删除失败');
        }
      },
    });
  };

  const bulkDelete = () => {
    if (!selectedIds.size) return;
    Modal.confirm({
      title: `批量删除 ${selectedIds.size} 项`,
      content: '此操作不可恢复，是否继续？',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await Promise.all(Array.from(selectedIds).map((id) => canvasesApi.remove(id)));
          setItems((arr) => arr.filter((x) => !selectedIds.has(x.id)));
          setSelectedIds(new Set());
          toast.success(`已删除 ${selectedIds.size} 项`);
        } catch {
          toast.error('批量删除失败');
        }
      },
    });
  };

  const bulkMove = async (folderId: number | null) => {
    if (!selectedIds.size) return;
    try {
      await Promise.all(
        Array.from(selectedIds).map((id) => canvasesApi.update(id, { folder_id: folderId })),
      );
      setItems((arr) =>
        arr.map((x) => (selectedIds.has(x.id) ? { ...x, folder_id: folderId } : x)),
      );
      setSelectedIds(new Set());
      setBulkMoveOpen(false);
      toast.success('已批量移动');
    } catch {
      toast.error('批量移动失败');
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /* ----- context menu ----- */

  const cardMenu = (item: CanvasItem) => ({
    onClick: ({ key, domEvent }: any) => {
      domEvent?.stopPropagation?.();
      switch (key) {
        case 'open':
          openProject(item.id);
          break;
        case 'rename':
          setRenameTarget(item);
          break;
        case 'select':
          setMultiSelect(true);
          setSelectedIds(new Set([item.id]));
          break;
        case 'move':
          setMoveTarget(item);
          break;
        case 'share':
          doShare(item);
          break;
        case 'team':
          moveToTeam(item);
          break;
        case 'delete':
          deleteOne(item);
          break;
      }
    },
    items: [
      {
        key: 'open',
        label: '打开',
        icon: <FolderOpenOutlined />,
      },
      {
        key: 'rename',
        label: '重命名',
        icon: <EditOutlined />,
      },
      {
        key: 'select',
        label: '选择',
        icon: <CheckSquareOutlined />,
      },
      { type: 'divider' as const },
      {
        key: 'move',
        label: '移动至…',
        icon: <FolderOpenOutlined />,
        disabled: scope === 'trash',
      },
      {
        key: 'share',
        label: item.share_token ? '重新生成分享链接' : '分享链接',
        icon: <ShareAltOutlined />,
        disabled: scope === 'trash',
      },
      {
        key: 'team',
        label: item.scope === 'team' ? '移回个人空间' : '移动至团队',
        icon: <TeamOutlined />,
        disabled: scope === 'trash',
      },
      { type: 'divider' as const },
      {
        key: 'delete',
        label: '删除',
        icon: <DeleteOutlined />,
        danger: true,
      },
    ],
  });

  /* ----- derived ----- */

  const counts = useMemo(
    () => ({ personal: items.filter((i) => i.scope === 'personal').length, team: items.filter((i) => i.scope === 'team').length }),
    [items],
  );

  const rootFolders = useMemo(() => folders.filter((f) => !f.parent_id), [folders]);

  return (
    <div className="pea-page" data-theme={mode}>
      <div className="projects-page">
        {/* ===== 子页头：左 tabs + 右工具栏 ===== */}
        <div className="projects-subnav">
          <div className="projects-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={scope === 'personal'}
              className={`projects-tab${scope === 'personal' ? ' active' : ''}`}
              onClick={() => setScope('personal')}
            >
              <BorderOutlined /> 个人
              <span className="projects-tab-count">{counts.personal}</span>
            </button>
            <button
              role="tab"
              aria-selected={scope === 'team'}
              className={`projects-tab${scope === 'team' ? ' active' : ''}`}
              onClick={() => setScope('team')}
            >
              <TeamOutlined /> 团队项目
              <span className="projects-tab-count">{counts.team}</span>
            </button>
          </div>

          <div className="projects-toolbar">
            <Input
              allowClear
              prefix={<SearchOutlined style={{ color: 'var(--pea-text-muted)' }} />}
              placeholder="搜索项目"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ width: 220 }}
            />
            <Select
              value={sortBy}
              onChange={changeSortBy}
              suffixIcon={<FilterOutlined />}
              style={{ width: 130 }}
              options={[
                { value: 'updated_at', label: '最近更新' },
                { value: 'created_at', label: '最近创建' },
                { value: 'name', label: '名称 A→Z' },
              ]}
            />
            <Tooltip title="网格视图">
              <button
                aria-pressed={view === 'grid'}
                className={`projects-view-btn${view === 'grid' ? ' active' : ''}`}
                onClick={() => setView('grid')}
              >
                <AppstoreOutlined />
              </button>
            </Tooltip>
            <Tooltip title="列表视图">
              <button
                aria-pressed={view === 'list'}
                className={`projects-view-btn${view === 'list' ? ' active' : ''}`}
                onClick={() => setView('list')}
              >
                <UnorderedListOutlined />
              </button>
            </Tooltip>
            <button className="projects-new-btn" onClick={newProject}>
              <PlusOutlined /> 新建项目
            </button>
          </div>
        </div>

        {/* ===== 文件夹面包屑/快捷 ===== */}
        {scope !== 'trash' && rootFolders.length > 0 && (
          <div className="projects-folders">
            <FolderOpenOutlined style={{ color: 'var(--pea-text-muted)' }} />
            <span className="projects-folders-label">文件夹：</span>
            {rootFolders.slice(0, 8).map((f) => (
              <button
                key={f.id}
                className="projects-folder-chip"
                onClick={() => toast.info(`「${f.name}」中 ${items.filter((i) => i.folder_id === f.id).length} 个项目`)}
              >
                {f.name}
              </button>
            ))}
            <button
              className="projects-folder-chip add"
              onClick={() => setFolderModalOpen(true)}
            >
              <FolderAddOutlined /> 新建文件夹
            </button>
          </div>
        )}

        {/* ===== 多选条 ===== */}
        {multiSelect && (
          <div className="projects-bulkbar">
            <span>
              已选 <b>{selectedIds.size}</b> 项
            </span>
            <button className="link" onClick={() => setSelectedIds(new Set(items.map((i) => i.id)))}>
              全选
            </button>
            <button className="link" onClick={() => setSelectedIds(new Set())}>
              清空
            </button>
            <span style={{ flex: 1 }} />
            <button className="ghost" onClick={() => setBulkMoveOpen(true)} disabled={!selectedIds.size}>
              <FolderOpenOutlined /> 移动至…
            </button>
            <button className="danger" onClick={bulkDelete} disabled={!selectedIds.size}>
              <DeleteOutlined /> 删除
            </button>
            <button className="icon" onClick={() => { setMultiSelect(false); setSelectedIds(new Set()); }}>
              <CloseOutlined />
            </button>
          </div>
        )}

        {/* ===== 内容区 ===== */}
        <div className={`projects-grid ${view === 'list' ? 'list' : ''}`}>
          {/* "+ 新建项目" 始终第一个 */}
          {!multiSelect && scope !== 'trash' && (
            <button className="projects-card projects-card-create" onClick={newProject}>
              <div className="projects-card-create-plus">
                <PlusOutlined />
              </div>
              <div className="projects-card-create-title">新建项目</div>
            </button>
          )}

          {loading ? (
            <div className="projects-loading">
              <Spin />
            </div>
          ) : items.length === 0 ? (
            <div className="projects-empty">
              <Empty
                description={
                  q
                    ? `没有匹配「${q}」的项目`
                    : scope === 'trash'
                    ? '回收站是空的'
                    : '这里还没有项目'
                }
              />
              {!q && scope !== 'trash' && (
                <button className="projects-new-btn" style={{ marginTop: 16 }} onClick={newProject}>
                  <PlusOutlined /> 新建项目
                </button>
              )}
            </div>
          ) : (
            items.map((item) => (
              <ProjectCard
                key={item.id}
                item={item}
                view={view}
                menu={cardMenu(item)}
                multiSelect={multiSelect}
                selected={selectedIds.has(item.id)}
                onToggleSelect={() => toggleSelect(item.id)}
                onOpen={() => openProject(item.id)}
                onRename={(t) => renameInline(item, t)}
                isTrash={scope === 'trash'}
              />
            ))
          )}
        </div>
      </div>

      {/* ===== Modals ===== */}

      {/* 重命名 */}
      <RenameModal
        target={renameTarget}
        onClose={() => setRenameTarget(null)}
        onConfirm={(t) => {
          if (renameTarget) {
            renameInline(renameTarget, t);
            setRenameTarget(null);
          }
        }}
      />

      {/* 分享 */}
      <ShareLinkModal
        target={shareTarget}
        onClose={() => setShareTarget(null)}
        onRevoke={() => {
          if (shareTarget) {
            revokeShare(shareTarget);
            setShareTarget(null);
          }
        }}
      />

      {/* 移动至 */}
      <MoveToModal
        target={moveTarget}
        folders={folders.filter((f) => f.scope === scope)}
        onClose={() => setMoveTarget(null)}
        onPick={(fid) => {
          if (moveTarget) {
            moveToFolder(moveTarget, fid);
            setMoveTarget(null);
          }
        }}
      />

      {/* 批量移动 */}
      <MoveToModal
        target={null}
        open={bulkMoveOpen}
        folders={folders.filter((f) => f.scope === scope)}
        title={`移动 ${selectedIds.size} 项至…`}
        onClose={() => setBulkMoveOpen(false)}
        onPick={(fid) => {
          bulkMove(fid);
          setBulkMoveOpen(false);
        }}
      />

      {/* 新建文件夹 */}
      <NewFolderModal
        open={folderModalOpen}
        scope={scope === 'trash' ? 'personal' : scope}
        onClose={() => setFolderModalOpen(false)}
        onCreated={async (name) => {
          try {
            await canvasesApi.createFolder(name, scope === 'trash' ? 'personal' : scope);
            toast.success(`已创建文件夹「${name}」`);
            refreshFolders();
          } catch {
            toast.error('创建失败');
          } finally {
            setFolderModalOpen(false);
          }
        }}
      />
    </div>
  );
}

/* ---------------- sub components ---------------- */

interface CardProps {
  item: CanvasItem;
  view: View;
  menu: any;
  multiSelect: boolean;
  selected: boolean;
  isTrash: boolean;
  onToggleSelect: () => void;
  onOpen: () => void;
  onRename: (newTitle: string) => void;
}

function ProjectCard({ item, view, menu, multiSelect, selected, isTrash, onToggleSelect, onOpen, onRename }: CardProps) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const inputRef = useRef<any>(null);

  useEffect(() => setTitle(item.title), [item.title]);
  useEffect(() => {
    if (editing) inputRef.current?.focus({ cursor: 'all' });
  }, [editing]);

  const commit = () => {
    setEditing(false);
    onRename(title);
  };

  const thumbStyle = item.thumbnail_url
    ? { backgroundImage: `url(${item.thumbnail_url})`, backgroundSize: 'cover', backgroundPosition: 'center' }
    : { background: gradientFor(item.id) };

  return (
    <div
      className={`projects-card${view === 'list' ? ' list' : ''}${multiSelect ? ' multi' : ''}${selected ? ' selected' : ''}`}
      data-canvas-id={item.id}
      onClick={(e) => {
        if (multiSelect) {
          e.stopPropagation();
          onToggleSelect();
        } else if (!editing) {
          onOpen();
        }
      }}
    >
      <div className="projects-card-thumb" style={thumbStyle as any}>
        <span className={`projects-card-scope scope-${item.scope}`}>{SCOPE_LABEL[item.scope]}</span>
        {item.share_token && <span className="projects-card-share" title="已开启分享链接"><ShareAltOutlined /></span>}
        {multiSelect && (
          <span className={`projects-card-check${selected ? ' on' : ''}`}>
            {selected ? <CheckSquareOutlined /> : <BorderOutlined />}
          </span>
        )}
      </div>

      <div className="projects-card-body">
        <div className="projects-card-row1">
          {editing ? (
            <Input
              ref={inputRef}
              size="small"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onPressEnter={commit}
              onBlur={commit}
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <div className="projects-card-title" title={item.title} onDoubleClick={(e) => { e.stopPropagation(); if (!multiSelect) setEditing(true); }}>
              {item.title}
            </div>
          )}
          {!multiSelect && !isTrash && (
            <Dropdown menu={menu} trigger={['click']} placement="bottomRight">
              <button
                className="projects-card-more"
                aria-label="更多操作"
                onClick={(e) => e.stopPropagation()}
              >
                <MoreOutlined />
              </button>
            </Dropdown>
          )}
        </div>
        <div className="projects-card-meta">编辑于 {relTime(item.updated_at)}</div>
      </div>
    </div>
  );
}

/* ---------------- modals ---------------- */

function RenameModal({
  target,
  onClose,
  onConfirm,
}: {
  target: CanvasItem | null;
  onClose: () => void;
  onConfirm: (t: string) => void;
}) {
  const [v, setV] = useState('');
  useEffect(() => {
    if (target) setV(target.title);
  }, [target]);
  return (
    <Modal
      title="重命名"
      open={!!target}
      onCancel={onClose}
      okText="保存"
      cancelText="取消"
      onOk={() => onConfirm(v)}
    >
      <Input
        autoFocus
        value={v}
        onChange={(e) => setV(e.target.value)}
        onPressEnter={() => onConfirm(v)}
        placeholder="项目标题"
      />
    </Modal>
  );
}

function ShareLinkModal({
  target,
  onClose,
  onRevoke,
}: {
  target: CanvasItem | null;
  onClose: () => void;
  onRevoke: () => void;
}) {
  const url = target?.share_token
    ? `${typeof window !== 'undefined' ? window.location.origin : ''}/shared/${target.share_token}`
    : '';
  const [copied, setCopied] = useState(false);
  useEffect(() => setCopied(false), [target?.share_token]);

  return (
    <Modal
      title="分享链接"
      open={!!target}
      onCancel={onClose}
      footer={null}
    >
      <p style={{ color: 'var(--pea-text-secondary)', fontSize: 13 }}>
        任何持有此链接的人都可以只读访问你的画布内容。
      </p>
      <div style={{ display: 'flex', gap: 8 }}>
        <Input value={url} readOnly />
        <button
          className="projects-new-btn"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(url);
              setCopied(true);
              toast.success('已复制');
              setTimeout(() => setCopied(false), 1500);
            } catch {
              toast.error('复制失败');
            }
          }}
        >
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <button className="link" onClick={onRevoke} style={{ color: 'var(--pea-text-secondary)' }}>
          取消分享
        </button>
      </div>
    </Modal>
  );
}

function MoveToModal({
  target,
  open,
  folders,
  title,
  onClose,
  onPick,
}: {
  target: CanvasItem | null;
  open?: boolean;
  folders: CanvasFolder[];
  title?: string;
  onClose: () => void;
  onPick: (folderId: number | null) => void;
}) {
  const visible = open !== undefined ? open : !!target;
  return (
    <Modal
      title={title ?? '移动至文件夹'}
      open={visible}
      onCancel={onClose}
      footer={null}
      width={420}
    >
      <div className="projects-move-list">
        <button className="projects-move-row" onClick={() => onPick(null)}>
          <BorderOutlined /> 根目录（不放入文件夹）
        </button>
        {folders.length === 0 && (
          <div style={{ color: 'var(--pea-text-muted)', fontSize: 13, padding: 12 }}>
            还没有文件夹，先去上方"新建文件夹"。
          </div>
        )}
        {folders.map((f) => (
          <button key={f.id} className="projects-move-row" onClick={() => onPick(f.id)}>
            <FolderOpenOutlined /> {f.name}
          </button>
        ))}
      </div>
    </Modal>
  );
}

function NewFolderModal({
  open,
  scope,
  onClose,
  onCreated,
}: {
  open: boolean;
  scope: 'personal' | 'team';
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const [v, setV] = useState('');
  useEffect(() => { if (!open) setV(''); }, [open]);
  return (
    <Modal
      title={`新建文件夹（${scope === 'team' ? '团队' : '个人'}）`}
      open={open}
      onCancel={onClose}
      okText="创建"
      cancelText="取消"
      onOk={() => v.trim() && onCreated(v.trim())}
    >
      <Input
        autoFocus
        value={v}
        onChange={(e) => setV(e.target.value)}
        placeholder="文件夹名称"
        onPressEnter={() => v.trim() && onCreated(v.trim())}
      />
    </Modal>
  );
}