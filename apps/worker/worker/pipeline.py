"""
Ti amo Jewelry Studio — Phase 2–3 worker.

Queue: Redis list `tiamo:jobs`
Stages: ingest → cutout → detail → scene → composite → inset → ready

Scene: FAL_KEY あり → Flux + PuLID（同一人物）。なし → ローカル仮シーン。
Composite: real cutout on scene with category anchors + transform JSON.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import numpy as np
import psycopg
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageOps
from redis import Redis

from worker.scene_gen import generate_all_scenes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("tiamo.worker")

QUEUE_KEY = "tiamo:jobs"
SIZE = 2000

METAL_TINT = {
    "YG": (1.08, 0.98, 0.82),
    "WG": (0.96, 0.97, 1.02),
    "PG": (1.08, 0.92, 0.90),
}

BG_BY_NAME = {
    "白大理石": "marble_white",
    "トラバーチン": "travertine",
    "リネン": "linen",
    "黒石": "black_stone",
}

# Anchor lists: earrings get 2 anchors (single cutout mirrored onto both ears —
# no separate left/right shoot needed (REQUIREMENTS.md §2 決定 2026-08-12).
CATEGORY_ANCHORS = {
    "necklace": [{"x": 0.5, "y": 0.36, "scale": 0.28}],
    "earring": [
        {"x": 0.4, "y": 0.32, "scale": 0.09},
        {"x": 0.6, "y": 0.32, "scale": 0.09},
    ],
    "ring": [{"x": 0.58, "y": 0.66, "scale": 0.13}],
    "bracelet": [{"x": 0.46, "y": 0.55, "scale": 0.2}],
}
BODY_ANCHORS = {
    "necklace": [{"x": 0.5, "y": 0.32, "scale": 0.14}],
    "earring": [
        {"x": 0.46, "y": 0.22, "scale": 0.045},
        {"x": 0.54, "y": 0.22, "scale": 0.045},
    ],
    "ring": [{"x": 0.55, "y": 0.58, "scale": 0.07}],
    "bracelet": [{"x": 0.48, "y": 0.48, "scale": 0.1}],
}

SLOT_DETAIL = ["detail_a", "detail_b", "detail_c"]
WEAR_SLOTS = ["wear_office", "wear_cafe", "wear_date", "wear_holiday"]
BODY_SLOTS = ["body_1", "body_2"]
SCENE_SLOTS = WEAR_SLOTS + BODY_SLOTS + ["wide_inset"]

ZIP_NAME = {
    "detail_a": "01_detail_a.jpg",
    "detail_b": "02_detail_b.jpg",
    "detail_c": "03_detail_c.jpg",
    "wear_office": "04_wear_office.jpg",
    "wear_cafe": "05_wear_cafe.jpg",
    "wear_date": "06_wear_date.jpg",
    "wear_holiday": "07_wear_holiday.jpg",
    "body_1": "08_body_tone1.jpg",
    "body_2": "09_body_tone2.jpg",
    "wide_inset": "10_wide_inset.jpg",
}


def new_id() -> str:
    return "c" + uuid.uuid4().hex[:24]


def env_path() -> None:
    here = Path(__file__).resolve()
    repo = here.parents[3]
    for p in [
        repo / "apps" / "web" / ".env.local",
        repo / "apps" / "web" / ".env",
        repo / ".env",
    ]:
        if p.exists():
            load_dotenv(p)
            break


def data_root() -> Path:
    raw = os.environ.get("DATA_ROOT")
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[3] / "apps" / "web" / ".data"


def job_dir(job_id: str) -> Path:
    return data_root() / "jobs" / job_id


def db_connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return psycopg.connect(url)


def set_stage(conn, job_id: str, stage: str, status: str = "running", error: str | None = None):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE "Job"
            SET stage = %s::"PipelineStage",
                status = %s::"JobStatus",
                error = %s,
                "updatedAt" = NOW()
            WHERE id = %s
            """,
            (stage, status, error, job_id),
        )
    conn.commit()


def upsert_asset(
    conn,
    job_id: str,
    slot_key: str,
    kind: str,
    storage_key: str,
    transform: dict | None = None,
):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM "JobAsset"
            WHERE "jobId" = %s AND "slotKey" = %s AND kind = %s
            LIMIT 1
            """,
            (job_id, slot_key, kind),
        )
        row = cur.fetchone()
        transform_json = json.dumps(transform) if transform is not None else None
        if row:
            if transform is not None:
                cur.execute(
                    """
                    UPDATE "JobAsset"
                    SET "storageKey" = %s, transform = %s::jsonb
                    WHERE id = %s
                    """,
                    (storage_key, transform_json, row[0]),
                )
            else:
                cur.execute(
                    'UPDATE "JobAsset" SET "storageKey" = %s WHERE id = %s',
                    (storage_key, row[0]),
                )
        else:
            cur.execute(
                """
                INSERT INTO "JobAsset"
                  (id, "jobId", "slotKey", kind, "storageKey", transform, "createdAt")
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
                """,
                (new_id(), job_id, slot_key, kind, storage_key, transform_json),
            )
    conn.commit()


def load_job(conn, job_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT j.id, j.category, j.metal, j."mainIndex", j."toneIds",
                   b.name AS background_name, p.name AS persona_name,
                   p."imageKey" AS persona_image_key
            FROM "Job" j
            JOIN "PresetBackground" b ON b.id = j."backgroundId"
            JOIN "PresetPersona" p ON p.id = j."personaId"
            WHERE j.id = %s
            """,
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Job not found: {job_id}")
        tone_ids = list(row[4] or [])
        tone_names: list[str] = []
        if tone_ids:
            cur.execute(
                'SELECT id, name FROM "PresetTone" WHERE id = ANY(%s)',
                (tone_ids,),
            )
            found = {r[0]: r[1] for r in cur.fetchall()}
            tone_names = [found[t] for t in tone_ids if t in found]
        return {
            "id": row[0],
            "category": row[1],
            "metal": row[2],
            "mainIndex": row[3],
            "toneIds": tone_ids,
            "tone_names": tone_names or ["トーン1", "トーン2"],
            "background_name": row[5],
            "persona_name": row[6],
            "persona_image_key": row[7],
        }


def bump_api_call_count(conn, job_id: str, n: int = 1) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE "Job"
            SET "apiCallCount" = "apiCallCount" + %s,
                "updatedAt" = NOW()
            WHERE id = %s
            """,
            (n, job_id),
        )
    conn.commit()


def make_background(kind: str, size: int = SIZE) -> Image.Image:
    yy, xx = np.mgrid[0:size, 0:size]
    if kind == "black_stone":
        v = 28 + ((xx * 7 + yy * 3) % 40)
        rgb = np.stack([v, np.clip(v - 2, 0, 255), np.clip(v - 4, 0, 255)], axis=-1)
    elif kind == "linen":
        n = ((xx // 3) + (yy // 11)) % 2
        d = np.where(n == 0, 4, -6)
        rgb = np.stack([237 + d, 230 + d, 217 + d], axis=-1)
    elif kind == "travertine":
        band = (yy // 40) % 2
        v = 190 - band * 18 + ((xx + yy) % 17)
        rgb = np.stack([v, np.clip(v - 8, 0, 255), np.clip(v - 18, 0, 255)], axis=-1)
    else:
        v = 220 + ((xx * 13 + yy * 7) % 25)
        rgb = np.stack(
            [np.clip(v, 0, 255), np.clip(v - 4, 0, 255), np.clip(v - 10, 0, 255)],
            axis=-1,
        )
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def cutout_light_bg(src: Image.Image, threshold: int = 235) -> Image.Image:
    rgba = np.array(src.convert("RGBA"))
    rgb = rgba[:, :, :3].astype(np.int16)
    m = rgb.min(axis=2)
    alpha = np.full(m.shape, 255, dtype=np.uint8)
    alpha[m >= threshold] = 0
    soft = (m > threshold - 25) & (m < threshold)
    alpha[soft] = ((threshold - m[soft]) * (255 / 25)).astype(np.uint8)
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, "RGBA")


def apply_metal_tint(img: Image.Image, metal: str) -> Image.Image:
    factors = METAL_TINT.get(metal, (1.0, 1.0, 1.0))
    r, g, b, a = img.split()
    r = r.point(lambda v: min(255, int(v * factors[0])))
    g = g.point(lambda v: min(255, int(v * factors[1])))
    b = b.point(lambda v: min(255, int(v * factors[2])))
    out = Image.merge("RGBA", (r, g, b, a))
    return ImageEnhance.Contrast(out).enhance(1.05)


def compose_detail(cutout: Image.Image, background: Image.Image, metal: str) -> Image.Image:
    tinted = apply_metal_tint(cutout, metal)
    max_side = int(SIZE * 0.72)
    fitted = ImageOps.contain(tinted, (max_side, max_side))
    canvas = background.copy().convert("RGBA")
    x = (SIZE - fitted.width) // 2
    y = (SIZE - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))
    return canvas.convert("RGB")


def default_transform() -> dict:
    return {"scale": 1.0, "offsetX": 0, "offsetY": 0}


def default_transforms(count: int) -> list[dict]:
    return [default_transform() for _ in range(count)]


def get_anchors(category: str, body: bool) -> list[dict]:
    anchors_by_category = BODY_ANCHORS if body else CATEGORY_ANCHORS
    return anchors_by_category.get(category, CATEGORY_ANCHORS["bracelet"])


def composite_on_scene(
    scene: Image.Image,
    cutout: Image.Image,
    category: str,
    metal: str,
    *,
    body: bool,
    transforms: list[dict] | None = None,
) -> Image.Image:
    anchors = get_anchors(category, body)
    ts = transforms if transforms is not None else default_transforms(len(anchors))
    tinted = apply_metal_tint(cutout, metal)
    canvas = scene.convert("RGBA")

    # Earrings: same cutout mirrored onto both ear anchors, each with its own
    # transform so left/right can be sized/placed independently.
    for i, anchor in enumerate(anchors):
        t = ts[i] if i < len(ts) else default_transform()
        jewel_w = max(24, int(SIZE * anchor["scale"] * float(t.get("scale", 1))))
        fitted = ImageOps.contain(tinted, (jewel_w, jewel_w))
        if i % 2 == 1:
            fitted = ImageOps.mirror(fitted)
        cx = int(SIZE * anchor["x"] + float(t.get("offsetX", 0)))
        cy = int(SIZE * anchor["y"] + float(t.get("offsetY", 0)))
        x = cx - fitted.width // 2
        y = cy - fitted.height // 2
        canvas.alpha_composite(fitted, (x, y))
    return canvas.convert("RGB")


def add_inset(wide: Image.Image, detail: Image.Image) -> Image.Image:
    """Bottom-right detail inset (Phase 3 simple; Phase 4 may refine source choice)."""
    canvas = wide.convert("RGBA")
    inset_size = 520
    thumb = ImageOps.contain(detail.convert("RGBA"), (inset_size, inset_size))
    pad = 48
    box = Image.new("RGBA", (thumb.width + 16, thumb.height + 16), (255, 255, 255, 230))
    box.paste(thumb, (8, 8), thumb if thumb.mode == "RGBA" else None)
    x = SIZE - box.width - pad
    y = SIZE - box.height - pad
    canvas.alpha_composite(box, (x, y))
    return canvas.convert("RGB")


def run_job(conn, job_id: str) -> None:
    t0 = time.time()
    logger.info("job_id=%s start", job_id)
    job = load_job(conn, job_id)
    root = job_dir(job_id)
    input_dir = root / "input"
    cutout_dir = root / "cutout"
    scene_dir = root / "scene"
    preview_dir = root / "preview"
    for d in (cutout_dir, scene_dir, preview_dir):
        d.mkdir(parents=True, exist_ok=True)

    # --- ingest ---
    set_stage(conn, job_id, "ingest", "running")
    inputs = sorted(input_dir.glob("product_*.jpg"))
    if len(inputs) != 3:
        raise RuntimeError(f"Expected 3 inputs, found {len(inputs)}")
    logger.info("job_id=%s stage=ingest ok", job_id)

    # --- cutout ---
    set_stage(conn, job_id, "cutout", "running")
    cutouts: list[Image.Image] = []
    for i, path in enumerate(inputs):
        src = ImageOps.exif_transpose(Image.open(path))
        src = ImageOps.contain(src.convert("RGB"), (SIZE, SIZE))
        canvas = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
        canvas.paste(src, ((SIZE - src.width) // 2, (SIZE - src.height) // 2))
        cut = cutout_light_bg(canvas)
        out = cutout_dir / f"cutout_{i}.png"
        cut.save(out, "PNG")
        upsert_asset(conn, job_id, f"cutout_{i}", "cutout", str(out))
        cutouts.append(cut)
        logger.info("job_id=%s stage=cutout i=%s", job_id, i)

    main_cut = cutouts[min(job["mainIndex"], 2)]

    # --- detail ---
    set_stage(conn, job_id, "detail", "running")
    bg_kind = BG_BY_NAME.get(job["background_name"], "marble_white")
    background = make_background(bg_kind)
    detail_imgs: list[Image.Image] = []
    for i, slot in enumerate(SLOT_DETAIL):
        detail = compose_detail(cutouts[i], background, job["metal"])
        out = preview_dir / ZIP_NAME[slot]
        detail.save(out, "JPEG", quality=90)
        upsert_asset(conn, job_id, slot, "preview", str(out))
        detail_imgs.append(detail)
        logger.info("job_id=%s stage=detail slot=%s", job_id, slot)

    # --- scene ---
    set_stage(conn, job_id, "scene", "running")

    def on_api_call() -> None:
        bump_api_call_count(conn, job_id, 1)

    scenes = generate_all_scenes(
        persona_name=job["persona_name"],
        persona_image_key=job.get("persona_image_key"),
        category=job["category"],
        slots=SCENE_SLOTS,
        tone_names=job["tone_names"],
        scene_dir=scene_dir,
        on_api_call=on_api_call,
    )
    ref_path = scene_dir / "persona_ref.jpg"
    if ref_path.is_file():
        upsert_asset(conn, job_id, "persona_ref", "persona_ref", str(ref_path))
    for slot, scene in scenes.items():
        out = scene_dir / f"{slot}.jpg"
        scene.save(out, "JPEG", quality=90)
        upsert_asset(conn, job_id, slot, "scene", str(out))
        logger.info("job_id=%s stage=scene slot=%s", job_id, slot)

    # --- composite ---
    set_stage(conn, job_id, "composite", "running")
    wear_transforms = default_transforms(len(get_anchors(job["category"], False)))
    body_transforms = default_transforms(len(get_anchors(job["category"], True)))
    composited: dict[str, Image.Image] = {}
    for slot in WEAR_SLOTS:
        img = composite_on_scene(
            scenes[slot], main_cut, job["category"], job["metal"], body=False, transforms=wear_transforms
        )
        out = preview_dir / ZIP_NAME[slot]
        img.save(out, "JPEG", quality=90)
        upsert_asset(conn, job_id, slot, "preview", str(out), transform=wear_transforms)
        composited[slot] = img
        logger.info("job_id=%s stage=composite slot=%s", job_id, slot)

    for slot in BODY_SLOTS:
        img = composite_on_scene(
            scenes[slot], main_cut, job["category"], job["metal"], body=True, transforms=body_transforms
        )
        out = preview_dir / ZIP_NAME[slot]
        img.save(out, "JPEG", quality=90)
        upsert_asset(conn, job_id, slot, "preview", str(out), transform=body_transforms)
        composited[slot] = img
        logger.info("job_id=%s stage=composite slot=%s", job_id, slot)

    # wide without inset first
    wide = composite_on_scene(
        scenes["wide_inset"],
        main_cut,
        job["category"],
        job["metal"],
        body=True,
        transforms=body_transforms,
    )

    # --- inset ---
    set_stage(conn, job_id, "inset", "running")
    wide_final = add_inset(wide, detail_imgs[0])
    out = preview_dir / ZIP_NAME["wide_inset"]
    wide_final.save(out, "JPEG", quality=90)
    upsert_asset(conn, job_id, "wide_inset", "preview", str(out), transform=body_transforms)
    logger.info("job_id=%s stage=inset slot=wide_inset", job_id)

    set_stage(conn, job_id, "ready", "ready", error=None)
    logger.info("job_id=%s ready in %.1fs", job_id, time.time() - t0)


def fail_job(conn, job_id: str, stage: str, message: str) -> None:
    logger.error("job_id=%s failed stage=%s: %s", job_id, stage, message)
    try:
        set_stage(conn, job_id, stage, "failed", error=message[:500])
    except Exception:
        logger.exception("failed to persist error for %s", job_id)


def listen_forever() -> None:
    env_path()
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    r = Redis.from_url(redis_url, decode_responses=True)
    logger.info("worker listening on %s key=%s data=%s", redis_url, QUEUE_KEY, data_root())

    while True:
        item = r.brpop(QUEUE_KEY, timeout=5)
        if not item:
            continue
        _, job_id = item
        with db_connect() as conn:
            stage = "ingest"
            try:
                with conn.cursor() as cur:
                    cur.execute('SELECT stage FROM "Job" WHERE id = %s', (job_id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        stage = row[0]
                run_job(conn, job_id)
            except Exception as e:
                try:
                    with conn.cursor() as cur:
                        cur.execute('SELECT stage FROM "Job" WHERE id = %s', (job_id,))
                        row = cur.fetchone()
                        if row and row[0]:
                            stage = row[0]
                except Exception:
                    pass
                if stage == "ready":
                    stage = "composite"
                fail_job(conn, job_id, stage, str(e))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        env_path()
        with db_connect() as conn:
            run_job(conn, sys.argv[2])
    else:
        listen_forever()
