import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    build: {
        sourcemap: false,
    },
    server: {
        port: 5173,
        proxy: {
            // 开发期把 API/WS 代理到本地 BFF (bff 容器内 4000, 宿主映射 4100; dev 跑在宿主 → 用 4100)
            '/auth': 'http://127.0.0.1:4100',
            '/users': 'http://127.0.0.1:4100',
            '/billing': 'http://127.0.0.1:4100',
            '/generation': 'http://127.0.0.1:4100',
            '/files': 'http://127.0.0.1:4100',
            '/canvases': 'http://127.0.0.1:4100',
            '/shared': 'http://127.0.0.1:4100',
            '/providers': 'http://127.0.0.1:4100',
            '/works': 'http://127.0.0.1:4100',
            '/internal': 'http://127.0.0.1:4100',
            '/admin': 'http://127.0.0.1:4100',
            '/models': 'http://127.0.0.1:4100',
            '/plans': 'http://127.0.0.1:4100',
            '/ws': { target: 'ws://127.0.0.1:4100', ws: true },
        },
    },
});
