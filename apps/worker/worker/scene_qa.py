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

TURNED_SLOTS = frozenset({"wear_cafe", "wear_date", "body_1"})
HAND_FOCUS = frozenset({"ring", "bracelet"})
WEAR = frozenset({"wear_office", "wear_cafe", "wear_date", "wear_holiday"})
FULL = frozenset({"body_1", "body_2", "wide_inset"})

# Chest band vs face width. Front-on bust is typically >2.0; a side-on body ~1.1–1.7.
_MIN_TORSO_RATIO = 1.85
# Full-body walking profiles often skip the clean-bg path; still reject obvious thin silhouettes.
_MIN_TORSO_RATIO_BUSY = 1.50
# True profile face on a full-body shot almost always means the torso turned too.
_PROFILE_FACE_EYE_SPAN = 0.26


def _torso_width_ratio(image: Image.Image, face: dict) -> tuple[float | None, bool]:
    """Foreground width at the upper chest divided by face width.

    Returns (ratio, busy_bg). ratio is None if the band is too unreliable.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w, _ = rgb.shape
    fw_px = float(face["w"] * w)
    fh_px = float(face["h"] * h)
    if fw_px < 8 or fh_px < 8:
        return None, False
    # Shift the chest sample toward the torso (opposite the nose) so a
    # profile head does not center the band on empty space beside the body.
    ndx = float(face.get("nose_dx") or 0.0)
    cx = int(face["cx"] * w - ndx * 1.15 * fw_px)
    cx = max(int(1.8 * fw_px), min(w - int(1.8 * fw_px), cx))
    chin_y = int((face["y"] + face["h"]) * h)
    row_y = chin_y + int(0.45 * fh_px)
    if row_y >= h - 4:
        return None, False
    y0, y1 = max(0, row_y - 6), min(h, row_y + 7)
    half = int(3.6 * fw_px)
    x0, x1 = max(0, cx - half), min(w, cx + half)
    band = rgb[y0:y1, x0:x1]
    if band.size == 0:
        return None, False
    gray = band.mean(axis=2).mean(axis=0)
    n = int(gray.shape[0])
    if n < 20:
        return None, False
    pad = max(3, n // 10)
    bg = float(np.median(np.concatenate([gray[:pad], gray[-pad:]])))
    diff = np.abs(gray - bg)
    busy = float(np.median(diff)) > 35
    thr = max(22.0, float(np.percentile(diff, 55)))
    if busy:
        thr = max(40.0, float(np.percentile(diff, 65)))
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
        return None, busy
    return longest / fw_px, busy


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
    if slot in FULL:
        # Necklace/earring wide shots also drift into over-shoulder busts.
        max_area = 0.030 if category in HAND_FOCUS else 0.040
        max_cy = 0.20 if category in HAND_FOCUS else 0.22
        if main["area"] > max_area:
            fails.append(f"face too large for full-body area={main['area']:.2f}")
        if main["cy"] > max_cy:
            fails.append(
                f"not full-length (likely over-shoulder / arms-crossed bust) cy={main['cy']:.2f}"
            )

    if slot == "wear_date":
        if main["cx"] > 0.62 and main["cy"] > 0.40:
            fails.append(
                f"date: foreground is not the woman cx={main['cx']:.2f} cy={main['cy']:.2f}"
            )
        # Ring/bracelet wear shots keep the face small on purpose.
        if category not in HAND_FOCUS and main["area"] < 0.03:
            fails.append("date: woman face too small (she is in the background)")
        if category not in HAND_FOCUS:
            companions = [
                f
                for f in faces[1:]
                if f["area"] < main["area"] * 0.95 and f["area"] > 0.004
            ]
            if not companions:
                fails.append("date: no second person (man missing)")
            else:
                man = max(companions, key=lambda f: f["area"])
                if man["area"] >= main["area"]:
                    fails.append("date: man is as large as the woman")

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
        ratio, busy = _torso_width_ratio(image, main)
        min_ratio = _MIN_TORSO_RATIO_BUSY if busy else _MIN_TORSO_RATIO
        if ratio is not None and ratio < min_ratio:
            fails.append(f"torso too side-on chest/face={ratio:.2f}")

        # Full profile head is allowed in the prompt, but on a full-body crop it
        # almost always means the whole person turned (walking side-view).
        profile_face = main["eye_span"] < _PROFILE_FACE_EYE_SPAN
        if slot in FULL:
            if main["cx"] < 0.22 or main["cx"] > 0.78:
                fails.append(f"likely walking profile (face cx={main['cx']:.2f})")
            if profile_face and (ratio is None or ratio < 2.0):
                fails.append(
                    f"body in profile (full-body + profile face "
                    f"eye_span={main['eye_span']:.2f})"
                )
            # Face looking back at the camera while the torso stays side-on.
            if (
                ratio is not None
                and ratio < 2.1
                and main["eye_span"] >= _PROFILE_FACE_EYE_SPAN
            ):
                fails.append(
                    f"over-shoulder side-on body chest/face={ratio:.2f} "
                    f"eye_span={main['eye_span']:.2f}"
                )
        elif main["eye_span"] < 0.22:
            fails.append(
                f"body in profile (full profile face eye_span={main['eye_span']:.2f})"
            )
    return fails
