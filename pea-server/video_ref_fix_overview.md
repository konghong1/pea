# 视频生成参考图失效 — 根因修复报告

## 问题现象
用户上传参考图（或使用 AI 生成图作为参考）进行视频生成时，生成的视频与参考图**完全无关**。
从 UI 看，参考图缩略图正常显示、prompt 也正确包含参考说明，但 Agnes 返回的视频仿佛从未见过这张图。

## 根因分析（两个独立 Bug 叠加）

### Bug 1（前端）：`resolveUpstreamMediaUrl` 缺少 scheme 校验 → 相对路径泄漏

**文件**: `web/src/components/NodeChatPrompt.tsx:97`

**机制**:
```
AI 生成图的 resultUrl = "/media/gen/xxx.png"（相对路径, 因 PEA_CDN_BASE_URL=/media）
       ↓
if (firstUrl) return firstUrl;   ← 无任何校验，直接返回
       ↓
reference_images = ["/media/gen/xxx.png"]  ← 发给编排器
       ↓
_normalize_refs() line 178: else: dropped += 1  ← 静默丢弃！
```

**影响范围**: 所有使用 **AI 生成图** 作为视频参考图 的场景。

**修复**: 增加 `firstUrl.startsWith('http')` 校验，非 http(s) URL 强制走 `fileKey → getPresignedUrl` 获取真实签名 URL。

同时修复孪生函数 `NodePromptInput.tsx` 两处相同缺陷（line 65 的 `resolveNodeMediaUrl` 和 line 486 的 `getParsed().referenceImages` 收集逻辑）。

---

### Bug 2（编排器）：内部 URL 转 data URI → 视频接口不认

**文件**: `services/generation-orchestrator/app/agnes_provider.py:358` + `param_adapters.py:170`

**机制**:
```
用户上传的参考图:
  getPresignedUrl(fileKey) → "http://localhost:9000/pea-media/...?X-Amz-..."
       ↓
_is_internal_url("localhost:9000") → True
       ↓
_resolve_internal_ref_via_minio() → 下载图片 → base64 编码
       ↓
"data:image/jpeg;base64,/9j/4AAQ..." (数 MB)
       ↓
payload["image"] = refs[0]   ← data URI 塞给视频接口
       ↓
Agnes 视频 API 的 image 字段只接受可下载的 http(s) URL！
→ 忽略 image 参数 → 视频和参考图无关 ✗
```

**为什么图片生成没问题？** 图片接口走 `extra_body.image[]` 数组，Agnes 图片 API 能接受 data URI。但视频接口的顶层 `image` 字段只认 URL 字符串。

**修复**: 新增 `_ensure_http_refs_for_video()` 函数：
1. 检测到 data URI 时，解码 base64
2. 调用 `storage.store_bytes()` 上传到公开 `gen/` 前缀
3. 返回公网 CDN URL 给 Agnes 下载
4. 若 `PEA_CDN_BASE_URL` 仍为 localhost，记录明确告警

---

## 修改文件清单

| 文件 | 改动 | 目的 |
|------|------|------|
| `web/src/components/NodeChatPrompt.tsx` | line 97 增加 `startsWith('http')` 校验 | 阻止相对路径/blob 泄漏到 reference_images |
| `web/src/components/NodePromptInput.tsx` | line 65 + line 486 同上 | 兜底：@ 引用编辑器的 URL 收集也过滤 |
| `services/generation-orchestrator/app/agnes_provider.py` | 新增 `_ensure_http_refs_for_video()` + line 405 调用 | 将 data URI 转为公网 URL |

---

## 部署步骤

```bash
# 1. 前端构建 + 热部署
cd pea-server/web && npm run build
docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/
docker exec pea-server-web-1 nginx -s reload

# 2. 编排器重新构建（含 Python 代码改动）
cd pea-server
docker compose build generation-orchestrator
docker compose up -d generation-orchestrator

# 3. 验证（看日志确认参考图传递）
docker logs -f pea-server-generation-orchestrator-1 2>&1 | grep -E "\[video-ref\]|\[refs\]"
# 期望看到：
#   [video-ref] data URI (N bytes) 已转存为公开 URL: http://...
#   [agnes] video submit ... refs=1
```

---

## ⚠️ 生产环境必读：CDN 配置

修复代码中包含了 **CDN 可达性检测**：若 `PEA_CDN_BASE_URL` 含 `localhost` 或为相对路径，会输出 WARNING 日志：

```
[video-ref] ⚠️ PEA_CDN_BASE_URL=... 含 localhost 或相对路径 ——
Agnes 等**外部模型**可能无法下载转存后的参考图 URL。
生产环境需将 PEA_CDN_BASE_URL 设为公网可达地址。
```

**生产环境必须确认**：
- 编排器的 `PEA_CDN_BASE_URL` 指向**公网可达地址**（如 `https://your-domain.com/media`）
- 或确保 MinIO / nginx 有对外暴露的端口且 Agnes 可访问
- 否则即使代码正确，外部模型仍无法下载参考图

开发环境（localhost）可通过查看日志确认链路正确，待部署生产时配好公网地址即可。

---

## 验证方法

1. **前端验证**：浏览器 DevTools → Network → `POST /generation/node-jobs` → 查看 `params.reference_images`
   - ✅ 应为 `["http://...?X-Amz-Signature=..."]`（签名 URL）
   - ❌ 不应为 `["/media/gen/xxx.png"]` 或 `["blob:..."]`

2. **编排器验证**：查看日志
   - ✅ `[video-ref] data URI 已转存为公开 URL` 或 refs 直接为 http URL
   - ❌ `[refs] dropped N unreachable reference image(s)`

3. **端到端验证**：用一张特征明显的参考图（如穿蓝色连衣裙的女性）生成视频，检查输出视频中人物服装/外貌是否与参考图一致
