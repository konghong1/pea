"""模型参数适配器 (Anti-Corruption Layer / Strategy).

为什么存在:
  前端/API 只讲"规范参数"(size_tier, aspect_ratio, n, seed, reference_images),
  不关心具体模型要什么形状。各模型/提供商的请求体差异很大(见官方文档):
    - Agnes 图像: size 用 档位式 "1K"/"2K"/"3K"/"4K" + 可选 ratio;
                  图生图 image 必须放 extra_body.image, 且绝不能发 tags;
                  response_format 必须在 extra_body 内。
    - OpenAI / DALL·E: size 用精确像素 "1024x1024"/"1792x1024", 不认 ratio。
  把这些差异收敛到一个 adapter 层, 后续接入新模型只需新增一个 adapter,
  不污染 provider 主流程, 也不让前端耦合具体模型。

设计:
  - NormImageParams: 规范参数(系统内部通用语)。
  - ImageParamAdapter (ABC) + Agnes / Generic 实现。
  - get_image_adapter(base_url): 按提供商族分派; 默认回退 Generic。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 档位式 -> 精确像素 (OpenAI/DALL·E 这类需要精确像素的模型用; DALL·E 非方图最大 1792x1024)
_TIER_TO_PIXELS = {
    "1K": "1024x1024",
    "2K": "1792x1024",
    "3K": "2048x2048",
    "4K": "2048x2048",
}

# Agnes 官方白名单 ratio (其它值丢弃并告警, 避免 400)
_AGNES_RATIOS = {"1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"}


def _normalize_refs(refs: Any) -> list[str]:
    """仅保留提供商可达的参考图: http(s) 外链或 data: 内联; 内部代理/相对/blob 路径丢弃。上限 8，保序。"""
    if not refs:
        return []
    if isinstance(refs, str):
        refs = [refs]
    out: list[str] = []
    dropped = 0
    for r in list(refs)[:8]:
        if isinstance(r, str) and (r.startswith("http") or r.startswith("data:")):
            out.append(r)
        else:
            dropped += 1
    if dropped:
        logger.warning(
            "[refs] dropped %d unreachable reference image(s): need http(s)/data: URL, "
            "blob:/relative paths are unusable by the model",
            dropped,
        )
    return out


@dataclass
class NormImageParams:
    """规范图像参数 —— 系统内部通用语, 与具体模型无关。"""
    prompt: str
    n: int = 1
    size_tier: str | None = None          # 已大写: "1K"/"2K"/"3K"/"4K"
    aspect_ratio: str | None = None       # "1:1"/"16:9"/...
    seed: int | None = None
    reference_images: list[str] = field(default_factory=list)


def normalize_image_params(req: dict) -> NormImageParams:
    """从 route() 收到的 req 抽取规范参数。前端已带 resolution/aspectRatio, 直接采用。"""
    p = req.get("params") or {}
    tier_raw = (p.get("resolution") or p.get("size") or "")
    tier = tier_raw.upper() if tier_raw else None
    n_raw = p.get("n", 1)
    try:
        n = int(n_raw)
    except (TypeError, ValueError):
        n = 1
    return NormImageParams(
        prompt=req["prompt"],
        n=max(1, min(8, n)),
        size_tier=tier,
        aspect_ratio=p.get("aspectRatio"),
        seed=p.get("seed"),
        reference_images=_normalize_refs(p.get("reference_images")),
    )


class ImageParamAdapter:
    def build(self, norm: NormImageParams, provider) -> dict:
        raise NotImplementedError


class AgnesImageAdapter(ImageParamAdapter):
    """Agnes 2.x 图像: 档位式 size + ratio + extra_body.image, 不发 tags。

    官方文档要点:
      - size 推荐 "1K".."4K" 档位, 配合 ratio 得到可预期尺寸 (2K+16:9 -> 2624x1472)。
      - 图生图 image 放 extra_body.image; 不要传 tags:["img2img"]。
      - response_format 必须在 extra_body 内 (顶层会 400); 但我们直接读 data[0].url,
        且历史行为不发送也能拿到 URL, 故默认不发送以兼容 2.0, 避免回归。
    """

    def build(self, norm: NormImageParams, provider) -> dict:
        payload: dict[str, Any] = {
            "model": provider.model_name,
            "prompt": norm.prompt,
            "n": norm.n,
            "size": norm.size_tier or "2K",   # 档位式, 不用精确像素
        }
        if norm.aspect_ratio:
            if norm.aspect_ratio in _AGNES_RATIOS:
                payload["ratio"] = norm.aspect_ratio
            else:
                logger.warning("[adapter] agnes 不支持的 ratio=%s, 已丢弃", norm.aspect_ratio)
        if norm.seed is not None:
            payload["seed"] = norm.seed
        # 图生图: image 必须进 extra_body, 且不带 tags
        if norm.reference_images:
            payload["extra_body"] = {"image": norm.reference_images}
            logger.info(
                "[adapter] agnes image refs=%d (order preserved, sent via extra_body.image)",
                len(norm.reference_images),
            )
        return payload


class GenericOpenAIImageAdapter(ImageParamAdapter):
    """OpenAI / DALL·E 兼容: size 用精确像素, 不认 ratio。"""

    def build(self, norm: NormImageParams, provider) -> dict:
        tier = norm.size_tier or "1K"
        payload: dict[str, Any] = {
            "model": provider.model_name,
            "prompt": norm.prompt,
            "n": norm.n,
            "size": _TIER_TO_PIXELS.get(tier, "1024x1024"),
        }
        if norm.seed is not None:
            payload["seed"] = norm.seed
        if norm.reference_images:
            payload["image"] = (
                norm.reference_images[0] if len(norm.reference_images) == 1
                else norm.reference_images
            )
        return payload


def get_image_adapter(base_url: str) -> ImageParamAdapter:
    """按提供商族分派。新增模型 = 在此加分支或注册表, 不动 provider。"""
    if "agnes" in (base_url or "").lower():
        return AgnesImageAdapter()
    return GenericOpenAIImageAdapter()
