"""RQ entrypoints. Phase 1: stub only — real pipeline starts in Phase 2."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_job(job_id: str, start_stage: str = "ingest") -> None:
    """Run the 7-stage pipeline for one job (checkpointed).

    Stages: ingest → cutout → detail → scene → composite → inset → ready
    """
    logger.info("job_id=%s stage=%s (stub — not implemented in Phase 1)", job_id, start_stage)
    raise NotImplementedError("Worker pipeline starts in Phase 2")
