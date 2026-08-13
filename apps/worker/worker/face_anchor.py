"""Shift necklace/earring starting position using a face bounding box.

Not landmark-based neck detection (that's the heavier 案A). We only find the
largest face, then put the jewel a fixed fraction of the face-height below the
chin (necklace) or at the sides of the box (earrings). Miss / unsupported
category → default zero transforms, same as before.

The resulting offsets are stored on JobAsset.transform so the web drag UI and
sharp recomposite keep using CATEGORY_ANCHORS + transform (no TS face detector).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover - worker requirements include opencv
    cv2 = None

logger = logging.getLogger("tiamo.worker")

SIZE = 2000  # must match packages/shared CANVAS_SIZE and pipeline.SIZE
# Must match packages/shared TRANSFORM_OFFSET_LIMIT (web drag + PATCH clamp).
OFFSET_LIMIT = 1000
_MODEL = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
# Source: https://github.com/opencv/opencv_zoo (face_detection_yunet, 2023mar)
_detector = None
_detector_size: tuple[int, int] | None = None

# Necklace center sits this many face-heights below the chin (collarbone-ish).
_NECKLACE_BELOW_CHIN = 0.45
# Ears are ~42% down the face box, slightly outside left/right edges.
_EAR_Y_IN_FACE = 0.42
_EAR_OUTSET = 0.10


def _default_transforms(count: int) -> list[dict]:
    return [{"scale": 1.0, "offsetX": 0, "offsetY": 0} for _ in range(count)]


def _clamp_offset(value: float) -> int:
    return int(max(-OFFSET_LIMIT, min(OFFSET_LIMIT, round(value))))


def _get_detector(w: int, h: int):
    """Reuse one YuNet instance. Recreating it every call spams OpenCV 5 warnings."""
    global _detector, _detector_size
    if cv2 is None:
        logger.warning("opencv not installed — skip face-based placement")
        return None
    if not _MODEL.is_file():
        logger.warning("YuNet model missing at %s — skip face-based placement", _MODEL)
        return None
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(str(_MODEL), "", (w, h), 0.55, 0.3, 5000)
        _detector_size = (w, h)
    elif _detector_size != (w, h):
        _detector.setInputSize((w, h))
        _detector_size = (w, h)
    return _detector


def detect_face_norm(image: Image.Image) -> tuple[float, float, float, float] | None:
    """Largest face as (x, y, w, h) in 0–1 image coords, or None."""
    if cv2 is None:
        return None
    rgb = np.array(image.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    detector = _get_detector(w, h)
    if detector is None:
        return None
    _retval, faces = detector.detect(bgr)
    if faces is None or len(faces) == 0:
        return None

    parsed: list[tuple[float, float, float, float, float, float, float]] = []
    for f in faces:
        x, y, fw, fh = (float(v) for v in f[:4])
        cx = (x + fw / 2) / w
        cy = (y + fh / 2) / h
        parsed.append((fw * fh, cx, cy, x / w, y / h, fw / w, fh / h))
    # Prefer a face in the middle of the frame (the jewelry wearer). A date
    # companion or a bokeh blob at the edge used to win "largest face" and
    # park the necklace on a shoulder / empty space.
    centered = [p for p in parsed if 0.18 <= p[1] <= 0.82 and p[2] < 0.70]
    pool = centered if centered else parsed
    _area, _cx, _cy, nx, ny, nw, nh = max(pool, key=lambda p: p[0])
    return (nx, ny, nw, nh)


def _necklace_target(face: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = face
    cx = x + w / 2
    chin_y = y + h
    ty = chin_y + _NECKLACE_BELOW_CHIN * h
    return (
        min(0.85, max(0.15, cx)),
        min(0.88, max(0.18, ty)),
    )


def _earring_targets(face: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    x, y, w, h = face
    ear_y = min(0.85, max(0.12, y + _EAR_Y_IN_FACE * h))
    left_x = min(0.85, max(0.08, x - _EAR_OUTSET * w))
    right_x = min(0.92, max(0.15, x + w + _EAR_OUTSET * w))
    return [(left_x, ear_y), (right_x, ear_y)]


def transforms_from_face(
    image: Image.Image,
    anchors: list[dict],
    category: str,
) -> list[dict]:
    """Per-anchor transforms that move jewelry from the fixed category anchor
    onto a face-relative spot. Ring/bracelet and detection misses return zeros.
    """
    n = len(anchors)
    if category not in ("necklace", "earring"):
        return _default_transforms(n)

    face = detect_face_norm(image)
    if face is None:
        logger.info("face not detected — using default anchors for %s", category)
        return _default_transforms(n)

    fx, fy, fw, fh = face
    logger.info(
        "face box x=%.2f y=%.2f w=%.2f h=%.2f category=%s",
        fx, fy, fw, fh, category,
    )

    if category == "necklace":
        targets = [_necklace_target(face)]
    else:
        targets = _earring_targets(face)

    out: list[dict] = []
    for i, anchor in enumerate(anchors):
        tx, ty = targets[i] if i < len(targets) else (anchor["x"], anchor["y"])
        out.append(
            {
                "scale": 1.0,
                "offsetX": _clamp_offset((tx - float(anchor["x"])) * SIZE),
                "offsetY": _clamp_offset((ty - float(anchor["y"])) * SIZE),
            }
        )
    return out
