# 问题4 后端修复总览：@图片发送后生成图不参考原图

## 现象
前端已正确把参考图签名 URL 放进 `/generation/node` 的 `params.reference_images`，
但编排器日志出现 `[refs] dropped 1 unreachable reference image(s)` —— 参考图被静默
丢弃，Agnes 生成的图与参考图"一点关系没有"。

## 真根因（关键认知纠正）
旧假设"localhost:9000 在容器内指向自身、非 MinIO"是**错的**：
- 编排器 MinIO 客户端本就配 `minio:9000`（`docker-compose` 的 `PEA_MINIO_ENDPOINT`），
  下载时**不按 URL 的 host**，而是用自有客户端按提取出的 object key 去 `get_object`。
- 真正的 bug 是 **key 编码错位**：
  - 上传对象以字面 key 存储：`u:594/uploads/xxx.png`（冒号是字面 `:`）
  - BFF 生成的签名 GET URL 路径把 `:` 编码成 `u%3A594/...`
  - 旧 `_extract_minio_key_from_url` 没做 `unquote` → 返回编码 key `u%3A594/...`
    → `get_object` → `NoSuchKey` → 丢弃
- 直接原因：编排器用 `build:`（无 volume 挂载），**运行容器是未含 unquote 修复的旧镜像**，
  源码改了但容器没重建，E2E 持续复现。

## 修复
1. `services/generation-orchestrator/app/param_adapters.py`
   - `_extract_minio_key_from_url`：对 path 做 `unquote`（磁盘源码已含，还原字面 key）。
   - `_resolve_internal_ref_via_minio`：对提取 key 同时尝试「解码后」(`u:594/...`) 与
     「原样」(`u%3A594/...`) 两种候选，`get_object` 任一命中即转 base64，防编码约定差异。
2. `docker compose up -d --build generation-orchestrator` —— **重建镜像**让运行容器吃上新代码
   （Dockerfile 源码 COPY 在 `pip install` 之后，源码改动使该层失效重拷）。

## 验证（全部通过）
- **单元诊断（容器内，用编排器自有模块）**：上传 `u:594/...` 对象 → 构造与 BFF 一致的
  签名 URL（minio:9000→localhost:9000）→ `_normalize_refs([url])` 现返回 `resolved`（不再 dropped）。
- **完整生产路径诊断**：`normalize_image_params` → `reference_images=[data:image/png;base64,…]`；
  `AgnesImageAdapter.build` → `extra_body.image=[data:…]`（参考图确实进入模型请求体）。
- **E2E `verify/verify_ref_issues.py`**：4 项问题全绿，`/generation/node` 捕获
  `reference_images=['http://localhost:9000/pea-media/u%3A594/uploads/…?X-Amz-…']`；
  对应实时 job `status=done`，resultUrl 为 Agnes `/i2i/` 真实出图（图生图模式 → 证明参考图被模型消费）。

## 经验
- Python 服务改源码后**必须重建镜像**（非 volume 挂载），否则运行容器仍是旧代码，
  E2E 会持续复现"已修复"的 bug。
- 诊断容器内逻辑用 `docker cp` 脚本到 `/app` 再 `python` 跑，比在宿主机猜更权威。
