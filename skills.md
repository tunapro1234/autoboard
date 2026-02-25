# ABD Skill: LLM-Driven PCB Workflow

This skill defines how an LLM should run PCB work through `abd` using two loops: schema and layout.
Goal: let the LLM make design decisions, and let `abd` enforce deterministic checks and stage control.

## HARD MODEL POLICY (NON-NEGOTIABLE)

1. ONLY Gemini models with major version `>= 3` are allowed for the layout loop.
2. Gemini `2.x` and below are disallowed under any condition.
3. If the model is not a Gemini 3+ variant (for example `gemini-3-pro-preview` or `gemini-3.1-pro-preview`), stop and fix configuration first.

## 1) Trigger (When to use)

Use this skill when:

1. You are iterating on PCB schematic/layout design.
2. You need stage-based validation and progress tracking.
3. You want rerun protection for unchanged failing boards.

Do not use this skill when:

1. You are only discussing circuit theory.
2. You are doing unrelated file formatting/refactors.
3. You intentionally want ad-hoc execution outside `abd`.

## 2) Scope and Responsibilities

LLM responsibilities:

1. Plan the board (power, IO, component choices, topology).
2. Build/fix schematic and placement.
3. Apply fixes based on failed ABD stages.

ABD responsibilities:

1. Persist stage state (`.autoboard/<example>.json`).
2. Run deterministic checks (net/pin/footprint and placement checks).
3. Run the pipeline chain (export -> route -> drc -> pack).
4. Block no-change reruns with `board_hash`.

## 3) Stage Model

Schema loop:

1. `schema_build`
2. `schema_check`

Layout loop:

1. `layout_place`
2. `layout_export`
3. `layout_route`
4. `layout_check`
5. `layout_pack`

Status values:

- `pending`
- `pass`
- `fail`

## 4) ABD Command Contract

Primary commands:

1. `./abd help`
2. `./abd status --example <name> [--pretty|--short]`
3. `./abd check --example <name>`
4. `./abd route --example <name>`
5. `./abd forward --example <name>`
6. `./abd pull-forward --example <name>`
7. `./abd rewind --example <name>`
8. `./abd reset --example <name>`

Behavior notes:

1. `route` = `check` + layout pipeline.
2. `forward` and `pull-forward` are route aliases for orchestrator-style flows.
3. `rewind` resets state and reruns from the start.
4. `reset` only clears state; it does not run routing.
5. `--force` bypasses hash-based rerun protection.

## 5) Mandatory LLM Runbook

Use this sequence for every iteration:

1. `./abd status --example <board> --short`
2. `./abd check --example <board>`
3. If checks pass: `./abd forward --example <board>`
4. Read the failed stage and patch files accordingly
5. Run `./abd forward --example <board>` again

Rules:

1. Do not keep editing before reading the latest ABD failure output.
2. Do not call `forward/route` repeatedly without actual board changes.

## 6) Failure-to-Action Map

1. `schema_check` fail:
   - Fix net naming, pin mapping, footprint mapping.
2. `layout_place` fail:
   - Fix overlaps, out-of-bound placement, spacing.
3. `layout_export` fail:
   - Fix footprint/export pipeline assumptions.
4. `layout_route` fail:
   - Simplify placement, improve routability, retry.
5. `layout_check` fail:
   - Fix DRC issues (clearance/unconnected/electrical).
6. `layout_pack` fail:
   - Fix gerber/render output generation.

## 7) Guardrails

1. Same `board_hash` + same failure -> ABD returns cached failure.
2. If `reused_failure: true`, change board files before retrying.
3. Stop at the failing stage; do not skip ahead manually.
4. Prefer `abd` over direct `pipeline.py` during normal operation.

## 8) Definition of Done

A board is done only if:

1. Schema loop status is `pass`.
2. Layout loop status is `pass`.
3. Last command output has `ok: true`.
4. Expected artifacts exist under `output/<board>/`.

## 9) Minimal End-to-End Example

1. `./abd status --example led --short`
2. `./abd check --example led`
3. `./abd forward --example led`
4. If failed, patch files and rerun `./abd forward --example led`
5. Final check: `./abd status --example led --pretty`

## 10) Why This Skill Design

1. Clear trigger: when to use vs not use.
2. Narrow scope: PCB execution orchestration only.
3. Measurable outcomes: stage statuses and deterministic pass/fail.
4. Reusable flow: same runbook for all board examples.
