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
    """Load scene_gen.py without importing worker/__init__.py (that pulls numpy)."""
    import importlib.util

    path = ROOT / "apps" / "worker" / "worker" / "scene_gen.py"
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
HAND_PRESENT_RULE = _sg.HAND_PRESENT_RULE
TURNED_SLOTS = _sg.TURNED_SLOTS
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
    for label, text in (("necklace date", date_n), ("ring date", date_r)):
        low = text.lower()
        if "man" not in low:
            _fail(f"{label}: missing man across the table", failures)
        if "blur" not in low:
            _fail(f"{label}: man must be blurred", failures)
        if "back" not in low and "hands" not in low:
            _fail(f"{label}: need blurred back or hands", failures)
    if "15" not in date_n:
        _fail("date necklace: torso must stay under 15 degrees", failures)
    if "15" not in date_r:
        _fail("date ring: torso must stay under 15 degrees", failures)

    for slot in SLOTS:
        p = build_scene_prompt("Sofia", slot, "necklace", "オフィス")
        if "15" not in p and "under 15" not in p.lower():
            _fail(f"{slot} necklace missing torso 15-degree rule", failures)

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

    for cat in ("necklace", "ring", "bracelet", "earring"):
        for slot in SLOTS:
            p = build_scene_prompt("Sofia", slot, cat, "オフィス").lower()
            n = slot_negative_prompt(slot, SCENE_META[slot]["mode"], cat).lower()
            if "no watch" not in p and "watch" not in n:
                _fail(f"{cat} {slot}: prompt/negative must ban watches", failures)
            if "jewelry" not in p and "jewelry" not in n:
                _fail(f"{cat} {slot}: must ban jewelry", failures)
            if ACCESSORY_BAN.split(":")[0].lower() not in p and "bare of accessories" not in p:
                if "no watch" not in p:
                    _fail(f"{cat} {slot}: missing accessory ban in prompt", failures)

    turned_ok = 0
    for slot in TURNED_SLOTS:
        pose = (POSE_VARIATION.get(slot, "") + HAND_HEAD_POSE.get(slot, "")).lower()
        if any(k in pose for k in ("turned 45", "turned 50", "turned 55", "80-90", "profile")):
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
    if "_generate_scene_until_qa" not in src or "evaluate_scene" not in src:
        _fail("runtime image QA retry missing from generate_all_scenes", failures)
    if "RETRY: do not copy the identity headshot" not in src:
        _fail("QA retry must strengthen the prompt, not only change seed", failures)
    if "generate_scene_flux_dev" not in src or "pulid exhausted" not in src:
        _fail("QA must not soft-accept; flux/dev fallback required after PuLID fails", failures)
    qa = (ROOT / "apps" / "worker" / "worker" / "scene_qa.py").read_text(encoding="utf-8")
    if "face too large for hand-hero" not in qa:
        _fail("scene_qa must reject portrait crops on ring/bracelet wear", failures)
    if "face too frontal" not in qa:
        _fail("scene_qa must reject frontal faces on turned slots", failures)
    if "foreground is not the woman" not in qa:
        _fail("scene_qa must reject date shots where the man is the foreground", failures)
    if "arms-crossed bust" not in qa:
        _fail("scene_qa must reject full-body shots that are actually crossed-arm busts", failures)

    return failures


def _hook_payload(failures: list[str], event: str, loop_count: int) -> dict:
    if not failures:
        if event == "stop":
            return {}
        return {
            "additional_context": "Scene-spec checklist passed (torso 15deg, 7 expressions, date man, hair up+tuck, open+turtleneck, ring/bracelet hands)."
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
