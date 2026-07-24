import { api } from './client';

/** 列表项类型（与 BFF `canvases.service.list` 返回对齐）。 */
export interface CanvasItem {
  id: number;
  title: string;
  scope: 'personal' | 'team';
  folder_id: number | null;
  share_token: string | null;
  thumbnail_url: string | null;
  version: number;
  node_count: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface CanvasDetail extends CanvasItem {
  graph_json: { nodes: any[]; edges: any[] } | string;
}

export interface CanvasFolder {
  id: number;
  name: string;
  scope: 'personal' | 'team';
  parent_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ListQuery {
  scope?: 'personal' | 'team' | 'trash' | 'all';
  folder_id?: number | '0';
  q?: string;
  limit?: number;
}

export const canvasesApi = {
  list: (q: ListQuery = {}) =>
    api
      .get<CanvasItem[]>('/canvases', { params: q })
      .then((r) => r.data ?? []),

  get: (id: number) =>
    api.get<CanvasDetail>(`/canvases/${id}`).then((r) => r.data),

  create: (title?: string, scope: 'personal' | 'team' = 'personal', folder_id?: number | null) =>
    api
      .post<{ id: number; title: string; scope: string; version: number }>('/canvases', {
        title: title ?? '未命名画布',
        scope,
        folder_id: folder_id ?? null,
      })
      .then((r) => r.data),

  save: (id: number, graph_json: object, version: number) =>
    api.put<{ id: number; version: number }>(`/canvases/${id}`, { graph_json, version }).then((r) => r.data),

  update: (id: number, patch: { title?: string; scope?: 'personal' | 'team'; folder_id?: number | null; thumbnail_url?: string | null; deleted?: boolean }) =>
    api.patch(`/canvases/${id}`, patch).then((r) => r.data),

  remove: (id: number) => api.delete(`/canvases/${id}`).then((r) => r.data),

  // 分享
  share: (id: number) =>
    api.post<{ token: string }>(`/canvases/${id}/share`).then((r) => r.data),
  revokeShare: (id: number) =>
    api.delete(`/canvases/${id}/share`).then((r) => r.data),

  // 文件夹
  folders: (scope: 'personal' | 'team' = 'personal') =>
    api.get<CanvasFolder[]>('/canvases/folders/list', { params: { scope } }).then((r) => r.data ?? []),
  createFolder: (name: string, scope: 'personal' | 'team' = 'personal') =>
    api.post<{ id: number; name: string }>('/canvases/folders', { name, scope }).then((r) => r.data),
  renameFolder: (id: number, name: string) =>
    api.patch(`/canvases/folders/${id}`, { name }).then((r) => r.data),
  deleteFolder: (id: number) =>
    api.delete(`/canvases/folders/${id}`).then((r) => r.data),
};