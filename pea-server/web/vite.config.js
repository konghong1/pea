import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    build: {
        sourcemap: false,
        // 沙箱环境 safe-delete shim 无法 trash 文件，emptyOutDir 会失败；关闭后由 CI/部署脚本负责清理 dist。
        // 关闭不影响产物正确性：新构建会写入带 hash 的新文件，index.html 只引用新 hash，旧文件不会被加载。
        emptyOutDir: false,
        // 静态产物输出到 /static/ 而非默认的 /assets/, 避免与素材库 API 前缀 /assets 冲突
        // (否则 nginx 会把打包后的 JS/CSS 也代理到 BFF 导致 404 白屏)
        assetsDir: 'static',
    },
    server: {
        port: 5173,
        proxy: {
            // 开发期把 API/WS 代理到本地 BFF (bff 容器内 4000, 宿主映射 4100; dev 跑在宿主 → 用 4100)
            '/assets': 'http://127.0.0.1:4100',
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
            '/chat': 'http://127.0.0.1:4100',
            '/platform-configs': 'http://127.0.0.1:4100',
            '/usage': 'http://127.0.0.1:4100',
            '/ws': { target: 'ws://127.0.0.1:4100', ws: true },
        },
    },
});
