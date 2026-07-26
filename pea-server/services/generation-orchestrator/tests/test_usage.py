"""token 用量计量钩子单元测试 (Phase3).

验证:
  - record_usage 把正确字段写入 usage_records (通过 mock db 验证调用)。
  - record_usage 静默吞掉 DB 异常, 不影响主生成链路。
"""
from unittest import mock

import app.usage as usage


def test_record_usage_writes_row():
    captured = {}

    def fake_insert(*, user_id, job_id, node_type, model, provider, platform_config_id, usage):
        captured.update(
            user_id=user_id, job_id=job_id, node_type=node_type,
            model=model, provider=provider, platform_config_id=platform_config_id,
            usage=usage,
        )

    with mock.patch.object(usage.db, "insert_usage_record", fake_insert):
        usage.record_usage(
            job_id="j1", user_id=7, node_type="image", model="m1",
            provider="p1", platform_config_id="pc1",
            usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        )
    assert captured["user_id"] == 7
    assert captured["node_type"] == "image"
    assert captured["platform_config_id"] == "pc1"
    assert captured["usage"]["total_tokens"] == 3


def test_record_usage_swallows_db_errors():
    def boom(**kwargs):
        raise RuntimeError("db down")

    with mock.patch.object(usage.db, "insert_usage_record", boom):
        # 不应抛出, 主链路不受影响
        usage.record_usage(
            job_id=None, user_id=1, node_type="text",
            model=None, provider=None, platform_config_id=None, usage={},
        )
