import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useUi, type PageKey } from '../store/ui';

/** 合法的导航页（与 store/ui.ts 的 PageKey 对齐）。 */
const VALID_PAGES: PageKey[] = [
  'home',
  'workspace',
  'canvas',
  'account',
  'settings',
  'ecom',
  'tvtv',
  'arena',
  'plans',
  'admin',
];

/**
 * 解除「崩溃页 → 持久化 → 刷新复现白屏」死锁。
 *
 * 旧逻辑：任何渲染期异常都会整页白屏，而 routePersist 已把 active 写入
 * localStorage，刷新后又从持久化里还原出同一个崩溃页 → 用户「回不到初始状态」。
 *
 * 本边界：
 *   1. 捕获子树渲染异常，展示可恢复的错误卡片（非白屏）；
 *   2. 捕获瞬间即清除持久化路由，使刷新 / 重置都能回到 workspace；
 *   3. 提供「返回工作空间」「刷新页面」两个出口，一键脱离死锁。
 */
function clearPersistedRoute() {
  try {
    localStorage.removeItem('pea_ui_route');
  } catch {
    /* 忽略 */
  }
  useUi.setState({ active: 'workspace', canvasId: null, _stack: ['workspace'] });
}

interface State {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, message: err?.message || String(err) };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 关键：崩溃页一旦被持久化，刷新会无限还原白屏。捕获即清除，解除死锁。
    clearPersistedRoute();
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] 渲染异常已被边界捕获：', error, info);
  }

  private handleReset = () => {
    clearPersistedRoute();
    this.setState({ hasError: false, message: '' });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const isDev = import.meta.env.DEV;
    return (
      <div
        style={{
          position: 'absolute',
          inset: 0,
          zIndex: 9999,
          display: 'grid',
          placeItems: 'center',
          padding: 24,
          background:
            'radial-gradient(1200px 600px at 50% -10%, rgba(127,119,221,0.18), transparent 60%), var(--pea-bg, #f6f7fb)',
        }}
      >
        <div
          style={{
            width: 'min(560px, 100%)',
            background: 'rgba(255,255,255,0.72)',
            backdropFilter: 'blur(24px) saturate(160%)',
            border: '1px solid rgba(127,119,221,0.22)',
            borderRadius: 20,
            padding: '32px 30px',
            boxShadow: '0 24px 70px rgba(20,20,40,0.18)',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: 40, lineHeight: 1, marginBottom: 12 }} aria-hidden>
            🛟
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 700, margin: '0 0 8px', color: '#1d1d2b' }}>
            页面出了点小问题
          </h2>
          <p style={{ fontSize: 13, color: '#6b6b80', margin: '0 0 18px', lineHeight: 1.7 }}>
            我们已拦截这次异常，不会让你卡在白屏。点击下方按钮即可回到工作空间；
            若仍异常，可刷新页面重新加载。
          </p>

          {isDev && this.state.message && (
            <pre
              style={{
                textAlign: 'left',
                fontSize: 12,
                color: '#b42318',
                background: 'rgba(180,35,24,0.06)',
                border: '1px solid rgba(180,35,24,0.18)',
                borderRadius: 10,
                padding: '10px 12px',
                margin: '0 0 18px',
                maxHeight: 160,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {this.state.message}
            </pre>
          )}

          <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
            <button
              onClick={this.handleReset}
              style={{
                appearance: 'none',
                border: 'none',
                cursor: 'pointer',
                background: 'linear-gradient(135deg,#7f77dd,#8b5cf6)',
                color: '#fff',
                fontWeight: 600,
                fontSize: 14,
                padding: '11px 20px',
                borderRadius: 12,
              }}
            >
              返回工作空间
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{
                appearance: 'none',
                cursor: 'pointer',
                background: 'rgba(127,119,221,0.1)',
                border: '1px solid rgba(127,119,221,0.25)',
                color: '#4a4763',
                fontWeight: 600,
                fontSize: 14,
                padding: '11px 20px',
                borderRadius: 12,
              }}
            >
              刷新页面
            </button>
          </div>
        </div>
      </div>
    );
  }
}

/** 校验持久化 active 是否为合法页（防止脏值导致空白页）。 */
export function isValidPage(p: unknown): p is PageKey {
  return typeof p === 'string' && (VALID_PAGES as string[]).includes(p);
}
