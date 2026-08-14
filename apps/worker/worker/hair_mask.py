"""Hair overlay for tucked-down slots (wear_cafe, wide_inset).

Jewelry is pasted as a flat cutout. On those two slots hair may fall behind
the ears onto the neck/chest, so we put detected hair pixels back on top.
If the mask is unusable we return None and compositing skips occlusion
(prompts already keep hair off the collarbones).

Must stay in sync with packages/shared HAIR_OVERLAY_SLOTS.
"""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from worker.face_anchor import detect_face_norm

logger = logging.getLogger("tiamo.worker")

HAIR_OVERLAY_SLOTS = frozenset({"wear_cafe", "wide_inset"})

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def build_hair_overlay(scene: Image.Image) -> Image.Image | None:
    """RGBA same size as scene; non-hair pixels fully transparent."""
    if cv2 is None:
        logger.warning("opencv missing — skip hair overlay")
        return None
    face = detect_face_norm(scene)
    if face is None:
        logger.info("hair overlay skipped — no face")
        return None

    rgb = np.array(scene.convert("RGB"))
    h, w = rgb.shape[:2]
    fx, fy, fw, fh = face
    x0 = int(max(0, (fx - 0.7 * fw) * w))
    x1 = int(min(w, (fx + 1.7 * fw) * w))
    y0 = int(max(0, (fy - 0.55 * fh) * h))
    y1 = int(min(h, (fy + 2.6 * fh) * h))
    if x1 - x0 < 40 or y1 - y0 < 40:
        return None

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    v = hsv[:, :, 2].astype(np.float32)
    s = hsv[:, :, 1].astype(np.float32)

    # Skin sample from inner face (avoid hairline).
    ix0 = int((fx + 0.25 * fw) * w)
    ix1 = int((fx + 0.75 * fw) * w)
    iy0 = int((fy + 0.30 * fh) * h)
    iy1 = int((fy + 0.70 * fh) * h)
    skin = np.ascontiguousarray(
        rgb[max(0, iy0) : min(h, iy1), max(0, ix0) : min(w, ix1)]
    )
    if skin.size == 0:
        return None
    skin_v = float(np.median(cv2.cvtColor(skin, cv2.COLOR_RGB2HSV)[:, :, 2]))

    # Corners ≈ background — exclude similar colors so cafe wood isn't "hair".
    cs = 80
    corners = np.concatenate(
        [
            rgb[:cs, :cs].reshape(-1, 3),
            rgb[:cs, -cs:].reshape(-1, 3),
            rgb[-cs:, :cs].reshape(-1, 3),
            rgb[-cs:, -cs:].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_mean = corners.mean(axis=0).astype(np.float32)

    roi = np.zeros((h, w), dtype=bool)
    roi[y0:y1, x0:x1] = True
    # Keep inner face clear (eyes/skin) but allow hair at sides (ears).
    face_mask = np.zeros((h, w), dtype=np.uint8)
    cx = int((fx + fw / 2) * w)
    cy = int((fy + fh / 2) * h)
    ax = int(fw * w * 0.38)
    ay = int(fh * h * 0.42)
    cv2.ellipse(face_mask, (cx, cy), (max(8, ax), max(8, ay)), 0, 0, 360, 255, -1)
    inner_face = face_mask > 0

    darker = v < skin_v * 0.72
    not_bright = v < 150
    not_gray_bg = s > 18
    diff = np.linalg.norm(rgb.astype(np.float32) - bg_mean, axis=2)
    not_bg = diff > 28

    hair = roi & darker & not_bright & not_gray_bg & not_bg & ~inner_face
    mask = hair.astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.GaussianBlur(mask, (0, 0), 1.6)

    frac = float((mask > 40).mean())
    if frac < 0.004 or frac > 0.32:
        logger.info("hair overlay skipped — coverage=%.3f", frac)
        return None

    rgba = np.dstack([rgb, mask])
    logger.info("hair overlay coverage=%.3f", frac)
    return Image.fromarray(rgba, "RGBA")
