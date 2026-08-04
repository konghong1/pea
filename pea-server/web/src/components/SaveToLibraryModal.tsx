import { useEffect, useMemo, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Input, Button } from 'antd';
import {
  FolderOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  RightOutlined,
  DownOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import {
  assetsApi,
  ASSET_FOLDERS_CHANGED_EVENT,
  type AssetFolder,
  type AssetScope,
} from '../api/assets';
import { toast } from '../store/toast';

interface SaveToLibraryModalProps {
  open: boolean;
  onClose: () => void;
  defaultName?: string;
  onSave: (payload: { scope: AssetScope; folderId: number | null }) => Promise<void>;
  /** 弹窗内新建/修改文件夹后，通知外部刷新文件夹列表 */
  onFoldersChange?: () => void;
}

/**
 * 保存到素材库弹窗（参考新版设计）：
 * - 深色一体化面板
 * - 右上角「+ 新建文件夹」
 * - 胶囊分段切换 个人 / 团队
 * - 树状文件夹结构，可展开/折叠、点选高亮
 * - 新建文件夹直接在目标文件夹下方内联输入（Finder 风格）
 * - 底部取消 / 保存
 */
export default function SaveToLibraryModal({
  open,
  onClose,
  defaultName,
  onSave,
  onFoldersChange,
}: SaveToLibraryModalProps) {
  const [scope, setScope] = useState<AssetScope>('personal');
  const [folders, setFolders] = useState<AssetFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  /** 正在哪个文件夹下新建子文件夹；null 表示在根目录下新建 */
  const [creatingUnder, setCreatingUnder] = useState<number | null>(null);
  const [newName, setNewName] = useState('');
  const [saving, setSaving] = useState(false);

  const loadFolders = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    try {
      const { data } = await assetsApi.listFolders(scope);
      setFolders(data);
    } catch {
      toast.error('获取文件夹失败');
    } finally {
      setLoading(false);
    }
  }, [open, scope]);

  useEffect(() => {
    loadFolders();
  }, [loadFolders]);

  // 切换 scope 时重置选中到根目录，并退出新建状态
  useEffect(() => {
    setSelectedId(null);
    setIsCreating(false);
    setCreatingUnder(null);
    setNewName('');
  }, [scope]);

  const rootFolders = useMemo(() => folders.filter((f) => f.parent_id == null), [folders]);

  const childFoldersOf = useCallback(
    (parentId: number) => folders.filter((f) => f.parent_id === parentId),
    [folders],
  );

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const startCreate = () => {
    setIsCreating(true);
    setCreatingUnder(selectedId);
    if (selectedId) {
      setExpanded((prev) => new Set(prev).add(selectedId));
    }
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) {
      setIsCreating(false);
      setCreatingUnder(null);
      return;
    }
    try {
      const { data: newFolder } = await assetsApi.createFolder(name, scope, creatingUnder ?? undefined);
      toast.success('文件夹已创建');
      setNewName('');
      setIsCreating(false);
      setCreatingUnder(null);
      // 创建后自动选中新文件夹，确保保存目标就是该新目录
      setSelectedId(newFolder.id);
      loadFolders();
      onFoldersChange?.();
      window.dispatchEvent(new CustomEvent(ASSET_FOLDERS_CHANGED_EVENT));
    } catch {
      toast.error('创建文件夹失败');
    }
  };

  const handleCancelCreate = () => {
    setNewName('');
    setIsCreating(false);
    setCreatingUnder(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({ scope, folderId: selectedId });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const renderNewInput = (depth = 0) => (
    <div className="pea-save-lib-new-input-row" style={{ paddingLeft: `${10 + depth * 18}px` }}>
      <FolderOutlined className="pea-save-lib-new-input-icon" />
      <Input
        autoFocus
        placeholder="文件夹名称"
        value={newName}
        onChange={(e) => setNewName(e.target.value)}
        onPressEnter={handleCreate}
        onBlur={() => {
          if (!newName.trim()) handleCancelCreate();
        }}
        maxLength={40}
      />
      <Button type="primary" size="small" onClick={handleCreate}>
        确认
      </Button>
    </div>
  );

  const renderTree = (folder: AssetFolder, depth = 0) => {
    const isExpanded = expanded.has(folder.id);
    const children = childFoldersOf(folder.id);
    const isSelected = selectedId === folder.id;
    const hasChildren = children.length > 0;

    return (
      <div key={folder.id} className="pea-save-lib-branch">
        <button
          type="button"
          className={`pea-save-lib-folder ${isSelected ? 'selected' : ''}`}
          style={{ paddingLeft: `${10 + depth * 18}px` }}
          onClick={() => setSelectedId(folder.id)}
        >
          {hasChildren ? (
            <span
              className="pea-save-lib-toggle"
              onClick={(e) => {
                e.stopPropagation();
                toggleExpand(folder.id);
              }}
            >
              {isExpanded ? <DownOutlined /> : <RightOutlined />}
            </span>
          ) : (
            <span className="pea-save-lib-toggle-placeholder" />
          )}
          <span className="pea-save-lib-folder-icon">
            {isExpanded ? <FolderOpenOutlined /> : <FolderOutlined />}
          </span>
          <span className="pea-save-lib-folder-name">{folder.name}</span>
        </button>

        {/* 在当前文件夹下方直接新建子文件夹 */}
        {isCreating && creatingUnder === folder.id && renderNewInput(depth + 1)}

        {isExpanded && children.map((child) => renderTree(child, depth + 1))}
      </div>
    );
  };

  if (!open) return null;

  return createPortal(
    <div className="pea-save-lib-overlay" onClick={onClose}>
      <div className="pea-save-lib-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="pea-save-lib-header">
          <div className="pea-save-lib-title">
            <FolderOutlined />
            <span>保存到素材库</span>
          </div>
          <div className="pea-save-lib-header-actions">
            <button
              type="button"
              className="pea-save-lib-new-btn"
              onClick={startCreate}
            >
              <PlusOutlined />
              <span>新建文件夹</span>
            </button>
            <button type="button" className="pea-save-lib-close" onClick={onClose} aria-label="关闭">
              <CloseOutlined />
            </button>
          </div>
        </div>

        {/* Scope switch */}
        <div className="pea-save-lib-scope">
          <button
            type="button"
            className={scope === 'personal' ? 'active' : ''}
            onClick={() => setScope('personal')}
          >
            个人
          </button>
          <button
            type="button"
            className={scope === 'team' ? 'active' : ''}
            onClick={() => setScope('team')}
          >
            团队
          </button>
        </div>

        {/* Tree */}
        <div className="pea-save-lib-tree">
          {/* 在根目录下新建时，输入框放在树的最开始 */}
          {isCreating && creatingUnder === null && renderNewInput(0)}

          {rootFolders.map((f) => renderTree(f))}

          {folders.length === 0 && !loading && !isCreating && (
            <div className="pea-save-lib-empty">暂无文件夹，点击右上角新建</div>
          )}
        </div>

        {/* Footer */}
        <div className="pea-save-lib-footer">
          <Button className="pea-save-lib-cancel" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button
            className="pea-save-lib-confirm"
            type="primary"
            loading={saving}
            onClick={handleSave}
          >
            保存
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
