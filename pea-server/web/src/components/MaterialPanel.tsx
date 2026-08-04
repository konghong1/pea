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
  CopyOutlined,
  DownloadOutlined,
  CloseOutlined,
  FileOutlined,
  PictureOutlined,
} from '@ant-design/icons';
import { App, Button, Dropdown, Input, Modal, Tooltip } from 'antd';
import {
  assetsApi,
  ASSET_FOLDERS_CHANGED_EVENT,
  ASSET_ASSETS_CHANGED_EVENT,
  type AssetFolder,
  type Asset,
  type AssetScope,
} from '../api/assets';
import { getFileUrl } from '../api/files';
import { toast } from '../store/toast';
import MoveToFolderModal from './MoveToFolderModal';
import AssetLightbox from './AssetLightbox';

type View = 'root' | 'favorites' | 'folder';

interface MaterialPanelProps {
  onClose: () => void;
}

/** 素材缩略图：优先用后端 url，裂图时走 BFF 代理 blob URL 兜底。 */
function AssetThumb({
  asset,
  size = 'sm',
  showLabel = false,
  className = '',
  onClick,
}: {
  asset: Asset;
  size?: 'sm' | 'md';
  showLabel?: boolean;
  className?: string;
  onClick?: (asset: Asset) => void;
}) {
  const [src, setSrc] = useState(asset.url);
  const isImage = /^image\//.test(asset.content_type);
  const isVideo = /^video\//.test(asset.content_type);

  useEffect(() => {
    setSrc(asset.url);
  }, [asset.url]);

  const handleError = useCallback(async () => {
    if (!isImage && !isVideo) return;
    try {
      const blobUrl = await getFileUrl(asset.object_key);
      if (blobUrl) setSrc(blobUrl);
    } catch {
      // 兜底失败则保留占位
    }
  }, [asset.object_key, isImage, isVideo]);

  const handleClick = () => {
    if (onClick && (isImage || isVideo)) onClick(asset);
  };

  return (
    <div
      className={`pea-material-thumb ${size} ${className} ${onClick && (isImage || isVideo) ? 'previewable' : ''}`}
      title={asset.name}
      onClick={handleClick}
      role={onClick && (isImage || isVideo) ? 'button' : undefined}
      tabIndex={onClick && (isImage || isVideo) ? 0 : undefined}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && onClick && (isImage || isVideo)) {
          e.preventDefault();
          onClick(asset);
        }
      }}
    >
      <div className="pea-material-thumb-img">
        {isImage ? (
          <img src={src} alt="" loading="lazy" onError={handleError} />
        ) : isVideo ? (
          <video src={src} muted preload="metadata" onError={handleError} />
        ) : (
          <PictureOutlined />
        )}
      </div>
      {showLabel && <div className="pea-material-thumb-label">{asset.name}</div>}
    </div>
  );
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
  const [moveTarget, setMoveTarget] = useState<Asset | null>(null);
  const [previewAsset, setPreviewAsset] = useState<Asset | null>(null);
  const [togglingFavoriteId, setTogglingFavoriteId] = useState<number | null>(null);
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
        // 收藏素材只在「收藏」入口展示，避免在文件夹视图重复出现
        setAssets(data.filter((a) => !a.is_favorite));
      } else if (view === 'root') {
        // 文件库根目录：仅展示未分类且未收藏的素材
        // 已收藏的素材只在「收藏」入口出现，避免与收藏视图重复
        const { data } = await assetsApi.listAssets(scope, null, query);
        setAssets(data.filter((a) => !a.is_favorite));
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

  // 监听其他组件（如 SaveToLibraryModal / MoveToFolderModal）新建的文件夹，即时刷新左侧树
  useEffect(() => {
    const handleFoldersChanged = () => refreshFolders();
    window.addEventListener(ASSET_FOLDERS_CHANGED_EVENT, handleFoldersChanged);
    return () => window.removeEventListener(ASSET_FOLDERS_CHANGED_EVENT, handleFoldersChanged);
  }, [refreshFolders]);

  // 监听素材变更事件（如节点一键收藏、保存到素材库、取消收藏等），即时刷新当前素材列表
  useEffect(() => {
    const handleAssetsChanged = () => refreshAssets();
    window.addEventListener(ASSET_ASSETS_CHANGED_EVENT, handleAssetsChanged);
    return () => window.removeEventListener(ASSET_ASSETS_CHANGED_EVENT, handleAssetsChanged);
  }, [refreshAssets]);

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
    if (togglingFavoriteId === a.id) return;
    const nextFavorite = !a.is_favorite;
    setTogglingFavoriteId(a.id);
    // 乐观更新：先在本地刷新状态，让 UI 立即响应
    setAssets((prev) => prev.map((item) => (item.id === a.id ? { ...item, is_favorite: nextFavorite } : item)));
    try {
      await assetsApi.updateAsset(a.id, { is_favorite: nextFavorite });
      // folder 视图下收藏后、或 favorites 视图下取消收藏后，应立刻从当前列表消失
      if ((view === 'folder' && nextFavorite) || (view === 'favorites' && !nextFavorite)) {
        setAssets((prev) => prev.filter((item) => item.id !== a.id));
      }
      // 其他情况整列表刷新，保证跨视图一致性
      if (!((view === 'folder' && nextFavorite) || (view === 'favorites' && !nextFavorite))) {
        refreshAssets();
      }
    } catch {
      toast.error('操作失败');
      // 失败回滚：恢复原来的收藏状态并重新拉取
      setAssets((prev) => prev.map((item) => (item.id === a.id ? { ...item, is_favorite: a.is_favorite } : item)));
      refreshAssets();
    } finally {
      setTogglingFavoriteId(null);
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

  const renameAsset = (a: Asset) => {
    let value = a.name;
    modal.confirm({
      title: '重命名',
      content: (
        <Input
          defaultValue={a.name}
          maxLength={80}
          onChange={(e) => {
            value = e.target.value;
          }}
          onPressEnter={() => {
            Modal.destroyAll();
            doRenameAsset(a.id, value);
          }}
        />
      ),
      onOk: () => doRenameAsset(a.id, value),
    });
  };

  const doRenameAsset = async (id: number, name: string) => {
    const n = name.trim();
    if (!n) return;
    try {
      await assetsApi.updateAsset(id, { name: n });
      refreshAssets();
      message.success('已重命名');
    } catch {
      toast.error('重命名失败');
    }
  };

  const duplicateAsset = async (a: Asset) => {
    try {
      await assetsApi.importAsset(
        a.object_key,
        `${a.name.replace(/\.[^.]+$/, '')} 副本`,
        a.scope,
        a.folder_id,
        a.is_favorite,
      );
      refreshAssets();
      message.success('已创建副本');
    } catch {
      toast.error('创建副本失败');
    }
  };

  const downloadAsset = async (a: Asset) => {
    try {
      const url = a.url || (await getFileUrl(a.object_key));
      if (!url) return;
      const link = document.createElement('a');
      link.href = url;
      link.download = a.name;
      link.target = '_blank';
      link.rel = 'noreferrer';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch {
      toast.error('下载失败');
    }
  };

  const doMoveAsset = async (a: Asset, folderId: number | null) => {
    try {
      await assetsApi.updateAsset(a.id, { folder_id: folderId });
      refreshAssets();
      message.success('已移动');
    } catch {
      toast.error('移动失败');
    }
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
    theme: 'dark' as const,
    items: [
      { key: 'rename', icon: <EditOutlined />, label: '重命名', onClick: () => renameFolder(f) },
      { key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true, onClick: () => deleteFolder(f) },
    ],
  });

  const assetMenu = (a: Asset) => ({
    theme: 'dark' as const,
    items: [
      {
        key: 'rename',
        icon: <EditOutlined />,
        label: '重命名',
        onClick: () => renameAsset(a),
      },
      {
        key: 'move',
        icon: <FolderOpenOutlined />,
        label: '移动到...',
        onClick: () => setMoveTarget(a),
      },
      {
        key: 'duplicate',
        icon: <CopyOutlined />,
        label: '创建副本',
        onClick: () => duplicateAsset(a),
      },
      {
        key: 'download',
        icon: <DownloadOutlined />,
        label: '下载',
        onClick: () => downloadAsset(a),
      },
      {
        key: 'favorite',
        icon: a.is_favorite ? <StarOutlined /> : <StarFilled />,
        label: a.is_favorite ? '取消收藏' : '收藏',
        disabled: togglingFavoriteId === a.id,
        onClick: () => toggleFavorite(a),
      },
      {
        key: 'delete',
        icon: <DeleteOutlined />,
        label: '删除',
        danger: true,
        onClick: () => deleteAsset(a),
      },
    ],
  });

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
    // root 视图下，收藏素材只在「收藏」入口展示，避免在文件夹树/根目录区域重复出现
    const source = view === 'root' ? assets.filter((a) => !a.is_favorite) : assets;
    const map = new Map<number | null, Asset[]>();
    source.forEach((a) => {
      const key = a.folder_id ?? null;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(a);
    });
    return map;
  }, [assets, view]);

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
    <AssetThumb key={a.id} asset={a} size={size} onClick={(asset) => setPreviewAsset(asset)} />
  );

  /** root / folder 视图下素材卡片：缩略图 + 收藏 + 更多 */
  const renderAssetCard = (a: Asset, size: 'sm' | 'md' = 'sm') => (
    <div key={a.id} className="pea-material-thumb-wrap" title={a.name}>
      <AssetThumb asset={a} size={size} onClick={(asset) => setPreviewAsset(asset)} />
      <div className="pea-material-thumb-actions">
        <button
          type="button"
          className={a.is_favorite ? 'favorite' : ''}
          disabled={togglingFavoriteId === a.id}
          onClick={(e) => {
            e.stopPropagation();
            toggleFavorite(a);
          }}
          aria-label={a.is_favorite ? '取消收藏' : '收藏'}
          title={a.is_favorite ? '取消收藏' : '收藏'}
        >
          {a.is_favorite ? <StarFilled /> : <StarOutlined />}
        </button>
        <Dropdown menu={assetMenu(a)} placement="bottomRight" arrow>
          <button type="button" aria-label="更多" title="更多">
            <MoreOutlined />
          </button>
        </Dropdown>
      </div>
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
              <div className="pea-material-asset-list">
                {folderAssets.map((a) => (
                  <div key={a.id} className="pea-material-asset-item" title={a.name}>
                    <AssetThumb asset={a} size="sm" onClick={(asset) => setPreviewAsset(asset)} />
                    <span className="pea-material-asset-item-name">{a.name}</span>
                    <button
                      type="button"
                      className={`pea-material-asset-item-favorite ${a.is_favorite ? 'favorite' : ''}`}
                      disabled={togglingFavoriteId === a.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleFavorite(a);
                      }}
                      aria-label={a.is_favorite ? '取消收藏' : '收藏'}
                      title={a.is_favorite ? '取消收藏' : '收藏'}
                    >
                      {a.is_favorite ? <StarFilled /> : <StarOutlined />}
                    </button>
                    <Dropdown menu={assetMenu(a)} placement="bottomRight" arrow>
                      <button type="button" className="pea-material-more" aria-label="更多">
                        <MoreOutlined />
                      </button>
                    </Dropdown>
                  </div>
                ))}
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
          <Dropdown menu={{ items: addMenuItems, theme: 'dark' }} placement="bottomRight" arrow>
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

            {/* 根目录下未归入文件夹的素材，直接展示不再显示“未分类”标题 */}
            {(assetsByFolder.get(null)?.length ?? 0) > 0 && (
              <div className="pea-material-root-assets">
                {assetsByFolder.get(null)?.map((a) => renderAssetCard(a, 'sm'))}
              </div>
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
                  {items.map((a) => (
                    <div key={a.id} className="pea-material-thumb-wrap" title={a.name}>
                      <button
                        type="button"
                        className="pea-material-fav-star"
                        disabled={togglingFavoriteId === a.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleFavorite(a);
                        }}
                        aria-label="取消收藏"
                        title="取消收藏"
                      >
                        <StarFilled />
                      </button>
                      <AssetThumb asset={a} size="md" onClick={(asset) => setPreviewAsset(asset)} />
                      <div className="pea-material-thumb-actions">
                        <Dropdown menu={assetMenu(a)} placement="bottomRight" arrow>
                          <button type="button" aria-label="更多">
                            <MoreOutlined />
                          </button>
                        </Dropdown>
                      </div>
                    </div>
                  ))}
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
            <div className="pea-material-folder-assets root">
              {assets.map((a) => (
                <div key={a.id} className="pea-material-thumb-wrap" title={a.name}>
                  <AssetThumb asset={a} size="sm" onClick={(asset) => setPreviewAsset(asset)} />
                  <div className="pea-material-thumb-actions">
                    <button
                      type="button"
                      className={a.is_favorite ? 'favorite' : ''}
                      disabled={togglingFavoriteId === a.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleFavorite(a);
                      }}
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
            </div>
          </>
        )}
      </div>

      <MoveToFolderModal
        open={!!moveTarget}
        onClose={() => setMoveTarget(null)}
        scope={scope}
        onMove={async (folderId) => {
          if (moveTarget) await doMoveAsset(moveTarget, folderId);
        }}
        onFoldersChange={refreshFolders}
      />

      <AssetLightbox asset={previewAsset} onClose={() => setPreviewAsset(null)} />
    </div>
  );
}
