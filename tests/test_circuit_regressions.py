"""Targeted regressions for Circuit + SPICE + KiCad exporters."""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import Circuit, circuit_to_spice, export_schematic, run_simulation


def test_duplicate_reference_overwrite_keeps_nets_consistent():
    c = Circuit("dup-ref")
    c.add_resistor("A", "B", "100", ref="R1")
    c.add_resistor("C", "D", "200", ref="R1")

    # Component is replaced and stale net links are removed.
    assert list(c.components.keys()) == ["R1"]
    assert c.components["R1"].pins == {"1": "C", "2": "D"}

    assert "A" not in c.nets
    assert "B" not in c.nets
    assert c.nets["C"].components == [("R1", "1")]
    assert c.nets["D"].components == [("R1", "2")]


def test_diode_default_model_is_defined_and_simulates():
    if shutil.which("ngspice") is None:
        pytest.skip("ngspice is not installed")

    c = Circuit("diode-default")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "N1", "1000")
    c.add_diode("N1", "GND")  # default model should be usable.

    spice = circuit_to_spice(c)
    assert "D1 2 0 D1N4148" in spice
    assert ".MODEL D1N4148" in spice

    result = run_simulation(c)
    assert result.success, f"Simulation failed: {result.errors}"


def test_custom_led_model_name_is_kept_in_netlist():
    c = Circuit("custom-led")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "N1", "330")
    c.add_led("N1", "GND", model="MYLED")

    spice = circuit_to_spice(c)
    assert "D1 2 0 MYLED" in spice
    assert ".MODEL MYLED" in spice


def test_kicad_export_escapes_quoted_values(tmp_path):
    if shutil.which("kicad-cli") is None:
        pytest.skip("kicad-cli is not installed")

    c = Circuit("quoted-value")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "N1", '10"k')
    c.add_led("N1", "GND")

    sch_path = tmp_path / "quoted.kicad_sch"
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
