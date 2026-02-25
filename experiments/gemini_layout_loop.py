#!/usr/bin/env python3
"""Experimental Gemini-driven layout loop for ABD workflows.

This script is intentionally experimental and isolated from the main pipeline.
It runs an internal tool loop with Gemini:
  1) apply_placement_patch
  2) test_layout
  3) finish_layout

The loop continues until the agent calls finish_layout successfully or max
iterations is reached.

HARD MODEL POLICY:
- ONLY Gemini models with major version >= 3 are allowed.
- Gemini 2.x or below is strictly forbidden.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from boards import get_example  # noqa: E402
from src.circuit import Circuit  # noqa: E402
from src.export_pcb import COMP_SPACING, FOOTPRINTS, PIN_TO_PAD, export_pcb  # noqa: E402

GRID_START_X = 120.0
GRID_START_Y = 80.0
GRID_COLS = 4
DEFAULT_SNAP_MM = 0.5
MIN_GEMINI_MAJOR = 3
DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
MODEL_POLICY_BANNER = (
    "HARD POLICY: ONLY GEMINI MODELS WITH MAJOR VERSION >= 3 ARE ALLOWED. "
    "GEMINI 2.x OR BELOW IS FORBIDDEN."
)


SYSTEM_PROMPT = """You are the internal PCB layout agent for this repository.

HARD POLICY:
- You are running under Gemini major version >= 3.
- Gemini 2.x or below is forbidden in this workflow.

You have exactly 3 tools:
1) apply_placement_patch
2) test_layout
3) finish_layout

Rules:
- Return ONLY one JSON object with this shape:
  {"tool":"<name>","args":{...}}
- Do not output prose.
- Be a professional PCB layout designer, not a random mover.
- Prefer small, targeted moves.
- Make ONE placement change at a time (single component per edit).
- After every placement edit, immediately call test_layout to generate a new snapshot.
- Call finish_layout only when test_layout reports:
  - overlap_count == 0
  - out_of_bounds_count == 0
  - footprint_error_count == 0
  - net_error_count == 0
- If a tool reports failure, adapt and continue.
- When finished, call finish_layout with a short summary.

Placement quality objectives:
- Keep functionally related components close (power block, USB block, IC support parts).
- Keep connectors and IO-facing parts at logical board edges.
- Keep decoupling capacitors close to the IC/regulator power pins.
- Align similar passives for clean routing channels and readability.
- Avoid placements that are technically valid but physically nonsensical.
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_key_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key_name = k.strip()
        value = v.strip()

        if value.startswith('"'):
            end = value.find('"', 1)
            if end > 0:
                parsed = value[1:end]
            else:
                parsed = value.strip('"').strip()
        elif value.startswith("'"):
            end = value.find("'", 1)
            if end > 0:
                parsed = value[1:end]
            else:
                parsed = value.strip("'").strip()
        else:
            parsed = value.split("#", 1)[0].strip()

        if parsed:
            out[key_name] = parsed
    return out


def _normalize_model_name(model: str) -> str:
    model = model.strip()
    if model.startswith("models/"):
        return model[len("models/") :]
    return model


def _gemini_major_version(model: str) -> int | None:
    normalized = _normalize_model_name(model)
    match = re.match(r"^gemini-(\d+)(?:\.[0-9]+)?(?:-|$)", normalized)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _is_allowed_model(model: str) -> bool:
    major = _gemini_major_version(model)
    return major is not None and major >= MIN_GEMINI_MAJOR


def _load_gemini_keys() -> list[str]:
    keys: list[str] = []
    env_primary = os.environ.get("GEMINI_API_KEY")
    env_secondary = os.environ.get("GEMINI_API_KEY_2")
    if env_primary:
        keys.append(env_primary)
    if env_secondary and env_secondary not in keys:
        keys.append(env_secondary)

    cfg = _read_key_file(Path.home() / ".config" / "keys.env")
    for name in ["GEMINI_API_KEY", "GEMINI_API_KEY_2"]:
        val = cfg.get(name)
        if val and val not in keys:
            keys.append(val)

    return keys


@dataclass
class GeminiClient:
    model: str
    keys: list[str]
    timeout_sec: int = 90

    def _build_request(self, key: str, text: str, image_path: Path | None) -> urllib.request.Request:
        parts: list[dict[str, Any]] = [{"text": text}]
        if image_path and image_path.exists():
            raw = image_path.read_bytes()
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(raw).decode("ascii"),
                }
            })

        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        body = json.dumps(payload).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"
        return urllib.request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def generate(self, text: str, image_path: Path | None = None) -> str:
        if not self.keys:
            raise RuntimeError("No Gemini API keys found in env or ~/.config/keys.env")

        last_error: Exception | None = None
        for key in self.keys:
            req = self._build_request(key, text, image_path)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                cands = data.get("candidates", [])
                if not cands:
                    raise RuntimeError(f"Gemini returned no candidates: {json.dumps(data)[:600]}")
                parts = cands[0].get("content", {}).get("parts", [])
                text_parts = [p.get("text", "") for p in parts if isinstance(p, dict)]
                out = "".join(text_parts).strip()
                if not out:
                    raise RuntimeError("Gemini returned empty text output")
                return out
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", errors="ignore")
                if e.code in {401, 403, 429}:
                    last_error = RuntimeError(f"Gemini key failed ({e.code})")
                    continue
                raise RuntimeError(f"Gemini HTTP error {e.code}: {msg[:600]}") from e
            except Exception as e:  # pragma: no cover - runtime network errors
                last_error = e
                continue

        raise RuntimeError(f"All Gemini keys failed: {last_error}")


def _footprint_kind(comp) -> str:
    if comp.footprint and comp.footprint in FOOTPRINTS:
        return comp.footprint
    return comp.kind


def _grid_position(index: int) -> tuple[float, float]:
    col = index % GRID_COLS
    row = index // GRID_COLS
    return (GRID_START_X + col * COMP_SPACING, GRID_START_Y + row * COMP_SPACING)


def _bbox(cx: float, cy: float, courtyard: dict) -> tuple[float, float, float, float]:
    x1 = cx + courtyard["x"]
    y1 = cy + courtyard["y"]
    x2 = x1 + courtyard["w"]
    y2 = y1 + courtyard["h"]
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _boxes_collide(a: tuple[float, float, float, float], b: tuple[float, float, float, float], clearance: float) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    if ax2 + clearance <= bx1:
        return False
    if bx2 + clearance <= ax1:
        return False
    if ay2 + clearance <= by1:
        return False
    if by2 + clearance <= ay1:
        return False
    return True


def _component_net_view(circuit: Circuit) -> dict[str, list[tuple[str, str]]]:
    expected: dict[str, list[tuple[str, str]]] = {}
    for ref, comp in circuit.components.items():
        if comp.simulation_only:
            continue
        for pin, net in comp.pins.items():
            expected.setdefault(net, []).append((ref, pin))
    for net_name in expected:
        expected[net_name] = sorted(expected[net_name])
    return expected


def _net_registry_view(circuit: Circuit) -> dict[str, list[tuple[str, str]]]:
    actual: dict[str, list[tuple[str, str]]] = {}
    for net_name, net in circuit.nets.items():
        filtered = []
        for ref, pin in net.components:
            comp = circuit.components.get(ref)
            if comp is None or comp.simulation_only:
                continue
            filtered.append((ref, pin))
        if filtered:
            actual[net_name] = sorted(filtered)
    return actual


def _validate_nets(circuit: Circuit) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for ref, comp in circuit.components.items():
        if comp.simulation_only:
            continue
        fp_kind = _footprint_kind(comp)
        if fp_kind not in FOOTPRINTS:
            errors.append(f"{ref}: footprint missing ({fp_kind})")
            continue
        pin_map = PIN_TO_PAD.get(comp.kind, PIN_TO_PAD.get(fp_kind, {}))
        if not pin_map:
            errors.append(f"{ref}: pin->pad map missing ({comp.kind}/{fp_kind})")
            continue
        for pin in comp.pins:
            if pin not in pin_map:
                errors.append(f"{ref}: pin not in pin map ({pin})")

    expected = _component_net_view(circuit)
    actual = _net_registry_view(circuit)
    if set(expected) != set(actual):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            errors.append(f"net registry missing nets: {', '.join(missing)}")
        if extra:
            errors.append(f"net registry extra nets: {', '.join(extra)}")
    for net_name in sorted(set(expected) & set(actual)):
        if expected[net_name] != actual[net_name]:
            errors.append(f"net mismatch: {net_name}")
    for net_name, conns in sorted(expected.items()):
        if len(conns) < 2:
            warnings.append(f"dangling net: {net_name} ({len(conns)} connections)")
    return errors, warnings


def _snap(value: float, step: float) -> float:
    if step <= 0:
        return value
    return round(round(value / step) * step, 4)


class LayoutLoop:
    def __init__(self, example: str, model: str, max_iters: int, clearance_mm: float, snap_mm: float):
        requested_model = _normalize_model_name(model)
        if not _is_allowed_model(requested_model):
            raise RuntimeError(
                f"{MODEL_POLICY_BANNER} Requested='{requested_model}'. "
                "Use a Gemini model with major version >= 3 (e.g. gemini-3-pro-preview or gemini-3.1-pro-preview)."
            )
        self.example = example
        self.model = requested_model
        self.max_iters = max_iters
        self.clearance_mm = clearance_mm
        self.snap_mm = snap_mm

        self.spec = get_example(example)
        self.circuit = self.spec.builder()
        self.board_w, self.board_h = self.spec.board_size
        self.board_left = GRID_START_X - 10.0
        self.board_top = GRID_START_Y - 10.0
        self.board_right = GRID_START_X + self.board_w
        self.board_bottom = GRID_START_Y + self.board_h

        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = ROOT / ".autoboard" / "agent_runs" / f"{example}_{self.run_id}"
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.placement = self._init_placement()
        self.last_report: dict[str, Any] | None = None
        self.finished = False
        self.finish_summary = ""
        self.history: list[dict[str, Any]] = []
        self._must_test_after_edit = False

        keys = _load_gemini_keys()
        self.client = GeminiClient(model=model, keys=keys)

        self._write_json("placement.json", self.placement)
        self._write_json("meta.json", {
            "example": example,
            "model": model,
            "created_at": _utc_now(),
            "max_iters": max_iters,
            "clearance_mm": clearance_mm,
            "snap_mm": snap_mm,
        })

    def _init_placement(self) -> dict[str, dict[str, float]]:
        base = self.spec.placement() or {}
        out: dict[str, dict[str, float]] = {}
        idx = 0
        for ref, comp in self.circuit.components.items():
            if comp.simulation_only:
                continue
            x, y = base.get(ref, _grid_position(idx))
            out[ref] = {"x": float(x), "y": float(y), "rotation": 0.0}
            idx += 1
        return out

    def _write_json(self, name: str, payload: Any):
        path = self.run_dir / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def _placement_tuple_map(self) -> dict[str, tuple[float, float]]:
        return {ref: (v["x"], v["y"]) for ref, v in self.placement.items()}

    def _placement_summary(self, limit: int = 24) -> list[dict[str, Any]]:
        rows = []
        for ref in sorted(self.placement.keys()):
            v = self.placement[ref]
            rows.append({
                "ref": ref,
                "x": round(v["x"], 3),
                "y": round(v["y"], 3),
                "rotation": round(v.get("rotation", 0.0), 2),
            })
        return rows[:limit]

    def tool_apply_placement_patch(self, args: dict[str, Any]) -> dict[str, Any]:
        edits = args.get("edits", [])
        if not isinstance(edits, list):
            return {"ok": False, "error": "edits must be a list"}
        if not edits:
            return {"ok": False, "error": "edits is empty"}

        # Enforce incremental loop behavior: one placement change per iteration.
        multi_edit_truncated = False
        if len(edits) > 1:
            edits = edits[:1]
            multi_edit_truncated = True

        applied = []
        rejected = []
        for edit in edits:
            if not isinstance(edit, dict):
                rejected.append({"edit": edit, "reason": "not an object"})
                continue
            ref = edit.get("ref")
            if not isinstance(ref, str) or ref not in self.placement:
                rejected.append({"edit": edit, "reason": "invalid ref"})
                continue

            current = self.placement[ref]
            x = current["x"]
            y = current["y"]
            rot = current.get("rotation", 0.0)

            if "x" in edit and "y" in edit:
                try:
                    x = float(edit["x"])
                    y = float(edit["y"])
                except Exception:
                    rejected.append({"edit": edit, "reason": "x/y must be numeric"})
                    continue
            elif "dx" in edit or "dy" in edit:
                try:
                    x = x + float(edit.get("dx", 0.0))
                    y = y + float(edit.get("dy", 0.0))
                except Exception:
                    rejected.append({"edit": edit, "reason": "dx/dy must be numeric"})
                    continue
            else:
                rejected.append({"edit": edit, "reason": "provide x+y or dx/dy"})
                continue

            if "rotation" in edit:
                try:
                    rot = float(edit["rotation"])
                except Exception:
                    pass

            x = _snap(x, self.snap_mm)
            y = _snap(y, self.snap_mm)
            rot = round(rot % 360.0, 2)

            self.placement[ref] = {"x": x, "y": y, "rotation": rot}
            applied.append({"ref": ref, "x": x, "y": y, "rotation": rot})

        self._write_json("placement.json", self.placement)
        self._must_test_after_edit = len(applied) > 0
        return {
            "ok": True,
            "applied_count": len(applied),
            "rejected_count": len(rejected),
            "multi_edit_truncated": multi_edit_truncated,
            "applied": applied[:40],
            "rejected": rejected[:40],
            "next_best_tool_hint": "MUST call test_layout next to capture a fresh snapshot.",
        }

    def _render_snapshot(self, pcb_path: Path, output_png: Path) -> dict[str, Any]:
        cmd = [
            "kicad-cli", "pcb", "render",
            "-o", str(output_png),
            "--side", "top",
            "--quality", "basic",
            "--background", "opaque",
            "-w", "1400",
            str(pcb_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            ok = output_png.exists()
            return {
                "ok": ok and proc.returncode == 0,
                "stdout_tail": (proc.stdout or "")[-400:],
                "stderr_tail": (proc.stderr or "")[-400:],
                "snapshot_path": str(output_png.relative_to(ROOT)) if ok else None,
                "snapshot_abs_path": str(output_png.resolve()) if ok else None,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "snapshot_path": None, "snapshot_abs_path": None}

    def tool_test_layout(self, args: dict[str, Any]) -> dict[str, Any]:
        self._must_test_after_edit = False
        net_errors, net_warnings = _validate_nets(self.circuit)

        boxes: dict[str, tuple[float, float, float, float]] = {}
        footprint_errors: list[str] = []
        bounds_errors: list[str] = []
        overlap_errors: list[str] = []

        for ref, comp in self.circuit.components.items():
            if comp.simulation_only:
                continue
            fp_kind = _footprint_kind(comp)
            fp_def = FOOTPRINTS.get(fp_kind)
            if fp_def is None:
                footprint_errors.append(f"{ref}: footprint not found ({fp_kind})")
                continue
            p = self.placement.get(ref)
            if p is None:
                footprint_errors.append(f"{ref}: missing placement")
                continue

            box = _bbox(p["x"], p["y"], fp_def["courtyard"])
            boxes[ref] = box
            x1, y1, x2, y2 = box
            if x1 < self.board_left or y1 < self.board_top or x2 > self.board_right or y2 > self.board_bottom:
                bounds_errors.append(
                    f"{ref}: out_of_bounds bbox={x1:.2f},{y1:.2f},{x2:.2f},{y2:.2f} "
                    f"board={self.board_left:.2f},{self.board_top:.2f},{self.board_right:.2f},{self.board_bottom:.2f}"
                )

        refs = sorted(boxes.keys())
        for i, ref_a in enumerate(refs):
            for ref_b in refs[i + 1:]:
                if _boxes_collide(boxes[ref_a], boxes[ref_b], self.clearance_mm):
                    overlap_errors.append(f"{ref_a} <-> {ref_b}")

        test_dir = self.run_dir / "artifacts"
        test_dir.mkdir(parents=True, exist_ok=True)
        pcb_path = test_dir / "layout_unrouted.kicad_pcb"
        export_pcb(
            self.circuit,
            str(pcb_path),
            board_width=self.board_w,
            board_height=self.board_h,
            placement=self._placement_tuple_map(),
        )
        snap_path = test_dir / "layout_snapshot_top.png"
        render = self._render_snapshot(pcb_path, snap_path)

        ok = not net_errors and not footprint_errors and not bounds_errors and not overlap_errors
        report = {
            "ok": ok,
            "created_at": _utc_now(),
            "reason": args.get("reason", ""),
            "counts": {
                "net_error_count": len(net_errors),
                "footprint_error_count": len(footprint_errors),
                "out_of_bounds_count": len(bounds_errors),
                "overlap_count": len(overlap_errors),
                "net_warning_count": len(net_warnings),
            },
            "errors": {
                "net_errors": net_errors[:80],
                "footprint_errors": footprint_errors[:80],
                "bounds_errors": bounds_errors[:80],
                "overlap_errors": overlap_errors[:200],
            },
            "warnings": net_warnings[:80],
            "snapshot": render,
            "next_best_tool_hint": (
                "If all error counts are zero and visual quality is good, call finish_layout. "
                "Otherwise call apply_placement_patch then test_layout again."
            ),
            "final_command_reminder": f"When layout is done, run: ./abd forward --example {self.example}",
        }
        self.last_report = report
        self._write_json("last_test_report.json", report)
        return report

    def tool_finish_layout(self, args: dict[str, Any]) -> dict[str, Any]:
        summary = str(args.get("summary", "")).strip()
        if self.last_report is None:
            return {
                "ok": False,
                "done": False,
                "error": "No test report yet. Call test_layout first.",
            }

        counts = self.last_report.get("counts", {})
        blocking = (
            int(counts.get("net_error_count", 0))
            + int(counts.get("footprint_error_count", 0))
            + int(counts.get("out_of_bounds_count", 0))
            + int(counts.get("overlap_count", 0))
        )
        if blocking > 0:
            return {
                "ok": False,
                "done": False,
                "error": f"Layout not clean yet ({blocking} blocking issues).",
                "next_best_tool_hint": "Call apply_placement_patch or test_layout again.",
            }

        self.finished = True
        self.finish_summary = summary or "Layout accepted by agent."
        result = {
            "ok": True,
            "done": True,
            "summary": self.finish_summary,
            "final_command_reminder": f"Run this now: ./abd forward --example {self.example}",
        }
        self._write_json("finish_result.json", result)
        return result

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        text = text.strip()
        if not text:
            return None
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        # Fallback: try to find first JSON object.
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
        return None

    def _build_user_prompt(self, iteration: int) -> str:
        last = self.last_report or {}
        counts = last.get("counts", {})
        recent = self.history[-4:]
        payload = {
            "project_context": {
                "repo": str(ROOT),
                "example": self.example,
                "board_size_mm": {"width": self.board_w, "height": self.board_h},
                "board_origin_model": {
                    "left": self.board_left,
                    "top": self.board_top,
                    "right": self.board_right,
                    "bottom": self.board_bottom,
                },
                "loop_goal": (
                    "Iterate placement -> snapshot -> check until layout is ready. "
                    "Then call finish_layout."
                ),
                "placement_quality_requirements": [
                    "Professional and sensible placement, not arbitrary valid coordinates.",
                    "Keep related functional blocks compact.",
                    "Preserve clear routing corridors.",
                    "Use one placement edit at a time.",
                    "After each edit, run test_layout for a fresh snapshot.",
                ],
            },
            "tool_contract": {
                "tools": [
                    {
                        "name": "apply_placement_patch",
                        "args_schema": {
                            "edits": [
                                {
                                    "ref": "R1",
                                    "x": 140.0,
                                    "y": 90.0,
                                    "rotation": 0.0,
                                    "dx": "optional",
                                    "dy": "optional",
                                }
                            ],
                            "policy": "Use exactly one edit item per call.",
                        },
                    },
                    {
                        "name": "test_layout",
                        "args_schema": {"reason": "short string"},
                    },
                    {
                        "name": "finish_layout",
                        "args_schema": {"summary": "short completion summary"},
                    },
                ]
            },
            "iteration": iteration,
            "max_iterations": self.max_iters,
            "last_test_counts": counts,
            "placement_preview": self._placement_summary(),
            "recent_tool_history": recent,
            "required_output_format": {"tool": "<tool_name>", "args": {"...": "..."}},
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    def _run_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if self._must_test_after_edit and tool_name != "test_layout":
            return self.tool_test_layout({"reason": "forced-test-after-placement-edit"})
        if tool_name == "apply_placement_patch":
            return self.tool_apply_placement_patch(args)
        if tool_name == "test_layout":
            return self.tool_test_layout(args)
        if tool_name == "finish_layout":
            return self.tool_finish_layout(args)
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}

    def run(self) -> dict[str, Any]:
        # Seed with an initial test to provide immediate visual/metric feedback.
        seed = self.tool_test_layout({"reason": "initial baseline"})
        self.history.append({"iteration": 0, "tool": "test_layout", "args": {"reason": "initial baseline"}, "result": seed})

        for i in range(1, self.max_iters + 1):
            prompt = self._build_user_prompt(i)
            image_path = None
            snap = (self.last_report or {}).get("snapshot", {})
            snap_rel = snap.get("snapshot_path")
            if isinstance(snap_rel, str):
                candidate = ROOT / snap_rel
                if candidate.exists():
                    image_path = candidate

            model_text = self.client.generate(prompt, image_path=image_path)
            action = self._extract_json(model_text) or {"tool": "test_layout", "args": {"reason": "fallback-invalid-json"}}
            tool_name = action.get("tool")
            args = action.get("args", {})
            if not isinstance(tool_name, str):
                tool_name = "test_layout"
            if not isinstance(args, dict):
                args = {"reason": "fallback-invalid-args"}
                tool_name = "test_layout"

            result = self._run_tool(tool_name, args)
            entry = {
                "iteration": i,
                "model_output_raw": model_text,
                "tool": tool_name,
                "args": args,
                "result": result,
            }
            self.history.append(entry)
            self._write_json("history.json", self.history)

            if tool_name == "finish_layout" and result.get("done") is True:
                break

            # Small pacing to reduce API burst and produce stable traces.
            time.sleep(0.2)

        final = {
            "ok": self.finished,
            "finished": self.finished,
            "finish_summary": self.finish_summary,
            "iterations_used": len(self.history) - 1,
            "max_iterations": self.max_iters,
            "model_policy": MODEL_POLICY_BANNER,
            "model_used": self.model,
            "run_dir": str(self.run_dir.relative_to(ROOT)),
            "run_dir_abs": str(self.run_dir.resolve()),
            "png_abs_paths": sorted(str(p.resolve()) for p in (self.run_dir / "artifacts").glob("*.png")),
            "last_report": self.last_report,
            "next_command": f"./abd forward --example {self.example}",
        }
        self._write_json("final_result.json", final)
        return final


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Experimental Gemini internal layout loop. "
            "HARD-LOCKED to Gemini major version >= 3 only."
        )
    )
    parser.add_argument("--example", default="led", help="Board example name (default: led)")
    parser.add_argument(
        "--model",
        default=DEFAULT_GEMINI_MODEL,
        help="Gemini model name (must be major version >= 3)",
    )
    parser.add_argument("--max-iters", type=int, default=8, help="Maximum model iterations")
    parser.add_argument("--clearance-mm", type=float, default=0.2, help="Overlap clearance")
    parser.add_argument("--snap-mm", type=float, default=DEFAULT_SNAP_MM, help="Placement snap grid")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    loop = LayoutLoop(
        example=args.example,
        model=args.model,
        max_iters=args.max_iters,
        clearance_mm=args.clearance_mm,
        snap_mm=args.snap_mm,
    )
    final = loop.run()
    print(json.dumps(final, indent=2, sort_keys=True))
    return 0 if final.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
