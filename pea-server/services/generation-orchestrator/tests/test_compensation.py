"""失败补偿退款基线测试 (T-GEN-07 / T-OBS-01).

验证:
  - BFF 可达时退款成功返回 True;
  - BFF 持续不可达时按重试 + 退避穷尽后返回 False (交每日对账脚本兜底, 不再静默丢钱)。
"""
from unittest import mock

import pytest

import app.compensation as comp


class _FakeResp:
    def __init__(self, status_code=200, ok=True):
        self.status_code = status_code
        self._json = {"ok": ok}

    def json(self):
        return self._json


class _OkClient:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, *a, **k):
        return _FakeResp(200, True)


class _FailClient:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, *a, **k):
        raise RuntimeError("network down")


def test_refund_success_returns_true():
    with mock.patch.object(comp.httpx, "Client", _OkClient):
        assert comp.refund_on_failure("job1", 1, 10) is True


def test_refund_retries_then_fails_returns_false():
    # 跳过退避 sleep, 加快测试
    with mock.patch.object(comp.httpx, "Client", _FailClient), \
         mock.patch.object(comp.time, "sleep", lambda *a, **k: None):
        assert comp.refund_on_failure("job1", 1, 10) is False
