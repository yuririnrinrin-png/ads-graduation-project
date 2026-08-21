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

from worker.image_io import open_image, save_image

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
        "TWO-PERSON DATE PHOTO, not a solo portrait. "
        "A couple enjoying dinner together, talking across the table. "
        "The WOMAN is the hero — closest to camera, sharp, jewelry zones unobstructed "
        "(neck, chest, or her own hands). "
        "A man sits across from her in the BACKGROUND, smaller than her: "
        "we see his FACE or three-quarter (eyes, nose), looking at her or talking with her. "
        "He is slightly blurred, never the hero. "
        "FORBIDDEN: only the back of the man's head, faceless silhouette, "
        "solo woman, empty table, man's hands in the foreground, "
        "focus on the man, woman blurred, man covering her jewelry. "
        "Fine-dining table, candle, two wine glasses. "
        "Her TORSO stays square to the lens (under 15 degrees)"
    ),
    "wear_holiday": (
        "sitting on a wooden beach pier railing, ocean waves and palm leaves "
        "blurred in the background, warm golden-hour sunlight, breezy relaxed mood"
    ),
}

# open = collarbones; turtleneck = pendant can sit on knit (less pasted-on).
# Both patterns MUST appear among the 7 person shots.
NECKLINE = {
    "wear_office": "open",
    "wear_cafe": "open",
    "wear_date": "open",
    "wear_holiday": "turtleneck",
    "body_1": "turtleneck",
    "body_2": "open",
    "wide_inset": "open",
}

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
        "wearing a fine-gauge turtleneck knit, the necklace zone is the knit "
        "at the base of the throat so jewelry can rest on fabric later"
    ),
}

TONE_SETTING = {
    "オフィス": (
        "wearing a sharply tailored conservative business suit or structured "
        "dress, polished corporate office fashion"
    ),
    "休日": (
        "wearing a relaxed weekend outfit, knit and easy trousers"
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

BODY_FASHION_NECK = {
    "turtleneck": (
        "fine-gauge turtleneck or mock-neck knit, necklace zone is the fabric "
        "at the base of the throat"
    ),
    "open": (
        "open neckline or V-neck, collarbones visible, no funnel collar hiding the chest"
    ),
}

# Torso stays jewelry-friendly. Never say "facing camera" about the person as
# a whole — Flux/PuLID treats that as a frontal FACE.
BODY_RULE = (
    "BODY: STANDING OR SITTING STILL, feet planted if standing, not walking, "
    "not striding. Both shoulders equally visible, chest and collarbones face "
    "the camera, hips square to the lens, torso yaw under 15 degrees. "
    "Not a side-on body, not a walking profile, not a street-fashion side view, "
    "not one shoulder to the camera. "
    "The HEAD may turn independently to three-quarter or side; "
    "do not rotate the torso with the head."
)

# Catalog shots must look like a camera photo, never fashion illustration.
PHOTO_RULE = (
    "REAL CAMERA PHOTOGRAPH of a real woman, photorealistic, natural skin pores "
    "and real fabric texture, photographic lighting. "
    "Not an illustration, not digital art, not a drawing, not 3D, not vector."
)

# Slots that must break the ID photo's front-facing eye-contact pose.
# wide_inset is full-body: a 45° head turn rotates the TORSO with it.
TURNED_SLOTS = frozenset({"wear_cafe", "wear_date", "body_1"})

POSE_VARIATION = {
    "wear_office": (
        "HEAD: three-quarter view, turned 30 degrees, not a passport photo. "
        "キリッとした笑顔: sharp closed-mouth smile, no teeth. "
        "GAZE: toward camera but SOFT, upper lids slightly lowered"
    ),
    "wear_cafe": (
        "HEAD only: turned 40 degrees, we see her ear and jaw; "
        "both shoulders still face the camera. Holding a cup. "
        "自然な笑顔: quiet closed-mouth smile. "
        "GAZE: DOWNCAST looking at the cup, eyes averted, ZERO eye contact, "
        "not looking at the lens"
    ),
    "wear_date": (
        "HEAD only: three-quarter, turned 45 degrees, ear visible; "
        "chest still faces the camera. "
        "甘えたような笑顔: coy closed-mouth smile. "
        "GAZE: looking toward the man across the table, slightly down, no eye contact"
    ),
    "wear_holiday": (
        "HEAD: tilted to one shoulder, turned about 25 degrees. "
        "華やかな笑顔: glamorous smile SHOWING TEETH. "
        "GAZE: toward camera but squinting softly from the smile, not a stare"
    ),
    "body_1": (
        "BODY stays front-on (both shoulders visible, yaw under 15 degrees), "
        "STANDING STILL, feet planted, we see the FRONT of her clothes and both hips. "
        "HEAD only: turned 50 degrees, ear and jaw shown, three-quarter FACE. "
        "Not a side-on body, not a walking profile, not a back view. "
        "上品な微笑: calm closed-mouth smile. "
        "GAZE: DOWNCAST, looking along her cheek, never at camera"
    ),
    "body_2": (
        "HEAD: turned 25 degrees with a playful tilt. "
        "屈託ない笑顔: open grin SHOWING TEETH. "
        "GAZE: toward camera but crinkled and soft"
    ),
    "wide_inset": (
        "BODY: STANDING STILL, FRONT VIEW, feet planted, not walking, not striding. "
        "Both shoulders and both hips face the camera, FRONT of her clothes visible, "
        "torso yaw under 15 degrees. "
        "HEAD: turned only about 20 degrees, a slight three-quarter. "
        "Do not turn the body with the head. Not a side view, not looking over the shoulder. "
        "穏やかな微笑: soft closed-mouth smile. "
        "GAZE: downcast, looking down and away, no eye contact"
    ),
}

# One distinct expression label per person slot (REQUIREMENTS §5).
SLOT_EXPRESSION = {
    "wear_office": "キリッとした笑顔",
    "wear_cafe": "自然な笑顔",
    "wear_date": "甘えたような笑顔",
    "wear_holiday": "華やかな笑顔",
    "body_1": "上品な微笑",
    "body_2": "屈託ない笑顔",
    "wide_inset": "穏やかな微笑",
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
        "LONG HAIR WORN DOWN, loosely tucked behind both ears so earlobes "
        "show, length visible while BOTH SHOULDERS still face the camera. "
        "This is NOT an updo and NOT a side-view of the hair",
    ),
}

HAIR_NEGATIVE_BY_STATE = {
    "up": "hair down, loose hair over the shoulders, hair covering the ears, "
    "hair covering the neck, hair on the chest",
    "tuck": "updo, bun, chignon, ponytail, hair pulled up, hair in a knot, "
    "short pixie, hair covering the collarbones, hair on the chest, "
    "hair covering the earlobes",
}

# Forbid over-shoulder / opposite hair. Do not ban "frontal face" on
# turned-head slots — that rotates the whole body past 15 degrees.
SLOT_NEGATIVE_EXTRA = {
    "wear_office": (
        "teeth showing, open-mouth laugh, coy pout, downcast looking away, "
        "eyes closed, blank stare, piercing stare"
    ),
    "wear_cafe": (
        "looking at the camera, eye contact, looking at the viewer, "
        "side-on body, body in profile, one shoulder to camera, "
        "passport photo, toothy grin, bun, ponytail, updo"
    ),
    "wear_date": (
        "looking at the camera, eye contact, side-on body, body in profile, "
        "passport photo, teeth showing, big laugh, "
        "solo portrait, one person, woman alone, empty table, no man, "
        "only the back of a man's head"
    ),
    "wear_holiday": (
        "eyes closed, downcast looking away, closed-mouth only, coy pout, "
        "serious frown, piercing stare, V-neck, open neckline, bare collarbones"
    ),
    "body_1": (
        "looking at the camera, eye contact, "
        "side-on body, body in profile, standing in profile, walking, striding, "
        "passport photo, teeth showing, big grin, tight headshot, "
        "back view, rear view, walking away"
    ),
    "body_2": (
        "closed-mouth polite smile, eyes closed, looking away, frowning, "
        "blank stare, piercing stare, tight headshot"
    ),
    "wide_inset": (
        "looking at the camera, eye contact, side-on body, body in profile, "
        "walking, striding, candid street, fashion-week side view, "
        "looking over the shoulder, over-the-shoulder, one shoulder to camera, "
        "passport photo, big grin, teeth showing, bun, ponytail, "
        "updo, tight headshot"
    ),
}

# Wear-4 camera: necklace/earring stay bust/face. Ring/bracelet put the
# placement zone (fingers / wrist) in the lower frame. Face stays in-shot
# so PuLID can still lock identity — never a finger-only macro.
#
# Keep HAND_* copy SHORT. fal-ai/flux-pulid uses max_sequence_length 512;
# ~350-word prompts plus necklace negatives ("frontal face") were making
# office shots hide hands behind a laptop and body_1 become a back view.
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
        "HAND SHOT, not a portrait: bare hands fill the lower two-thirds. "
        "Camera aimed at the table. Face small at the top edge only."
    ),
    "bracelet": (
        "WRIST SHOT, not a portrait: bare forearm and inner wrist fill the "
        "lower two-thirds. Camera aimed at the table. Face small at the top edge only."
    ),
}

HAND_PRESENT_RULE = {
    "ring": "Backs of the hands face the lens, fingers slightly spread, ring finger empty. Uncovered empty wrists.",
    "bracelet": "Inner wrist faces the lens almost flat. Bare forearm, uncovered empty wrists.",
}

WEAR_HAND_POSE = {
    "ring": {
        "wear_office": "Hands rest on an empty glass desk. No laptop in the photo.",
        "wear_cafe": "Hands rest on the table beside the cup, not gripping it.",
        "wear_date": "One hand rests on the tablecloth, back of the hand to the camera.",
        "wear_holiday": "Hands rest on the pier railing, all fingertips in frame.",
    },
    "bracelet": {
        "wear_office": "Forearm on an empty glass desk, inner wrist fully shown. No laptop.",
        "wear_cafe": "Forearm on the table beside the cup; she is not holding the cup.",
        "wear_date": "Forearm on the tablecloth, inner wrist flat, arms uncrossed.",
        "wear_holiday": "Forearm on the pier railing, wrist bone uncovered.",
    },
}

WEAR_SETTING_HAND = {
    "wear_office": (
        "modern office, city window, empty glass desk. "
        "NO laptop, NO computer, NO keyboard, NO screen"
    ),
    "wear_cafe": "wooden cafe table, cup and plate to the side of her hands",
    "wear_date": (
        "TWO-PERSON DATE PHOTO. She is sharp in the foreground, her own forearm on the table, "
        "jewelry zone on her hands unobstructed. "
        "A couple enjoying dinner: a man sits across from her in the BACKGROUND, "
        "smaller, slightly blurred, but we see his FACE or three-quarter, "
        "looking at her or talking with her. "
        "FORBIDDEN: only the back of the man's head, solo woman, empty table, "
        "man's hands in the foreground, woman out of focus, man covering her hands"
    ),
    "wear_holiday": "wooden pier railing, golden hour, ocean behind",
}

TONE_PLACE_HAND = {
    "オフィス": "bright office interior",
    "休日": "relaxed weekend interior",
    "エレガント": "refined softly lit interior",
    "リラックス": "casual airy interior",
}

WEAR_FASHION_HAND = {
    "ring": "short sleeves or open jacket, bare fingers, no gloves, no rings",
    "bracelet": "sleeves rolled to mid-forearm, uncovered empty wrists",
}

CATEGORY_FULL_EXTRA = {
    "ring": (
        "Head-to-toe standing catalog photo, 35mm, camera several meters back. "
        "Head near the top edge, shoes visible at the bottom edge. "
        "Every fingertip visible. Not a waist-up crop."
    ),
    "bracelet": (
        "Head-to-toe standing catalog photo, 35mm, camera several meters back. "
        "Head near the top edge, shoes visible at the bottom edge. "
        "Both wrists visible. Not a waist-up crop."
    ),
}

FULL_HAND_POSE = {
    "ring": {
        "body_1": (
            "LEFT arm hangs straight with a gap beside the torso; "
            "RIGHT hand rests by her hip, fingers visible."
        ),
        "body_2": (
            "Both arms hang straight at her sides, palms slightly forward, "
            "a gap of clothing between each arm and the torso."
        ),
        "wide_inset": (
            "STANDING STILL, not walking. One hand rests on her thigh, "
            "the other hangs straight. Fingertips visible. Both hips face the camera."
        ),
    },
    "bracelet": {
        "body_1": (
            "LEFT arm hangs straight with a gap beside the torso; "
            "RIGHT inner wrist rests by her hip, facing the camera."
        ),
        "body_2": (
            "Both arms hang straight at her sides like a standing catalog pose, "
            "a gap of clothing between each arm and the torso, both wrists uncovered."
        ),
        "wide_inset": (
            "STANDING STILL, not walking. One wrist rests by her thigh, "
            "the other arm hangs straight. Both wrists visible. Both hips face the camera."
        ),
    },
}

# Head/body for hand categories only. Do NOT reuse necklace body_1
# "STRICT SIDE PROFILE" — that became a back view and hid the hands.
HAND_HEAD_POSE = {
    "wear_office": (
        "HEAD: three-quarter, turned 30 degrees. キリッとした笑顔. Soft gaze. "
        "Both shoulders face the camera. Torso yaw under 15 degrees."
    ),
    "wear_cafe": (
        "HEAD only: turned 40 degrees, ear and jaw visible, not a passport face. "
        "自然な笑顔. Looking down, no eye contact. "
        "Both shoulders face the camera. Torso yaw under 15 degrees."
    ),
    "wear_date": (
        "HEAD only: turned 45 degrees, ear visible. 甘えたような笑顔. "
        "Looking toward the man across the table. "
        "Chest to the lens. Torso yaw under 15 degrees."
    ),
    "wear_holiday": (
        "HEAD: tilted, turned 25 degrees. 華やかな笑顔 showing teeth. Soft gaze. "
        "Torso yaw under 15 degrees."
    ),
    "body_1": (
        "HEAD only: turned 50 degrees, ear visible. 上品な微笑. Looking down. "
        "FRONT of her clothes, both shoulders visible. Torso yaw under 15 degrees. "
        "Not a back view, not a side-on body."
    ),
    "body_2": (
        "HEAD: tilt 25 degrees. 屈託ない笑顔 showing teeth. Soft gaze. "
        "Torso yaw under 15 degrees."
    ),
    "wide_inset": (
        "HEAD: turned about 20 degrees. 穏やかな微笑. Looking down. "
        "STANDING STILL, FRONT VIEW, not walking. FRONT of her clothes, both shoulders and "
        "both hips visible. Torso yaw under 15 degrees. Not a side view."
    ),
}

HAND_NEGATIVE = (
    "headshot, no hands, hands cut off, waist-up, bust crop, cropped at the hips, "
    "laptop, computer, monitor, keyboard, notebook computer, "
    "object covering hands, cup covering fingers, "
    "back to camera, rear view, walking away, walking, striding, over-the-shoulder, "
    "side-on body, body in profile, standing in profile, "
    "hands in pockets, gloves, extra fingers, deformed hands, "
    "watch, wristwatch, smartwatch, necklace, chain, pendant, earrings, rings, bracelet, jewelry, "
    "arms crossed, hands on face, hands behind back"
)

HAND_NEGATIVE_BY_CATEGORY = {
    "ring": "fingers hidden, fist, edge-on hand",
    "bracelet": "long sleeves covering wrists, watch, wrist in profile",
}

# Necklace SLOT_NEGATIVE_EXTRA forbids "frontal face" / "both eyes visible"
# on body_1 and cafe — that turns the WHOLE person away. Do not reuse it.
HAND_SLOT_NEGATIVE = {
    "wear_office": "laptop, computer, monitor, keyboard, screen in front of hands",
    "wear_cafe": "holding a cup, gripping a mug",
    "wear_date": "hands under the table, solo portrait, woman alone, empty table, no man",
    "wear_holiday": "hands behind the railing",
    "body_1": "back view, rear view, walking away, photographed from behind, side-on body, body in profile, arms crossed, arms folded",
    "body_2": "hands on cheeks, cropped at the hips, arms crossed, arms folded, side-on body",
    "wide_inset": "back view, rear view, walking, striding, walking away, cropped at the hips, side-on body, body in profile, arms crossed, arms folded",
}

NEGATIVE = (
    "illustration, cartoon, anime, manga, digital art, vector art, painting, "
    "drawing, cgi, 3d render, stylized, comic, cel shaded, flat color, "
    "fashion illustration, smooth airbrushed skin, "
    "jewelry, necklace, layered necklace, thin chain, pendant, choker, "
    "earrings, hoop earrings, stud earrings, rings, bracelet, "
    "watch, wristwatch, smartwatch, fitness tracker, accessories, "
    "text, watermark, logo, deformed hands, extra fingers, low quality, blurry, "
    "back to camera, body facing away, over-the-shoulder body twist, "
    "side-on body, body in profile, standing in profile, one shoulder to camera, "
    "walking, striding, candid walking shot, street-fashion side view, "
    "passport photo, identical polite smile, piercing stare into the lens, "
    "extreme close-up, tight face-only crop, "
    "face filling the entire frame, cropped above the collarbone, "
    "hair covering the ears, hair covering the front of the neck"
)

ACCESSORY_BAN = (
    "NO jewelry of any kind: no necklace, no chain, no pendant, no choker, "
    "no earrings, no rings, no bracelet, no watch. "
    "Bare neck, bare earlobes, uncovered empty wrists. "
    "Jewelry will be composited later — do not draw any."
)

NEGATIVE_BUST = NEGATIVE + (
    ", hair on the chest"
)

# Face-lock models bias toward tight headshots; push back for the wider
# "coordinate" shots so at least the outfit/torso reads clearly (feet may
# still be out of frame — that's fine, we only need the styling to be visible).
# Turtleneck is allowed on full-body / wide shots.
NEGATIVE_FULL_BODY = NEGATIVE + (
    ", extreme close-up, tight headshot, face-only crop, cut off above the waist, "
    "waist-up, three-quarter crop, folded arms, arms across the chest, "
    "walking, striding, motion blur, body in profile, side-on walking pose, "
    "watch on wrist, timepiece"
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


def slot_pulid_params(slot: str | None, mode: str, category: str | None = None) -> dict:
    """Lower id_weight + higher true_cfg so the prompt can turn the head.

    Do NOT send start_step>0 to fal-ai/flux-pulid — that path returns
    400 "Failed to get ID embeddings (no face detected): facexlib align face fail".
    """
    if slot == "wear_date":
        return {"id_weight": 0.18, "true_cfg": 4.0, "guidance_scale": 7.0}
    if category in HAND_FOCUS_CATEGORIES:
        return {"id_weight": 0.18, "true_cfg": 4.0, "guidance_scale": 7.0}
    turned = slot in TURNED_SLOTS
    if turned:
        return {"id_weight": 0.22, "true_cfg": 3.6, "guidance_scale": 6.2}
    return {
        "id_weight": 0.32 if mode == "full" else 0.34,
        "true_cfg": 2.8,
        "guidance_scale": 5.4,
    }


def slot_id_weight(slot: str, mode: str, category: str | None = None) -> float:
    return float(slot_pulid_params(slot, mode, category)["id_weight"])


def slot_negative_prompt(slot: str, mode: str, category: str | None = None) -> str:
    if category in HAND_FOCUS_CATEGORIES:
        extras = [
            HAND_NEGATIVE,
            HAND_NEGATIVE_BY_CATEGORY.get(category or "", ""),
            HAND_SLOT_NEGATIVE.get(slot, ""),
        ]
        if NECKLINE.get(slot) == "open":
            extras.append("turtleneck, high neck, mock neck")
        else:
            extras.append("plunging neckline")
        extra = ", ".join(e for e in extras if e)
        extra = extra + ", watch, wristwatch, smartwatch, necklace, chain, pendant, earrings, jewelry"
        return extra
    base = NEGATIVE_FULL_BODY if mode == "full" else NEGATIVE_BUST
    extras = [HAIR_NEGATIVE_BY_STATE.get(hair_state(slot), "")]
    extras.append(SLOT_NEGATIVE_EXTRA.get(slot, ""))
    extras.append(
        "watch, wristwatch, smartwatch, fitness tracker, necklace, chain, pendant, "
        "choker, earrings, rings, bracelet, jewelry"
    )
    if NECKLINE.get(slot) == "open":
        extras.append("turtleneck, high neck, mock neck")
    else:
        extras.append("plunging neckline, bare collarbones as the only necklace zone")
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
    if category == "necklace" and NECKLINE.get(slot) == "turtleneck":
        framing = (
            "bust-up showing face and the turtleneck knit at the base of the throat "
            "(jewelry will sit on fabric later, not empty skin)"
        )

    if category in HAND_FOCUS_CATEGORIES:
        return _build_hand_scene_prompt(
            look, slot, category, framing, tone_label, meta["mode"]
        )

    pose = POSE_VARIATION.get(slot, "torso square, distinct head angle")
    hair_line = _hair_line(persona_name, slot)
    lead = f"{PHOTO_RULE} {ACCESSORY_BAN} {pose} {hair_line} {BODY_RULE}"

    if meta["mode"] == "bust":
        setting = WEAR_SETTING.get(slot, "lifestyle interior, soft natural light")
        fashion = WEAR_FASHION.get(slot, "wearing a stylish coordinated outfit")
        companion = ""
        if slot == "wear_date":
            companion = (
                "TWO-PERSON DATE PHOTO, not a solo portrait. "
                "A couple enjoying dinner together, talking. "
                "The woman is the hero, closest, sharp, jewelry zones unobstructed. "
                "The man is a real second person in the background — FACE or "
                "three-quarter visible, looking at her or talking with her — "
                "not only the back of his head. Slightly blurred, never the hero. "
                "Her torso stays under 15 degrees to the lens. "
            )
        return (
            f"{lead} {companion}"
            f"Photorealistic commercial jewelry catalog photo of {look}. "
            f"{fashion}. {framing}. Setting: {setting}. "
            "Same woman as the identity reference but do NOT copy that photo's "
            "frontal pose or eye contact. Head angle and gaze must match "
            "the HEAD / GAZE lines above. "
            f"{ACCESSORY_BAN}. "
            "No text, no watermark."
        )

    tone_bit = TONE_SETTING.get(tone_label or "", "wearing a stylish coordinated outfit")
    neck = BODY_FASHION_NECK.get(NECKLINE.get(slot, "open"), "")
    if slot == "wide_inset":
        setting = (
            "STANDING STILL in a real photo studio, feet planted, camera in front of her, "
            "soft photographic lighting, not a street, not walking"
        )
    else:
        setting = (
            f"STANDING STILL in a softly lit lifestyle interior, feet planted, "
            f"camera in front of her, {tone_bit}"
        )
    return (
        f"{lead} "
        f"Photorealistic catalog standing photograph of {look}, not a walking candid. "
        f"Standing still, camera framing from the top of her head down "
        f"to at least mid-thigh so her full coordinated outfit and styling are "
        f"clearly visible. We see the FRONT of her clothes and both hips. {neck}. "
        f"{setting}. "
        "Same woman as the identity reference but do NOT copy that photo's "
        "frontal pose or eye contact. Head angle and gaze must match "
        "the HEAD / GAZE lines above. "
        f"{ACCESSORY_BAN}. "
        "Square 1:1 crop, no text, no watermark."
    )


def _pose_line(slot: str, category: str) -> str:
    if category in HAND_FOCUS_CATEGORIES:
        return HAND_HEAD_POSE.get(slot, "HEAD: three-quarter, not a passport photo.")
    return POSE_VARIATION.get(slot, "torso square, distinct head angle")


def _hand_fashion(slot: str, category: str) -> str:
    # Do NOT reuse necklace WEAR_FASHION (open neckline / collarbones) —
    # that pulls PuLID back into a bust portrait and hides the hands.
    base = WEAR_FASHION_HAND.get(category, "sleeves clear of the hands")
    if NECKLINE.get(slot) == "turtleneck":
        return f"{base}; turtleneck or mock-neck knit"
    return f"{base}; open neckline or V-neck, not a turtleneck"


def _build_hand_scene_prompt(
    look: str,
    slot: str,
    category: str,
    framing: str,
    tone_label: str | None,
    mode: str,
) -> str:
    pose = _pose_line(slot, category)
    present = HAND_PRESENT_RULE.get(category, "")
    hand_pose = WEAR_HAND_POSE.get(category, {}).get(
        slot, "bare hands clearly visible in the lower frame"
    )
    fashion = _hand_fashion(slot, category)
    hair = (
        "Hair UP, ears visible."
        if hair_state(slot) == "up"
        else "Hair DOWN, tucked behind both ears."
    )

    if mode == "bust":
        setting = WEAR_SETTING_HAND.get(slot, "lifestyle interior")
        two_person = "TWO-PERSON DATE PHOTO, not a solo portrait. " if slot == "wear_date" else ""
        return (
            f"{two_person}{PHOTO_RULE} {ACCESSORY_BAN} {framing} {present} {hand_pose} {pose} {hair} {BODY_RULE} "
            f"Photorealistic jewelry catalog photo of {look}. {fashion}. "
            f"Setting: {setting}. "
            "Do not copy the identity photo's head-and-shoulders crop. "
            "Hands are the largest subject. Face stays small at the edge. "
            "No text."
        )

    place = TONE_PLACE_HAND.get(tone_label or "", "a softly lit interior")
    setting = (
        "airy studio, camera in front of her"
        if slot == "wide_inset"
        else f"standing in {place}, camera in front of her"
    )
    extra = CATEGORY_FULL_EXTRA.get(category, "")
    standing_hands = FULL_HAND_POSE.get(category, {}).get(slot, "")
    return (
        f"{ACCESSORY_BAN} {extra} {present} {standing_hands} {pose} {hair} {BODY_RULE} "
        f"{PHOTO_RULE} Photorealistic full-length photo of {look}. {fashion}. {setting}. "
        "Do not copy the identity photo's tight crop. "
        "Fingertips stay in frame and stay obvious. No text."
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


def _pulid_id_has_face(img: Image.Image) -> bool:
    """True when the ID photo still has two eyes (facexlib can align)."""
    from worker.face_anchor import detect_faces_detail

    faces = detect_faces_detail(img)
    if not faces:
        return False
    f = faces[0]
    return f["eye_span"] >= 0.28 and f["h"] >= 0.22


def _crop_face_for_pulid(img: Image.Image) -> tuple[Image.Image, bool]:
    """One face crop so facexlib can lock ID. Wide collarbone shots fail.

    Never run this on an already-saved persona_ref.jpg — a second crop
    shrinks to nose/mouth and PuLID returns facexlib align face fail.
    """
    from worker.face_anchor import detect_face_norm

    face = detect_face_norm(img)
    if face is None:
        logger.warning("YuNet found no face on ID image — sending full frame")
        return _to_square_size(img, FAL_GEN_SIZE), False
    x, y, fw, fh = face
    w, h = img.size
    pad_x, pad_top, pad_bot = 0.35, 0.40, 0.28
    x0 = max(0, int((x - pad_x * fw) * w))
    y0 = max(0, int((y - pad_top * fh) * h))
    x1 = min(w, int((x + (1 + pad_x) * fw) * w))
    y1 = min(h, int((y + (1 + pad_bot) * fh) * h))
    cropped = _to_square_size(img.crop((x0, y0, x1, y1)), FAL_GEN_SIZE)
    if not _pulid_id_has_face(cropped):
        logger.warning("face crop lost eyes — using wider ID frame")
        return _to_square_size(img, FAL_GEN_SIZE), _pulid_id_has_face(img)
    return cropped, True


def _is_no_face_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "no face" in msg or "facexlib" in msg or "id embeddings" in msg


class PulidNoFaceError(RuntimeError):
    """PuLID could not align the ID photo (usually a too-tight crop)."""


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


class FalBillingError(RuntimeError):
    """fal.ai refused the call because the account has no spendable credit."""


def _is_billing_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "exhausted balance",
            "top_up",
            "top up",
            "user is locked",
            "payment required",
            "insufficient credit",
            "403 forbidden",
        )
    )


def _billing_message() -> str:
    return (
        "fal.ai の残高不足でアカウントがロックされています。"
        "fal.ai/dashboard/billing でチャージし、反映を確認してから"
        "「失敗した段階からリトライ」してください。"
        "チャージ前に何度もリトライすると、途中まで課金されたあとで止まります。"
    )


def _fal_subscribe(model: str, arguments: dict) -> dict:
    import fal_client

    logger.info("fal subscribe model=%s", model)
    try:
        return fal_client.subscribe(model, arguments=arguments)
    except Exception as exc:
        if _is_billing_error(exc):
            raise FalBillingError(_billing_message()) from exc
        raise


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
    category: str | None = None,
    negative_prompt: str | None = None,
    on_api_call: Callable[[], None] | None = None,
    id_weight_scale: float = 1.0,
) -> Image.Image:
    is_full = mode == "full"
    negative = negative_prompt or (NEGATIVE_FULL_BODY if is_full else NEGATIVE)
    params = dict(slot_pulid_params(slot, mode, category))
    if id_weight_scale < 1.0:
        params["id_weight"] = max(0.12, float(params["id_weight"]) * id_weight_scale)
        params["true_cfg"] = float(params["true_cfg"]) + 0.5
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
    except FalBillingError:
        raise
    except Exception as exc:
        if not _is_no_face_error(exc):
            raise
        logger.warning("pulid no-face on %s — retrying once: %s", slot, exc)
        arguments["seed"] = random.randint(1, 2_147_483_647)
        try:
            result = _fal_subscribe("fal-ai/flux-pulid", arguments)
        except FalBillingError:
            raise
        except Exception as retry_exc:
            if _is_no_face_error(retry_exc):
                raise PulidNoFaceError(str(retry_exc)) from retry_exc
            raise
    if on_api_call:
        on_api_call()
    url = _image_url_from_result(result)
    return _to_square_size(_download_image(url), SIZE)


def generate_scene_flux_dev(
    prompt: str,
    *,
    negative_prompt: str,
    on_api_call: Callable[[], None] | None = None,
) -> Image.Image:
    """Last-resort pose shot without PuLID (ID lock was copying a frontal bust)."""
    seed = random.randint(1, 2_147_483_647)
    logger.info("scene flux/dev fallback seed=%s prompt_len=%s", seed, len(prompt))
    result = _fal_subscribe(
        "fal-ai/flux/dev",
        {
            "prompt": prompt,
            "image_size": {"width": FAL_GEN_SIZE, "height": FAL_GEN_SIZE},
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "seed": seed,
            "negative_prompt": negative_prompt,
            "output_format": "jpeg",
            "enable_safety_checker": True,
        },
    )
    if on_api_call:
        on_api_call()
    return _to_square_size(_download_image(_image_url_from_result(result)), SIZE)


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


def _save_and_upload_persona_ref(
    raw: Image.Image,
    scene_dir: Path,
    *,
    crop: bool,
) -> str:
    src_path = scene_dir / "persona_ref_src.jpg"
    save_image(raw, src_path, "JPEG", quality=92)
    if crop:
        id_img, found = _crop_face_for_pulid(raw)
    else:
        id_img, found = _to_square_size(raw, FAL_GEN_SIZE), _pulid_id_has_face(raw)
    ref_path = scene_dir / "persona_ref.jpg"
    save_image(id_img, ref_path, "JPEG", quality=92)
    url = _upload_jpeg(id_img)
    logger.info("saved persona reference crop=%s found_face=%s %s", crop, found, ref_path)
    return url


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
    reuse_existing_scenes: bool = False,
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
    src_path = scene_dir / "persona_ref_src.jpg"
    ref_url: str | None = None
    if cached:
        raw = open_image(cached, "RGB")
        # Already cropped once. Cropping again collapses to a nose close-up.
        if _pulid_id_has_face(raw):
            ref_url = _upload_jpeg(raw)
            logger.info("reusing cached persona reference %s", cached)
        else:
            logger.warning("cached persona_ref is not a usable ID face — regenerating")
            cached.unlink(missing_ok=True)
            cached = None
    if ref_url is None:
        ref_url = resolve_reference_url(
            persona_name, persona_image_key, on_api_call=on_api_call
        )
        try:
            raw = _to_square_size(_download_image(ref_url), SIZE)
            ref_url = _save_and_upload_persona_ref(raw, scene_dir, crop=True)
        except Exception:
            logger.exception("could not cache persona reference image")

    rebuilt_id = False
    for slot in slots:
        existing = scene_dir / f"{slot}.jpg"
        if reuse_existing_scenes and existing.is_file():
            scenes[slot] = open_image(existing, "RGB")
            logger.info("reusing existing scene slot=%s (skip fal)", slot)
            continue
        tone_label = _tone_for_slot(slot, tone_names)
        prompt = build_scene_prompt(persona_name, slot, category, tone_label)
        mode = SCENE_META[slot]["mode"]
        negative = slot_negative_prompt(slot, mode, category)
        logger.info("scene fal slot=%s mode=%s id_weight=%s prompt_len=%s", slot, mode, slot_id_weight(slot, mode, category), len(prompt))
        while True:
            try:
                scenes[slot] = _generate_scene_until_qa(
                    prompt,
                    ref_url,
                    mode=mode,
                    slot=slot,
                    category=category,
                    negative_prompt=negative,
                    on_api_call=on_api_call,
                )
                break
            except FalBillingError:
                raise
            except PulidNoFaceError as exc:
                if rebuilt_id:
                    raise
                logger.warning("PuLID rejected ID photo — using wider reference: %s", exc)
                if src_path.is_file():
                    raw = open_image(src_path, "RGB")
                    ref_url = _save_and_upload_persona_ref(raw, scene_dir, crop=False)
                else:
                    fresh = resolve_reference_url(
                        persona_name, persona_image_key, on_api_call=on_api_call
                    )
                    raw = _to_square_size(_download_image(fresh), SIZE)
                    ref_url = _save_and_upload_persona_ref(raw, scene_dir, crop=False)
                rebuilt_id = True
        save_image(scenes[slot], existing, "JPEG", quality=90)
        logger.info("saved scene slot=%s", slot)
    return scenes


MAX_SCENE_TRIES = 2
MAX_FLUX_TRIES = 1
MAX_WIDE_FLUX_TRIES = 3


def _needs_standing_fallback(fails: list[str]) -> bool:
    blob = " ".join(fails).lower()
    return any(
        k in blob
        for k in (
            "torso too side-on",
            "body in profile",
            "walking profile",
            "over-shoulder",
            "not full-length",
            "no second person",
            "man missing",
        )
    )


def _candidate_rank(fails: list[str]) -> tuple:
    """Higher is better. Never prefer a side-on body over a front-ish one."""
    blob = " ".join(fails).lower()
    side = any(
        k in blob
        for k in (
            "torso too side-on",
            "over-shoulder",
            "body in profile",
            "walking profile",
        )
    )
    crop = "not full-length" in blob or "face too large" in blob
    ratio = 0.0
    for line in fails:
        if "chest/face=" in line:
            try:
                ratio = max(ratio, float(line.split("chest/face=")[1].split()[0]))
            except ValueError:
                pass
    return (0 if side else 1, 0 if crop else 1, ratio)


def _standing_catalog_lead() -> str:
    return (
        "REAL CAMERA PHOTOGRAPH, photorealistic, not an illustration. "
        "FRONT VIEW standing catalog photograph. Camera is in FRONT of her. "
        "We see both shoulders, both hips, and the FRONT of her clothes. "
        "NOT a side view, NOT a profile, NOT walking, NOT looking over the shoulder. "
        "35mm lens, camera several meters away. Head near the top edge, shoes visible "
        "at the bottom edge. STANDING STILL, feet planted. "
        "Both arms hang straight down with a gap of "
        "clothing between each arm and the torso. Uncovered empty wrists. "
    )


def _generate_scene_until_qa(
    prompt: str,
    ref_url: str,
    *,
    mode: str,
    slot: str,
    category: str,
    negative_prompt: str,
    on_api_call: Callable[[], None] | None,
) -> Image.Image:
    from worker.scene_qa import evaluate_scene

    # PuLID copies the ID bust. On the wide full-body slot that rotates the
    # whole person into profile. Ring/bracelet full shots have the same issue.
    skip_pulid = (mode == "full" and category in HAND_FOCUS_CATEGORIES) or slot == "wide_inset"
    candidates: list[tuple[Image.Image, list[str]]] = []
    torso_retry = (
        "RETRY: FRONT VIEW, STANDING STILL, both shoulders face the camera equally, "
        "chest and both hips to the lens, not walking, not a side-on or profile body, "
        "not looking over the shoulder. The head may turn a little; the torso must not. "
    )
    if not skip_pulid:
        for attempt in range(MAX_SCENE_TRIES):
            scale = 1.0 if attempt == 0 else max(0.45, 0.75**attempt)
            use_prompt = prompt
            if attempt > 0:
                use_prompt = (
                    torso_retry
                    + "RETRY: do not copy the identity headshot. "
                    + prompt
                )
            img = generate_scene_fal(
                use_prompt,
                ref_url,
                mode=mode,
                slot=slot,
                category=category,
                negative_prompt=negative_prompt,
                on_api_call=on_api_call,
                id_weight_scale=scale,
            )
            fails = evaluate_scene(img, slot, category)
            if not fails:
                return img
            candidates.append((img, fails))
            logger.warning(
                "scene qa slot=%s try=%s/%s %s",
                slot, attempt + 1, MAX_SCENE_TRIES, fails,
            )
        logger.warning("scene qa slot=%s pulid exhausted — flux/dev fallback", slot)

    last_fails = candidates[-1][1] if candidates else []
    need_standing = skip_pulid or not candidates or _needs_standing_fallback(last_fails)
    flux_tries = MAX_WIDE_FLUX_TRIES if slot == "wide_inset" else MAX_FLUX_TRIES
    if need_standing:
        for attempt in range(flux_tries):
            use_prompt = prompt
            if mode == "full":
                use_prompt = torso_retry + _standing_catalog_lead() + prompt
            elif attempt > 0:
                use_prompt = torso_retry + "RETRY: do not copy the identity headshot. " + prompt
            else:
                use_prompt = torso_retry + prompt
            img = generate_scene_flux_dev(
                use_prompt,
                negative_prompt=negative_prompt,
                on_api_call=on_api_call,
            )
            fails = evaluate_scene(img, slot, category)
            if not fails:
                return img
            candidates.append((img, fails))
            logger.warning(
                "scene qa slot=%s flux try=%s/%s %s",
                slot, attempt + 1, flux_tries, fails,
            )
    if not candidates:
        raise RuntimeError(f"scene qa slot={slot} failed after retries: {last_fails}")
    best_img, best_fails = max(candidates, key=lambda c: _candidate_rank(c[1]))
    logger.warning(
        "scene qa slot=%s failed after retries, keeping last frame: %s",
        slot,
        best_fails,
    )
    return best_img


def _tone_for_slot(slot: str, tone_names: list[str]) -> str | None:
    if slot == "body_1":
        return tone_names[0] if tone_names else None
    if slot == "body_2":
        return tone_names[1] if len(tone_names) > 1 else None
    return None
