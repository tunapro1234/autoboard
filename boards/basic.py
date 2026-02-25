"""Basic reference board/circuit definitions."""

from src.circuit import Circuit


def build_led() -> Circuit:
    """Simple LED circuit: 5V -> 330R -> LED -> GND."""
    c = Circuit("LED Circuit")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "LED_A", "330")
    c.add_led("LED_A", "GND")
    return c


def build_rc_filter() -> Circuit:
    """RC low-pass filter: 1k + 100nF."""
    c = Circuit("RC Low-Pass Filter")
    c.add_voltage_source("VIN", "GND", "5")
    c.add_resistor("VIN", "VOUT", "1k")
    c.add_capacitor("VOUT", "GND", "100n")
    return c


def build_voltage_divider() -> Circuit:
    """Voltage divider: 5V -> 10k -> 10k -> GND."""
    c = Circuit("Voltage Divider")
    c.add_voltage_source("VCC", "GND", "5")
    c.add_resistor("VCC", "VMID", "10k")
    c.add_resistor("VMID", "GND", "10k")
    return c
