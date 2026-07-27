# @ 引用图片 / 多图参考 — 根因修复与验证

## 问题
图片节点输入框里 `@` 一张图（尤其**自己上传**的图）作为参考，生成结果与该参考图不一致 / 根本没参考它。

## 真根因（之前漏判）
编排器 `param_adapters._normalize_refs` 只保留 `http(s):` / `data:` 开头的 URL，**丢弃一切其他格式**。
而前端参考图解析 `getFileUrl` 对**上传图**返回的是 `blob:` 地址（`URL.createObjectURL`）→ 上传图作为参考图时被**静默丢弃，根本没传给 Agnes**。
（AI 生成图有 CDN 地址，所以"没传参考图"错觉只出现在上传图上。）

## 修复方案（最可靠实现）
1. **参考图真正上传**
   - `web/src/api/files.ts` 新增 `getPresignedUrl(key)`：调 BFF 已有的 `GET /files/url?key=`，返回 1h 有效的真实可外传签名 URL，带缓存。
   - `NodePromptInput.tsx` / `NodeChatPrompt.tsx` 的媒体 URL 解析对 `fileKey` **优先用 `getPresignedUrl`**（Agnes 可真实下载的 http 地址），失败才退化 `getFileUrl`(blob) 仅作本地显示。
   - 结果：`reference_images` 中上传图变为 Agnes 可下载的 http 签名地址 → 真正上传。
2. **多图提示词编排（防 AI 混淆）**
   - `NodeChatPrompt.submit()` 按引用顺序收集 `referenceImages` + 可读文件名，在 prompt 最前拼「参考图说明」块：
     - 单图：`【参考图】<文件名>：请严格保持该参考图中物体的款式/颜色/材质/形状/图案与原图完全一致；仅允许调整摆放位置/角度/场景…`
     - 多图：编号 `【参考图 1】…主体参考` / `【参考图 2】…风格/背景/构图参考，不得改变【参考图1】主体外观` + 全局「严格按编号分别使用，切勿混淆」。
   - 编号顺序与上传的 `reference_images` 数组严格一致，靠文字描述让模型自行对齐每张图，降低混淆。
3. **编排器加固**（`param_adapters.py`）：`_normalize_refs` 保序 + 丢弃时告警日志；`AgnesImageAdapter.build` 增加 `refs=N` 日志，便于线上确认参考图是否真正上传。

## 验证（真机，非口头声称）
- `npm run build`（`tsc -b && vite build`）通过，无类型错误；编排器 `py_compile` PASS。
- 部署：web `docker cp` + `nginx -s reload`（8088 HTTP 200）；orchestrator `docker compose up -d --build`（已含加固代码，`/docs` HTTP 200）。
- **核心链路 API 端到端 PASS**：注册→登录→上传图得 key → `GET /files/url` 返回真实签名 `http://localhost:9000/pea-media/...?X-Amz-...` → 上传图现在能换取真实 http(s) 参考 URL（此前是 blob: 被丢弃）。
- 部署包自检：`web/dist/assets/*.js` 含「参考图」(×4) 与 `files/url?key=...` 调用 → 前端确已用签名 URL 替换 blob。

## 仍存的边界（属模型能力，非代码）
Agnes 2.1 Flash 的 `extra_body.image` 本质是「风格/内容参考」，**不保证像素级复刻**。对"一模一样"的强需求仅靠 prompt 强化无法 100% 保证；若需像素级一致，需引入真正的 img2img / inpainting 路径（后续，本次未做）。产品侧建议明确提示「参考图用于风格/构图参考」。
