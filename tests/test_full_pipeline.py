"""
Full pipeline test: Circuit → Simulate → PCB → Freerouting
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.circuit import Circuit
from src.simulate import run_simulation, circuit_to_spice
from src.export_pcb import export_pcb, run_freerouting

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "output")
os.makedirs(OUTPUT, exist_ok=True)


def main():
    # 1. Define circuit
    print("=" * 50)
    print("STEP 1: Define Circuit")
    print("=" * 50)
    c = Circuit("LED Blinker")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "LED_A", "330")
    c.add_led("LED_A", "GND")
    print(c.summary())

    # 2. Simulate
    print("\n" + "=" * 50)
    print("STEP 2: SPICE Simulation")
    print("=" * 50)
    spice = circuit_to_spice(c)
    print(spice)

    result = run_simulation(c)
    print(f"\nSuccess: {result.success}")
    print(f"Voltages: {result.node_voltages}")

    if result.node_voltages:
        vcc = result.node_voltages.get("V(1)", 0)
        vled = result.node_voltages.get("V(2)", 0)
        i_led = (vcc - vled) / 330
        print(f"LED current: {i_led * 1000:.2f} mA")
        print(f"LED voltage: {vled:.3f} V")

        assert 1.5 < vled < 2.5, f"LED voltage {vled}V out of range"
        assert 5 < i_led * 1000 < 15, f"LED current {i_led*1000}mA out of range"
        print("✓ Simulation validates OK")
    else:
        print("WARNING: No voltages parsed, check raw output")
        print(result.raw_output[-500:])

    # 3. Export PCB
    print("\n" + "=" * 50)
    print("STEP 3: Export PCB")
    print("=" * 50)
    pcb_path = os.path.join(OUTPUT, "led_circuit.kicad_pcb")
    export_pcb(c, pcb_path)
    print(f"PCB exported: {pcb_path}")
    print(f"File size: {os.path.getsize(pcb_path)} bytes")

    # 4. Run DRC
    print("\n" + "=" * 50)
    print("STEP 4: DRC Check")
    print("=" * 50)
    drc_out = os.popen(f'kicad-cli pcb drc --format json "{pcb_path}" 2>&1').read()
    print(drc_out[:500] if drc_out else "DRC: no output")

    # 5. Freerouting
    print("\n" + "=" * 50)
    print("STEP 5: Freerouting Auto-Route")
    print("=" * 50)
    fr_result = run_freerouting(pcb_path, OUTPUT)
    print(f"Success: {fr_result['success']}")
    if fr_result["errors"]:
        print(f"Errors: {fr_result['errors']}")
    if fr_result.get("freerouting_stdout"):
        print(f"Stdout (last 300): {fr_result['freerouting_stdout'][-300:]}")
    if fr_result.get("freerouting_stderr"):
        print(f"Stderr (last 300): {fr_result['freerouting_stderr'][-300:]}")

    for f in ["circuit.dsn", "circuit.ses"]:
        fp = os.path.join(OUTPUT, f)
        if os.path.exists(fp):
            print(f"  {f}: {os.path.getsize(fp)} bytes")

    print("\n" + "=" * 50)
    print("PIPELINE COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    main()
