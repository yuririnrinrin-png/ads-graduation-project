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
        "hazel eyes, elegant quiet expression"
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
        "sitting in a fine-dining restaurant booth across from a man in a dark "
        "suit — his face out of focus or turned away so attention stays on her, "
        "only his blurred silhouette and perhaps his hand near hers on the table "
        "visible, a lit candle and two wine glasses between them, strings of warm "
        "bokeh lights blurred in the background, romantic evening mood"
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
        "wearing a sharply tailored business blazer over a silk blouse, "
        "polished professional office fashion"
    ),
    "wear_cafe": (
        "wearing a relaxed yet elegant knit sweater or silky blouse with "
        "tailored trousers, casual-chic weekend-brunch style"
    ),
    "wear_date": (
        "wearing a sophisticated fitted dress with a subtly sexy neckline, "
        "intelligent and alluring grown-up evening style"
    ),
    "wear_holiday": (
        "wearing a refined flowing one-piece dress, elegant resort holiday style"
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

# Per-slot expression / head-angle / gaze / pose variety. PuLID's face-lock
# defaults to a straight-on neutral copy of the reference portrait, so each
# entry spells out an explicit angle and a distinctly different emotion.
POSE_VARIATION = {
    "wear_office": (
        "head turned about 30 degrees to her left in a three-quarter angle, "
        "chin slightly lifted, sharp confident closed-mouth smile, eyes locked "
        "on camera, shoulders squared, upright poised posture"
    ),
    "wear_cafe": (
        "head tilted gently to one side in a soft side profile, warm open "
        "smile clearly showing her teeth as if laughing at something someone "
        "said, eyes crinkled with genuine warmth"
    ),
    "wear_date": (
        "looking back over her shoulder toward the camera in a near-profile "
        "pose (body facing away, face turned back), soft sultry half-lidded "
        "gaze with a closed-mouth smirk"
    ),
    "wear_holiday": (
        "head thrown back slightly in genuine joyful laughter with teeth "
        "showing and eyes softly closed, face angled about 20 degrees upward "
        "and to the side"
    ),
    "body_1": (
        "strong side profile with her head turned almost fully to face left, "
        "serene composed closed-mouth smile, one hand resting lightly on her hip"
    ),
    "body_2": (
        "big candid grin showing teeth, head tilted playfully to one side "
        "in a three-quarter angle, bright eyes looking straight at camera"
    ),
    "wide_inset": (
        "calm gentle closed-mouth smile with a soft downward gaze away from "
        "camera in a three-quarter turned pose"
    ),
}

# Hairstyle is handled separately from pose because it needs its own strong
# positive AND negative wording — "hair down" alone is easily overpowered by
# the reference portrait's own hairstyle, so we explicitly forbid the other
# states too.
HAIR_STYLE = {
    "wear_office": (
        "up",
        "fully swept up and back into a sleek low bun, every strand pulled "
        "cleanly away from her neck — NOT flowing, NOT loose",
    ),
    "wear_cafe": (
        "down",
        "completely down and loose, flowing freely over both shoulders and "
        "down her back",
    ),
    "wear_date": (
        "up",
        "swept up into a high sleek ponytail gathered at the crown, smooth "
        "against her head — NOT flowing, NOT loose",
    ),
    "wear_holiday": (
        "down",
        "completely down and loose, wind-blown waves flowing freely past her "
        "shoulders",
    ),
    "body_1": (
        "up",
        "swept back into a smooth low chignon at the nape of her neck, sleek "
        "and fully gathered — NOT flowing, NOT loose",
    ),
    "body_2": (
        "down",
        "completely down and loose, natural tousled waves falling freely "
        "past her shoulders",
    ),
    "wide_inset": (
        "half",
        "styled half-up half-down — the top section gathered back while the "
        "rest falls loosely past her shoulders",
    ),
}

HAIR_NEGATIVE_BY_STATE = {
    "up": "hair down, loose hair, flowing hair, hair falling over shoulders",
    "down": "hair up, ponytail, bun, chignon, braid, plait, hair tie, updo, "
    "hair pinned up, hair pulled back",
    "half": "hair fully up, hair fully down, ponytail, bun, braid, plait",
}

# What body region the wear shot must expose for later jewelry composite.
CATEGORY_FRAMING = {
    "necklace": (
        "bust-up portrait showing face, neck, and upper chest, camera pulled "
        "back enough that neck and collarbones are clearly inside the frame "
        "(not a tight face-only close-up). Bare neck and décolletage clearly visible"
    ),
    "earring": (
        "close portrait of the face with both ears clearly visible. "
        "Bare earlobes, hair tucked or parted away from ears"
    ),
    "ring": (
        "fashion photo emphasizing elegant bare hands and fingers in a natural pose, "
        "face softly visible in background or cropped"
    ),
    "bracelet": (
        "fashion photo emphasizing bare forearm and wrist, "
        "hands relaxed, face softly visible"
    ),
}

NEGATIVE = (
    "jewelry, necklace, earrings, rings, bracelet, watch, accessories, "
    "text, watermark, logo, deformed hands, extra fingers, low quality, blurry, "
    "neutral expressionless face, blank stare, straight-on symmetric portrait, "
    "stiff passport-photo pose, extreme close-up, tight face-only crop, "
    "face filling the entire frame, cropped above the collarbone"
)

# Face-lock models bias toward tight headshots; push back for the wider
# "coordinate" shots so at least the outfit/torso reads clearly (feet may
# still be out of frame — that's fine, we only need the styling to be visible).
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
        f"Photorealistic head-and-shoulders portrait of {look}, with {hair} "
        "worn down naturally. Camera pulled back enough to show her neck "
        "and collarbones, not just a tight face close-up. "
        "Facing camera, neutral soft expression, studio softbox lighting, "
        "plain warm gray background, high detail skin, 85mm lens. "
        "No jewelry, no earrings, bare ears and neck visible."
    )


def hair_state(slot: str) -> str:
    return HAIR_STYLE.get(slot, ("down", ""))[0]


def slot_negative_prompt(slot: str, mode: str) -> str:
    base = NEGATIVE_FULL_BODY if mode == "full" else NEGATIVE
    hair_neg = HAIR_NEGATIVE_BY_STATE.get(hair_state(slot))
    if hair_neg:
        return f"{base}, {hair_neg}"
    return base


def build_scene_prompt(
    persona_name: str,
    slot: str,
    category: str,
    tone_label: str | None = None,
) -> str:
    look = persona_look(persona_name)
    hair_color = persona_hair(persona_name)
    meta = SCENE_META[slot]
    framing = category_framing(category)

    pose = POSE_VARIATION.get(slot, "natural relaxed expression and pose")
    _, hair_style = HAIR_STYLE.get(slot, ("down", "worn naturally"))
    # Hair goes right after the subject, before fashion/setting, so it isn't
    # drowned out — prompt position matters for how strongly it's honored.
    # (Do not also repeat/shout this elsewhere in the prompt: doing so in an
    # earlier pass made the model zoom in tight on the face/hair and broke
    # the fixed-anchor neck framing — see docs/HANDOFF.md.)
    hair_line = f"Hairstyle: her {hair_color} is {hair_style}."

    if meta["mode"] == "bust":
        setting = WEAR_SETTING.get(slot, "lifestyle interior, soft natural light")
        fashion = WEAR_FASHION.get(slot, "wearing a stylish coordinated outfit")
        return (
            f"Photorealistic commercial jewelry catalog photo of {look}. "
            f"{hair_line} {fashion}. "
            f"{framing}. Setting: {setting}. Expression and pose: {pose}. "
            "Same woman, editorial fashion lighting, square 1:1 crop. "
            "Absolutely no jewelry on the model — bare skin where jewelry would sit. "
            "No text, no watermark."
        )

    tone_bit = TONE_SETTING.get(tone_label or "", "wearing a stylish coordinated outfit")
    if slot == "wide_inset":
        setting = "standing in an airy studio space with plain soft-toned background"
    else:
        setting = f"standing in a softly lit lifestyle interior, {tone_bit}"
    return (
        f"Three-quarter length fashion photograph of {look}. "
        f"{hair_line} Standing, camera framing from the top of her head down "
        f"to at least mid-thigh so her full coordinated outfit and styling are "
        f"clearly visible. {setting}. "
        f"Expression and pose: {pose}. "
        "Same woman, soft daylight, editorial fashion photography, outfit and "
        "silhouette clearly readable. "
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
    negative_prompt: str | None = None,
    on_api_call: Callable[[], None] | None = None,
) -> Image.Image:
    # PuLID's default id_weight=1 biases hard toward copying the reference
    # portrait's expression/pose/hairstyle/crop almost exactly. Lower it a bit
    # for every slot so those can vary shot to shot while identity stays
    # recognizable; full-body slots need even more room to compose.
    is_full = mode == "full"
    negative = negative_prompt or (NEGATIVE_FULL_BODY if is_full else NEGATIVE)
    result = _fal_subscribe(
        "fal-ai/flux-pulid",
        {
            "prompt": prompt,
            "reference_image_url": reference_image_url,
            "image_size": {"width": FAL_GEN_SIZE, "height": FAL_GEN_SIZE},
            "num_inference_steps": 24,
            # NOTE: pushing guidance_scale up / id_weight down further (tried
            # 5.0-5.5 / 0.5-0.6 in an earlier pass) made the model crop in
            # much tighter on the face, breaking the fixed-anchor jewelry
            # placement (necklace landed on the nose/mouth instead of the
            # neck) — see docs/HANDOFF.md. Keep these at the values that were
            # confirmed to frame correctly; fix hairstyle/pose adherence via
            # prompt wording instead of these knobs.
            "guidance_scale": 4.5 if is_full else 4.2,
            "negative_prompt": negative,
            "id_weight": 0.65 if is_full else 0.75,
            "enable_safety_checker": True,
        },
    )
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
    caption = f"{persona_name} · {label} · local scene"
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
) -> dict[str, Image.Image]:
    """
    Build person-only scenes for every slot.
    Saves optional persona_ref.jpg when using fal.
    """
    scenes: dict[str, Image.Image] = {}

    if not fal_enabled():
        logger.info("FAL_KEY unset — using local placeholder scenes")
        for slot in slots:
            tone_label = _tone_for_slot(slot, tone_names)
            scenes[slot] = render_scene_local(persona_name, slot, tone_label)
        return scenes

    logger.info("FAL_KEY set — generating scenes via flux/dev + flux-pulid")
    ref_url = resolve_reference_url(
        persona_name, persona_image_key, on_api_call=on_api_call
    )
    # Keep a local copy of the reference for debugging / Phase 4 regen.
    try:
        ref_img = _to_square_size(_download_image(ref_url), SIZE)
        ref_path = scene_dir / "persona_ref.jpg"
        ref_img.save(ref_path, "JPEG", quality=90)
        logger.info("saved persona reference %s", ref_path)
    except Exception:
        logger.exception("could not cache persona reference image")

    for slot in slots:
        tone_label = _tone_for_slot(slot, tone_names)
        prompt = build_scene_prompt(persona_name, slot, category, tone_label)
        mode = SCENE_META[slot]["mode"]
        negative = slot_negative_prompt(slot, mode)
        logger.info("scene fal slot=%s mode=%s prompt_len=%s", slot, mode, len(prompt))
        scenes[slot] = generate_scene_fal(
            prompt,
            ref_url,
            mode=mode,
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
