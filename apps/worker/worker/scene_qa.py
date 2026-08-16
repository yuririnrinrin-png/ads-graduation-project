"""Runtime checks on generated person scenes (not just prompt text).

PuLID copies the ID portrait, so prompt-only checks are not enough.
Failed shots are retried in scene_gen.generate_all_scenes.
"""

from __future__ import annotations

import logging

from PIL import Image

from worker.face_anchor import detect_faces_detail

logger = logging.getLogger("tiamo.worker.scene_qa")

TURNED_SLOTS = frozenset({"wear_cafe", "wear_date", "body_1", "wide_inset"})
HAND_FOCUS = frozenset({"ring", "bracelet"})
WEAR = frozenset({"wear_office", "wear_cafe", "wear_date", "wear_holiday"})
FULL = frozenset({"body_1", "body_2", "wide_inset"})


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
        if main["area"] > 0.10:
            fails.append(f"face too large for full-body area={main['area']:.2f}")
        if main["cy"] > 0.32:
            fails.append(
                f"not full-length (likely arms-crossed bust) cy={main['cy']:.2f}"
            )

    if slot == "wear_date":
        if main["cx"] > 0.62 and main["cy"] > 0.40:
            fails.append(
                f"date: foreground is not the woman cx={main['cx']:.2f} cy={main['cy']:.2f}"
            )
        if category in HAND_FOCUS and main["area"] < 0.03:
            fails.append("date: woman face too small (she is in the background)")

    if slot in TURNED_SLOTS and main["frontal"]:
        fails.append(
            f"face too frontal for turned slot eye_span={main['eye_span']:.2f} "
            f"nose_offset={main['nose_offset']:.2f}"
        )
    return fails
