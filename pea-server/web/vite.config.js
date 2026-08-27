import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    build: {
        sourcemap: false,
        // 静态产物输出到 /static/ 而非默认的 /assets/, 避免与素材库 API 前缀 /assets 冲突
        // (否则 nginx 会把打包后的 JS/CSS 也代理到 BFF 导致 404 白屏)
        assetsDir: 'static',
        // 本地构建时跳过清空输出目录：当前环境的 node 安全删除 shim 在删除大目录时会抛错，
        // 导致 vite build 的 emptyOutDir 阶段失败。真实 Linux 容器构建不受影响；本地残留的旧
        // chunk 仅未被 index.html 引用、无害。如需彻底清理可手动 rm -rf dist。
        emptyOutDir: false,
    },
    server: {
        port: 5173,
        host: '127.0.0.1',
        proxy: {
            // 所有 BFF 接口统一以 /api 为前缀 (BFF main.ts 已 setGlobalPrefix('api'))。
            // 一条规则覆盖所有 controller, 以后新增接口无需改此处。
            // 默认 path 透传：/api/xxx 完整转发到 BFF (BFF 端路径本就含 /api)。
            '/api': {
                target: 'http://127.0.0.1:4100',
                changeOrigin: true,
            },
            // WebSocket 实时推送不走 /api (前端代码仍是裸 /ws)
            '/ws': { target: 'ws://127.0.0.1:4100', ws: true },
        },
    },
});
