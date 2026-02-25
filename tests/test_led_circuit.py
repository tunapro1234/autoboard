"""
MVP Test: Simple LED circuit.

Circuit: 5V -> 330Ω resistor -> LED -> GND

Expected:
- LED forward voltage: ~1.8-2.2V
- Current through LED: ~9-10mA
- Voltage across resistor: ~2.8-3.2V
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import Circuit, run_simulation, circuit_to_spice, export_schematic


def test_led_circuit():
    # 1. Define circuit
    c = Circuit("Simple LED")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "LED_A", "330")
    c.add_led("LED_A", "GND")

    print("=== Circuit Summary ===")
    print(c.summary())

    # 2. Generate SPICE netlist
    spice = circuit_to_spice(c)
    print("\n=== SPICE Netlist ===")
    print(spice)

    # 3. Run simulation
    print("\n=== Running Simulation ===")
    result = run_simulation(c)
    print(f"Success: {result.success}")
    print(f"Node voltages: {result.node_voltages}")
    print(f"Branch currents: {result.branch_currents}")

    if result.errors:
        print(f"Errors: {result.errors}")

    # 4. Validate results
    if result.node_voltages:
        print("\n=== Validation ===")
        # Find LED anode voltage (should be ~2V for LED forward voltage)
        for node, voltage in result.node_voltages.items():
            print(f"  {node} = {voltage:.4f}V")

    # 5. Export to KiCad schematic
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    sch_path = os.path.join(output_dir, "led_circuit.kicad_sch")
    export_schematic(c, sch_path)
    print(f"\n=== KiCad Schematic exported to: {sch_path} ===")

    # 6. Run ERC if kicad-cli available
    erc_result = os.popen(f"kicad-cli sch erc --format json '{sch_path}' 2>&1").read()
    print(f"\n=== ERC Result ===\n{erc_result[:500]}")

    print("\n=== DONE ===")


if __name__ == "__main__":
    test_led_circuit()
