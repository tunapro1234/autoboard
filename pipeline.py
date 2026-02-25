#!/usr/bin/env python3
"""
PCB Pipeline: Natural language → Simulate → Route → Render

Usage:
    python pipeline.py                  # run default LED example
    python pipeline.py --example rc     # run RC filter example
"""

import argparse
import json
import os
import sys

from src.circuit import Circuit
from src.simulate import run_simulation, circuit_to_spice
from src.export_pcb import full_pipeline


def example_led() -> Circuit:
    """Simple LED circuit: 5V → 330Ω → LED → GND"""
    c = Circuit("LED Circuit")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "LED_A", "330")
    c.add_led("LED_A", "GND")
    return c


def example_rc_filter() -> Circuit:
    """RC low-pass filter: 1kΩ + 100nF, cutoff ~1.6kHz"""
    c = Circuit("RC Low-Pass Filter")
    c.add_voltage_source("VIN", "GND", "5")
    c.add_resistor("VIN", "VOUT", "1k")
    c.add_capacitor("VOUT", "GND", "100n")
    return c


def example_voltage_divider() -> Circuit:
    """Voltage divider: 5V → 10kΩ → 10kΩ → GND, Vout = 2.5V"""
    c = Circuit("Voltage Divider")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "VMID", "10k")
    c.add_resistor("VMID", "GND", "10k")
    return c


EXAMPLES = {
    "led": example_led,
    "rc": example_rc_filter,
    "divider": example_voltage_divider,
}


def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def run(circuit: Circuit, output_dir: str):
    # --- Simulation ---
    print_header("1. CIRCUIT")
    print(circuit.summary())

    print_header("2. SPICE NETLIST")
    spice = circuit_to_spice(circuit)
    print(spice)

    print_header("3. SIMULATION")
    sim = run_simulation(circuit)
    print(f"  Status: {'PASS' if sim.success else 'FAIL'}")
    if sim.node_voltages:
        for node, v in sim.node_voltages.items():
            print(f"  {node} = {v:.4f} V")
    if sim.errors:
        print(f"  Errors: {sim.errors}")
        print(f"\n  Raw output (last 500 chars):")
        print(f"  {sim.raw_output[-500:]}")

    # --- PCB Pipeline ---
    print_header("4. PCB PIPELINE (export → route → render)")
    result = full_pipeline(circuit, output_dir)

    for step_name, step_data in result["steps"].items():
        if isinstance(step_data, dict) and "ok" in step_data:
            status = "OK" if step_data["ok"] else "FAIL"
            extra = ""
            if "path" in step_data:
                extra = f" → {step_data['path']}"
            if "trace_count" in step_data:
                extra = f" ({step_data['trace_count']} traces)"
            if "output" in step_data:
                extra += f"\n    {step_data['output']}"
            if "error" in step_data:
                extra = f" ({step_data['error']})"
            print(f"  [{status}] {step_name}{extra}")
        elif isinstance(step_data, dict):
            # render sub-dict
            for sub, sub_data in step_data.items():
                status = "OK" if sub_data.get("ok") else "FAIL"
                path = sub_data.get("path", "")
                print(f"  [{status}] render_{sub} → {path}")

    print_header("5. RESULT")
    if result["success"]:
        print("  PIPELINE SUCCESS")
        print(f"\n  Output files in: {output_dir}/")
        for f in sorted(os.listdir(output_dir)):
            size = os.path.getsize(os.path.join(output_dir, f))
            print(f"    {f:30s} {size:>8,} bytes")
    else:
        print("  PIPELINE HAD ISSUES (check steps above)")
        # Still list files
        if os.path.exists(output_dir):
            print(f"\n  Files in: {output_dir}/")
            for f in sorted(os.listdir(output_dir)):
                size = os.path.getsize(os.path.join(output_dir, f))
                print(f"    {f:30s} {size:>8,} bytes")


def main():
    parser = argparse.ArgumentParser(description="PCB LLM Pipeline")
    parser.add_argument("--example", choices=list(EXAMPLES.keys()),
                        default="led", help="Example circuit to run")
    parser.add_argument("--output", default=None, help="Output directory")
    args = parser.parse_args()

    circuit = EXAMPLES[args.example]()
    output_dir = args.output or os.path.join("output", args.example)

    run(circuit, output_dir)


if __name__ == "__main__":
    main()
