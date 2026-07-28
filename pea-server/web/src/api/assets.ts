import { api } from './client';

export type AssetScope = 'personal' | 'team';

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
  updateAsset(id: number, payload: Partial<Pick<Asset, 'name' | 'folder_id' | 'is_favorite'>>) {
    return api.patch(`/assets/${id}`, payload);
  },
  deleteAsset(id: number) {
    return api.delete(`/assets/${id}`);
  },
};
