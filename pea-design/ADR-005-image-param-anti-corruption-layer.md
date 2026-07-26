# ADR-005: 图像生成参数防腐层（按模型/提供商封装）

## Status
Accepted

## Context
节点聊天 Agent 调 Agnes 出图。接官方文档 `agnes-image-2.1-flash` 后核对代码，发现 3 个与文档不符、且会在“接入新模型”时必然爆发的兼容性问题：

1. **比例选择是死代码**：前端已计算并下发 `aspectRatio`（如 `16:9`），但后端 `_generate_image` 只用 `_map_size` 发精确像素 `size:"2048x2048"`，**从不发 `ratio`** → 用户选 16:9 也永远返回 1:1。
2. **图生图参数放错位置**：现状把 `image` 放**请求顶层**还加 `tags:["img2img"]`；文档要求 `image` 必须进 `extra_body.image`，且**禁止** `tags`。
3. **size 用精确像素而非档位式**：文档推荐 `"1K"/"2K"/"3K"/"4K"` 档位配合 `ratio`；发 `2048x2048` 仅在“恰好是 1:1 的 2K”时侥幸不出错，换只认档位的模型会标准化错误或直接 400。

用户明确诉求：“后续配置的模型调用不兼容之类的会不有问题，所以我想抽象一层，针对不同的模型传参数的封装。”——典型的防腐层（Anti-Corruption Layer）/ Strategy 场景：前端只讲规范参数，模型差异收敛到一层。

## Decision
在 `generation-orchestrator/app/param_adapters.py` 新增参数适配器层：

- `NormImageParams`：规范参数（系统与前端通用语）——`prompt / n / size_tier / aspect_ratio / seed / reference_images`。
- `ImageParamAdapter`（ABC）+ 两个实现：
  - `AgnesImageAdapter`：`size` 发档位式 `"2K"`，带 `ratio`；图生图 `image` 进 `extra_body`，**不发 `tags`**。
  - `GenericOpenAIImageAdapter`：按 DALL·E 约定把档位映射到精确像素 `size`，不认 `ratio`。
- `get_image_adapter(base_url)`：按提供商族分派，默认回退 Generic。**接入新模型 = 在此加一个分支/注册项，不动 provider 主流程，也不让前端耦合具体模型。**

`agnes_provider._generate_image` 改为：`norm = normalize_image_params(req)` → `adapter = get_image_adapter(self.base_url)` → `payload = adapter.build(norm, self)`。原 `_map_size`、`_normalize_refs` 迁移进 `param_adapters`（`_normalize_refs` 供视频路径复用）。

前端无需改动：其 `params` 已带 `resolution`（档位）与 `aspectRatio`，适配器直接采用。

## Consequences
- **易**：比例选择真实生效（16:9 → 2624x1472）；图生图参数位置正确；size 用文档推荐的档位式。
- **易**：后续接入 DALL·E / 其它 OpenAI 兼容模型只需新增一个 adapter，主流程零改动；新增模型不兼容风险被隔离在适配器内。
- **难**：多一层抽象（但远比散落的 `_is_agnes` 分支好维护）；每个 adapter 需按其模型文档核对（已在 `param_adapters.py` 内注释写明文档约束）。
- **验证**：单元测试确认三种负载形状正确；真实 Agnes `2K+16:9` 调用返回 200 且图片尺寸 ~2624x1472（比例生效）。

## 关联
- ADR-004：真实模型出图 + 超时/重试修复（本次在其之上叠加参数防腐层）。
- 注：Agnes 文档指出 `response_format` 须放 `extra_body` 内（顶层会 400）；当前直接读 `data[0].url` 已能拿到 URL，且为兼容 2.0 避免回归，**未主动发送 `response_format`**。若后续需要 base64 输出，由 adapter 按模型决定是否在 `extra_body` 内发送。
