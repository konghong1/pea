import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import {
  LeftOutlined,
  UserOutlined,
  PlusOutlined,
  UploadOutlined,
  FolderAddOutlined,
  SearchOutlined,
  StarOutlined,
  StarFilled,
  FolderOutlined,
  FolderOpenOutlined,
  RightOutlined,
  DownOutlined,
  MoreOutlined,
  DeleteOutlined,
  EditOutlined,
  CloseOutlined,
  FileOutlined,
  PictureOutlined,
} from '@ant-design/icons';
import { App, Button, Dropdown, Input, Modal, Tooltip } from 'antd';
import { assetsApi, type AssetFolder, type Asset, type AssetScope } from '../api/assets';
import { toast } from '../store/toast';

type View = 'root' | 'favorites' | 'folder';

interface MaterialPanelProps {
  onClose: () => void;
}

export default function MaterialPanel({ onClose }: MaterialPanelProps) {
  const { message, modal } = App.useApp();
  const [scope, setScope] = useState<AssetScope>('personal');
  const [view, setView] = useState<View>('root');
  const [folderId, setFolderId] = useState<number | null>(null);
  const [folderName, setFolderName] = useState('');
  const [query, setQuery] = useState('');

  const [folders, setFolders] = useState<AssetFolder[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<number>>(new Set());
  const fileInput = useRef<HTMLInputElement>(null);

  const refreshFolders = useCallback(async () => {
    try {
      const { data } = await assetsApi.listFolders(scope);
      setFolders(data);
    } catch {
      toast.error('获取文件夹失败');
    }
  }, [scope]);

  const refreshAssets = useCallback(async () => {
    setLoading(true);
    try {
      if (view === 'favorites') {
        // 收藏跨文件夹：先拉当前 scope 全部，前端按 is_favorite 过滤
        const { data } = await assetsApi.listAssets(scope, null, query);
        setAssets(data.filter((a) => a.is_favorite));
      } else if (view === 'folder' && folderId != null) {
        const { data } = await assetsApi.listAssets(scope, folderId, query);
        setAssets(data);
      } else if (view === 'root') {
        // 文件库根目录：拉取当前 scope 全部素材，按文件夹分组展示
        const { data } = await assetsApi.listAssets(scope, null, query);
        setAssets(data);
      } else {
        setAssets([]);
      }
    } catch {
      toast.error('获取素材失败');
    } finally {
      setLoading(false);
    }
  }, [scope, view, folderId, query]);

  useEffect(() => {
    refreshFolders();
  }, [refreshFolders]);

  useEffect(() => {
    refreshAssets();
  }, [refreshAssets]);

  const createFolder = () => {
    let value = '';
    modal.confirm({
      title: '新建文件夹',
      content: (
        <Input
          placeholder="文件夹名称"
          defaultValue=""
          maxLength={40}
          onChange={(e) => {
            value = e.target.value;
          }}
          onPressEnter={() => {
            Modal.destroyAll();
            doCreate(value);
          }}
        />
      ),
      onOk: () => doCreate(value),
    });
  };

  const doCreate = async (name: string) => {
    const n = name.trim();
    if (!n) return;
    try {
      await assetsApi.createFolder(n, scope);
      refreshFolders();
      message.success('文件夹已创建');
    } catch {
      toast.error('创建失败');
    }
  };

  const renameFolder = (f: AssetFolder) => {
    let value = f.name;
    modal.confirm({
      title: '重命名文件夹',
      content: (
        <Input
          defaultValue={f.name}
          maxLength={40}
          onChange={(e) => {
            value = e.target.value;
          }}
          onPressEnter={() => {
            Modal.destroyAll();
            doRename(f.id, value);
          }}
        />
      ),
      onOk: () => doRename(f.id, value),
    });
  };

  const doRename = async (id: number, name: string) => {
    const n = name.trim();
    if (!n) return;
    try {
      await assetsApi.updateFolder(id, { name: n });
      refreshFolders();
      if (folderId === id) setFolderName(n);
      message.success('已重命名');
    } catch {
      toast.error('重命名失败');
    }
  };

  const deleteFolder = async (f: AssetFolder) => {
    modal.confirm({
      title: `删除文件夹「${f.name}」？`,
      content: '文件夹内的素材将回到根目录。',
      okType: 'danger',
      onOk: async () => {
        try {
          await assetsApi.deleteFolder(f.id);
          refreshFolders();
          if (folderId === f.id) setView('root');
          message.success('已删除');
        } catch {
          toast.error('删除失败');
        }
      },
    });
  };

  const uploadFile = async (file: File) => {
    try {
      await assetsApi.upload(file, scope, folderId ?? undefined);
      refreshAssets();
      message.success('上传成功');
    } catch {
      toast.error('上传失败');
    }
  };

  const toggleFavorite = async (a: Asset) => {
    try {
      await assetsApi.updateAsset(a.id, { is_favorite: !a.is_favorite });
      refreshAssets();
    } catch {
      toast.error('操作失败');
    }
  };

  const deleteAsset = (a: Asset) => {
    modal.confirm({
      title: `删除「${a.name}」？`,
      okType: 'danger',
      onOk: async () => {
        try {
          await assetsApi.deleteAsset(a.id);
          refreshAssets();
          message.success('已删除');
        } catch {
          toast.error('删除失败');
        }
      },
    });
  };

  const openFolder = (f: AssetFolder) => {
    setFolderId(f.id);
    setFolderName(f.name);
    setView('folder');
  };

  const title = view === 'root' ? '素材库' : view === 'favorites' ? '收藏' : folderName || '文件夹';

  const addMenuItems = [
    {
      key: 'upload',
      icon: <UploadOutlined />,
      label: '上传',
      onClick: () => fileInput.current?.click(),
    },
    {
      key: 'folder',
      icon: <FolderAddOutlined />,
      label: '新建文件夹',
      onClick: createFolder,
    },
  ];

  const folderMenu = (f: AssetFolder) => ({
    items: [
      { key: 'rename', icon: <EditOutlined />, label: '重命名', onClick: () => renameFolder(f) },
      { key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true, onClick: () => deleteFolder(f) },
    ],
  });

  const assetMenu = (a: Asset) => ({
    items: [
      {
        key: 'favorite',
        icon: a.is_favorite ? <StarOutlined /> : <StarFilled />,
        label: a.is_favorite ? '取消收藏' : '收藏',
        onClick: () => toggleFavorite(a),
      },
      { key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true, onClick: () => deleteAsset(a) },
    ],
  });

  const isImage = (a: Asset) => /^image\//.test(a.content_type);
  const isVideo = (a: Asset) => /^video\//.test(a.content_type);

  const folderMap = useMemo(() => {
    const map = new Map<number, AssetFolder>();
    folders.forEach((f) => map.set(f.id, f));
    return map;
  }, [folders]);

  const rootFolders = useMemo(
    () => folders.filter((f) => f.parent_id == null),
    [folders]
  );

  const assetsByFolder = useMemo(() => {
    const map = new Map<number | null, Asset[]>();
    assets.forEach((a) => {
      const key = a.folder_id ?? null;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(a);
    });
    return map;
  }, [assets]);

  const childFoldersOf = useCallback(
    (parentId: number) => folders.filter((f) => f.parent_id === parentId),
    [folders]
  );

  const toggleFolder = (id: number) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandFolder = (id: number) => {
    setExpandedFolders((prev) => new Set(prev).add(id));
  };

  const favoriteGroups = useMemo(() => {
    const groups = new Map<string, Asset[]>();
    assets.forEach((a) => {
      const day = a.created_at.slice(0, 10);
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day)!.push(a);
    });
    return Array.from(groups.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }, [assets]);

  const renderAssetThumb = (a: Asset, size: 'sm' | 'md' = 'sm') => (
    <div
      key={a.id}
      className={`pea-material-thumb ${size}`}
      title={a.name}
      onClick={() => { /* 未来可预览 */ }}
    >
      <div className="pea-material-thumb-img">
        {isImage(a) ? (
          <img src={a.url} alt={a.name} loading="lazy" />
        ) : isVideo(a) ? (
          <video src={a.url} muted preload="metadata" />
        ) : (
          <PictureOutlined />
        )}
      </div>
      <div className="pea-material-thumb-label">{a.name}</div>
    </div>
  );

  const renderFolderTree = (f: AssetFolder, depth = 0) => {
    const isExpanded = expandedFolders.has(f.id);
    const children = childFoldersOf(f.id);
    const folderAssets = assetsByFolder.get(f.id) ?? [];

    return (
      <div key={f.id} className="pea-material-folder-branch">
        <div className="pea-material-folder-row-wrap">
          <button
            type="button"
            className={`pea-material-folder-row ${isExpanded ? 'expanded' : ''}`}
            style={{ paddingLeft: `${10 + depth * 14}px` }}
            onClick={() => {
              toggleFolder(f.id);
              expandFolder(f.id);
            }}
          >
            <span
              className="pea-material-folder-toggle"
              onClick={(e) => {
                e.stopPropagation();
                toggleFolder(f.id);
              }}
            >
              {children.length > 0 || folderAssets.length > 0 ? (
                isExpanded ? <DownOutlined /> : <RightOutlined />
              ) : (
                <span className="pea-material-folder-toggle-placeholder" />
              )}
            </span>
            <span className="pea-material-folder-icon">
              {isExpanded ? <FolderOpenOutlined /> : <FolderOutlined />}
            </span>
            <span className="pea-material-folder-name">{f.name}</span>
            {folderAssets.length > 0 && (
              <span className="pea-material-folder-count">{folderAssets.length}</span>
            )}
          </button>
          <Dropdown menu={folderMenu(f)} placement="bottomRight" arrow>
            <button type="button" className="pea-material-more" aria-label="更多">
              <MoreOutlined />
            </button>
          </Dropdown>
        </div>

        {isExpanded && (
          <div className="pea-material-folder-children">
            {children.map((child) => renderFolderTree(child, depth + 1))}
            {folderAssets.length > 0 && (
              <div className="pea-material-folder-assets">
                {folderAssets.map((a) => renderAssetThumb(a, 'sm'))}
              </div>
            )}
            {folderAssets.length === 0 && children.length === 0 && (
              <div className="pea-material-folder-empty">该文件夹暂无素材</div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="pea-material-panel">
      <input
        ref={fileInput}
        type="file"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) uploadFile(f);
          e.target.value = '';
        }}
      />

      {/* Header */}
      <div className="pea-material-header">
        <div className="pea-material-header-left">
          <button
            type="button"
            className="pea-material-iconbtn"
            aria-label={view === 'root' ? '关闭' : '返回'}
            onClick={() => {
              if (view === 'root') onClose();
              else setView('root');
            }}
          >
            {view === 'root' ? <CloseOutlined /> : <LeftOutlined />}
          </button>
          <span className="pea-material-title">{title}</span>
        </div>
        <div className="pea-material-header-right">
          <Tooltip title="AI 角色" placement="bottom">
            <button
              type="button"
              className="pea-material-pillbtn"
              aria-label="AI 角色"
              onClick={() => toast.info('AI 角色管理即将开放')}
            >
              <UserOutlined />
              <span>AI 角色</span>
            </button>
          </Tooltip>
          <Dropdown menu={{ items: addMenuItems }} placement="bottomRight" arrow>
            <button type="button" className="pea-material-iconbtn" aria-label="新建">
              <PlusOutlined />
            </button>
          </Dropdown>
        </div>
      </div>

      {/* Scope switch */}
      <div className="pea-material-scope">
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

      {/* Search */}
      <div className="pea-material-search">
        <SearchOutlined />
        <Input
          placeholder="搜索"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          bordered={false}
        />
      </div>

      {/* Body */}
      <div className="pea-material-body">
        {view === 'root' && (
          <>
            <button
              type="button"
              className="pea-material-row"
              onClick={() => setView('favorites')}
            >
              <span className="pea-material-row-icon">
                <StarFilled />
              </span>
              <span className="pea-material-row-label">收藏</span>
            </button>

            <div className="pea-material-section">文件夹</div>
            {folders.length === 0 && !loading && (
              <div className="pea-material-empty">暂无文件夹</div>
            )}
            {rootFolders.map((f) => renderFolderTree(f))}

            {/* 根目录下未归入文件夹的素材 */}
            {(assetsByFolder.get(null)?.length ?? 0) > 0 && (
              <>
                <div className="pea-material-section">未分类</div>
                <div className="pea-material-folder-assets root">
                  {assetsByFolder.get(null)?.map((a) => renderAssetThumb(a, 'sm'))}
                </div>
              </>
            )}
          </>
        )}

        {view === 'favorites' && (
          <>
            {favoriteGroups.length === 0 && !loading && (
              <div className="pea-material-empty">还没有收藏素材</div>
            )}
            {favoriteGroups.map(([day, items]) => (
              <div key={day} className="pea-material-fav-group">
                <div className="pea-material-fav-date">{day}</div>
                <div className="pea-material-fav-grid">
                  {items.map((a) => renderAssetThumb(a, 'md'))}
                </div>
              </div>
            ))}
          </>
        )}

        {view === 'folder' && (
          <>
            {assets.length === 0 && !loading && (
              <div className="pea-material-empty">文件夹为空，点击 + 上传</div>
            )}
            {assets.map((a) => (
              <div key={a.id} className="pea-material-asset">
                <div className="pea-material-asset-thumb">
                  {isImage(a) ? (
                    <img src={a.url} alt={a.name} loading="lazy" />
                  ) : (
                    <PictureOutlined />
                  )}
                </div>
                <div className="pea-material-asset-meta">
                  <div className="pea-material-asset-name" title={a.name}>
                    {a.name}
                  </div>
                  <div className="pea-material-asset-sub">
                    {(a.size / 1024).toFixed(1)} KB · {a.content_type || '文件'}
                  </div>
                </div>
                <div className="pea-material-asset-actions">
                  <button
                    type="button"
                    className={a.is_favorite ? 'favorite' : ''}
                    onClick={() => toggleFavorite(a)}
                    aria-label={a.is_favorite ? '取消收藏' : '收藏'}
                  >
                    {a.is_favorite ? <StarFilled /> : <StarOutlined />}
                  </button>
                  <Dropdown menu={assetMenu(a)} placement="bottomRight" arrow>
                    <button type="button" aria-label="更多">
                      <MoreOutlined />
                    </button>
                  </Dropdown>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
