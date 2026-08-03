import { useEffect, useMemo, useState } from 'react';
import { Modal, Button, Input } from 'antd';
import {
  FolderOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  RightOutlined,
  DownOutlined,
} from '@ant-design/icons';
import { assetsApi, type AssetFolder, type AssetScope } from '../api/assets';
import { toast } from '../store/toast';

interface SaveToLibraryModalProps {
  open: boolean;
  onClose: () => void;
  defaultName?: string;
  onSave: (payload: { scope: AssetScope; folderId: number | null }) => Promise<void>;
}

export default function SaveToLibraryModal({
  open,
  onClose,
  defaultName = '',
  onSave,
}: SaveToLibraryModalProps) {
  const [scope, setScope] = useState<AssetScope>('personal');
  const [folders, setFolders] = useState<AssetFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!open) return;
    setScope('personal');
    setSelectedId(null);
    setCreating(false);
    setNewName(defaultName);
    setExpanded(new Set());
    loadFolders();
  }, [open, defaultName]);

  useEffect(() => {
    if (!open) return;
    loadFolders();
  }, [scope, open]);

  const loadFolders = async () => {
    setLoading(true);
    try {
      const { data } = await assetsApi.listFolders(scope);
      setFolders(data);
    } catch {
      toast.error('获取文件夹失败');
    } finally {
      setLoading(false);
    }
  };

  const doCreateFolder = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      await assetsApi.createFolder(name, scope);
      setCreating(false);
      setNewName('');
      loadFolders();
      toast.success('文件夹已创建');
    } catch {
      toast.error('创建文件夹失败');
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({ scope, folderId: selectedId });
      onClose();
    } catch {
      // 错误由调用方 toast
    } finally {
      setSaving(false);
    }
  };

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const folderMap = useMemo(() => {
    const map = new Map<number, AssetFolder>();
    folders.forEach((f) => map.set(f.id, f));
    return map;
  }, [folders]);

  const rootFolders = useMemo(
    () => folders.filter((f) => f.parent_id == null),
    [folders]
  );

  const childrenOf = (parentId: number) =>
    folders.filter((f) => f.parent_id === parentId);

  const renderFolder = (f: AssetFolder, depth = 0) => {
    const kids = childrenOf(f.id);
    const isExpanded = expanded.has(f.id);
    const isSelected = selectedId === f.id;

    return (
      <div key={f.id}>
        <button
          type="button"
          className={`pea-save-lib-folder ${isSelected ? 'selected' : ''}`}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          onClick={() => setSelectedId(f.id)}
        >
          {kids.length > 0 ? (
            <span
              className="pea-save-lib-folder-toggle"
              onClick={(e) => {
                e.stopPropagation();
                toggleExpand(f.id);
              }}
            >
              {isExpanded ? <DownOutlined /> : <RightOutlined />}
            </span>
          ) : (
            <span className="pea-save-lib-folder-toggle" />
          )}
          <span className="pea-save-lib-folder-icon">
            {isExpanded ? <FolderOpenOutlined /> : <FolderOutlined />}
          </span>
          <span className="pea-save-lib-folder-name">{f.name}</span>
        </button>
        {isExpanded && kids.map((child) => renderFolder(child, depth + 1))}
      </div>
    );
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        <div className="pea-save-lib-title">
          <FolderOutlined />
          <span>保存到素材库</span>
        </div>
      }
      footer={
        <div className="pea-save-lib-footer">
          <Button onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button type="primary" loading={saving} onClick={handleSave}>
            保存
          </Button>
        </div>
      }
      width={420}
      destroyOnClose
      className="pea-save-lib-modal"
      centered
    >
      {/* 范围切换 */}
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

      {/* 新建文件夹 */}
      {!creating ? (
        <button
          type="button"
          className="pea-save-lib-new"
          onClick={() => {
            setCreating(true);
            setNewName(defaultName);
          }}
        >
          <PlusOutlined />
          <span>新建文件夹</span>
        </button>
      ) : (
        <div className="pea-save-lib-new-input">
          <Input
            autoFocus
            placeholder="文件夹名称"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onPressEnter={doCreateFolder}
            maxLength={40}
          />
          <Button type="primary" size="small" onClick={doCreateFolder}>
            确认
          </Button>
          <Button size="small" onClick={() => setCreating(false)}>
            取消
          </Button>
        </div>
      )}

      {/* 文件夹树 */}
      <div className="pea-save-lib-tree">
        <button
          type="button"
          className={`pea-save-lib-folder ${selectedId === null ? 'selected' : ''}`}
          onClick={() => setSelectedId(null)}
        >
          <span className="pea-save-lib-folder-toggle" />
          <span className="pea-save-lib-folder-icon">
            <FolderOutlined />
          </span>
          <span className="pea-save-lib-folder-name">根目录</span>
        </button>
        {loading && folders.length === 0 && (
          <div className="pea-save-lib-empty">加载中…</div>
        )}
        {!loading && folders.length === 0 && (
          <div className="pea-save-lib-empty">暂无文件夹</div>
        )}
        {rootFolders.map((f) => renderFolder(f))}
      </div>
    </Modal>
  );
}
