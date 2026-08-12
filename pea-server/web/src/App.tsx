import { useEffect, useRef, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme as antdTheme, App as AntApp } from 'antd';
import Login from './components/Login';
import Workspace from './components/Workspace';
import Toast from './components/Toast';
import { useAuth } from './store/auth';
import { useTheme } from './store/theme';
import { useUi, PageKey, installPopState } from './store/ui';
import { useCanvas } from './store/canvas';
import { loadRoute } from './store/routePersist';
import ErrorBoundary from './components/ErrorBoundary';

export default function App() {
  const token = useAuth((s) => s.token);
  const { mode, init } = useTheme();
  useEffect(() => init(), [init]);
  useEffect(() => installPopState(), []);

  // 跟随系统：订阅系统配色变化，使 antd 算法与自定义令牌实时联动。
  const [sysDark, setSysDark] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => setSysDark(mq.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const isDark =
    mode === 'dark' || (mode === 'system' && sysDark);

  // antd 令牌随主题走：明→黑药丸白字，暗→白药丸深字，info=AI 紫。
  // 解决深色模式下近黑文字叠近黑背景导致组件内文字不可见的问题。
  const themeTokens = isDark
    ? {
        colorPrimary: '#e4e4e7',
        colorInfo: '#a78bfa',
        colorText: '#f5f5f5',
        colorTextSecondary: '#a1a1a1',
        colorBgContainer: '#111111',
        colorBgElevated: '#1a1a1a',
        colorBorder: '#27272a',
        colorBorderSecondary: '#27272a',
      }
    : {
        colorPrimary: '#171717',
        colorInfo: '#8b5cf6',
        colorText: '#171717',
        colorTextSecondary: '#4d4d4d',
        colorBgContainer: '#ffffff',
        colorBgElevated: '#ffffff',
        colorBorder: '#ebebeb',
        colorBorderSecondary: '#ebebeb',
      };

  // 启动还原：token 有效时，读回上次导航页/打开的画布（强刷不丢位置）。
  const restoredRef = useRef(false);
  useEffect(() => {
    if (!token || restoredRef.current) return;
    restoredRef.current = true;
    const r = loadRoute();
    if (!r) return;
    const ui = useUi.getState();
    if (r.active === 'canvas' && r.canvasId) {
      ui.setActive('canvas');
      useCanvas
        .getState()
        .openCanvas(r.canvasId)
        .catch(() => ui.setActive('workspace'));
    } else if (r.active && r.active !== 'login') {
      ui.setActive(r.active as PageKey);
    }
  }, [token]);

  return (
    <ConfigProvider
      theme={{
        algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          ...themeTokens,
          borderRadius: 6,
          fontFamily:
            "'Geist', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Noto Sans CJK SC', sans-serif",
        },
      }}
    >
      <AntApp>
        <Toast />
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                token ? (
                  <ErrorBoundary>
                    <Workspace />
                  </ErrorBoundary>
                ) : (
                  <Navigate to="/login" replace />
                )
              }
            />
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}
