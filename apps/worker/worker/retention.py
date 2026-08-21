"""Delete generated job files 14 days after creation (REQUIREMENTS §6)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger("tiamo.worker.retention")

RETENTION_DAYS = 14
PURGE_INTERVAL_SEC = 600
PURGE_MESSAGE = "生成結果は14日で削除されました"


def purge_expired(conn, jobs_root: Path) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM "Job"
            WHERE status <> 'expired'
              AND status <> 'running'
              AND (
                ("expiresAt" IS NOT NULL AND "expiresAt" <= NOW())
                OR ("expiresAt" IS NULL AND "createdAt" <= NOW() - (%s * INTERVAL '1 day'))
              )
            """,
            (RETENTION_DAYS,),
        )
        rows = cur.fetchall()

    n = 0
    for (job_id,) in rows:
        dest = jobs_root / job_id
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE "Job"
                SET status = 'expired'::"JobStatus",
                    error = %s,
                    "updatedAt" = NOW()
                WHERE id = %s AND status <> 'running'
                """,
                (PURGE_MESSAGE, job_id),
            )
        n += 1
        logger.info("purged expired job_id=%s", job_id)
    if n:
        conn.commit()
    return n
