# 素材库收藏与素材项操作优化完成

## 修复与改动

### 1. 收藏内容不再出现在文件夹树下
- **问题**：root 视图下，收藏素材会显示在文件夹树或根目录素材区域，与「收藏」入口重复。
- **修复**：`MaterialPanel.tsx` 中 `assetsByFolder` 在 `view === 'root'` 时过滤掉 `is_favorite` 素材，收藏内容仅在「收藏」视图展示。

### 2. 节点收藏星标变黄色
- **问题**：浅色主题下 `html:not(.dark) .pea-node-result-star` 选择器优先级更高，覆盖了 `.saved` 样式，导致收藏后星标没变金黄。
- **修复**：`index.css` 新增 `html:not(.dark) .pea-node-result-star.saved` / `:hover` 样式，确保浅/深主题下均为深灰底 + 金黄色星标。

### 3. 素材项操作菜单
- **新增 `MoveToFolderModal.tsx`**：深色树形文件夹选择弹窗，支持选择目标文件夹、内联新建文件夹。
- **扩展 `assetMenu`**：
  - 重命名 → `updateAsset({ name })`
  - 移动到... → `MoveToFolderModal` + `updateAsset({ folder_id })`
  - 创建副本 → `importAsset` 复制同一 object_key
  - 下载 → `url` / BFF 代理 blob URL 下载
  - 收藏/取消收藏 → `updateAsset({ is_favorite })`
  - 删除 → `deleteAsset`
- **菜单样式**：所有素材/文件夹 Dropdown 菜单统一使用 `theme: 'dark'`，贴近参考截图。
- **收藏视图卡片**：新增 hover 显示的右上角「更多」按钮与左上角黄色收藏星标。

## 改动文件

- `pea-server/web/src/components/MaterialPanel.tsx`
- `pea-server/web/src/components/MoveToFolderModal.tsx`（新增）
- `pea-server/web/src/styles/index.css`

## 验证结果

- `pea-server/web`: `npm run build` ✅
- `pea-server/services/bff`: `npm run build` ✅
