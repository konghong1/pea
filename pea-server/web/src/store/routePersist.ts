/**
 * 路由/画布持久化（极简）：
 * - 把当前导航页 active + 打开的 canvasId 写入 localStorage，
 *   强刷/重开浏览器后由 App 启动还原（仅 token 有效时）。
 * - 与认证无关：token 失效被踢去登录时不动它；重新登录后启动还原仍生效。
 */
const KEY = 'pea_ui_route';

export interface PersistedRoute {
  active: string;
  canvasId: number | null;
}

export function saveRoute(r: PersistedRoute): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(r));
  } catch {
    /* localStorage 不可用时静默 */
  }
}

export function loadRoute(): PersistedRoute | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const r = JSON.parse(raw) as PersistedRoute;
    if (r && typeof r.active === 'string') return r;
  } catch {
    /* 解析失败则当无 */
  }
  return null;
}
