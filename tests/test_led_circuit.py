"""Regression tests for the simple LED reference circuit."""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import Circuit, circuit_to_spice, export_schematic, run_simulation


def _build_led_circuit() -> Circuit:
    c = Circuit("Simple LED")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "LED_A", "330")
    c.add_led("LED_A", "GND")
    return c


def test_led_circuit_simulation():
    if shutil.which("ngspice") is None:
        pytest.skip("ngspice is not installed")

    c = _build_led_circuit()
    spice = circuit_to_spice(c)
    assert "D1 2 0 LED" in spice
    assert ".MODEL LED" in spice

    result = run_simulation(c)
    assert result.success, f"Simulation failed: {result.errors}"

    led_v = result.node_voltages.get("LED_A", result.node_voltages.get("V(2)"))
    assert led_v is not None, f"No LED node voltage parsed: {result.node_voltages}"
    assert 1.5 < led_v < 2.5

    # ngspice reports source branch current as v1#branch; parser should map it.
    assert "V1" in result.branch_currents
    assert result.branch_currents["V1"] < 0


def test_led_circuit_kicad_export_loads(tmp_path):
    if shutil.which("kicad-cli") is None:
        pytest.skip("kicad-cli is not installed")

    c = _build_led_circuit()
    sch_path = tmp_path / "led_circuit.kicad_sch"
    export_schematic(c, str(sch_path))

    proc = subprocess.run(
        [
            "kicad-cli", "sch", "erc", "--format", "json",
            "-o", str(tmp_path / "erc.json"),
            str(sch_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    out = (proc.stdout or "") + (proc.stderr or "")
    assert "Failed to load schematic" not in out
    assert proc.returncode == 0, out
