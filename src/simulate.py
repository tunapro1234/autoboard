"""
SPICE simulation backend using PySpice + ngspice.
Takes a Circuit and runs electrical simulations.
"""

import subprocess
import tempfile
import os
import re
from pathlib import Path
from dataclasses import dataclass

from .circuit import Circuit, Component


@dataclass
class SimResult:
    """Results from a SPICE simulation."""
    node_voltages: dict[str, float]  # net_name -> voltage
    branch_currents: dict[str, float]  # component_ref -> current (A)
    raw_output: str
    success: bool
    errors: list[str]


def circuit_to_spice(circuit: Circuit) -> str:
    """Convert our Circuit to a SPICE netlist string."""
    lines = [f"* {circuit.name}", ""]

    # Map net names to SPICE node numbers
    # "GND" or "0" always maps to 0
    net_map: dict[str, str] = {}
    node_counter = 1
    for net_name in circuit.nets:
        if net_name.upper() in ("GND", "0", "VSS"):
            net_map[net_name] = "0"
        else:
            net_map[net_name] = str(node_counter)
            node_counter += 1

    # LED / diode model
    needs_led_model = False
    needs_diode_model = False

    for ref, comp in circuit.components.items():
        if comp.kind == "resistor":
            n1 = net_map[comp.pins["1"]]
            n2 = net_map[comp.pins["2"]]
            lines.append(f"{ref} {n1} {n2} {comp.value}")

        elif comp.kind == "capacitor":
            n1 = net_map[comp.pins["1"]]
            n2 = net_map[comp.pins["2"]]
            lines.append(f"{ref} {n1} {n2} {comp.value}")

        elif comp.kind == "voltage_source":
            np = net_map[comp.pins["+"]]
            nn = net_map[comp.pins["-"]]
            lines.append(f"{ref} {np} {nn} DC {comp.value}")

        elif comp.kind == "led":
            na = net_map[comp.pins["A"]]
            nk = net_map[comp.pins["K"]]
            lines.append(f"{ref} {na} {nk} LED")
            needs_led_model = True

        elif comp.kind == "diode":
            na = net_map[comp.pins["A"]]
            nk = net_map[comp.pins["K"]]
            model = comp.spice_model or "D1N4148"
            lines.append(f"{ref} {na} {nk} {model}")
            needs_diode_model = True

    lines.append("")

    if needs_led_model:
        # Simple red LED model: Vf ~2V, Is=1e-20
        lines.append(".MODEL LED D(IS=1E-20 N=1.8 RS=5 BV=5 IBV=100U)")

    if needs_diode_model:
        lines.append(".MODEL D1N4148 D(IS=2.52E-9 RS=0.568 N=1.752 BV=100 IBV=100U)")

    lines.append("")

    # Operating point analysis
    lines.append(".OP")
    lines.append(".END")

    return "\n".join(lines)


def run_simulation(circuit: Circuit) -> SimResult:
    """Run ngspice operating point simulation and return results."""
    spice_netlist = circuit_to_spice(circuit)

    with tempfile.TemporaryDirectory() as tmpdir:
        netlist_path = os.path.join(tmpdir, "circuit.cir")
        output_path = os.path.join(tmpdir, "output.txt")

        with open(netlist_path, "w") as f:
            f.write(spice_netlist)

        # Run ngspice in batch mode
        cmd = [
            "ngspice", "-b",  # batch mode
            "-o", output_path,
            netlist_path
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )

        raw_output = result.stdout + "\n" + result.stderr

        # Also read the output file
        if os.path.exists(output_path):
            with open(output_path) as f:
                raw_output += "\n" + f.read()

        # Parse node voltages from ngspice output
        node_voltages = {}
        branch_currents = {}
        errors = []

        # Parse "Node  Voltage" section
        in_voltage_section = False
        for line in raw_output.split("\n"):
            line = line.strip()

            if "Node" in line and "Voltage" in line:
                in_voltage_section = True
                continue

            if in_voltage_section:
                if not line or line.startswith("-"):
                    if node_voltages:  # we already got some, done
                        in_voltage_section = False
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    try:
                        node_name = parts[0]
                        voltage = float(parts[1])
                        node_voltages[node_name] = voltage
                    except (ValueError, IndexError):
                        pass

            # Parse branch currents
            branch_match = re.match(r".*@(\w+)\[(\w+)\]\s*=\s*([-\d.eE+]+)", line)
            if branch_match:
                ref = branch_match.group(1)
                branch_currents[ref] = float(branch_match.group(3))

            if "error" in line.lower() and "0 errors" not in line.lower():
                errors.append(line)

        success = result.returncode == 0 and len(errors) == 0

        return SimResult(
            node_voltages=node_voltages,
            branch_currents=branch_currents,
            raw_output=raw_output,
            success=success,
            errors=errors,
        )
