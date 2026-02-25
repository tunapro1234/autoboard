"""
Circuit definition module.
Provides a simple API for defining circuits that can be:
1. Simulated with ngspice (via PySpice)
2. Exported to KiCad schematic
3. Validated with ERC/DRC
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Component:
    ref: str  # e.g. "R1", "C1", "U1"
    kind: str  # e.g. "resistor", "capacitor", "led", "voltage_source"
    value: str  # e.g. "330", "100n", "5"
    unit: str = ""  # e.g. "ohm", "F", "V"
    footprint: str = ""
    spice_model: str = ""
    pins: dict = field(default_factory=dict)  # pin_name -> net_name


@dataclass
class Net:
    name: str
    components: list[tuple[str, str]] = field(default_factory=list)  # [(ref, pin_name), ...]


class Circuit:
    """A circuit that can be simulated and exported."""

    def __init__(self, name: str):
        self.name = name
        self.components: dict[str, Component] = {}
        self.nets: dict[str, Net] = {}
        self._ref_counters: dict[str, int] = {}

    def _next_ref(self, prefix: str) -> str:
        count = self._ref_counters.get(prefix, 0) + 1
        self._ref_counters[prefix] = count
        return f"{prefix}{count}"

    def add_resistor(self, net1: str, net2: str, value: str, ref: str = "") -> str:
        ref = ref or self._next_ref("R")
        comp = Component(ref=ref, kind="resistor", value=value, unit="ohm",
                         pins={"1": net1, "2": net2})
        self.components[ref] = comp
        self._connect(ref, "1", net1)
        self._connect(ref, "2", net2)
        return ref

    def add_capacitor(self, net1: str, net2: str, value: str, ref: str = "") -> str:
        ref = ref or self._next_ref("C")
        comp = Component(ref=ref, kind="capacitor", value=value, unit="F",
                         pins={"1": net1, "2": net2})
        self.components[ref] = comp
        self._connect(ref, "1", net1)
        self._connect(ref, "2", net2)
        return ref

    def add_voltage_source(self, net_pos: str, net_neg: str, voltage: str, ref: str = "") -> str:
        ref = ref or self._next_ref("V")
        comp = Component(ref=ref, kind="voltage_source", value=voltage, unit="V",
                         pins={"+": net_pos, "-": net_neg})
        self.components[ref] = comp
        self._connect(ref, "+", net_pos)
        self._connect(ref, "-", net_neg)
        return ref

    def add_led(self, anode: str, cathode: str, ref: str = "", model: str = "LED") -> str:
        ref = ref or self._next_ref("D")
        comp = Component(ref=ref, kind="led", value="LED", spice_model=model,
                         pins={"A": anode, "K": cathode})
        self.components[ref] = comp
        self._connect(ref, "A", anode)
        self._connect(ref, "K", cathode)
        return ref

    def add_diode(self, anode: str, cathode: str, ref: str = "", model: str = "1N4148") -> str:
        ref = ref or self._next_ref("D")
        comp = Component(ref=ref, kind="diode", value=model, spice_model=model,
                         pins={"A": anode, "K": cathode})
        self.components[ref] = comp
        self._connect(ref, "A", anode)
        self._connect(ref, "K", cathode)
        return ref

    def _connect(self, ref: str, pin: str, net_name: str):
        if net_name not in self.nets:
            self.nets[net_name] = Net(name=net_name)
        self.nets[net_name].components.append((ref, pin))

    def summary(self) -> str:
        lines = [f"Circuit: {self.name}"]
        lines.append(f"  Components: {len(self.components)}")
        for ref, comp in self.components.items():
            lines.append(f"    {ref}: {comp.kind} = {comp.value}{comp.unit}")
        lines.append(f"  Nets: {len(self.nets)}")
        for name, net in self.nets.items():
            conns = ", ".join(f"{r}.{p}" for r, p in net.components)
            lines.append(f"    {name}: {conns}")
        return "\n".join(lines)
