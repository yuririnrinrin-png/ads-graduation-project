"""Per-job fal.ai spend cap (REQUIREMENTS.md §9).

1 job = 200 yen including slot regen on the same job. Numbers must match
packages/shared/src/index.ts. Live enforcement is here; the web UI copies
the same formula so regen/retry can be refused before enqueue.
"""

from __future__ import annotations

import logging
import math
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

logger = logging.getLogger("tiamo.worker")

# Keep in sync with packages/shared JOB_COST_* / FAL_* constants.
_DEFAULT_LIMIT_YEN = 200
_DEFAULT_USD_JPY = 150.0
_FAL_GEN_SIZE = 1024
_USD_PER_MP_FLUX_DEV = 0.025
_USD_PER_MP_FLUX_PULID = 0.0333


class JobCostLimitError(RuntimeError):
    """This job has no remaining yen budget for another fal.ai call."""


@dataclass
class JobCostTracker:
    conn: Any
    job_id: str
    spent_yen: int
    limit_yen: int


_current: ContextVar[JobCostTracker | None] = ContextVar("job_cost", default=None)


def job_cost_yen_limit() -> int:
    raw = os.environ.get("JOB_COST_YEN_LIMIT", str(_DEFAULT_LIMIT_YEN))
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_LIMIT_YEN


def usd_jpy_rate() -> float:
    raw = os.environ.get("USD_JPY_RATE", str(_DEFAULT_USD_JPY))
    try:
        return max(1.0, float(raw))
    except ValueError:
        return _DEFAULT_USD_JPY


def billed_megapixels(size: int = _FAL_GEN_SIZE) -> int:
    return max(1, math.ceil((size * size) / 1_000_000))


def yen_for_model(model: str) -> int:
    key = (model or "").lower()
    if "pulid" in key:
        usd_per_mp = float(os.environ.get("FAL_USD_PER_MP_FLUX_PULID", str(_USD_PER_MP_FLUX_PULID)))
    else:
        usd_per_mp = float(os.environ.get("FAL_USD_PER_MP_FLUX_DEV", str(_USD_PER_MP_FLUX_DEV)))
    usd = usd_per_mp * billed_megapixels()
    return max(1, math.ceil(usd * usd_jpy_rate()))


def limit_message(spent_yen: int, limit_yen: int | None = None) -> str:
    limit = limit_yen if limit_yen is not None else job_cost_yen_limit()
    return (
        f"このジョブの画像生成費が上限の{limit}円に達したため、停止しました"
        f"（いま約{spent_yen}円）。同じジョブの再生成もこの上限に含みます。"
        "新しいジョブを作ってください。"
    )


def before_fal_call(model: str) -> None:
    tracker = _current.get()
    if tracker is None:
        return
    cost = yen_for_model(model)
    if tracker.spent_yen + cost > tracker.limit_yen:
        raise JobCostLimitError(limit_message(tracker.spent_yen, tracker.limit_yen))


def after_fal_call(model: str) -> None:
    tracker = _current.get()
    if tracker is None:
        return
    cost = yen_for_model(model)
    with tracker.conn.cursor() as cur:
        cur.execute(
            """
            UPDATE "Job"
            SET "apiSpendYen" = "apiSpendYen" + %s,
                "apiCallCount" = "apiCallCount" + 1,
                "updatedAt" = NOW()
            WHERE id = %s
            RETURNING "apiSpendYen"
            """,
            (cost, tracker.job_id),
        )
        row = cur.fetchone()
    tracker.conn.commit()
    if row:
        tracker.spent_yen = int(row[0] or 0)
    else:
        tracker.spent_yen += cost
    logger.info(
        "job_id=%s fal cost +%s yen spent=%s/%s model=%s",
        tracker.job_id,
        cost,
        tracker.spent_yen,
        tracker.limit_yen,
        model,
    )


@contextmanager
def track_job_cost(conn, job_id: str) -> Iterator[JobCostTracker]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "apiSpendYen", "apiCallCount" FROM "Job" WHERE id = %s',
            (job_id,),
        )
        row = cur.fetchone()
    spent = int(row[0] or 0) if row else 0
    calls = int(row[1] or 0) if row else 0
    # Jobs created before apiSpendYen: estimate from call count (PuLID unit).
    if spent == 0 and calls > 0:
        spent = calls * yen_for_model("fal-ai/flux-pulid")
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE "Job"
                SET "apiSpendYen" = %s, "updatedAt" = NOW()
                WHERE id = %s AND "apiSpendYen" = 0
                """,
                (spent, job_id),
            )
        conn.commit()
    tracker = JobCostTracker(
        conn=conn,
        job_id=job_id,
        spent_yen=spent,
        limit_yen=job_cost_yen_limit(),
    )
    token = _current.set(tracker)
    logger.info(
        "job_id=%s cost spent=%s yen limit=%s yen",
        job_id,
        tracker.spent_yen,
        tracker.limit_yen,
    )
    try:
        yield tracker
    finally:
        _current.reset(token)
