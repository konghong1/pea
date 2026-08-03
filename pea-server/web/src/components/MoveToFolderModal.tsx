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
import { assetsApi, type AssetFolder, type AssetScope } from '../api/assets';
import { toast } from '../store/toast';

interface MoveToFolderModalProps {
  open: boolean;
  onClose: () => void;
  scope: AssetScope;
  onMove: (folderId: number | null) => Promise<void>;
}

/**
 * 移动素材到文件夹弹窗：
 * - 深色一体化面板
 * - 树状文件夹结构，可展开/折叠、点选高亮
 * - 右上角「+ 新建文件夹」（便于直接创建目标文件夹）
 * - 底部取消 / 移动
 */
export default function MoveToFolderModal({
  open,
  onClose,
  scope,
  onMove,
}: MoveToFolderModalProps) {
  const [folders, setFolders] = useState<AssetFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [creatingUnder, setCreatingUnder] = useState<number | null>(null);
  const [newName, setNewName] = useState('');
  const [moving, setMoving] = useState(false);

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

  // 打开时重置选中状态
  useEffect(() => {
    if (open) {
      setSelectedId(null);
      setIsCreating(false);
      setCreatingUnder(null);
      setNewName('');
    }
  }, [open]);

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
      await assetsApi.createFolder(name, scope, creatingUnder ?? undefined);
      toast.success('文件夹已创建');
      setNewName('');
      setIsCreating(false);
      setCreatingUnder(null);
      loadFolders();
    } catch {
      toast.error('创建文件夹失败');
    }
  };

  const handleCancelCreate = () => {
    setNewName('');
    setIsCreating(false);
    setCreatingUnder(null);
  };

  const handleMove = async () => {
    setMoving(true);
    try {
      await onMove(selectedId);
      onClose();
    } finally {
      setMoving(false);
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
            <span>移动到</span>
          </div>
          <div className="pea-save-lib-header-actions">
            <button type="button" className="pea-save-lib-new-btn" onClick={startCreate}>
              <PlusOutlined />
              <span>新建文件夹</span>
            </button>
            <button type="button" className="pea-save-lib-close" onClick={onClose} aria-label="关闭">
              <CloseOutlined />
            </button>
          </div>
        </div>

        {/* Tree */}
        <div className="pea-save-lib-tree">
          {isCreating && creatingUnder === null && renderNewInput(0)}
          {rootFolders.map((f) => renderTree(f))}
          {folders.length === 0 && !loading && !isCreating && (
            <div className="pea-save-lib-empty">暂无文件夹，点击右上角新建</div>
          )}
        </div>

        {/* Footer */}
        <div className="pea-save-lib-footer">
          <Button className="pea-save-lib-cancel" onClick={onClose} disabled={moving}>
            取消
          </Button>
          <Button
            className="pea-save-lib-confirm"
            type="primary"
            loading={moving}
            onClick={handleMove}
          >
            移动
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
