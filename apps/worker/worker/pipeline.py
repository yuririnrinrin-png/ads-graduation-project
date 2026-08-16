"""
Ti amo Jewelry Studio — Phase 2–4 worker.

Queue: Redis list `tiamo:jobs` (jobId or JSON {jobId, fromStage, slots})
Stages: ingest → cutout → detail → scene → composite → inset → ready
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
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from redis import Redis

from worker.face_anchor import transforms_from_face
from worker.hair_mask import HAIR_OVERLAY_SLOTS, build_hair_overlay
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
# `rotate` (degrees, clockwise) is a small fixed baseline tilt — NOT a per-shot
# 3D perspective correction and not user-adjustable — added only to soften the
# "pasted flat" look of a straight cutout on a neck/ear that is rarely
# perfectly upright. Must mirror packages/shared/src/index.ts exactly.
CATEGORY_ANCHORS = {
    "necklace": [{"x": 0.5, "y": 0.36, "scale": 0.28, "rotate": 6}],
    "earring": [
        {"x": 0.4, "y": 0.32, "scale": 0.09, "rotate": 6},
        {"x": 0.6, "y": 0.32, "scale": 0.09, "rotate": -6},
    ],
    "ring": [{"x": 0.58, "y": 0.70, "scale": 0.11, "rotate": 0}],
    "bracelet": [{"x": 0.48, "y": 0.62, "scale": 0.18, "rotate": 0}],
}
BODY_ANCHORS = {
    "necklace": [{"x": 0.5, "y": 0.32, "scale": 0.14, "rotate": 4}],
    "earring": [
        {"x": 0.46, "y": 0.22, "scale": 0.045, "rotate": 4},
        {"x": 0.54, "y": 0.22, "scale": 0.045, "rotate": -4},
    ],
    "ring": [{"x": 0.56, "y": 0.78, "scale": 0.06, "rotate": 0}],
    "bracelet": [{"x": 0.48, "y": 0.74, "scale": 0.09, "rotate": 0}],
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
                   p."imageKey" AS persona_image_key,
                   j."insetSlot" AS inset_slot
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
            "inset_slot": row[8] if len(row) > 8 and row[8] in SLOT_DETAIL else "detail_a",
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


# Keep this faint — a heavy shadow reads as a color shift on the metal.
SCENE_SHADOW_BLUR = 12
SCENE_SHADOW_OPACITY = 48


def apply_metal_tint(img: Image.Image, metal: str) -> Image.Image:
    factors = METAL_TINT.get(metal, (1.0, 1.0, 1.0))
    r, g, b, a = img.split()
    r = r.point(lambda v: min(255, int(v * factors[0])))
    g = g.point(lambda v: min(255, int(v * factors[1])))
    b = b.point(lambda v: min(255, int(v * factors[2])))
    out = Image.merge("RGBA", (r, g, b, a))
    return ImageEnhance.Contrast(out).enhance(1.05)


def make_shadow_layer(rgba: Image.Image, *, blur: int, opacity: int) -> tuple[Image.Image, int]:
    """Soft blurred dark silhouette from an RGBA cutout's alpha channel.

    Used as a light contact shadow so a flat real-photo cutout doesn't read
    as "pasted on top" of the scene/background — NOT a 3D relight, just a
    cheap grounding cue (REQUIREMENTS.md §5: no AI-drawn jewelry, no real
    perspective correction; this is a lightweight exception approved
    2026-08-13, see docs/HANDOFF.md). Returns (shadow_image, pad) where pad
    is how much bigger the shadow canvas is on each side vs. the input, so
    callers can offset the paste position accordingly.
    """
    alpha = rgba.split()[-1]
    pad = blur * 2
    padded_alpha = Image.new("L", (alpha.width + pad * 2, alpha.height + pad * 2), 0)
    padded_alpha.paste(alpha, (pad, pad))
    dark = Image.new("RGBA", padded_alpha.size, (40, 34, 28, 0))
    dark.putalpha(padded_alpha.point(lambda v: int(v * opacity / 255)))
    return dark.filter(ImageFilter.GaussianBlur(blur)), pad


def match_jewel_to_scene(
    jewel: Image.Image,
    scene_rgb: np.ndarray,
    cx: int,
    cy: int,
) -> Image.Image:
    """Nudge cutout brightness slightly toward the scene. Do not restain
    the metal — the uploaded cutout color is the source of truth."""
    arr = np.array(jewel.convert("RGBA"))
    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3].astype(np.float32)
    opaque = alpha > 32
    if int(opaque.sum()) < 50:
        return jewel

    j_mean = rgb[opaque].mean(axis=0)
    h, w = scene_rgb.shape[:2]
    radius = max(24, max(jewel.size) // 3)
    y0, y1 = max(0, cy - radius), min(h, cy + radius)
    x0, x1 = max(0, cx - radius), min(w, cx + radius)
    patch = scene_rgb[y0:y1, x0:x1].astype(np.float32)
    if patch.size == 0:
        return jewel
    s_mean = patch.mean(axis=(0, 1))

    j_y = 0.299 * j_mean[0] + 0.587 * j_mean[1] + 0.114 * j_mean[2]
    s_y = 0.299 * s_mean[0] + 0.587 * s_mean[1] + 0.114 * s_mean[2]
    scale = 1.0 if j_y < 8 else float(np.clip(s_y / j_y, 0.94, 1.06))
    mixed = rgb * scale
    arr[:, :, :3] = np.clip(mixed, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _clear_hair_overlay_asset(conn, job_id: str, slot: str, out) -> None:
    if out.is_file():
        out.unlink()
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM "JobAsset"
            WHERE "jobId" = %s AND "slotKey" = %s AND kind = 'hair_overlay'
            """,
            (job_id, slot),
        )
    conn.commit()


def prepare_hair_overlay(
    conn,
    job_id: str,
    slot: str,
    scene: Image.Image,
    category: str | None = None,
) -> Image.Image | None:
    """Hair-over-jewelry is for necklaces on tucked-down slots only.

    Putting hair pixels on top of earrings hides them after 完了 (the edit
    canvas shows the cutout without the overlay, so it looks like a vanish).
    """
    out = job_dir(job_id) / "scene" / f"hair_{slot}.png"
    if slot not in HAIR_OVERLAY_SLOTS:
        return None
    if category and category != "necklace":
        _clear_hair_overlay_asset(conn, job_id, slot, out)
        return None
    overlay = build_hair_overlay(scene)
    if overlay is None:
        _clear_hair_overlay_asset(conn, job_id, slot, out)
        return None
    overlay.save(out, "PNG")
    upsert_asset(conn, job_id, slot, "hair_overlay", str(out))
    return overlay


def load_hair_overlay(job_id: str, slot: str) -> Image.Image | None:
    path = job_dir(job_id) / "scene" / f"hair_{slot}.png"
    if not path.is_file():
        return None
    return Image.open(path).convert("RGBA")


def compose_detail(cutout: Image.Image, background: Image.Image, metal: str) -> Image.Image:
    tinted = apply_metal_tint(cutout, metal)
    max_side = int(SIZE * 0.72)
    fitted = ImageOps.contain(tinted, (max_side, max_side))
    canvas = background.copy().convert("RGBA")
    x = (SIZE - fitted.width) // 2
    y = (SIZE - fitted.height) // 2
    shadow, pad = make_shadow_layer(fitted, blur=14, opacity=90)
    shadow_offset = max(6, int(fitted.width * 0.02))
    canvas.alpha_composite(shadow, (x - pad, y - pad + shadow_offset))
    canvas.alpha_composite(fitted, (x, y))
    return canvas.convert("RGB")


def default_transform() -> dict:
    return {"scale": 1.0, "offsetX": 0, "offsetY": 0, "rotate": 0, "hidden": False}


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
    hair_overlay: Image.Image | None = None,
) -> Image.Image:
    anchors = get_anchors(category, body)
    ts = transforms if transforms is not None else default_transforms(len(anchors))
    tinted = apply_metal_tint(cutout, metal)
    canvas = scene.convert("RGBA")
    scene_rgb = np.array(scene.convert("RGB"))

    # Earrings: same cutout mirrored onto both ear anchors, each with its own
    # transform so left/right can be sized/placed independently.
    for i, anchor in enumerate(anchors):
        t = ts[i] if i < len(ts) else default_transform()
        if t.get("hidden"):
            continue
        jewel_w = max(24, int(SIZE * anchor["scale"] * float(t.get("scale", 1))))
        fitted = ImageOps.contain(tinted, (jewel_w, jewel_w))
        if i % 2 == 1:
            fitted = ImageOps.mirror(fitted)
        # Fixed baseline tilt (not a 3D perspective fix, see Anchor docstring
        # in packages/shared/src/index.ts) so a straight cutout doesn't look
        # perfectly flat/pasted on a neck or ear that is rarely upright.
        rotate = float(anchor.get("rotate") or 0) + float(t.get("rotate") or 0)
        if rotate:
            # Positive degrees are clockwise (matches sharp on the web side);
            # Pillow's rotate() is counter-clockwise, so negate here.
            fitted = fitted.rotate(-rotate, resample=Image.BICUBIC, expand=True)
        cx = int(SIZE * anchor["x"] + float(t.get("offsetX", 0)))
        cy = int(SIZE * anchor["y"] + float(t.get("offsetY", 0)))
        fitted = match_jewel_to_scene(fitted, scene_rgb, cx, cy)
        x = cx - fitted.width // 2
        y = cy - fitted.height // 2
        shadow, pad = make_shadow_layer(
            fitted, blur=SCENE_SHADOW_BLUR, opacity=SCENE_SHADOW_OPACITY
        )
        shadow_offset = max(5, int(fitted.width * 0.025))
        canvas.alpha_composite(shadow, (x - pad, y - pad + shadow_offset))
        canvas.alpha_composite(fitted, (x, y))
    if hair_overlay is not None:
        overlay = hair_overlay.convert("RGBA")
        if overlay.size != canvas.size:
            overlay = overlay.resize(canvas.size, Image.Resampling.BILINEAR)
        canvas.alpha_composite(overlay)
    return canvas.convert("RGB")


def add_inset(wide: Image.Image, detail: Image.Image) -> Image.Image:
    """Bottom-right detail inset. Source detail is chosen via Job.insetSlot."""
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


STAGE_ORDER = ["ingest", "cutout", "detail", "scene", "composite", "inset"]


def parse_queue_item(raw: str) -> tuple[str, str | None, list[str] | None]:
    raw = (raw or "").strip()
    if raw.startswith("{"):
        data = json.loads(raw)
        slots = data.get("slots")
        if isinstance(slots, str):
            slots = [slots]
        return str(data["jobId"]), data.get("fromStage"), slots
    return raw, None, None


def stage_rank(stage: str | None) -> int:
    if not stage:
        return 0
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return 0


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise RuntimeError(f"チェックポイントがありません: {path.name}")
    return path


def load_cutouts_from_disk(cutout_dir: Path) -> list[Image.Image]:
    out: list[Image.Image] = []
    for i in range(3):
        path = require_file(cutout_dir / f"cutout_{i}.png")
        out.append(Image.open(path).convert("RGBA"))
    return out


def load_scene_image(scene_dir: Path, slot: str) -> Image.Image:
    return Image.open(require_file(scene_dir / f"{slot}.jpg")).convert("RGB")


def load_detail_image(preview_dir: Path, slot: str) -> Image.Image:
    return Image.open(require_file(preview_dir / ZIP_NAME[slot])).convert("RGB")


def load_preview_transform(conn, job_id: str, slot: str) -> list[dict] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT transform FROM "JobAsset"
            WHERE "jobId" = %s AND "slotKey" = %s AND kind = 'preview'
            LIMIT 1
            """,
            (job_id, slot),
        )
        row = cur.fetchone()
    if not row or row[0] is None:
        return None
    raw = row[0]
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    return None


def save_scene_slots(conn, job_id: str, scene_dir: Path, scenes: dict[str, Image.Image]) -> None:
    ref_path = scene_dir / "persona_ref.jpg"
    if ref_path.is_file():
        upsert_asset(conn, job_id, "persona_ref", "persona_ref", str(ref_path))
    for slot, scene in scenes.items():
        out = scene_dir / f"{slot}.jpg"
        scene.save(out, "JPEG", quality=90)
        upsert_asset(conn, job_id, slot, "scene", str(out))
        logger.info("job_id=%s stage=scene slot=%s", job_id, slot)


def composite_slot(
    conn,
    job_id: str,
    job: dict,
    slot: str,
    scene: Image.Image,
    main_cut: Image.Image,
    preview_dir: Path,
    *,
    reuse_transform: bool = False,
) -> list[dict]:
    body = slot in BODY_SLOTS or slot == "wide_inset"
    ts = None
    if reuse_transform:
        ts = load_preview_transform(conn, job_id, slot)
    if ts is None:
        ts = transforms_from_face(scene, get_anchors(job["category"], body), job["category"])
    overlay = prepare_hair_overlay(conn, job_id, slot, scene, job["category"])
    img = composite_on_scene(
        scene,
        main_cut,
        job["category"],
        job["metal"],
        body=body,
        transforms=ts,
        hair_overlay=overlay,
    )
    if slot != "wide_inset":
        out = preview_dir / ZIP_NAME[slot]
        img.save(out, "JPEG", quality=90)
        upsert_asset(conn, job_id, slot, "preview", str(out), transform=ts)
    logger.info("job_id=%s stage=composite slot=%s transform=%s", job_id, slot, ts)
    return ts


def write_inset(
    conn,
    job_id: str,
    job: dict,
    wide_rgb: Image.Image,
    wide_ts: list[dict],
    preview_dir: Path,
    detail_imgs: dict[str, Image.Image],
) -> None:
    inset_key = job.get("inset_slot") or "detail_a"
    detail = detail_imgs.get(inset_key) or detail_imgs.get("detail_a")
    if detail is None:
        raise RuntimeError("インセット用のディテール画像がありません")
    wide_final = add_inset(wide_rgb, detail)
    out = preview_dir / ZIP_NAME["wide_inset"]
    wide_final.save(out, "JPEG", quality=90)
    upsert_asset(conn, job_id, "wide_inset", "preview", str(out), transform=wide_ts)
    logger.info("job_id=%s stage=inset source=%s", job_id, inset_key)


def run_cutouts(conn, job_id: str, inputs: list[Path], cutout_dir: Path) -> list[Image.Image]:
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
    return cutouts


def run_details(
    conn,
    job_id: str,
    job: dict,
    cutouts: list[Image.Image],
    preview_dir: Path,
    slots: list[str] | None = None,
) -> dict[str, Image.Image]:
    bg_kind = BG_BY_NAME.get(job["background_name"], "marble_white")
    background = make_background(bg_kind)
    target = slots or SLOT_DETAIL
    out_imgs: dict[str, Image.Image] = {}
    for slot in target:
        i = SLOT_DETAIL.index(slot)
        detail = compose_detail(cutouts[i], background, job["metal"])
        out = preview_dir / ZIP_NAME[slot]
        detail.save(out, "JPEG", quality=90)
        upsert_asset(conn, job_id, slot, "preview", str(out))
        out_imgs[slot] = detail
        logger.info("job_id=%s stage=detail slot=%s", job_id, slot)
    return out_imgs


def run_scenes(
    conn,
    job_id: str,
    job: dict,
    scene_dir: Path,
    slots: list[str],
    *,
    reuse_ref: bool,
) -> dict[str, Image.Image]:
    def on_api_call() -> None:
        bump_api_call_count(conn, job_id, 1)

    ref = scene_dir / "persona_ref.jpg" if reuse_ref else None
    scenes = generate_all_scenes(
        persona_name=job["persona_name"],
        persona_image_key=job.get("persona_image_key"),
        category=job["category"],
        slots=slots,
        tone_names=job["tone_names"],
        scene_dir=scene_dir,
        on_api_call=on_api_call,
        reuse_reference_path=ref,
    )
    save_scene_slots(conn, job_id, scene_dir, scenes)
    return scenes


def run_regen(conn, job_id: str, job: dict, slots: list[str], dirs: dict[str, Path]) -> None:
    """Regenerate a subset of slots, keeping persona identity."""
    cutout_dir = dirs["cutout"]
    scene_dir = dirs["scene"]
    preview_dir = dirs["preview"]
    cutouts = load_cutouts_from_disk(cutout_dir)
    main_cut = cutouts[min(job["mainIndex"], 2)]

    details_needed = [s for s in slots if s in SLOT_DETAIL]
    scene_needed = [s for s in slots if s in SCENE_SLOTS]

    if details_needed:
        set_stage(conn, job_id, "detail", "running", error=None)
        run_details(conn, job_id, job, cutouts, preview_dir, details_needed)

    if scene_needed:
        set_stage(conn, job_id, "scene", "running", error=None)
        new_scenes = run_scenes(conn, job_id, job, scene_dir, scene_needed, reuse_ref=True)
        set_stage(conn, job_id, "composite", "running")
        wide_ts = None
        wide_rgb = None
        for slot in scene_needed:
            scene = new_scenes[slot]
            ts = composite_slot(conn, job_id, job, slot, scene, main_cut, preview_dir)
            if slot == "wide_inset":
                wide_ts = ts
                wide_rgb = composite_on_scene(
                    scene,
                    main_cut,
                    job["category"],
                    job["metal"],
                    body=True,
                    transforms=ts,
                    hair_overlay=load_hair_overlay(job_id, slot),
                )

        if "wide_inset" in scene_needed and wide_rgb is not None and wide_ts is not None:
            set_stage(conn, job_id, "inset", "running")
            detail_imgs = {s: load_detail_image(preview_dir, s) for s in SLOT_DETAIL}
            write_inset(conn, job_id, job, wide_rgb, wide_ts, preview_dir, detail_imgs)
    elif details_needed and job.get("inset_slot") in details_needed:
        set_stage(conn, job_id, "inset", "running")
        scene = load_scene_image(scene_dir, "wide_inset")
        ts = load_preview_transform(conn, job_id, "wide_inset") or transforms_from_face(
            scene, get_anchors(job["category"], True), job["category"]
        )
        overlay = prepare_hair_overlay(
            conn, job_id, "wide_inset", scene, job["category"]
        )
        wide_rgb = composite_on_scene(
            scene,
            main_cut,
            job["category"],
            job["metal"],
            body=True,
            transforms=ts,
            hair_overlay=overlay,
        )
        detail_imgs = {s: load_detail_image(preview_dir, s) for s in SLOT_DETAIL}
        write_inset(conn, job_id, job, wide_rgb, ts, preview_dir, detail_imgs)

    set_stage(conn, job_id, "ready", "ready", error=None)


def run_job(
    conn,
    job_id: str,
    *,
    from_stage: str | None = None,
    regen_slots: list[str] | None = None,
) -> None:
    t0 = time.time()
    start = from_stage or "ingest"
    if start == "ready":
        start = "ingest"
    logger.info("job_id=%s start from=%s regen=%s", job_id, start, regen_slots)
    job = load_job(conn, job_id)
    root = job_dir(job_id)
    input_dir = root / "input"
    cutout_dir = root / "cutout"
    scene_dir = root / "scene"
    preview_dir = root / "preview"
    for d in (cutout_dir, scene_dir, preview_dir):
        d.mkdir(parents=True, exist_ok=True)
    dirs = {"cutout": cutout_dir, "scene": scene_dir, "preview": preview_dir}

    if regen_slots:
        run_regen(conn, job_id, job, regen_slots, dirs)
        logger.info("job_id=%s regen ready in %.1fs", job_id, time.time() - t0)
        return

    skip_before = stage_rank(start)

    inputs = sorted(input_dir.glob("product_*.jpg"))
    if len(inputs) != 3:
        raise RuntimeError(f"Expected 3 inputs, found {len(inputs)}")

    if skip_before <= stage_rank("ingest"):
        set_stage(conn, job_id, "ingest", "running", error=None)
        logger.info("job_id=%s stage=ingest ok", job_id)

    if skip_before <= stage_rank("cutout"):
        set_stage(conn, job_id, "cutout", "running", error=None)
        cutouts = run_cutouts(conn, job_id, inputs, cutout_dir)
    else:
        cutouts = load_cutouts_from_disk(cutout_dir)

    main_cut = cutouts[min(job["mainIndex"], 2)]

    if skip_before <= stage_rank("detail"):
        set_stage(conn, job_id, "detail", "running")
        detail_imgs = run_details(conn, job_id, job, cutouts, preview_dir)
    else:
        detail_imgs = {s: load_detail_image(preview_dir, s) for s in SLOT_DETAIL}

    if skip_before <= stage_rank("scene"):
        set_stage(conn, job_id, "scene", "running")
        scenes = run_scenes(
            conn,
            job_id,
            job,
            scene_dir,
            SCENE_SLOTS,
            reuse_ref=(scene_dir / "persona_ref.jpg").is_file(),
        )
    else:
        scenes = {s: load_scene_image(scene_dir, s) for s in SCENE_SLOTS}

    if skip_before <= stage_rank("composite"):
        set_stage(conn, job_id, "composite", "running")
        for slot in WEAR_SLOTS:
            composite_slot(conn, job_id, job, slot, scenes[slot], main_cut, preview_dir)
        for slot in BODY_SLOTS:
            composite_slot(conn, job_id, job, slot, scenes[slot], main_cut, preview_dir)
        wide_ts = transforms_from_face(
            scenes["wide_inset"], get_anchors(job["category"], True), job["category"]
        )
        wide_overlay = prepare_hair_overlay(
            conn, job_id, "wide_inset", scenes["wide_inset"], job["category"]
        )
        wide = composite_on_scene(
            scenes["wide_inset"],
            main_cut,
            job["category"],
            job["metal"],
            body=True,
            transforms=wide_ts,
            hair_overlay=wide_overlay,
        )
    else:
        wide_ts = load_preview_transform(conn, job_id, "wide_inset") or transforms_from_face(
            scenes["wide_inset"], get_anchors(job["category"], True), job["category"]
        )
        wide = composite_on_scene(
            scenes["wide_inset"],
            main_cut,
            job["category"],
            job["metal"],
            body=True,
            transforms=wide_ts,
            hair_overlay=load_hair_overlay(job_id, "wide_inset"),
        )

    if skip_before <= stage_rank("inset"):
        set_stage(conn, job_id, "inset", "running")
        write_inset(conn, job_id, job, wide, wide_ts, preview_dir, detail_imgs)

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
        _, raw = item
        try:
            job_id, from_stage, slots = parse_queue_item(raw)
        except Exception:
            logger.exception("invalid queue payload: %r", raw)
            continue
        with db_connect() as conn:
            stage = from_stage or "ingest"
            try:
                run_job(conn, job_id, from_stage=from_stage, regen_slots=slots)
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
