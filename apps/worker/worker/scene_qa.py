"""Runtime checks on generated person scenes (not just prompt text).

PuLID copies the ID portrait, so prompt-only checks are not enough.
Failed shots are retried in scene_gen.generate_all_scenes.
"""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from worker.face_anchor import detect_faces_detail

logger = logging.getLogger("tiamo.worker.scene_qa")

TURNED_SLOTS = frozenset({"wear_cafe", "wear_date", "body_1", "wide_inset"})
HAND_FOCUS = frozenset({"ring", "bracelet"})
WEAR = frozenset({"wear_office", "wear_cafe", "wear_date", "wear_holiday"})
FULL = frozenset({"body_1", "body_2", "wide_inset"})

# Chest band vs face width. Front-on bust is typically >2.0; a side-on body ~1.1–1.7.
_MIN_TORSO_RATIO = 1.85


def _torso_width_ratio(image: Image.Image, face: dict) -> float | None:
    """Foreground width at the upper chest divided by face width, or None if unsure."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w, _ = rgb.shape
    fw_px = float(face["w"] * w)
    fh_px = float(face["h"] * h)
    if fw_px < 8 or fh_px < 8:
        return None
    cx = int(face["cx"] * w)
    chin_y = int((face["y"] + face["h"]) * h)
    row_y = chin_y + int(0.45 * fh_px)
    if row_y >= h - 4:
        return None
    y0, y1 = max(0, row_y - 6), min(h, row_y + 7)
    half = int(3.6 * fw_px)
    x0, x1 = max(0, cx - half), min(w, cx + half)
    band = rgb[y0:y1, x0:x1]
    if band.size == 0:
        return None
    gray = band.mean(axis=2).mean(axis=0)
    n = int(gray.shape[0])
    if n < 20:
        return None
    pad = max(3, n // 10)
    bg = float(np.median(np.concatenate([gray[:pad], gray[-pad:]])))
    diff = np.abs(gray - bg)
    if float(np.median(diff)) > 35:
        return None
    thr = max(22.0, float(np.percentile(diff, 55)))
    mask = diff > thr
    longest = 0
    run = 0
    for v in mask:
        if v:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    if longest < 8:
        return None
    return longest / fw_px


def evaluate_scene(image: Image.Image, slot: str, category: str) -> list[str]:
    """Return human-readable failures. Empty list = pass (or undetectable)."""
    faces = detect_faces_detail(image)
    fails: list[str] = []
    if not faces:
        fails.append("no face detected")
        return fails

    main = faces[0]
    if category in HAND_FOCUS and slot in WEAR:
        if main["area"] > 0.16:
            fails.append(f"face too large for hand-hero crop area={main['area']:.2f}")
        if main["cy"] > 0.48:
            fails.append(f"face not at top/edge cy={main['cy']:.2f}")
    if category in HAND_FOCUS and slot in FULL:
        # Waist-up crossed-arm fashion shots put the face near the top
        # (cy~0.23, area~0.04). Real head-to-toe is smaller and higher.
        if main["area"] > 0.030:
            fails.append(f"face too large for full-body area={main['area']:.2f}")
        if main["cy"] > 0.20:
            fails.append(
                f"not full-length (likely arms-crossed bust) cy={main['cy']:.2f}"
            )

    if slot == "wear_date":
        if main["cx"] > 0.62 and main["cy"] > 0.40:
            fails.append(
                f"date: foreground is not the woman cx={main['cx']:.2f} cy={main['cy']:.2f}"
            )
        # Ring/bracelet wear shots keep the face small on purpose.
        if category not in HAND_FOCUS and main["area"] < 0.03:
            fails.append("date: woman face too small (she is in the background)")

    # Passport-level front face on slots that must show a turned HEAD.
    # Do not require a full profile — that rotates the whole body past 15°.
    if (
        slot in TURNED_SLOTS
        and main["eye_span"] > 0.42
        and main["nose_offset"] < 0.05
    ):
        fails.append(
            f"face too frontal for turned slot eye_span={main['eye_span']:.2f} "
            f"nose_offset={main['nose_offset']:.2f}"
        )

    hand_wear = category in HAND_FOCUS and slot in WEAR
    if not hand_wear:
        if main["eye_span"] < 0.22:
            fails.append(
                f"body in profile (full profile face eye_span={main['eye_span']:.2f})"
            )
        ratio = _torso_width_ratio(image, main)
        if ratio is not None and ratio < _MIN_TORSO_RATIO:
            fails.append(f"torso too side-on chest/face={ratio:.2f}")
    return fails
