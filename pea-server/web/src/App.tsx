import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme as antdTheme, App as AntApp } from 'antd';
import Login from './components/Login';
import Workspace from './components/Workspace';
import Toast from './components/Toast';
import { useAuth } from './store/auth';
import { useTheme } from './store/theme';

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
