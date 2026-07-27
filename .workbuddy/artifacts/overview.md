# @ 引用图片输入框裂图修复

## 问题
在节点输入框中用 `@` 引用图片节点（如 `@image#1:Clipboard_Screenshot.png`）时，inline token 显示浏览器默认裂图/破图图标，而非缩略图。

## 根因
- `NodePromptInput.insertRefToken` 在缩略图 URL 尚未解析完成时，直接生成 `<img src="">` 并标记 `data-pea-pending="1"`；部分浏览器对空 `src` 会渲染裂图/alt 占位，CSS 背景无法完全覆盖。
- 即使后续解析出真实 URL（如直接 MinIO presigned），若该 URL 因过期、CORS 或网络失败，也没有任何降级，同样裂图。

## 改动

### `pea-server/web/src/components/NodePromptInput.tsx`
1. 未解析或 URL 不合法时，渲染 `<span class="pea-ref-thumb pea-ref-thumb-fallback-inline">🖼️</span>` 占位图标，彻底避免裂图。
2. token 上记录 `data-file-key`；图片 `onerror` 时优先用 `getFileUrl(fileKey)` 换取 blob URL（走 BFF 代理，稳定可显），仍失败再降级为占位图标。
3. `resolvedThumbs` 更新后，占位图标被替换为真实 `<img>`；已有 `<img>` 仅在实际 URL 变化时更新 `src`。

### `pea-server/web/src/styles/index.css`
- 新增 `.pea-ref-thumb.pea-ref-thumb-fallback-inline`：居中显示图片占位 emoji，与输入框暗黑风格一致。

## 验证与部署
- `npm run build` 通过（`tsc -b && vite build`）。
- 生产构建已 `docker cp` 到 `pea-server-web-1:/usr/share/nginx/html/`，并 `nginx -s reload`。
- `curl localhost:8088/index.html` 确认引用到新 hash 的 `index-CDmkcOaC.js` / `index-oK1Z9cnx.css`。

## 测试建议
1. 打开画布，选中一个图片/生成节点。
2. 在节点下方输入框输入 `@`，选择上游图片节点（尤其上传图）。
3. 观察 inline token：应显示缩略图；若 URL 暂不可用，应显示 🖼️ 占位，而非裂图。
4. 刷新页面重新选中该节点，持久化的 `@` 引用应能恢复显示。
