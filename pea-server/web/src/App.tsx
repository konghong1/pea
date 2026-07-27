import { useEffect, useRef } from 'react';
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

export default function App() {
  const token = useAuth((s) => s.token);
  const { mode, init } = useTheme();
  useEffect(() => init(), [init]);
  useEffect(() => installPopState(), []);

  const isDark =
    mode === 'dark' ||
    (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

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
          colorPrimary: '#1fa2dc',
          colorInfo: '#1fa2dc',
          borderRadius: 10,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Noto Sans CJK SC', sans-serif",
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
              element={token ? <Workspace /> : <Navigate to="/login" replace />}
            />
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}
