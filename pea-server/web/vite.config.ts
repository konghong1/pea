import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 开发期把 API/WS 代理到本地 BFF
      '/auth': 'http://localhost:4000',
      '/users': 'http://localhost:4000',
      '/billing': 'http://localhost:4000',
      '/generation': 'http://localhost:4000',
      '/files': 'http://localhost:4000',
      '/canvases': 'http://localhost:4000',
      '/shared': 'http://localhost:4000',
      '/providers': 'http://localhost:4000',
      '/works': 'http://localhost:4000',
      '/internal': 'http://localhost:4000',
      '/ws': { target: 'ws://localhost:4000', ws: true },
    },
  },
});
