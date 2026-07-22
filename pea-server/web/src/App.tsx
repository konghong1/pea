import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme as antdTheme, App as AntApp } from 'antd';
import Login from './components/Login';
import TopNav from './components/TopNav';
import CanvasEditor from './components/CanvasEditor';
import { useAuth } from './store/auth';
import { useTheme } from './store/theme';
import { useWs } from './hooks/useWs';

function Workspace() {
  useWs();
  return (
    <div className="flex h-screen flex-col">
      <TopNav />
      <div className="flex-1 overflow-hidden">
        <CanvasEditor />
      </div>
    </div>
  );
}

export default function App() {
  const token = useAuth((s) => s.token);
  const { mode, init } = useTheme();
  useEffect(() => init(), [init]);

  const isDark =
    mode === 'dark' ||
    (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  return (
    <ConfigProvider
      theme={{
        algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: { colorPrimary: '#6C5CE7' },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={token ? <Workspace /> : <Navigate to="/login" replace />}
            />
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}
