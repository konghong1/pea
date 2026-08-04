import { api } from './client';

export type AssetScope = 'personal' | 'team';

/** 素材库文件夹变更事件名：任何组件创建/修改/删除文件夹后应 dispatch，供需要同步刷新的面板监听。 */
export const ASSET_FOLDERS_CHANGED_EVENT = 'pea:asset-folders-changed';

/** 素材库素材列表变更事件名：任何组件创建/收藏/取消收藏/删除/移动素材后应 dispatch，供需要同步刷新的面板监听。 */
export const ASSET_ASSETS_CHANGED_EVENT = 'pea:asset-assets-changed';

export interface AssetFolder {
  id: number;
  name: string;
  scope: AssetScope;
  parent_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: number;
  folder_id: number | null;
  name: string;
  object_key: string;
  content_type: string;
  size: number;
  scope: AssetScope;
  source: 'upload' | 'generated';
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
  url: string;
}

export const assetsApi = {
  listFolders(scope: AssetScope) {
    return api.get<AssetFolder[]>('/assets/folders', { params: { scope } });
  },
  createFolder(name: string, scope: AssetScope, parent_id?: number | null) {
    return api.post<AssetFolder>('/assets/folders', { name, scope, parent_id });
  },
  updateFolder(id: number, payload: Partial<Pick<AssetFolder, 'name' | 'parent_id'>>) {
    return api.patch<AssetFolder>(`/assets/folders/${id}`, payload);
  },
  deleteFolder(id: number) {
    return api.delete(`/assets/folders/${id}`);
  },
  listAssets(scope: AssetScope, folder_id?: number | null, q?: string) {
    const params: Record<string, any> = { scope };
    if (folder_id !== undefined && folder_id !== null) params.folder_id = folder_id;
    if (q) params.q = q;
    return api.get<Asset[]>('/assets', { params });
  },
  upload(file: File, scope: AssetScope, folder_id?: number | null) {
    const form = new FormData();
    form.append('file', file);
    return api.post<Asset>('/assets/upload', form, {
      params: { scope, folder_id },
    });
  },
  importAsset(
    object_key: string,
    name: string,
    scope: AssetScope,
    folder_id?: number | null,
    is_favorite?: boolean,
  ) {
    return api.post<Asset>('/assets/import', {
      object_key,
      name,
      scope,
      folder_id,
      is_favorite,
    });
  },
  updateAsset(id: number, payload: Partial<Pick<Asset, 'name' | 'folder_id' | 'is_favorite'>>) {
    return api.patch(`/assets/${id}`, payload);
  },
  deleteAsset(id: number) {
    return api.delete(`/assets/${id}`);
  },
};
