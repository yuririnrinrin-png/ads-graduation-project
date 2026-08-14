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

# Jewelry is a front-facing 2D cutout, so every shot stays nearly frontal
# (yaw within ~15°). Variety comes from expression, a small unique yaw,
# hairstyle, setting, and clothes — not from profile or over-the-shoulder.
POSE_VARIATION = {
    "wear_office": (
        "CRITICAL EXPRESSION — キリッとした笑顔: a sharp, composed, "
        "closed-mouth smile with firm lifted corners, intense focused eyes, "
        "no teeth, not soft, not dreamy. Face turned about 10 degrees left, "
        "both eyes visible, yaw within 15 degrees"
    ),
    "wear_cafe": (
        "CRITICAL EXPRESSION — 屈託ない笑顔: a big carefree laugh, teeth "
        "clearly showing, cheeks pushed up, eyes crinkled with genuine joy, "
        "unselfconscious. Face turned about 8 degrees right, both eyes visible"
    ),
    "wear_date": (
        "CRITICAL EXPRESSION — 甘えたような笑顔: a coy, sweet, slightly "
        "pleading closed-mouth smile, softer lower lip, gentle upward glance "
        "toward the camera, NOT teeth, NOT a smirk of confidence. Face turned "
        "about 5 degrees left, both eyes visible"
    ),
    "wear_holiday": (
        "CRITICAL EXPRESSION — 華やかな笑顔: a glamorous, radiant, wide smile "
        "showing teeth, bright sparkling eyes, polished beauty-campaign energy "
        "(not a casual laugh). Chin slightly lifted, face turned about 12 "
        "degrees right, both eyes open"
    ),
    "body_1": (
        "CRITICAL EXPRESSION — 自然な笑顔: an easy, unposed closed-mouth "
        "smile, relaxed cheeks, kind eyes, as if caught mid-conversation. "
        "NOT a fashion-model pose. Face turned 15 degrees left, BOTH eyes visible"
    ),
    "body_2": (
        "CRITICAL EXPRESSION — 弾ける満面の笑み: an exuberant open grin, "
        "teeth showing, one playful head tilt, eyes shining — different from "
        "a polite smile. Face turned about 10 degrees right, both eyes visible"
    ),
    "wide_inset": (
        "CRITICAL EXPRESSION — 上品な微笑: an elegant, calm smile with "
        "clearly lifted mouth corners, lips closed, composed and gracious, "
        "gaze slightly down but face still toward camera. NOT blank, NOT a "
        "grin. Face almost straight-on, both eyes visible"
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
        "profile, teeth showing, open-mouth laugh, coy pout, dreamy eyes, "
        "blank stare, hair down over shoulders, turtleneck"
    ),
    "wear_cafe": (
        "profile, bun, ponytail, updo, hair pulled up, closed-mouth polite "
        "smile, serious face, frowning, turtleneck, hair on the chest"
    ),
    "wear_date": (
        "looking over the shoulder, profile, teeth showing, big laugh, "
        "sharp intense eyes, hair down over the chest, turtleneck"
    ),
    "wear_holiday": (
        "head thrown back, eyes closed, profile, closed-mouth smile, "
        "serious frown, coy pout, turtleneck, hair down over shoulders"
    ),
    "body_1": (
        "side profile, teeth showing, open mouth, fashion-model pout, "
        "blank stare, laughing, tight headshot"
    ),
    "body_2": (
        "side profile, closed-mouth polite smile, frowning, blank stare, "
        "tight headshot"
    ),
    "wide_inset": (
        "profile, big grin, teeth showing, bun, ponytail, updo, blank stare, "
        "hair on the chest, tight headshot"
    ),
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
    "side profile, full profile, looking over the shoulder, "
    "face turned more than 15 degrees, only one eye visible, "
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
        f"Photorealistic head-and-shoulders portrait of {look}, with {hair} "
        "worn DOWN (not a bun), tucked behind both ears so the earlobes, neck, "
        "and collarbones are fully visible, hair length falling down her back. "
        "Open neckline. Facing the camera straight-on, soft neutral "
        "closed-mouth expression, studio softbox lighting, plain warm gray "
        "background, high detail skin, 85mm lens. "
        "No jewelry, no earrings, bare ears and neck visible."
    )


def hair_state(slot: str) -> str:
    return HAIR_STYLE.get(slot, ("up", ""))[0]


def slot_id_weight(slot: str, mode: str) -> float:
    """Reference is hair-down + ears out. Tuck slots keep a tighter lock so
    they copy that down hair. Updo slots loosen so bun/ponytail can win."""
    if hair_state(slot) == "tuck":
        return 0.62
    return 0.48 if mode == "full" else 0.50


def slot_negative_prompt(slot: str, mode: str) -> str:
    base = NEGATIVE_FULL_BODY if mode == "full" else NEGATIVE_BUST
    extras = [HAIR_NEGATIVE_BY_STATE.get(hair_state(slot), "")]
    extras.append(SLOT_NEGATIVE_EXTRA.get(slot, ""))
    extra = ", ".join(e for e in extras if e)
    return f"{base}, {extra}" if extra else base


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

    pose = POSE_VARIATION.get(slot, "nearly frontal face, natural expression")
    state, hair_style = HAIR_STYLE.get(slot, ("up", "worn off the neck"))
    # Pose + hair MUST lead the prompt. fal-ai/flux-pulid defaults
    # max_sequence_length=128, which silently dropped the old tail.
    if state == "up":
        hair_line = (
            f"CRITICAL HAIRSTYLE: hair is UP. "
            f"The nape of her neck and both ears are fully exposed. "
            f"Zero hair on the chest or in front of the neck. "
            f"Her {hair_color} is {hair_style}."
        )
        lead = (
            f"{pose} {hair_line} "
            "Head is nearly frontal — both eyes visible, yaw within 15 degrees."
        )
    else:
        hair_line = (
            f"CRITICAL HAIRSTYLE: HAIR IS DOWN. Long hair falling down her "
            f"back, loosely tucked behind both ears. You can see the hair "
            f"length past the shoulders. NOT a bun, NOT a ponytail, NOT an updo. "
            f"Collarbones and the front of the neck stay clear. "
            f"Her {hair_color} is {hair_style}."
        )
        lead = (
            f"{hair_line} {pose} "
            "Head is nearly frontal — both eyes visible, yaw within 15 degrees."
        )

    if meta["mode"] == "bust":
        setting = WEAR_SETTING.get(slot, "lifestyle interior, soft natural light")
        fashion = WEAR_FASHION.get(slot, "wearing a stylish coordinated outfit")
        companion = ""
        if slot == "wear_date":
            companion = (
                "A second person may be softly blurred in the background. "
                "She faces the camera, not looking over her shoulder. "
            )
        return (
            f"{lead} {companion}"
            f"Photorealistic commercial jewelry catalog photo of {look}. "
            f"{fashion}. {framing}. Setting: {setting}. "
            "Same woman as the identity reference. Keep the face nearly frontal. "
            "Do NOT copy a blank or identical polite smile — this shot's "
            "expression must match the CRITICAL EXPRESSION above. "
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
        "Same woman as the identity reference. Keep the face nearly frontal. "
        "Do NOT copy a blank or identical polite smile — this shot's "
        "expression must match the CRITICAL EXPRESSION above. "
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
    slot: str | None = None,
    negative_prompt: str | None = None,
    on_api_call: Callable[[], None] | None = None,
) -> Image.Image:
    # PuLID's default id_weight=1 copies the reference portrait's
    # expression. Tuck-down slots use a slightly looser lock.
    is_full = mode == "full"
    negative = negative_prompt or (NEGATIVE_FULL_BODY if is_full else NEGATIVE)
    id_w = slot_id_weight(slot, mode) if slot else (0.55 if is_full else 0.62)
    # Omit/0 makes every regen a copy of the first shot (same prompt + same face).
    seed = random.randint(1, 2_147_483_647)
    logger.info("scene fal seed=%s slot=%s", seed, slot)
    result = _fal_subscribe(
        "fal-ai/flux-pulid",
        {
            "prompt": prompt,
            "reference_image_url": reference_image_url,
            "image_size": {"width": FAL_GEN_SIZE, "height": FAL_GEN_SIZE},
            "num_inference_steps": 24,
            "seed": seed,
            # max_sequence_length=512: the default 128 truncated pose/hair.
            "guidance_scale": 4.5 if is_full else 4.2,
            "true_cfg": 1.8,
            "max_sequence_length": "512",
            "negative_prompt": negative,
            "id_weight": id_w,
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
    if cached:
        import fal_client

        ref_url = fal_client.upload_file(str(cached))
        logger.info("reusing cached persona reference %s", cached)
    else:
        ref_url = resolve_reference_url(
            persona_name, persona_image_key, on_api_call=on_api_call
        )
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
