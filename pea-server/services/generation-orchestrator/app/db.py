"""MySQL 连接池 (pymysql). 仅 orchestrator 拥有的 generation_* 表.

注意: 不依赖 pymysql.ConnectionPool (不同版本/镜像源 API 不稳定),
改为基于 queue.Queue 的轻量连接池, with 语义归还连接而非关闭。
"""
from __future__ import annotations

import queue

import pymysql
from pymysql.cursors import DictCursor

from app.config import settings
from app import models

_POOL_SIZE = 10


class _Pool:
    def __init__(self, maxsize: int = _POOL_SIZE) -> None:
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)
        for _ in range(maxsize):
            self._q.put(self._new())

    @staticmethod
    def _new():
        return pymysql.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )

    def acquire(self):
        try:
            conn = self._q.get(block=False)
        except queue.Empty:
            conn = self._new()
        if not getattr(conn, "open", False):
            conn = self._new()
        return conn

    def release(self, conn) -> None:
        try:
            self._q.put(conn, block=False)
        except queue.Full:
            conn.close()


_pool: _Pool | None = None


def _get_pool() -> _Pool:
    global _pool
    if _pool is None:
        _pool = _Pool()
    return _pool


class _Conn:
    """with 语义: 进入返回原始连接, 退出归还连接池(不关闭). 其余属性透传到原始连接."""

    def __init__(self, raw) -> None:
        self._raw = raw

    def __enter__(self):
        return self._raw

    def __exit__(self, *exc) -> bool:
        # 归还前必须回滚未提交事务 (连接池卫生).
        # 自定义连接池复用同一物理连接, 而 MySQL 默认 autocommit=False + REPEATABLE READ:
        # 任何 SELECT/SELECT..FOR UPDATE 都会开启一个事务并固定快照.
        # 若带着未提交事务回到池中, 下次该连接上的 SELECT 仍看旧快照,
        # 看不到新插入的行 -> get_job 对存在的 job 误报 404 -> BFF 透传为 500.
        # 显式 rollback 只丢弃被中断/泄漏的事务; 已 commit 的事务 rollback 为 no-op, 安全.
        try:
            if getattr(self._raw, "open", False):
                try:
                    self._raw.rollback()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            _get_pool().release(self._raw)
        return False

    def __getattr__(self, name):
        return getattr(self._raw, name)


def get_conn() -> _Conn:
    """返回连接池中的连接 (DictCursor). 用完必须退出 with 以归还."""
    return _Conn(_get_pool().acquire())


def get_model_with_provider(model_id: str) -> dict | None:
    """按 ai_models.id 联表取模型 + 其提供商配置 (含明文密钥, 仅内部服务使用)。

    返回单行 dict: model_name / model_type / provider_type / base_url / api_key / provider_name 等,
    找不到或提供商停用返回 None (由调用方决定回退 Mock 还是失败)。
    """
    if not model_id:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.id            AS model_id,
                       m.model_name    AS model_name,
                       m.model_type    AS model_type,
                       m.enabled       AS model_enabled,
                       p.id            AS provider_id,
                       p.name          AS provider_name,
                       p.provider_type AS provider_type,
                       p.base_url      AS base_url,
                       p.api_key       AS api_key,
                       p.enabled       AS provider_enabled
                FROM ai_models m
                JOIN ai_providers p ON p.id = m.provider_id
                WHERE m.id = %s
                """,
                [model_id],
            )
            return cur.fetchone()


def update_job_status(job_id: str, status: str, *, result_json=None, cost_tapies=None,
                      usage_json=None, error=None) -> None:
    """更新任务状态, 并强制校验状态机合法性 (T-GEN-01).

    非法跳转 (如 done -> refunded, queued -> done) 直接抛错, 杜绝状态错乱。
    幂等: 目标状态与当前一致时不报错。

    error: 失败详情 (T-FIX-ERROR-2026-07-28, 持久化到 generation_jobs.error).
           只在 status=failed 时写入; 传 None 不动列。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM generation_jobs WHERE id=%s FOR UPDATE", [job_id])
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"job not found: {job_id}")
            current = row["status"]
            if current == status:
                return  # 幂等
            if not models.can_transition(current, status):
                raise ValueError(f"illegal transition: {current} -> {status}")

            has_meta = any(x is not None for x in (result_json, cost_tapies, usage_json))
            has_error = error is not None
            if has_meta or has_error:
                fields, vals = [], []
                if result_json is not None:
                    fields.append("result_json = %s")
                    vals.append(result_json)
                if cost_tapies is not None:
                    fields.append("cost_tapies = %s")
                    vals.append(cost_tapies)
                if usage_json is not None:
                    fields.append("usage_json = %s")
                    vals.append(usage_json)
                if has_error:
                    fields.append("error = %s")
                    vals.append(error)
                vals.append(job_id)
                cur.execute(
                    f"UPDATE generation_jobs SET status=%s, {', '.join(fields)} "
                    f"WHERE id=%s",
                    [status, *vals],
                )
            else:
                cur.execute(
                    "UPDATE generation_jobs SET status=%s WHERE id=%s", [status, job_id]
                )
        conn.commit()


def get_platform_config(pc_id: str) -> dict | None:
    """按 platform_configs.id 取平台提示词配置 (编排器只读, CRUD 归 BFF)。"""
    if not pc_id:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, owner_id, name, platform, kind, prompt_mode,
                       presets_json, expand_model, is_default
                FROM platform_configs WHERE id=%s
                """,
                [pc_id],
            )
            return cur.fetchone()


def insert_usage_record(*, user_id: int, job_id: str | None, node_type: str,
                        model: str | None, provider: str | None,
                        platform_config_id: str | None, usage: dict) -> None:
    """Phase3: 落 token 用量审计。usage = {input_tokens, output_tokens, total_tokens}。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage_records
                (user_id, job_id, node_type, model, provider, platform_config_id,
                 input_tokens, output_tokens, total_tokens)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    user_id, job_id, node_type, model, provider, platform_config_id,
                    int(usage.get("input_tokens") or 0),
                    int(usage.get("output_tokens") or 0),
                    int(usage.get("total_tokens") or
                        (int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0))),
                ],
            )
        conn.commit()
