"""
Circuit definition module.
Provides a simple API for defining circuits that can be:
1. Simulated with ngspice (via PySpice)
2. Exported to KiCad schematic
3. Validated with ERC/DRC
"""

from dataclasses import dataclass, field


@dataclass
class Component:
    ref: str  # e.g. "R1", "C1", "U1"
    kind: str  # e.g. "resistor", "capacitor", "led", "voltage_source"
    value: str  # e.g. "330", "100n", "5"
    unit: str = ""  # e.g. "ohm", "F", "V"
    footprint: str = ""
    spice_model: str = ""
    pins: dict[str, str] = field(default_factory=dict)  # pin_name -> net_name
    simulation_only: bool = False  # If True, skip in PCB/schematic export


@dataclass
class Net:
    name: str
    components: list[tuple[str, str]] = field(default_factory=list)  # [(ref, pin_name), ...]


class Circuit:
    """A circuit that can be simulated and exported."""

    _PREFIX_BY_KIND = {
        "resistor": "R",
        "capacitor": "C",
        "voltage_source": "V",
        "led": "D",
        "diode": "D",
        "switch": "SW",
        "connector": "J",
        "ic": "U",
    }

    def __init__(self, name: str):
        self.name = name
        self.components: dict[str, Component] = {}
        self.nets: dict[str, Net] = {}
        self._ref_counters: dict[str, int] = {}

    def _next_ref(self, prefix: str) -> str:
        count = self._ref_counters.get(prefix, 0) + 1
        self._ref_counters[prefix] = count
        return f"{prefix}{count}"

    def _default_prefix(self, kind: str) -> str:
        return self._PREFIX_BY_KIND.get(kind, "U")

    def _detach_ref(self, ref: str):
        """Remove a component reference from all nets before overwrite."""
        for net_name in list(self.nets.keys()):
            net = self.nets[net_name]
            net.components = [(r, p) for r, p in net.components if r != ref]
            if not net.components:
                del self.nets[net_name]

    def _register(self, comp: Component) -> str:
        if not comp.pins:
            raise ValueError(f"Component {comp.ref} has no pins")

        # Keep nets consistent when replacing a component with same ref.
        if comp.ref in self.components:
            self._detach_ref(comp.ref)

        self.components[comp.ref] = comp
        for pin_name, net_name in comp.pins.items():
            self._connect(comp.ref, pin_name, net_name)
        return comp.ref

    def add_component(self, kind: str, pins: dict[str, str], ref: str = "",
                      value: str = "", unit: str = "", footprint: str = "",
                      spice_model: str = "", ref_prefix: str = "",
                      simulation_only: bool = False) -> str:
        """Add a generic component with arbitrary pins."""
        prefix = ref_prefix or self._default_prefix(kind)
        comp_ref = ref or self._next_ref(prefix)
        comp = Component(
            ref=comp_ref,
            kind=kind,
            value=value or kind,
            unit=unit,
            footprint=footprint,
            spice_model=spice_model,
            pins=dict(pins),
            simulation_only=simulation_only,
        )
        return self._register(comp)

    def add_resistor(self, net1: str, net2: str, value: str, ref: str = "") -> str:
        return self.add_component(
            kind="resistor",
            pins={"1": net1, "2": net2},
            ref=ref,
            value=value,
            unit="ohm",
        )

    def add_capacitor(self, net1: str, net2: str, value: str, ref: str = "") -> str:
        return self.add_component(
            kind="capacitor",
            pins={"1": net1, "2": net2},
            ref=ref,
            value=value,
            unit="F",
        )

    def add_voltage_source(self, net_pos: str, net_neg: str, voltage: str, ref: str = "") -> str:
        return self.add_component(
            kind="voltage_source",
            pins={"+": net_pos, "-": net_neg},
            ref=ref,
            value=voltage,
            unit="V",
        )

    def add_led(self, anode: str, cathode: str, ref: str = "", model: str = "LED") -> str:
        return self.add_component(
            kind="led",
            pins={"A": anode, "K": cathode},
            ref=ref,
            value="LED",
            spice_model=model,
        )

    def add_diode(self, anode: str, cathode: str, ref: str = "", model: str = "D1N4148") -> str:
        return self.add_component(
            kind="diode",
            pins={"A": anode, "K": cathode},
            ref=ref,
            value=model,
            spice_model=model,
        )

    def add_ic(self, kind: str, pins: dict[str, str], ref: str = "",
               value: str = "", footprint: str = "", spice_model: str = "",
               ref_prefix: str = "U") -> str:
        """Add a multi-pin IC/module component.

        Args:
            kind: Component type (e.g. "esp32s3", "ams1117", "usblc6")
            pins: Dict mapping pin_name -> net_name
            ref: Reference designator (auto-generated if empty)
            value: Component value string
            footprint: Footprint name
            spice_model: SPICE model name (empty if not simulatable)
            ref_prefix: Prefix for auto-ref (default "U")
        """
        ref = ref or self._next_ref(ref_prefix)
        return self.add_component(
            kind=kind,
            pins=pins,
            ref=ref,
            value=value or kind,
            footprint=footprint,
            spice_model=spice_model,
            ref_prefix=ref_prefix,
        )

    def add_switch(self, pin1_net: str, pin2_net: str, ref: str = "",
                   kind: str = "switch") -> str:
        """Add a tactile switch (2-pin: 1 and 2)."""
        return self.add_component(
            kind=kind,
            pins={"1": pin1_net, "2": pin2_net},
            ref=ref,
            value="SW",
            ref_prefix="SW",
        )

    def add_connector(self, kind: str, pins: dict[str, str], ref: str = "",
                      value: str = "", ref_prefix: str = "J") -> str:
        """Add a connector (USB-C, pin header, etc.) with arbitrary pins."""
        return self.add_component(
            kind=kind,
            pins=pins,
            ref=ref,
            value=value or kind,
            ref_prefix=ref_prefix,
        )

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
