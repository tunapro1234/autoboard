#!/usr/bin/env python3
"""
PCB Pipeline: circuit example -> simulate -> route -> render

Usage:
    python pipeline.py
    python pipeline.py --example rc
    python pipeline.py --example esp32s3
"""

import argparse
import os

from boards import get_example, list_example_names
from src.circuit import Circuit
from src.export_pcb import full_pipeline
from src.simulate import circuit_to_spice, run_simulation


def print_header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def run(circuit: Circuit, output_dir: str, example_name: str = "led"):
    print_header("1. CIRCUIT")
    print(circuit.summary())

    print_header("2. SPICE NETLIST")
    print(circuit_to_spice(circuit))

    print_header("3. SIMULATION")
    sim = run_simulation(circuit)
    print(f"  Status: {'PASS' if sim.success else 'FAIL'}")
    if sim.node_voltages:
        for node, voltage in sim.node_voltages.items():
            print(f"  {node} = {voltage:.4f} V")
    if sim.errors:
        print(f"  Errors: {sim.errors}")
        print("\n  Raw output (last 500 chars):")
        print(f"  {sim.raw_output[-500:]}")

    print_header("4. PCB PIPELINE (export -> route -> render)")
    spec = get_example(example_name)
    board_w, board_h = spec.board_size
    placement = spec.placement()

    result = full_pipeline(
        circuit,
        output_dir,
        board_width=board_w,
        board_height=board_h,
        placement=placement,
    )

    for step_name, step_data in result["steps"].items():
        if isinstance(step_data, dict) and "ok" in step_data:
            status = "OK" if step_data["ok"] else "FAIL"
            extra = ""
            if "path" in step_data:
                extra = f" -> {step_data['path']}"
            if "trace_count" in step_data:
                extra = f" ({step_data['trace_count']} traces)"
            if "output" in step_data:
                extra += f"\n    {step_data['output']}"
            if "error" in step_data:
                extra = f" ({step_data['error']})"
            print(f"  [{status}] {step_name}{extra}")
        elif isinstance(step_data, dict):
            for sub, sub_data in step_data.items():
                status = "OK" if sub_data.get("ok") else "FAIL"
                path = sub_data.get("path", "")
                print(f"  [{status}] render_{sub} -> {path}")

    print_header("5. RESULT")
    if result["success"]:
        print("  PIPELINE SUCCESS")
        print(f"\n  Output files in: {output_dir}/")
    else:
        print("  PIPELINE HAD ISSUES (check steps above)")
        if os.path.exists(output_dir):
            print(f"\n  Files in: {output_dir}/")

    if os.path.exists(output_dir):
        for name in sorted(os.listdir(output_dir)):
            fpath = os.path.join(output_dir, name)
            if os.path.isfile(fpath):
                size = os.path.getsize(fpath)
                print(f"    {name:30s} {size:>8,} bytes")


def main():
    examples = list_example_names()

    parser = argparse.ArgumentParser(description="PCB LLM Pipeline")
    parser.add_argument("--example", choices=examples, default="led",
                        help="Example circuit to run")
    parser.add_argument("--output", default=None, help="Output directory")
    args = parser.parse_args()

    spec = get_example(args.example)
    circuit = spec.builder()
    output_dir = args.output or os.path.join("output", args.example)

    run(circuit, output_dir, example_name=args.example)


if __name__ == "__main__":
    main()
