#!/usr/bin/env python3
"""Launch the shared scene-spec checker for Claude Code hooks.

Uses the worker venv (needs PIL). Maps output to Claude Code hook JSON.
Same checks as Cursor: .cursor/hooks/check_scene_spec.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".cursor" / "hooks" / "check_scene_spec.py"
STATE_DIR = ROOT / ".claude" / ".hook-state"
STOP_COUNT = STATE_DIR / "stop_fail_count"
MAX_STOP_LOOPS = 3


def _venv_python() -> Path | None:
    win = ROOT / "apps" / "worker" / ".venv" / "Scripts" / "python.exe"
    nix = ROOT / "apps" / "worker" / ".venv" / "bin" / "python"
    if win.is_file():
        return win
    if nix.is_file():
        return nix
    return None


def _edited_path(data: dict) -> str:
    inp = data.get("tool_input") or data.get("toolInput") or {}
    if not isinstance(inp, dict):
        return ""
    return str(
        inp.get("file_path") or inp.get("path") or inp.get("filePath") or ""
    )


def _is_scene_gen_edit(data: dict) -> bool:
    blob = _edited_path(data).replace("\\", "/")
    if "scene_gen.py" in blob:
        return True
    # Some tools put the path only in tool_response / extra fields.
    raw = json.dumps(data, ensure_ascii=False)
    return "scene_gen.py" in raw.replace("\\", "/")


def _event_name(data: dict) -> str:
    return str(
        data.get("hook_event_name") or data.get("hookEventName") or data.get("event") or ""
    )


def _run_checker(payload: dict) -> tuple[int, str]:
    py = _venv_python()
    if py is None:
        return 0, json.dumps(
            {
                "systemMessage": "worker venv が無いので scene-spec 検査をスキップしました。apps/worker で venv を作ってください。"
            },
            ensure_ascii=False,
        )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [str(py), str(CHECKER)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        env=env,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0 and not out:
        return proc.returncode, json.dumps(
            {"systemMessage": err or "scene-spec checker failed"},
            ensure_ascii=False,
        )
    return proc.returncode, out


def _parse_checker_json(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _read_stop_count() -> int:
    try:
        return int(STOP_COUNT.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def _write_stop_count(n: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STOP_COUNT.write_text(str(n), encoding="utf-8")


def main() -> int:
    raw_stdin = sys.stdin.read() if not sys.stdin.isatty() else ""
    data: dict = {}
    if raw_stdin.strip():
        try:
            parsed = json.loads(raw_stdin)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = {}

    event = _event_name(data).lower()
    is_stop = event == "stop"
    is_post = event in ("posttooluse", "afterfileedit", "afterfileedit_failure")

    if is_post and data and not _is_scene_gen_edit(data):
        return 0

    checker_payload = {
        "hook_event_name": "stop" if is_stop else "afterFileEdit",
        "loop_count": _read_stop_count() if is_stop else 0,
    }
    _code, checker_out = _run_checker(checker_payload)
    parsed = _parse_checker_json(checker_out)
    report = parsed.get("followup_message") or parsed.get("additional_context") or ""
    failed = bool(parsed.get("followup_message")) or (
        isinstance(report, str) and "FAILED" in report
    )

    if is_stop:
        if not failed:
            _write_stop_count(0)
            return 0
        n = _read_stop_count() + 1
        _write_stop_count(n)
        if n >= MAX_STOP_LOOPS:
            return 0
        sys.stdout.write(
            json.dumps(
                {
                    "decision": "block",
                    "reason": report or "Scene-spec checklist failed. Fix scene_gen.py.",
                },
                ensure_ascii=False,
            )
        )
        return 0

    # PostToolUse / other: give the model the checklist result.
    if report:
        sys.stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": report,
                    }
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
