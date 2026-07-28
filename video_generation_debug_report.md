# Agnes 视频生成排查报告（agnes-video-v2.0）

> 排查对象：`pea-server/services/generation-orchestrator/app/agnes_provider.py` 等视频生成链路
> 对照基准：官方文档 https://agnes-ai.com/zh-Hans/docs/agnes-video-v20
> 结论：**不是单点故障，是「参数形状错 + 参数被静默丢弃 + 轮询超时」三处叠加**。后端确凿 bug 已修复。

---

## 一、TL;DR（先看这个）

| # | 问题 | 严重度 | 状态 |
|---|------|--------|------|
| 1 | **图生视频单图参数形状错**：1 张参考图被塞进 `extra_body.image=["url"]` 数组，无 `mode`；官方要求是顶层 `image="url"`(字符串) + `mode:"ti2vid"` | 🔴 高（图片类视频必失败/被忽略） | ✅ 已修 |
| 2 | **`duration` 传字符串 `"5s"`**，后端 `int("5s")` 抛错被兜底成 5s → UI 选的时长永远无效 | 🟠 中（参数没传对，你问的就是这个） | ✅ 已修（后端兼容） |
| 3 | **`num_frames` 未归一化**：`duration*frame_rate+1` 违反 Agnes 硬约束 `≤441 且 8n+1` → 400 | 🟠 中（非 24 帧率/长视频必炸） | ✅ 已修 |
| 4 | **`gen_mode`/`audio_enabled` 后端完全没读**，UI 选择的生成模式无效 | 🟡 低（功能缺失，非必崩） | ✅ 已修 |
| 5 | **`video_poll_max_s=300`** 小于 Agnes 晚高峰真实出片 5–10 分钟 → 长任务被误杀成 failed | 🔴 高（高峰必失败） | ✅ 已修（→900） |
| 6 | **配置项需你确认**：`model_name` 是否严格 `agnes-video-v2.0`、`base_url`、`api_key` | ⚠️ 待你核查 | 👉 见第四节 |

---

## 二、与官方文档逐项比对（请求体）

官方 `POST /v1/videos` 参数：

| 参数 | 官方要求 | 我们代码实际 | 判定 |
|------|----------|--------------|------|
| `model` | 字符串，必须 `agnes-video-v2.0` | `self.model_name`（来自 DB `ai_models`） | ✅ 取决于配置（见四） |
| `prompt` | 字符串，必填 | `req["prompt"]` | ✅ |
| `image` | **字符串**（图生视频单图 URL） | 旧：1 图时塞进 `extra_body.image` 数组 ❌ | 🔴 已修为顶层字符串 |
| `extra_body.image` | **数组**（关键帧多图） | ≥2 图时 `extra_body.image=[...]` | ✅ 正确 |
| `mode` | `ti2vid` / `keyframes` | 旧：仅 ≥2 图时 `keyframes`，单图无 mode ❌ | 🔴 已修：单图 `ti2vid` |
| `height`/`width` | 整数，可省略（自动映射到 480p/720p/1080p） | 前端算好传入，后端 clamp 64–4096 | ✅ 可接受 |
| `num_frames` | **必须 ≤441 且 8n+1** | 旧：直接计算不校验 ❌ | 🔴 已修：归一化 |
| `frame_rate` | 1–60 | 默认 24，clamp 1–60 | ✅ |
| `duration` | ——（我们用它推 `num_frames`） | 前端传 `"5s"` 字符串 ❌ | 🔴 已修：剥单位 |
| `seed` | 整数 | 透传 | ✅ |
| `negative_prompt` | 字符串 | 未传（可选，无害） | ✅ |
| `gen_mode`/`audio_enabled` | ——（前端扩展字段） | 旧：完全忽略 ❌ | 🟡 已修：读 `gen_mode` |

---

## 三、4 个代码层问题的根因与修复

### 问题 1（图生视频核心 bug）— `agnes_provider.py:_build_video_payload`

**旧代码（错）**
```python
if refs:
    if _is_agnes(self.base_url):
        extra = payload.setdefault("extra_body", {})
        extra["image"] = refs              # ← 单图也变成数组 ["url"]
        if len(refs) > 1:
            extra["mode"] = "keyframes"     # ← 单图根本没有 mode
```

**官方形态**
- 1 图（img2vid）：`{ "image": "https://...png", "mode": "ti2vid" }`（顶层字符串）
- ≥2 图（keyframes）：`{ "extra_body": { "image": [...], "mode": "keyframes" } }`

**修复后**
```python
if refs:
    if len(refs) == 1 and gen_mode != "keyframes":
        payload["image"] = refs[0]          # 顶层字符串
        payload["mode"] = "ti2vid"
    else:
        extra = payload.setdefault("extra_body", {})
        extra["image"] = refs
        extra["mode"] = "keyframes"
```

### 问题 2（duration 被静默丢弃）
前端 `NodeChatPrompt.tsx` 发 `mergedParams.duration = '5s'`（字符串）。
后端 `_clamp_int('5s', ...)` 里 `int('5s')` 抛 `ValueError` → 返回默认 `5`。
**修复**：后端先 `raw_dur.rstrip("sS")` 再转整秒，UI 选 10s/15s 等都生效。

### 问题 3（num_frames 越界 → 400）
`num_frames = duration*frame_rate+1` 从不校验。`frame_rate=30` 时 `5*30+1=151`，`151-1=150` 不是 8 的倍数 → 违反 `8n+1`；`duration` 大时还会超 441。
**修复**：`min(441)` 后再向下取整到最近的 `8n+1`，下限 9。

### 问题 4（生成模式选择无效）
前端发 `gen_mode`，后端根本没读，纯靠参考图数量隐式推断。
**修复**：读 `params.gen_mode`，识别 `keyframes`；其余按参考图数量推断（0 图=文生视频，1 图=图生视频）。

### 问题 5（轮询超时误杀长任务）— `config.py`
`video_poll_max_s=300`，但 Agnes 晚高峰真实出片常需 5–10 分钟（你的 `provider_video_submit_timeout_s` 注释已承认这点）。超过 5 分钟的视频任务会被 Completer 判 timeout → failed → 退款。
**修复**：`video_poll_max_s` 300 → **900**（与 submit 超时对齐）。该值无 env 覆盖，config.py 默认值生效。

---

## 四、需要你这边确认的配置（我看不到你的 DB）

视频请求体的 `model` 来自 `ai_models.model_name`，`base_url`/`api_key` 来自 `ai_providers`。这些在 Admin 后台配，代码里没有硬编码默认值。请用下面的命令直接打 Agnes 验证：

```bash
# 1) 纯文生视频（最小可复现，先排除参数问题）
curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer <你的_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A cat walking on the beach at sunset, cinematic",
    "height": 768, "width": 1152, "num_frames": 121, "frame_rate": 24
  }'

# 2) 图生视频（验证单图形态）
curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer <你的_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "The woman slowly turns around, cinematic",
    "image": "https://example.com/your-image.png",
    "mode": "ti2vid",
    "num_frames": 121, "frame_rate": 24
  }'
```

**判定标准**
- `401` → `api_key` 错/失效（改 Admin 里的 key）
- `400` 且报 `model` → `ai_models.model_name` 不是严格 `agnes-video-v2.0`（注意大小写）
- `404` → `base_url` 不对（应为 `https://apihub.agnes-ai.com`，代码会自动拼 `/v1/videos`）
- 返回 `task_id`/`video_id` → 配置 OK，问题在代码（已修复）

另外请在 Admin → 模型管理确认：**视频模型的 `model_name` 字段一字不差 = `agnes-video-v2.0`**，且绑定的 provider `base_url` 不含多余路径、key 有效。

---

## 五、部署提醒（重要）

容器 `/app` 是镜像内烘焙，代码改动**必须 rebuild 才生效**：
```bash
cd pea-server
docker compose build generation-orchestrator && docker compose up -d generation-orchestrator
# 前端若有改动（本次未改前端，duration 已由后端兼容）才需要：
# docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/ && docker exec pea-server-web-1 nginx -s reload
```

---

## 六、给团队的代码质量建议（资深视角）

1. **参数防腐层 100% 对齐官方「字段名 + 类型 + 单/复数值形态」**。本次根因就是：单图应是*字符串* `image`，代码却发成*数组*；`mode` 是枚举，却靠数量隐式推断。建议给 `agnes_provider` 写一份 **schema 断言测试**，每次升级模型就把官方示例请求体贴进去跑 diff。
2. **枚举参数显式映射，不要隐式推断**。生成模式（ti2vid/keyframes）应由前端 `gen_mode` 显式驱动，失败要有明确报错，而不是"猜"。
3. **外部 API 的数值硬约束必须在防腐层兜底**。`num_frames` 的 `8n+1`/`≤441` 是 Agnes 铁律，应在发请求前归一化，而不是等 400 才暴露。
4. **超时配置要和真实 SLA 对齐并集中管理**。`video_poll_max_s` 与 `provider_video_submit_timeout_s` 要一起看，避免"提交能等 15 分钟、轮询却只等 5 分钟"的自相矛盾。
5. **前端→后端参数要有类型契约**。前端发 `"5s"` 字符串、后端当整数，这种类型错应在 BFF 的 DTO/校验层就拦下，而不是在 `_clamp_int` 里静默兜底成默认值（静默兜底 = Bug 伪装成"正常"）。

---
*已修改文件：`pea-server/services/generation-orchestrator/app/agnes_provider.py`、`pea-server/services/generation-orchestrator/app/config.py`。*
