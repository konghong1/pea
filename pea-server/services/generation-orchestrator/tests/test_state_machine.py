"""生成状态机基线测试 (T-GEN-01 / T-OBS-01).

验证:
  - 合法状态转移;
  - 非法转移被 can_transition 拒绝;
  - db.update_job_status 会强制校验状态机 (非法跳转抛 ValueError);
  - 同状态幂等不报错。
"""
from unittest import mock

import pytest

from app import db, models


def test_valid_transitions():
    assert models.can_transition("queued", "running")
    assert models.can_transition("queued", "failed")
    assert models.can_transition("running", "done")
    assert models.can_transition("running", "failed")
    assert models.can_transition("failed", "refunded")


def test_invalid_transitions():
    assert not models.can_transition("queued", "done")      # 不能跳过 running
    assert not models.can_transition("done", "refunded")    # done 是终态
    assert not models.can_transition("refunded", "queued")  # refunded 是终态
    assert not models.can_transition("running", "queued")   # 不能回退


def test_terminal():
    assert models.is_terminal("done")
    assert models.is_terminal("refunded")
    assert not models.is_terminal("queued")


class _FakeCursor:
    def __init__(self, status):
        self._status = status
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "SELECT status FROM generation_jobs" in sql:
            self._row = {"status": self._status}

    def fetchone(self):
        return getattr(self, "_row", None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, status):
        self.cur = _FakeCursor(status)

    def cursor(self):
        return self.cur

    def commit(self):
        for sql, params in self.cur.executed:
            if sql.strip().upper().startswith("UPDATE GENERATION_JOBS SET STATUS"):
                self.cur._status = params[0]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_update_job_status_valid():
    c = _FakeConn("queued")
    with mock.patch.object(db, "get_conn", return_value=c):
        db.update_job_status("job1", "running")
    assert c.cur._status == "running"


def test_update_job_status_illegal_raises():
    c = _FakeConn("done")
    with mock.patch.object(db, "get_conn", return_value=c):
        with pytest.raises(ValueError):
            db.update_job_status("job1", "refunded")


def test_update_job_status_idempotent_same():
    c = _FakeConn("refunded")
    with mock.patch.object(db, "get_conn", return_value=c):
        db.update_job_status("job1", "refunded")  # 不应抛错
    assert c.cur._status == "refunded"
