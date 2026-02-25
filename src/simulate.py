"""
SPICE simulation backend using PySpice + ngspice.
Takes a Circuit and runs electrical simulations.
"""

import subprocess
import tempfile
import os
import re
from dataclasses import dataclass

from .circuit import Circuit


@dataclass
class SimResult:
    """Results from a SPICE simulation."""
    node_voltages: dict[str, float]  # net_name -> voltage
    branch_currents: dict[str, float]  # component_ref -> current (A)
    raw_output: str
    success: bool
    errors: list[str]


# Component kinds that are simulatable in SPICE
SPICE_KINDS = {"resistor", "capacitor", "voltage_source", "led", "diode", "ams1117"}

# Kinds to skip silently (connectors, modules, switches, etc.)
SKIP_KINDS = {"esp32s3", "usblc6", "usb_c", "switch", "pin_header_20"}

GROUND_ALIASES = {"GND", "0", "VSS"}

MODEL_ALIASES = {
    "1N4148": "D1N4148",
    "1N5819": "D1N5819",
}

MODEL_LIBRARY = {
    # Simple red LED model: Vf around 2V.
    "LED": "D(IS=1E-20 N=1.8 RS=5 BV=5 IBV=100U)",
    # Common silicon small-signal diode.
    "D1N4148": "D(IS=2.52E-9 RS=0.568 N=1.752 BV=100 IBV=100U)",
    # Schottky for reverse protection / low Vf.
    "D1N5819": "D(IS=3.16E-5 RS=0.042 N=1.094 BV=40 IBV=1M CJO=110P VJ=0.34 M=0.35 TT=5N)",
}


def _build_spice_net_map(circuit: Circuit) -> dict[str, str]:
    """Map logical net names to SPICE node names."""
    net_map: dict[str, str] = {}
    node_counter = 1
    for net_name in circuit.nets:
        if net_name.upper() in GROUND_ALIASES:
            net_map[net_name] = "0"
        else:
            net_map[net_name] = str(node_counter)
            node_counter += 1
    return net_map


def _normalize_model_name(name: str) -> str:
    model = (name or "").strip()
    if not model:
        return ""
    return MODEL_ALIASES.get(model.upper(), model)


def _spice_ref(ref: str, kind: str) -> str:
    """Ensure SPICE element name starts with the correct prefix for its kind.

    SPICE requires: R=resistor, C=capacitor, V=voltage, D=diode/LED, X=subcircuit, etc.
    """
    SPICE_PREFIX = {
        "resistor": "R",
        "capacitor": "C",
        "voltage_source": "V",
        "led": "D",
        "diode": "D",
    }
    required = SPICE_PREFIX.get(kind)
    if required and not ref.upper().startswith(required):
        return f"{required}_{ref}"
    return ref


def circuit_to_spice(circuit: Circuit) -> str:
    """Convert our Circuit to a SPICE netlist string."""
    lines = [f"* {circuit.name}", ""]

    net_map = _build_spice_net_map(circuit)
    model_definitions: dict[str, str] = {}
    needs_ams1117_model = False

    for ref, comp in circuit.components.items():
        sref = _spice_ref(ref, comp.kind)

        if comp.kind == "resistor":
            n1 = net_map[comp.pins["1"]]
            n2 = net_map[comp.pins["2"]]
            lines.append(f"{sref} {n1} {n2} {comp.value}")

        elif comp.kind == "capacitor":
            n1 = net_map[comp.pins["1"]]
            n2 = net_map[comp.pins["2"]]
            lines.append(f"{sref} {n1} {n2} {comp.value}")

        elif comp.kind == "voltage_source":
            np = net_map[comp.pins["+"]]
            nn = net_map[comp.pins["-"]]
            lines.append(f"{sref} {np} {nn} DC {comp.value}")

        elif comp.kind == "led":
            na = net_map[comp.pins["A"]]
            nk = net_map[comp.pins["K"]]
            requested = _normalize_model_name(comp.spice_model or "LED")
            model_name = requested or "LED"
            lines.append(f"{sref} {na} {nk} {model_name}")
            params = MODEL_LIBRARY.get(model_name, MODEL_LIBRARY["LED"])
            model_definitions[model_name] = params

        elif comp.kind == "diode":
            na = net_map[comp.pins["A"]]
            nk = net_map[comp.pins["K"]]
            requested = _normalize_model_name(comp.spice_model or "D1N4148")
            model_name = requested or "D1N4148"
            lines.append(f"{sref} {na} {nk} {model_name}")
            params = MODEL_LIBRARY.get(model_name, MODEL_LIBRARY["D1N4148"])
            model_definitions[model_name] = params

        elif comp.kind == "ams1117":
            # Model AMS1117-3.3 as a subcircuit: VIN, VOUT, GND
            vin = net_map.get(comp.pins.get("VIN", ""), "0")
            vout = net_map.get(comp.pins.get("VOUT", ""), "0")
            gnd = net_map.get(comp.pins.get("GND", ""), "0")
            lines.append(f"X{ref} {vin} {vout} {gnd} AMS1117_33")
            needs_ams1117_model = True

        elif comp.kind in SKIP_KINDS:
            # Non-simulatable components — skip
            lines.append(f"* {ref}: {comp.kind} (not simulated)")
            continue

        else:
            # Unknown kind — skip with comment
            lines.append(f"* {ref}: {comp.kind} (not simulated)")

    lines.append("")

    for model_name, params in sorted(model_definitions.items()):
        lines.append(f".MODEL {model_name} {params}")

    if needs_ams1117_model:
        # AMS1117-3.3 as behavioral subcircuit
        # Simple model: voltage-controlled source with dropout behavior
        lines.append("* AMS1117-3.3 LDO model (behavioral)")
        lines.append(".SUBCKT AMS1117_33 VIN VOUT GND")
        lines.append("* Internal resistance and regulation")
        lines.append("Rint VIN VIN_INT 0.5")
        lines.append("* Output clamp at 3.3V using voltage-controlled source")
        lines.append("* If VIN_INT - GND > 4.3V (3.3 + 1V dropout), output is 3.3V")
        lines.append("* Otherwise output follows input minus dropout")
        lines.append("Breg VOUT GND V=MIN(V(VIN_INT,GND)-1.0, 3.3)")
        lines.append("* Quiescent current ~5mA")
        lines.append("Rq VIN_INT GND 1k")
        lines.append(".ENDS AMS1117_33")

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

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
        except FileNotFoundError:
            return SimResult(
                node_voltages={},
                branch_currents={},
                raw_output="",
                success=False,
                errors=["ngspice not found in PATH"],
            )
        except subprocess.TimeoutExpired:
            return SimResult(
                node_voltages={},
                branch_currents={},
                raw_output="",
                success=False,
                errors=["ngspice timed out after 30s"],
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
            if not line:
                continue

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
                        continue

            # Parse branch currents
            branch_match = re.match(r"([A-Za-z][\w]*)#branch\s+([-\d.eE+]+)", line)
            if branch_match:
                ref = branch_match.group(1).upper()
                branch_currents[ref] = float(branch_match.group(2))
            else:
                # Fallback for other ngspice formats: @r1[i] = ...
                alt_match = re.match(r".*@([A-Za-z][\w]*)\[[^\]]+\]\s*=\s*([-\d.eE+]+)", line)
                if alt_match:
                    ref = alt_match.group(1).upper()
                    branch_currents[ref] = float(alt_match.group(2))

            if "error" in line.lower() and "0 errors" not in line.lower():
                errors.append(line)

        # Add human-friendly net aliases alongside V(<node>) keys.
        reverse_net_map = {node: net for net, node in _build_spice_net_map(circuit).items()}
        for key, value in list(node_voltages.items()):
            match = re.match(r"V\(([^)]+)\)", key, flags=re.IGNORECASE)
            if not match:
                continue
            node = match.group(1)
            if node in reverse_net_map:
                node_voltages.setdefault(reverse_net_map[node], value)

        success = result.returncode == 0 and len(errors) == 0

        return SimResult(
            node_voltages=node_voltages,
            branch_currents=branch_currents,
            raw_output=raw_output,
            success=success,
            errors=errors,
        )
