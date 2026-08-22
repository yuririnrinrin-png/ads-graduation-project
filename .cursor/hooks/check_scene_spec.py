#!/usr/bin/env python3
"""Deterministic checks for person-scene prompt rules (REQUIREMENTS §5).

Used as a Cursor hook (JSON on stdin) or as a CLI:
  python .cursor/hooks/check_scene_spec.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_scene_gen():
    """Load scene_gen.py without importing worker.pipeline (that pulls redis)."""
    import importlib.util

    worker_root = ROOT / "apps" / "worker"
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))
    path = worker_root / "worker" / "scene_gen.py"
    spec = importlib.util.spec_from_file_location("tiamo_scene_gen", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tiamo_scene_gen"] = mod
    spec.loader.exec_module(mod)
    return mod


_sg = _load_scene_gen()
HAIR_STYLE = _sg.HAIR_STYLE
HAND_HEAD_POSE = _sg.HAND_HEAD_POSE
NECKLINE = _sg.NECKLINE
POSE_VARIATION = _sg.POSE_VARIATION
SCENE_META = _sg.SCENE_META
SLOT_EXPRESSION = _sg.SLOT_EXPRESSION
WEAR_SETTING = _sg.WEAR_SETTING
WEAR_SETTING_HAND = _sg.WEAR_SETTING_HAND
ACCESSORY_BAN = _sg.ACCESSORY_BAN
PHOTO_RULE = _sg.PHOTO_RULE
NEGATIVE = _sg.NEGATIVE
HAND_PRESENT_RULE = _sg.HAND_PRESENT_RULE
TURNED_SLOTS = _sg.TURNED_SLOTS
BODY_RULE = _sg.BODY_RULE
slot_pulid_params = _sg.slot_pulid_params
MAX_SCENE_TRIES = _sg.MAX_SCENE_TRIES
build_scene_prompt = _sg.build_scene_prompt
hair_state = _sg.hair_state
slot_negative_prompt = _sg.slot_negative_prompt

WEAR = ["wear_office", "wear_cafe", "wear_date", "wear_holiday"]
FULL = ["body_1", "body_2", "wide_inset"]
SLOTS = list(SCENE_META)


def _fail(msg: str, failures: list[str]) -> None:
    failures.append(msg)


def run_checks() -> list[str]:
    failures: list[str] = []

    labels = list(SLOT_EXPRESSION.values())
    if len(set(labels)) != 7:
        _fail(f"SLOT_EXPRESSION must be 7 unique labels, got {labels}", failures)

    for slot, label in SLOT_EXPRESSION.items():
        pose = POSE_VARIATION.get(slot, "")
        hand = HAND_HEAD_POSE.get(slot, "")
        if label not in pose:
            _fail(f"{slot} necklace pose missing expression {label!r}", failures)
        if label not in hand:
            _fail(f"{slot} hand pose missing expression {label!r}", failures)

    states = {hair_state(s) for s in SLOTS}
    if "up" not in states or "tuck" not in states:
        _fail(f"hair must include both up and tuck, got {states}", failures)
    if hair_state("wear_cafe") != "tuck" or hair_state("wide_inset") != "tuck":
        _fail("cafe and wide_inset must be ear-tuck down hair", failures)

    neck = {NECKLINE.get(s) for s in SLOTS}
    if "open" not in neck or "turtleneck" not in neck:
        _fail(f"neckline map must mix open and turtleneck, got {neck}", failures)

    open_hits = 0
    turtle_hits = 0
    for slot in SLOTS:
        p = build_scene_prompt("Sofia", slot, "ring", "オフィス").lower()
        if "turtleneck" in p or "mock-neck" in p:
            turtle_hits += 1
        if "open neckline" in p or "v-neck" in p:
            open_hits += 1
    if turtle_hits < 1 or open_hits < 1:
        _fail(
            f"ring prompts must mix open neckline and turtleneck "
            f"(open={open_hits} turtle={turtle_hits})",
            failures,
        )

    date_n = build_scene_prompt("Sofia", "wear_date", "necklace")
    date_r = build_scene_prompt("Sofia", "wear_date", "ring")
    date_e = build_scene_prompt("Sofia", "wear_date", "earring")
    for label, text in (
        ("necklace date", date_n),
        ("ring date", date_r),
        ("earring date", date_e),
    ):
        low = text.lower()
        if "man" not in low:
            _fail(f"{label}: missing man across the table", failures)
        if "blur" not in low:
            _fail(f"{label}: man must be softly blurred (woman stays the hero)", failures)
        if "enjoying" not in low and "together" not in low and "talking" not in low:
            _fail(f"{label}: date must feel like a couple enjoying dinner", failures)
        if "two-person" not in low and "two people" not in low:
            _fail(f"{label}: must say TWO-PERSON so the man is actually in frame", failures)
        if "face" not in low and "three-quarter" not in low:
            _fail(f"{label}: man must be visible as a person (face/three-quarter), not only a back", failures)
        if "only the back" not in low and "back of the man" not in low:
            _fail(f"{label}: must forbid a back-only man", failures)
        if "hero" not in low and "foreground" not in low:
            _fail(f"{label}: woman must stay the hero / foreground", failures)
        if "jewelry" not in low and "unobstructed" not in low:
            _fail(f"{label}: jewelry zones must stay visible / unobstructed", failures)
    if "15" not in date_n:
        _fail("date necklace: torso must stay under 15 degrees", failures)
    if "15" not in date_r:
        _fail("date ring: torso must stay under 15 degrees", failures)

    setting_date = WEAR_SETTING["wear_date"].lower()
    if "enjoying" not in setting_date:
        _fail("WEAR_SETTING wear_date must describe a couple enjoying the date", failures)
    if "face" not in setting_date and "three-quarter" not in setting_date:
        _fail("WEAR_SETTING wear_date: man needs a visible face, not only a back", failures)
    hand_date = WEAR_SETTING_HAND["wear_date"].lower()
    if "face" not in hand_date and "three-quarter" not in hand_date:
        _fail("WEAR_SETTING_HAND wear_date: man needs a visible face, not only a back", failures)

    if "15" not in BODY_RULE or "head may turn" not in BODY_RULE.lower():
        _fail("BODY_RULE must keep torso under 15 degrees and allow the head to turn", failures)
    if "not walking" not in BODY_RULE.lower() and "standing still" not in BODY_RULE.lower():
        _fail("BODY_RULE must forbid walking / require standing or sitting still", failures)
    if "street-fashion side view" not in BODY_RULE.lower() and "walking profile" not in BODY_RULE.lower():
        _fail("BODY_RULE must forbid a walking / street-fashion side-on body", failures)

    for slot in SLOTS:
        p = build_scene_prompt("Sofia", slot, "necklace", "オフィス")
        low = p.lower()
        if "15" not in p and "under 15" not in low:
            _fail(f"{slot} necklace missing torso 15-degree rule", failures)
        if "head may turn" not in low and "head only" not in low:
            _fail(f"{slot}: missing head-turns-independently instruction", failures)
        if "do not rotate the torso" not in low and "torso with the head" not in low:
            _fail(f"{slot}: must say the torso does not turn with the head", failures)

    for slot in FULL:
        p = build_scene_prompt("Sofia", slot, "necklace", "オフィス").lower()
        n = slot_negative_prompt(slot, "full", "necklace").lower()
        if "standing still" not in p and "not walking" not in p:
            _fail(f"{slot}: full-body prompt must say standing still / not walking", failures)
        if "walking" not in n and "striding" not in n:
            _fail(f"{slot}: full-body negative must ban walking/striding", failures)
        if slot == "wide_inset" and "over-the-shoulder" not in n and "looking over" not in n:
            _fail("wide_inset negative must ban looking over the shoulder", failures)
        if "front of her clothes" not in p and "both hips" not in p:
            _fail(f"{slot}: full-body must show the FRONT of the clothes / both hips", failures)

    gazes = []
    for slot in SLOTS:
        pose = POSE_VARIATION[slot].lower()
        gazes.append(pose)
    if not any("downcast" in g or "looking down" in g for g in gazes):
        _fail("need at least one downcast gaze among 7", failures)
    if not any("soft" in g for g in gazes):
        _fail("need at least one soft gaze among 7", failures)

    for slot in WEAR:
        p = build_scene_prompt("Sofia", slot, "ring")
        low = p.lower()
        if "hand" not in low and "wrist" not in low:
            _fail(f"ring {slot}: hands/wrist must lead", failures)
        if "largest" not in low and "fill the lower" not in low and "two-thirds" not in low:
            _fail(f"ring {slot}: hands should be the hero crop", failures)
    for slot in FULL:
        p = build_scene_prompt("Sofia", slot, "ring", "オフィス")
        low = p.lower()
        if "fingertip" not in low and "hands" not in low:
            _fail(f"ring {slot}: full body must keep hands visible", failures)
        if "front" not in low:
            _fail(f"ring {slot}: must be photographed from the front", failures)
        if "back view" not in slot_negative_prompt(slot, "full", "ring").lower() and slot in (
            "body_1",
            "wide_inset",
        ):
            if "back view" not in p.lower() and "not a back" not in p.lower():
                _fail(f"ring {slot}: forbid back view", failures)

    # Import-only sanity: settings still mention the man for date.
    if "man" not in WEAR_SETTING["wear_date"].lower():
        _fail("WEAR_SETTING wear_date missing man", failures)
    if "man" not in WEAR_SETTING_HAND["wear_date"].lower():
        _fail("WEAR_SETTING_HAND wear_date missing man", failures)
    if HAIR_STYLE["wear_cafe"][0] != "tuck":
        _fail("HAIR_STYLE cafe must be tuck", failures)

    if "like showing a watch" in HAND_PRESENT_RULE.get("bracelet", "").lower():
        _fail("bracelet pose must not say 'showing a watch' (model draws watches)", failures)

    # Extra jewelry is never drawn. The uploaded product is composited later.
    ban = ACCESSORY_BAN.lower()
    if "no necklace" not in ban or "no earrings" not in ban or "no rings" not in ban:
        _fail(
            "ACCESSORY_BAN must forbid necklace, earrings, and rings "
            "(product jewelry is composited later)",
            failures,
        )
    if "composited later" not in ban and "do not draw" not in ban:
        _fail("ACCESSORY_BAN must say jewelry is added later, not drawn by the model", failures)
    for cat in ("necklace", "ring", "bracelet", "earring"):
        for slot in SLOTS:
            p = build_scene_prompt("Sofia", slot, cat, "オフィス").lower()
            n = slot_negative_prompt(slot, SCENE_META[slot]["mode"], cat).lower()
            if "no watch" not in p and "watch" not in n:
                _fail(f"{cat} {slot}: prompt/negative must ban watches", failures)
            if "no necklace" not in p and "necklace" not in n:
                _fail(f"{cat} {slot}: must ban extra necklaces in every scene", failures)
            if "no earrings" not in p and "earrings" not in n:
                _fail(f"{cat} {slot}: must ban extra earrings in every scene", failures)
            if "jewelry" not in p and "jewelry" not in n:
                _fail(f"{cat} {slot}: must ban jewelry", failures)
            if "no jewelry" not in p and "bare neck" not in p:
                _fail(
                    f"{cat} {slot}: missing all-scenes extra-jewelry ban in the prompt",
                    failures,
                )
            if "photorealistic" not in p and "real camera photograph" not in p:
                _fail(f"{cat} {slot}: must ask for a real photograph, not an illustration", failures)

    photo = PHOTO_RULE.lower()
    if "photorealistic" not in photo or "illustration" not in photo:
        _fail("PHOTO_RULE must demand a camera photo and forbid illustration", failures)
    if "illustration" not in NEGATIVE.lower():
        _fail("NEGATIVE must ban illustration so scenes stay photographs", failures)

    turned_ok = 0
    for slot in TURNED_SLOTS:
        pose = (POSE_VARIATION.get(slot, "") + HAND_HEAD_POSE.get(slot, "")).lower()
        if "80-90" in pose or "strict side profile" in pose:
            _fail(f"{slot}: full profile head turns the whole body past 15 degrees", failures)
        if any(k in pose for k in ("turned 45", "turned 50", "turned 55", "turned 40")):
            turned_ok += 1
        p = build_scene_prompt("Sofia", slot, "necklace").lower()
        if "turned" not in p and "profile" not in p:
            _fail(f"{slot}: turned-face instruction missing from necklace prompt", failures)
    if turned_ok < 3:
        _fail(f"need several turned-face slots, got {turned_ok}", failures)

    hand_w = slot_pulid_params("wear_office", "bust", "ring")["id_weight"]
    if float(hand_w) > 0.22:
        _fail(f"ring id_weight too high ({hand_w}); ID portrait will hide hands", failures)
    date_w = slot_pulid_params("wear_date", "bust", "necklace")["id_weight"]
    if not (0.16 <= float(date_w) <= 0.22):
        _fail(
            f"date id_weight={date_w} should stay mid (too low: man becomes hero; "
            "too high: no second person)",
            failures,
        )
    date_b = build_scene_prompt("Sofia", "wear_date", "bracelet").lower()
    if "background" not in date_b:
        _fail("bracelet date: man must stay in the BACKGROUND", failures)
    if "foreground" not in date_b:
        _fail("bracelet date: the woman must be in the foreground", failures)
    if "blurred hands in frame" in date_b:
        _fail("date prompt must not put the man's hands in the foreground", failures)
    if MAX_SCENE_TRIES < 2:
        _fail("MAX_SCENE_TRIES must retry failed scene QA", failures)

    src = (ROOT / "apps" / "worker" / "worker" / "scene_gen.py").read_text(encoding="utf-8")
    if "_pulid_id_has_face" not in src:
        _fail("cached persona_ref must be checked for two eyes before PuLID")
    if "id_img.save(cached" in src:
        _fail("must not re-crop and overwrite cached persona_ref (collapses to a nose)")
    if "PulidNoFaceError" not in src or "persona_ref_src" not in src:
        _fail("PuLID facexlib fail must rebuild ID from persona_ref_src, not recrop cache")
    if "_generate_scene_until_qa" not in src or "evaluate_scene" not in src:
        _fail("runtime image QA retry missing from generate_all_scenes", failures)
    if "RETRY: do not copy the identity headshot" not in src:
        _fail("QA retry must strengthen the prompt, not only change seed", failures)
    if "generate_scene_flux_dev" not in src or "pulid exhausted" not in src:
        _fail("QA must not skip flux/dev fallback after PuLID fails", failures)
    if "FalBillingError" not in src or "_is_billing_error" not in src:
        _fail("fal billing lock must abort immediately instead of retrying slots", failures)
    if "JobCostLimitError" not in src:
        _fail("per-job yen cap must abort fal calls instead of retrying slots", failures)
    cost_src = (ROOT / "apps" / "worker" / "worker" / "job_cost.py").read_text(encoding="utf-8")
    if "before_fal_call" not in cost_src or "apiSpendYen" not in cost_src:
        _fail("job_cost.py must record yen spend and block before the next fal call", failures)
    if "keeping last frame" not in src or "failed after retries" not in src:
        _fail("scene QA must keep last frame after retries so the job can finish", failures)
    if "_needs_standing_fallback" not in src:
        _fail("side-on / over-shoulder QA fail must still try flux standing fallback", failures)
    if "skip_pulid" not in src:
        _fail("ring/bracelet full-body must skip PuLID (it copies crossed-arm busts)", failures)
    if 'slot == "wide_inset"' not in src:
        _fail("wide_inset must skip PuLID so the torso stays front-on", failures)
    if "MAX_WIDE_FLUX_TRIES" not in src:
        _fail("wide_inset must retry flux standing shots more than once", failures)
    qa = (ROOT / "apps" / "worker" / "worker" / "scene_qa.py").read_text(encoding="utf-8")
    if "face too large for hand-hero" not in qa:
        _fail("scene_qa must reject portrait crops on ring/bracelet wear", failures)
    if "face too frontal" not in qa:
        _fail("scene_qa must reject passport-frontal faces on turned slots", failures)
    if "torso too side-on" not in qa or "body in profile" not in qa:
        _fail("scene_qa must reject side-on / profile bodies (15-degree torso)", failures)
    if "likely walking profile" not in qa:
        _fail("scene_qa must reject full-body walking / off-center profile bodies", failures)
    if "over-shoulder side-on body" not in qa:
        _fail("scene_qa must reject looking-over-the-shoulder side-on bodies", failures)
    if "not full-length (likely over-shoulder / arms-crossed bust)" not in qa:
        _fail("scene_qa must reject over-shoulder bust crops on full-body slots", failures)
    if "_MIN_TORSO_RATIO_BUSY" not in qa:
        _fail("scene_qa must still measure torso width on busy backgrounds", failures)
    if "foreground is not the woman" not in qa:
        _fail("scene_qa must reject date shots where the man is the foreground", failures)
    if "no second person" not in qa:
        _fail("scene_qa must reject date shots with no man in frame", failures)
    if "arms-crossed bust" not in qa:
        _fail("scene_qa must reject full-body shots that are actually crossed-arm busts", failures)

    return failures


def _hook_payload(failures: list[str], event: str, loop_count: int) -> dict:
    if not failures:
        if event == "stop":
            return {}
        return {
            "additional_context": "Scene-spec checklist passed (torso 15deg, date two-person, extra jewelry banned in every scene)."
        }

    report = "Scene-spec checklist FAILED:\n- " + "\n- ".join(failures)
    report += (
        "\nFix apps/worker/worker/scene_gen.py (and docs if the spec changed) "
        "then re-run. Do not skip these product rules."
    )
    if event == "stop":
        if loop_count >= 3:
            return {}
        return {"followup_message": report}
    return {"additional_context": report}


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    event = "cli"
    loop_count = 0
    if raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        event = str(data.get("hook_event_name") or data.get("event") or "afterFileEdit")
        loop_count = int(data.get("loop_count") or 0)

    failures = run_checks()
    if event == "cli":
        if failures:
            print("FAIL")
            for f in failures:
                print(f"- {f}")
            return 1
        print("OK")
        return 0

    sys.stdout.write(json.dumps(_hook_payload(failures, event, loop_count), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
