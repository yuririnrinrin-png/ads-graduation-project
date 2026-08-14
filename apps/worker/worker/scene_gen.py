"""
Person-only scene generation for wear / body / wide slots.

- No FAL_KEY → local silhouette placeholders (dev without spend)
- FAL_KEY set → Flux base face + PuLID scenes (same persona across 7 shots)

Jewelry is never drawn here; real cutouts are composited later.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import random
from pathlib import Path
from typing import Callable
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("tiamo.worker.scene")

SIZE = 2000
FAL_GEN_SIZE = 1024  # generate square_hd-ish, then upscale to SIZE

# Seed personas: stable appearance text so Flux can invent a reference face.
# IMPORTANT: this must NOT mention hairstyle/state (up, down, ponytail, etc).
# It used to bake in a fixed hairstyle (e.g. "long wavy hair"), which then
# contradicted the per-slot "hair up in a bun" instructions below in the same
# prompt — the model almost always obeyed this earlier, stronger-sounding
# description and ignored the later hair override. Hair length/color only
# (not styling state) lives in PERSONA_HAIR so it can be combined with a
# per-slot style word without conflicting.
PERSONA_LOOK = {
    "Sofia": (
        "Italian woman in her late 20s, warm olive skin, soft brown eyes, "
        "refined features, natural makeup"
    ),
    "Elena": (
        "Italian woman in her early 30s, fair skin with light freckles, "
        "hazel eyes, refined features, natural makeup"
    ),
    "Mia": (
        "young Italian woman about 25, light tan skin, dark eyes, fresh minimal makeup"
    ),
}

# Hair length/color only — no styling state (that comes from HAIR_STYLE per slot).
PERSONA_HAIR = {
    "Sofia": "long chestnut-brown hair",
    "Elena": "shoulder-length ash-brown hair",
    "Mia": "dark hair",
}

SCENE_META = {
    "wear_office": {"label": "office", "mode": "bust", "bg": (214, 208, 198)},
    "wear_cafe": {"label": "cafe", "mode": "bust", "bg": (196, 178, 158)},
    "wear_date": {"label": "date", "mode": "bust", "bg": (188, 176, 186)},
    "wear_holiday": {"label": "holiday", "mode": "bust", "bg": (186, 198, 178)},
    "body_1": {"label": "body · tone1", "mode": "full", "bg": (210, 200, 188)},
    "body_2": {"label": "body · tone2", "mode": "full", "bg": (198, 188, 176)},
    "wide_inset": {"label": "wide", "mode": "full", "bg": (204, 196, 184)},
}

WEAR_SETTING = {
    "wear_office": (
        "sitting at a modern glass office desk with an open laptop and a small "
        "potted plant, floor-to-ceiling window showing a blurred city skyline "
        "behind her, bright daylight, professional atmosphere"
    ),
    "wear_cafe": (
        "sitting at a rustic wooden cafe table with a cappuccino cup and a "
        "croissant on a small plate, shelves of coffee beans and warm pendant "
        "lights softly blurred behind her, sunlit afternoon"
    ),
    "wear_date": (
        "she sits facing the camera at a fine-dining table; a man in a dark "
        "suit is softly blurred in the background, not the focus. A lit candle "
        "and two wine glasses, warm bokeh lights, romantic evening. She does "
        "NOT look over her shoulder"
    ),
    "wear_holiday": (
        "sitting on a wooden beach pier railing, ocean waves and palm leaves "
        "blurred in the background, warm golden-hour sunlight, breezy relaxed mood"
    ),
}

# Distinct fashion style per wear slot — without this, the model defaults to
# one generic outfit for all four scenes.
WEAR_FASHION = {
    "wear_office": (
        "wearing an open tailored blazer over a V-neck or scoop silk blouse, "
        "collarbones and the front of the neck fully visible, jacket not "
        "buttoned to the throat, polished professional office fashion"
    ),
    "wear_cafe": (
        "wearing an open-collar or V-neck blouse, collarbones visible, "
        "no turtleneck, casual-chic weekend-brunch style"
    ),
    "wear_date": (
        "wearing a sophisticated fitted dress with an open neckline, "
        "collarbones and décolletage visible, grown-up evening style"
    ),
    "wear_holiday": (
        "wearing a refined flowing dress with an open neckline, "
        "collarbones visible, elegant resort holiday style"
    ),
}

TONE_SETTING = {
    "オフィス": (
        "wearing a sharply tailored conservative business suit or structured "
        "dress, polished corporate office fashion"
    ),
    "休日": (
        "wearing a relaxed weekend outfit, soft knit sweater and easy trousers"
    ),
    "エレガント": (
        "wearing an elegant conservative tailored dress or set in refined "
        "fabrics, sophisticated understated luxury"
    ),
    "リラックス": (
        "wearing fresh casual denim jeans with a crisp clean white or pastel "
        "t-shirt, relaxed effortlessly cool everyday style"
    ),
}

# Torso stays jewelry-friendly. Never say "facing camera" about the person as
# a whole — Flux/PuLID treats that as a frontal FACE.
BODY_RULE = (
    "Shoulders and chest stay square to the lens (torso yaw under 15 degrees). "
    "The FACE is independent and must NOT copy a frontal ID photo."
)

# Slots that must break the ID photo's front-facing eye-contact pose.
TURNED_SLOTS = frozenset({"wear_cafe", "wear_date", "body_1", "wide_inset"})

POSE_VARIATION = {
    "wear_office": (
        "HEAD: three-quarter view, turned 30 degrees, not a passport photo. "
        "キリッとした笑顔: sharp closed-mouth smile, no teeth. "
        "GAZE: toward camera but SOFT, upper lids slightly lowered"
    ),
    "wear_cafe": (
        "HEAD: strong three-quarter, turned 50–60 degrees — we see her ear, "
        "jaw, and one cheek more than the other. Holding a cup. "
        "自然な笑顔: quiet closed-mouth smile. "
        "GAZE: DOWNCAST looking at the cup, eyes averted, ZERO eye contact, "
        "not looking at the lens"
    ),
    "wear_date": (
        "HEAD: three-quarter, turned 45 degrees, ear visible. "
        "甘えたような笑顔: coy closed-mouth smile. "
        "GAZE: looking off-camera and slightly down, no eye contact"
    ),
    "wear_holiday": (
        "HEAD: tilted to one shoulder, turned about 25 degrees. "
        "華やかな笑顔: glamorous smile SHOWING TEETH. "
        "GAZE: toward camera but squinting softly from the smile, not a stare"
    ),
    "body_1": (
        "HEAD: STRICT SIDE PROFILE, about 80–90 degrees. We see only ONE eye, "
        "her ear, and the side of her nose. Chin slightly up. "
        "上品で静か: calm closed lips. "
        "GAZE: eyes closed or looking down along the profile — never at camera"
    ),
    "body_2": (
        "HEAD: turned 25 degrees with a playful tilt. "
        "屈託ない笑顔: open grin SHOWING TEETH. "
        "GAZE: toward camera but crinkled and soft"
    ),
    "wide_inset": (
        "HEAD: three-quarter, turned 45–50 degrees, ear and jaw clearly shown. "
        "上品な微笑: calm closed-mouth smile. "
        "GAZE: downcast, looking down and away, no eye contact"
    ),
}

# Each slot a distinct jewelry-safe style. "tuck" = down the back only
# (cafe + wide). Never hair over the chest, ears, or front of the neck.
HAIR_STYLE = {
    "wear_office": (
        "up",
        "in a sleek high bun at the crown, every strand off the neck, "
        "nape and both ears fully exposed",
    ),
    "wear_cafe": (
        "tuck",
        "LONG HAIR WORN COMPLETELY DOWN, length clearly visible past the "
        "shoulders down her back, loosely tucked behind both ears so earlobes "
        "show. This is NOT an updo. Hair mass behind her is obvious",
    ),
    "wear_date": (
        "up",
        "in a high sleek ponytail at the crown, nape and both ears fully "
        "visible, no hair on the shoulders",
    ),
    "wear_holiday": (
        "up",
        "in a smooth low bun at the nape, both ears visible, no loose hair "
        "on the chest",
    ),
    "body_1": (
        "up",
        "in a gathered updo, both ears fully visible, neck clear",
    ),
    "body_2": (
        "up",
        "in an updo with both ears completely uncovered, neck clear",
    ),
    "wide_inset": (
        "tuck",
        "LONG HAIR WORN COMPLETELY DOWN, length clearly visible past the "
        "shoulders down her back, loosely tucked behind both ears so earlobes "
        "show. This is NOT an updo. Hair mass behind her is obvious",
    ),
}

HAIR_NEGATIVE_BY_STATE = {
    "up": "hair down, loose hair over the shoulders, hair covering the ears, "
    "hair covering the neck, hair on the chest",
    "tuck": "updo, bun, chignon, ponytail, hair pulled up, hair in a knot, "
    "short pixie, hair covering the collarbones, hair on the chest, "
    "hair covering the earlobes",
}

# Forbid profile / over-shoulder / the opposite hair of this slot.
SLOT_NEGATIVE_EXTRA = {
    "wear_office": (
        "teeth showing, open-mouth laugh, coy pout, downcast looking away, "
        "eyes closed, blank stare, piercing stare, turtleneck"
    ),
    "wear_cafe": (
        "looking at the camera, eye contact, looking at the viewer, "
        "facing the camera, frontal face, both eyes equally visible, "
        "passport photo, toothy grin, bun, ponytail, updo, turtleneck"
    ),
    "wear_date": (
        "looking at the camera, eye contact, frontal face, passport photo, "
        "teeth showing, big laugh, turtleneck"
    ),
    "wear_holiday": (
        "eyes closed, downcast looking away, closed-mouth only, coy pout, "
        "serious frown, piercing stare, turtleneck"
    ),
    "body_1": (
        "looking at the camera, eye contact, frontal face, both eyes visible, "
        "passport photo, teeth showing, big grin, tight headshot"
    ),
    "body_2": (
        "closed-mouth polite smile, eyes closed, looking away, frowning, "
        "blank stare, piercing stare, tight headshot"
    ),
    "wide_inset": (
        "looking at the camera, eye contact, frontal face, passport photo, "
        "both eyes equally visible, big grin, teeth showing, bun, ponytail, "
        "updo, tight headshot"
    ),
}

# Wear-4 camera: necklace/earring stay bust/face. Ring/bracelet put the
# placement zone (fingers / wrist) in the lower frame. Face stays in-shot
# so PuLID can still lock identity — never a finger-only macro.
HAND_FOCUS_CATEGORIES = frozenset({"ring", "bracelet"})

CATEGORY_FRAMING = {
    "necklace": (
        "bust-up portrait showing face, neck, and upper chest, camera pulled "
        "back enough that neck and collarbones are clearly inside the frame "
        "(not a tight face-only close-up). Bare neck and décolletage clearly visible"
    ),
    "earring": (
        "portrait showing at least the near ear fully, bare earlobe, "
        "hair tucked behind the ear so jewelry can sit there"
    ),
    "ring": (
        "CRITICAL CROP: her BARE HANDS AND FINGERS fill the lower two-thirds "
        "of the square frame and are the subject. The PALM OR BACK OF THE HAND "
        "faces the camera (hand plane yaw under 15 degrees) so a flat ring "
        "photo can sit on the finger. Fingers slightly spread, ring finger "
        "unobstructed. Her face stays clearly visible in the upper third "
        "(identity), smaller than the hands — not a face close-up, not a "
        "finger-only macro with no face"
    ),
    "bracelet": (
        "CRITICAL CROP: her BARE FOREARM AND WRIST fill the lower two-thirds "
        "of the square frame and are the subject. The INNER WRIST faces the "
        "camera almost flat (wrist yaw under 15 degrees), forearm lying across "
        "the lower frame like a jewelry catalog, sleeve pushed up so the wrist "
        "bone is fully visible. NOT a steep side-on cylinder. "
        "Her face stays clearly visible in the upper third (identity), "
        "smaller than the arm — not a face close-up, not a wrist-only "
        "macro with no face"
    ),
}

# Same idea as BODY_RULE for the torso: the placement plane faces the lens
# so a flat real cutout can sit on it. Lead the hand-category prompts with this.
HAND_PRESENT_RULE = {
    "ring": (
        "HANDS FACE THE LENS. The back or palm of the near hand is square to "
        "the camera. Do NOT twist the wrist into profile. Do NOT cross the arms. "
        "Do NOT rest a hand on the opposite shoulder."
    ),
    "bracelet": (
        "WRIST FACES THE LENS. The inner wrist is presented almost flat to the "
        "camera, like showing a watch. Forearm across the lower frame, not "
        "pointing at the lens as a steep cylinder. Do NOT cross the arms. "
        "Do NOT hug herself. Do NOT rest a hand on the opposite shoulder."
    ),
}

# Per-slot hand/wrist action so the four wear shots are not copies.
WEAR_HAND_POSE = {
    "ring": {
        "wear_office": (
            "Both hands rest on the glass desk, palms down, backs of the hands "
            "facing the camera, fingers relaxed and slightly spread."
        ),
        "wear_cafe": (
            "Hands rest on the table beside the cup — not gripping it. "
            "Backs of the hands face the camera, fingers fully visible."
        ),
        "wear_date": (
            "One hand rests flat on the tablecloth near a wine glass, "
            "back of the hand to the camera, fingers loosely open."
        ),
        "wear_holiday": (
            "Hands rest on the pier railing, backs of the hands to the camera, "
            "fingers slightly spread in sunlight."
        ),
    },
    "bracelet": {
        "wear_office": (
            "One forearm lies across the glass desk toward the camera, "
            "inner wrist flat and fully shown, sleeve rolled to mid-forearm."
        ),
        "wear_cafe": (
            "Forearm rests on the wooden table beside the cup, inner wrist "
            "flat to the camera, sleeve pushed up. She is not holding the cup."
        ),
        "wear_date": (
            "One forearm rests on the white tablecloth, inner wrist presented "
            "flat to the camera near a wine glass. Arms are NOT crossed."
        ),
        "wear_holiday": (
            "Forearm rests along the pier railing, inner wrist flat to the "
            "camera, sleeve away from the wrist bone."
        ),
    },
}

WEAR_FASHION_HAND = {
    "ring": (
        "wearing a refined outfit whose sleeves stay clear of the hands; "
        "bare fingers, no gloves, no stacked rings"
    ),
    "bracelet": (
        "wearing a refined outfit with sleeves rolled or short so both wrists "
        "can show; no watch, no cuff covering the wrist bone"
    ),
}

# Full-body / wide: keep the standing crop, but the placement zone must exist.
CATEGORY_FULL_EXTRA = {
    "ring": (
        "One hand is slightly forward, back of the hand facing the camera, "
        "fingers visible (not in pockets, not a fist, not behind her back, "
        "arms not crossed)."
    ),
    "bracelet": (
        "One forearm is slightly forward, inner wrist facing the camera, "
        "sleeve not covering the wrist (not hands in pockets, arms not "
        "crossed, not hugging herself)."
    ),
}

HAND_NEGATIVE = (
    "tight face-only crop, headshot, no hands, hands out of frame, "
    "hands in pockets, clenched fists, gloves, extra fingers, "
    "deformed hands, missing fingers, jewelry on the hands, "
    "arms crossed, crossed arms, hugging herself, hand on opposite "
    "shoulder, wrist in profile, steep foreshortened arm, "
    "side-on wrist, arm pointing at the camera"
)

HAND_NEGATIVE_BY_CATEGORY = {
    "ring": "fingers hidden, fist, hands behind back, edge-on hand",
    "bracelet": (
        "long sleeves covering wrists, watch, cuffs over the wrist, "
        "arms crossed, wrist in profile, cylindrical side view of the arm"
    ),
}

NEGATIVE = (
    "jewelry, necklace, earrings, rings, bracelet, watch, accessories, "
    "text, watermark, logo, deformed hands, extra fingers, low quality, blurry, "
    "back to camera, body facing away, over-the-shoulder body twist, "
    "passport photo, identical polite smile, piercing stare into the lens, "
    "extreme close-up, tight face-only crop, "
    "face filling the entire frame, cropped above the collarbone, "
    "hair covering the ears, hair covering the front of the neck"
)

NEGATIVE_BUST = NEGATIVE + (
    ", turtleneck, high neck, mock neck, hair on the chest"
)

# Face-lock models bias toward tight headshots; push back for the wider
# "coordinate" shots so at least the outfit/torso reads clearly (feet may
# still be out of frame — that's fine, we only need the styling to be visible).
# Turtleneck is allowed on full-body / wide shots.
NEGATIVE_FULL_BODY = NEGATIVE + (
    ", extreme close-up, tight headshot, face-only crop, cut off above the waist"
)


def fal_enabled() -> bool:
    return bool(os.environ.get("FAL_KEY", "").strip())


def persona_look(name: str) -> str:
    if name in PERSONA_LOOK:
        return PERSONA_LOOK[name]
    # Unknown persona: deterministic soft description from the name hash.
    h = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return (
        f"Italian woman named {name}, adult, photorealistic beauty editorial look, "
        f"natural features (id {h[:8]})"
    )


def persona_hair(name: str) -> str:
    if name in PERSONA_HAIR:
        return PERSONA_HAIR[name]
    h = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return f"medium-length brown hair (id {h[:4]})"


def category_framing(category: str) -> str:
    return CATEGORY_FRAMING.get(category, CATEGORY_FRAMING["necklace"])


def build_reference_prompt(persona_name: str) -> str:
    look = persona_look(persona_name)
    hair = persona_hair(persona_name)
    return (
        f"Photorealistic CLOSE-UP identity portrait of {look}, face filling "
        f"most of the frame, both eyes clearly visible, looking straight at the "
        f"camera. {hair} tucked behind both ears so earlobes show. Tight "
        "head-and-shoulders crop (not a wide shot). Neutral closed-mouth "
        "expression, studio softbox, plain warm gray background, 85mm lens. "
        "No jewelry, no earrings."
    )


def hair_state(slot: str) -> str:
    return HAIR_STYLE.get(slot, ("up", ""))[0]


def slot_pulid_params(slot: str | None, mode: str) -> dict:
    """Lower id_weight + higher true_cfg so the prompt can turn the head.

    Do NOT send start_step>0 to fal-ai/flux-pulid — that path returns
    400 "Failed to get ID embeddings (no face detected): facexlib align face fail".
    """
    turned = slot in TURNED_SLOTS
    if turned:
        return {"id_weight": 0.32, "true_cfg": 3.0, "guidance_scale": 5.8}
    return {
        "id_weight": 0.42 if mode == "full" else 0.45,
        "true_cfg": 2.4,
        "guidance_scale": 5.0,
    }


def slot_id_weight(slot: str, mode: str) -> float:
    return float(slot_pulid_params(slot, mode)["id_weight"])


def slot_negative_prompt(slot: str, mode: str, category: str | None = None) -> str:
    if category in HAND_FOCUS_CATEGORIES:
        extras = [
            HAND_NEGATIVE,
            HAND_NEGATIVE_BY_CATEGORY.get(category or "", ""),
            HAIR_NEGATIVE_BY_STATE.get(hair_state(slot), ""),
            SLOT_NEGATIVE_EXTRA.get(slot, ""),
        ]
        if mode == "full":
            extras.append("tight headshot, cut off above the waist")
        extra = ", ".join(e for e in extras if e)
        return f"{NEGATIVE}, {extra}"
    base = NEGATIVE_FULL_BODY if mode == "full" else NEGATIVE_BUST
    extras = [HAIR_NEGATIVE_BY_STATE.get(hair_state(slot), "")]
    extras.append(SLOT_NEGATIVE_EXTRA.get(slot, ""))
    extra = ", ".join(e for e in extras if e)
    return f"{base}, {extra}" if extra else base


def _hair_line(persona_name: str, slot: str) -> str:
    hair_color = persona_hair(persona_name)
    state, hair_style = HAIR_STYLE.get(slot, ("up", "worn off the neck"))
    if state == "up":
        return (
            f"CRITICAL HAIRSTYLE: hair is UP. "
            f"The nape of her neck and both ears are fully exposed. "
            f"Zero hair on the chest or in front of the neck. "
            f"Her {hair_color} is {hair_style}."
        )
    return (
        f"CRITICAL HAIRSTYLE: HAIR IS DOWN. Long hair falling down her "
        f"back, loosely tucked behind both ears. You can see the hair "
        f"length past the shoulders. NOT a bun, NOT a ponytail, NOT an updo. "
        f"Collarbones and the front of the neck stay clear. "
        f"Her {hair_color} is {hair_style}."
    )


def build_scene_prompt(
    persona_name: str,
    slot: str,
    category: str,
    tone_label: str | None = None,
) -> str:
    look = persona_look(persona_name)
    meta = SCENE_META[slot]
    framing = category_framing(category)

    if category in HAND_FOCUS_CATEGORIES:
        return _build_hand_scene_prompt(
            persona_name, look, slot, category, framing, tone_label, meta["mode"]
        )

    pose = POSE_VARIATION.get(slot, "torso square, distinct head angle")
    hair_line = _hair_line(persona_name, slot)
    # Pose/gaze MUST be the first tokens. BODY_RULE used to lead with
    # "facing camera" and PuLID copied a frontal face for every slot.
    lead = f"{pose} {hair_line} {BODY_RULE}"

    if meta["mode"] == "bust":
        setting = WEAR_SETTING.get(slot, "lifestyle interior, soft natural light")
        fashion = WEAR_FASHION.get(slot, "wearing a stylish coordinated outfit")
        companion = ""
        if slot == "wear_date":
            companion = (
                "A second person may be softly blurred in the background. "
                "She sits with her torso toward the camera; her head may turn. "
                "She does not twist her whole body away. "
            )
        return (
            f"{lead} {companion}"
            f"Photorealistic commercial jewelry catalog photo of {look}. "
            f"{fashion}. {framing}. Setting: {setting}. "
            "Same woman as the identity reference but do NOT copy that photo's "
            "frontal pose or eye contact. Head angle and gaze must match "
            "the HEAD / GAZE lines above. "
            "Absolutely no jewelry on the model — bare skin where jewelry would sit. "
            "No text, no watermark."
        )

    tone_bit = TONE_SETTING.get(tone_label or "", "wearing a stylish coordinated outfit")
    if slot == "wide_inset":
        setting = "standing in an airy studio space with plain soft-toned background"
    else:
        setting = f"standing in a softly lit lifestyle interior, {tone_bit}"
    return (
        f"{lead} "
        f"Three-quarter length fashion photograph of {look}. "
        f"Standing, camera framing from the top of her head down "
        f"to at least mid-thigh so her full coordinated outfit and styling are "
        f"clearly visible. {setting}. "
        "Same woman as the identity reference but do NOT copy that photo's "
        "frontal pose or eye contact. Head angle and gaze must match "
        "the HEAD / GAZE lines above. "
        "Bare of jewelry (no necklace, earrings, rings, or bracelets). "
        "Square 1:1 crop, no text, no watermark."
    )


def _pose_line(slot: str, category: str) -> str:
    pose = POSE_VARIATION.get(slot, "torso square, distinct head angle")
    if category in HAND_FOCUS_CATEGORIES:
        # Cup-in-hands hides the wrist/fingers we need to composite onto.
        pose = pose.replace("Holding a cup. ", "").replace("Holding a cup.", "")
    return pose


def _hand_fashion(slot: str, category: str) -> str:
    scene_fashion = WEAR_FASHION.get(slot, "wearing a stylish coordinated outfit")
    hand_bit = WEAR_FASHION_HAND.get(category, "")
    return f"{scene_fashion}. {hand_bit}" if hand_bit else scene_fashion


def _build_hand_scene_prompt(
    persona_name: str,
    look: str,
    slot: str,
    category: str,
    framing: str,
    tone_label: str | None,
    mode: str,
) -> str:
    pose = _pose_line(slot, category)
    hair_line = _hair_line(persona_name, slot)
    present = HAND_PRESENT_RULE.get(category, "")
    hand_pose = WEAR_HAND_POSE.get(category, {}).get(
        slot, "bare hands clearly visible in the lower frame"
    )
    fashion = _hand_fashion(slot, category)
    # HEAD / hair / expression first (same as necklace/earring), then the
    # wrist/hand must still face the lens for a flat cutout to sit.
    lead = f"{pose} {hair_line} {present}"

    if mode == "bust":
        setting = WEAR_SETTING.get(slot, "lifestyle interior, soft natural light")
        companion = ""
        if slot == "wear_date":
            companion = (
                "A second person may be softly blurred in the background. "
                "She sits with her torso toward the camera; her head may turn. "
                "She does not twist her whole body away. "
            )
        return (
            f"{lead} {companion} {framing} {hand_pose} "
            f"Photorealistic commercial jewelry catalog photo of {look}. "
            f"{fashion}. Setting: {setting}. "
            "Same woman as the identity reference but do NOT copy that photo's "
            "frontal pose or eye contact. Head angle, expression, and gaze must "
            "match the HEAD / GAZE lines above. The FACE may turn; the "
            "wrist/hand plane stays square to the lens. "
            "Absolutely no jewelry on the model — bare skin on fingers and wrists. "
            "No text, no watermark."
        )

    tone_bit = TONE_SETTING.get(tone_label or "", "wearing a stylish coordinated outfit")
    if slot == "wide_inset":
        setting = "standing in an airy studio space with plain soft-toned background"
    else:
        setting = f"standing in a softly lit lifestyle interior, {tone_bit}"
    extra = CATEGORY_FULL_EXTRA.get(category, "")
    return (
        f"{lead} "
        f"Three-quarter length fashion photograph of {look}. "
        f"Standing, camera framing from the top of her head down "
        f"to at least mid-thigh so her full coordinated outfit and styling are "
        f"clearly visible. {extra} {fashion}. {setting}. "
        "Same woman as the identity reference but do NOT copy that photo's "
        "frontal pose or eye contact. Head angle, expression, and gaze must "
        "match the HEAD / GAZE lines above. The FACE may turn; the "
        "wrist/hand plane stays square to the lens. "
        "Bare of jewelry (no necklace, earrings, rings, or bracelets). "
        "Square 1:1 crop, no text, no watermark."
    )


def _download_image(url: str) -> Image.Image:
    with urlopen(url, timeout=120) as resp:
        data = resp.read()
    return Image.open(io.BytesIO(data)).convert("RGB")


def _to_square_size(img: Image.Image, size: int = SIZE) -> Image.Image:
    """Center-crop to square then resize to target (Pillow LANCZOS)."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = img.crop((left, top, left + side, top + side))
    return cropped.resize((size, size), Image.Resampling.LANCZOS)


def _crop_face_for_pulid(img: Image.Image) -> tuple[Image.Image, bool]:
    """Tight face crop so facexlib can lock ID. Wide collarbone shots fail."""
    from worker.face_anchor import detect_face_norm

    face = detect_face_norm(img)
    if face is None:
        logger.warning("YuNet found no face on ID image — sending full frame")
        return _to_square_size(img, FAL_GEN_SIZE), False
    x, y, fw, fh = face
    w, h = img.size
    pad_x, pad_y = 0.55, 0.50
    x0 = max(0, int((x - pad_x * fw) * w))
    y0 = max(0, int((y - pad_y * fh) * h))
    x1 = min(w, int((x + (1 + pad_x) * fw) * w))
    y1 = min(h, int((y + (1 + 0.40) * fh) * h))
    return _to_square_size(img.crop((x0, y0, x1, y1)), FAL_GEN_SIZE), True


def _upload_jpeg(img: Image.Image) -> str:
    import fal_client
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        img.convert("RGB").save(path, "JPEG", quality=92)
        return fal_client.upload_file(path)
    finally:
        Path(path).unlink(missing_ok=True)


def _is_no_face_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "no face" in msg or "facexlib" in msg or "id embeddings" in msg


def _fal_subscribe(model: str, arguments: dict) -> dict:
    import fal_client

    logger.info("fal subscribe model=%s", model)
    result = fal_client.subscribe(model, arguments=arguments)
    return result


def _image_url_from_result(result: dict) -> str:
    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"fal response missing images: {result!r}")
    url = images[0].get("url")
    if not url:
        raise RuntimeError(f"fal image missing url: {images[0]!r}")
    return url


def resolve_reference_url(
    persona_name: str,
    persona_image_key: str | None,
    *,
    on_api_call: Callable[[], None] | None = None,
) -> str:
    """
    Prefer PresetPersona.imageKey (http URL or local file).
    Otherwise generate a Flux portrait and upload/return its fal URL.
    """
    key = (persona_image_key or "").strip()
    if key.startswith("http://") or key.startswith("https://"):
        return key
    if key:
        path = Path(key)
        if path.is_file():
            import fal_client

            return fal_client.upload_file(str(path))

    prompt = build_reference_prompt(persona_name)
    result = _fal_subscribe(
        "fal-ai/flux/dev",
        {
            "prompt": prompt,
            "image_size": {"width": FAL_GEN_SIZE, "height": FAL_GEN_SIZE},
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "output_format": "jpeg",
            "enable_safety_checker": True,
        },
    )
    if on_api_call:
        on_api_call()
    return _image_url_from_result(result)


def generate_scene_fal(
    prompt: str,
    reference_image_url: str,
    *,
    mode: str = "bust",
    slot: str | None = None,
    negative_prompt: str | None = None,
    on_api_call: Callable[[], None] | None = None,
) -> Image.Image:
    is_full = mode == "full"
    negative = negative_prompt or (NEGATIVE_FULL_BODY if is_full else NEGATIVE)
    params = slot_pulid_params(slot, mode)
    seed = random.randint(1, 2_147_483_647)
    logger.info(
        "scene fal seed=%s slot=%s id_weight=%s true_cfg=%s guidance=%s",
        seed,
        slot,
        params["id_weight"],
        params["true_cfg"],
        params["guidance_scale"],
    )
    arguments = {
        "prompt": prompt,
        "reference_image_url": reference_image_url,
        "image_size": {"width": FAL_GEN_SIZE, "height": FAL_GEN_SIZE},
        "num_inference_steps": 28,
        "seed": seed,
        "max_sequence_length": "512",
        "guidance_scale": params["guidance_scale"],
        "true_cfg": params["true_cfg"],
        "negative_prompt": negative,
        "id_weight": params["id_weight"],
        "enable_safety_checker": True,
    }
    try:
        result = _fal_subscribe("fal-ai/flux-pulid", arguments)
    except Exception as exc:
        if not _is_no_face_error(exc):
            raise
        logger.warning("pulid no-face on %s — retrying once: %s", slot, exc)
        arguments["seed"] = random.randint(1, 2_147_483_647)
        result = _fal_subscribe("fal-ai/flux-pulid", arguments)
    if on_api_call:
        on_api_call()
    url = _image_url_from_result(result)
    return _to_square_size(_download_image(url), SIZE)


def persona_palette(name: str) -> dict:
    h = hashlib.sha256(name.encode("utf-8")).digest()
    skin = (210 - h[0] % 40, 170 - h[1] % 30, 145 - h[2] % 25)
    hair = (40 + h[3] % 50, 28 + h[4] % 30, 22 + h[5] % 25)
    cloth = (55 + h[6] % 80, 48 + h[7] % 70, 42 + h[8] % 60)
    return {"skin": skin, "hair": hair, "cloth": cloth}


def render_scene_local(
    persona_name: str,
    slot: str,
    tone_label: str | None = None,
) -> Image.Image:
    """Local stand-in when FAL_KEY is unset — same palette per persona name."""
    meta = SCENE_META[slot]
    pal = persona_palette(persona_name)
    img = Image.new("RGB", (SIZE, SIZE), meta["bg"])
    draw = ImageDraw.Draw(img)
    mode = meta["mode"]

    if mode == "bust":
        draw.ellipse([500, 900, 1500, 2200], fill=pal["cloth"])
        draw.rectangle([880, 720, 1120, 980], fill=pal["skin"])
        draw.ellipse([700, 280, 1300, 900], fill=pal["skin"])
        draw.ellipse([680, 220, 1320, 620], fill=pal["hair"])
        draw.pieslice([700, 400, 1300, 900], 200, 340, fill=pal["hair"])
    else:
        draw.ellipse([820, 120, 1180, 480], fill=pal["skin"])
        draw.ellipse([800, 80, 1200, 300], fill=pal["hair"])
        draw.rectangle([900, 450, 1100, 560], fill=pal["skin"])
        draw.polygon([(700, 560), (1300, 560), (1200, 1200), (800, 1200)], fill=pal["cloth"])
        draw.rectangle([820, 1200, 980, 1750], fill=(40, 36, 32))
        draw.rectangle([1020, 1200, 1180, 1750], fill=(40, 36, 32))

    label = meta["label"]
    if tone_label:
        label = f"{label} · {tone_label}"
    caption = f"{persona_name} · {label} · local scene · {random.randint(100, 999)}"
    draw.rectangle([40, SIZE - 110, 900, SIZE - 40], fill=(26, 22, 18))
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    draw.text((60, SIZE - 95), caption, fill=(232, 220, 200), font=font)
    return img


def generate_all_scenes(
    *,
    persona_name: str,
    persona_image_key: str | None,
    category: str,
    slots: list[str],
    tone_names: list[str],
    scene_dir: Path,
    on_api_call: Callable[[], None] | None = None,
    reuse_reference_path: Path | None = None,
) -> dict[str, Image.Image]:
    """
    Build person-only scenes for the given slots.
    Saves optional persona_ref.jpg when using fal.
    On slot regen, pass reuse_reference_path so the face stays the same person.
    """
    scenes: dict[str, Image.Image] = {}

    if not fal_enabled():
        logger.info("FAL_KEY unset — using local placeholder scenes")
        for slot in slots:
            tone_label = _tone_for_slot(slot, tone_names)
            scenes[slot] = render_scene_local(persona_name, slot, tone_label)
        return scenes

    logger.info("FAL_KEY set — generating scenes via flux/dev + flux-pulid")
    cached = reuse_reference_path if reuse_reference_path and reuse_reference_path.is_file() else None
    ref_url: str | None = None
    if cached:
        raw = Image.open(cached).convert("RGB")
        id_img, found = _crop_face_for_pulid(raw)
        if found:
            id_img.save(cached, "JPEG", quality=92)
            ref_url = _upload_jpeg(id_img)
            logger.info("reusing cached persona reference (face-cropped) %s", cached)
        else:
            logger.warning("cached persona_ref has no detectable face — regenerating")
            cached = None
    if ref_url is None:
        ref_url = resolve_reference_url(
            persona_name, persona_image_key, on_api_call=on_api_call
        )
        try:
            raw = _to_square_size(_download_image(ref_url), SIZE)
            id_img, found = _crop_face_for_pulid(raw)
            ref_path = scene_dir / "persona_ref.jpg"
            id_img.save(ref_path, "JPEG", quality=92)
            if found:
                ref_url = _upload_jpeg(id_img)
            logger.info("saved persona reference found_face=%s %s", found, ref_path)
        except Exception:
            logger.exception("could not cache persona reference image")

    for slot in slots:
        tone_label = _tone_for_slot(slot, tone_names)
        prompt = build_scene_prompt(persona_name, slot, category, tone_label)
        mode = SCENE_META[slot]["mode"]
        negative = slot_negative_prompt(slot, mode, category)
        logger.info("scene fal slot=%s mode=%s id_weight=%s prompt_len=%s", slot, mode, slot_id_weight(slot, mode), len(prompt))
        scenes[slot] = generate_scene_fal(
            prompt,
            ref_url,
            mode=mode,
            slot=slot,
            negative_prompt=negative,
            on_api_call=on_api_call,
        )
    return scenes


def _tone_for_slot(slot: str, tone_names: list[str]) -> str | None:
    if slot == "body_1":
        return tone_names[0] if tone_names else None
    if slot == "body_2":
        return tone_names[1] if len(tone_names) > 1 else None
    return None
