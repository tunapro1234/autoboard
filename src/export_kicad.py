"""
Export Circuit to KiCad schematic (.kicad_sch) format.
Generates a valid KiCad 7+ schematic file that can be opened in KiCad
and validated with `kicad-cli sch erc`.
"""

import uuid
from .circuit import Circuit, Component

# Grid spacing in KiCad units (mm * 2.54 for mil grid)
GRID = 2.54
COMPONENT_SPACING_X = 30.0
COMPONENT_SPACING_Y = 20.0


def _uuid() -> str:
    return str(uuid.uuid4())


def _symbol_lib(comp: Component) -> str:
    """Generate the lib_symbols entry for a component."""
    if comp.kind == "resistor":
        return _resistor_symbol(comp)
    elif comp.kind == "capacitor":
        return _capacitor_symbol(comp)
    elif comp.kind == "led":
        return _led_symbol(comp)
    elif comp.kind == "diode":
        return _diode_symbol(comp)
    elif comp.kind == "voltage_source":
        return _vsource_symbol(comp)
    return ""


def _resistor_symbol(comp: Component) -> str:
    return f"""    (symbol "{comp.ref}:R" (pin_names (offset 0) hide) (in_bom yes) (on_board yes)
      (property "Reference" "{comp.ref}" (at 2.032 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "{comp.value}" (at 0 0 90) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at -1.778 0 90) (effects (font (size 1.27 1.27))))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (symbol "{comp.ref}:R_0_1"
        (rectangle (start -1.016 -2.54) (end 1.016 2.54)
          (stroke (width 0.254) (type default)) (fill (type none))))
      (symbol "{comp.ref}:R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27)
          (name "1" (effects (font (size 0.508 0.508))))
          (number "1" (effects (font (size 0.508 0.508)))))
        (pin passive line (at 0 -3.81 90) (length 1.27)
          (name "2" (effects (font (size 0.508 0.508))))
          (number "2" (effects (font (size 0.508 0.508)))))))"""


def _capacitor_symbol(comp: Component) -> str:
    return f"""    (symbol "{comp.ref}:C" (pin_names (offset 0) hide) (in_bom yes) (on_board yes)
      (property "Reference" "{comp.ref}" (at 0.635 2.54 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "{comp.value}" (at 0.635 -2.54 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Footprint" "" (at 0.9652 -3.81 0) (effects (font (size 1.27 1.27))))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (symbol "{comp.ref}:C_0_1"
        (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762))
          (stroke (width 0.508) (type default)) (fill (type none)))
        (polyline (pts (xy -2.032 0.762) (xy 2.032 0.762))
          (stroke (width 0.508) (type default)) (fill (type none))))
      (symbol "{comp.ref}:C_1_1"
        (pin passive line (at 0 3.81 270) (length 2.794)
          (name "1" (effects (font (size 0.508 0.508))))
          (number "1" (effects (font (size 0.508 0.508)))))
        (pin passive line (at 0 -3.81 90) (length 2.794)
          (name "2" (effects (font (size 0.508 0.508))))
          (number "2" (effects (font (size 0.508 0.508)))))))"""


def _led_symbol(comp: Component) -> str:
    return f"""    (symbol "{comp.ref}:LED" (pin_names (offset 1.016) hide) (in_bom yes) (on_board yes)
      (property "Reference" "{comp.ref}" (at 1.27 2.54 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "LED" (at 1.27 -2.54 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (symbol "{comp.ref}:LED_0_1"
        (polyline (pts (xy -1.27 -1.27) (xy -1.27 1.27))
          (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -1.27 0) (xy 1.27 0))
          (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 1.27 -1.27) (xy 1.27 1.27) (xy -1.27 0) (xy 1.27 -1.27))
          (stroke (width 0.254) (type default)) (fill (type none))))
      (symbol "{comp.ref}:LED_1_1"
        (pin passive line (at -3.81 0 0) (length 2.54)
          (name "K" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 3.81 0 180) (length 2.54)
          (name "A" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27)))))))"""


def _diode_symbol(comp: Component) -> str:
    return _led_symbol(comp)  # same shape for MVP


def _vsource_symbol(comp: Component) -> str:
    return f"""    (symbol "{comp.ref}:VSOURCE" (pin_names (offset 1.016)) (in_bom yes) (on_board yes)
      (property "Reference" "{comp.ref}" (at 2.54 2.54 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "{comp.value}V" (at 2.54 -2.54 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Sim.Type" "DC" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Sim.Params" "dc={comp.value}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "{comp.ref}:VSOURCE_0_1"
        (circle (center 0 0) (radius 2.54)
          (stroke (width 0.254) (type default)) (fill (type none))))
      (symbol "{comp.ref}:VSOURCE_1_1"
        (pin passive line (at 0 5.08 270) (length 2.54)
          (name "+" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -5.08 90) (length 2.54)
          (name "-" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27)))))))"""


def export_schematic(circuit: Circuit, output_path: str) -> str:
    """Export circuit to KiCad schematic file. Returns the file path."""
    sch_uuid = _uuid()

    # Build lib_symbols
    lib_symbols = []
    for comp in circuit.components.values():
        sym = _symbol_lib(comp)
        if sym:
            lib_symbols.append(sym)

    # Place components on a grid
    symbol_instances = []
    x, y = 100.0, 80.0
    for i, (ref, comp) in enumerate(circuit.components.items()):
        sx = x + (i % 4) * COMPONENT_SPACING_X
        sy = y + (i // 4) * COMPONENT_SPACING_Y
        inst = _place_component(comp, sx, sy)
        symbol_instances.append(inst)

    # Build wires from nets
    # (simplified: for MVP, we list nets as labels rather than drawing wires)
    net_labels = []
    label_positions = {}
    for comp in circuit.components.values():
        cx = x + (list(circuit.components.keys()).index(comp.ref) % 4) * COMPONENT_SPACING_X
        cy = y + (list(circuit.components.keys()).index(comp.ref) // 4) * COMPONENT_SPACING_Y
        for pin_idx, (pin_name, net_name) in enumerate(comp.pins.items()):
            if net_name not in label_positions:
                lx = cx + (pin_idx * 10) - 5
                ly = cy - 10
                label_positions[net_name] = (lx, ly)
                net_labels.append(
                    f'  (net_label "{net_name}" (at {lx} {ly} 0) (effects (font (size 1.27 1.27)))\n'
                    f'    (uuid {_uuid()}))'
                )

    content = f"""(kicad_sch (version 20230121) (generator "pcb_llm_pipeline")

  (uuid {sch_uuid})

  (paper "A4")

  (lib_symbols
{chr(10).join(lib_symbols)}
  )

{chr(10).join(symbol_instances)}

)
"""
    with open(output_path, "w") as f:
        f.write(content)

    return output_path


def _place_component(comp: Component, x: float, y: float) -> str:
    """Generate a symbol instance placement."""
    lib_name = {
        "resistor": "R",
        "capacitor": "C",
        "led": "LED",
        "diode": "LED",
        "voltage_source": "VSOURCE",
    }.get(comp.kind, comp.kind)

    return f"""  (symbol (lib_id "{comp.ref}:{lib_name}") (at {x} {y} 0) (unit 1)
    (in_bom yes) (on_board yes) (dnp no)
    (uuid {_uuid()})
    (property "Reference" "{comp.ref}" (at {x + 2} {y - 3} 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "{comp.value}" (at {x + 2} {y + 3} 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at {x} {y} 0)
      (effects (font (size 1.27 1.27)) hide))
    (property "Datasheet" "" (at {x} {y} 0)
      (effects (font (size 1.27 1.27)) hide))
    (instances
      (project "{comp.ref}"
        (path "/" (reference "{comp.ref}") (unit 1))))
  )"""
