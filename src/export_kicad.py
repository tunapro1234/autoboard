"""
Export Circuit to KiCad schematic (.kicad_sch) format.
Generates a KiCad 9-compatible schematic with symbols, wires and labels.
"""

from __future__ import annotations

import re
import uuid

from .circuit import Circuit, Component

GRID = 2.54
COMPONENT_SPACING_X = 32.0
COMPONENT_SPACING_Y = 24.0
LIB_PREFIX = "pcb_llm"


def _uuid() -> str:
    return str(uuid.uuid4())


def _q(value: str) -> str:
    """Escape string for KiCad S-expression quoted strings."""
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _project_name(raw_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", raw_name.strip())
    return safe or "project"


def _ref_prefix(ref: str) -> str:
    match = re.match(r"[A-Za-z#]+", ref)
    return match.group(0) if match else "U"


def _pin_layout(comp: Component) -> tuple[list[dict], dict[str, str], float, float]:
    """
    Create a simple rectangular symbol pin layout.
    Returns (pins, pin_name_to_number, body_width, body_height).
    """
    pin_names = list(comp.pins.keys())
    if not pin_names:
        pin_names = ["1"]

    left_count = (len(pin_names) + 1) // 2
    right_count = len(pin_names) - left_count
    rows = max(left_count, right_count, 1)

    pitch = GRID
    body_width = 7.62
    body_height = max(5.08, (rows - 1) * pitch + 5.08)
    top_y = (rows - 1) * pitch / 2.0

    pins: list[dict] = []
    pin_map: dict[str, str] = {}
    pin_num = 1

    # Left side pins
    for i, pin_name in enumerate(pin_names[:left_count]):
        y = top_y - i * pitch
        number = str(pin_num)
        pin_map[pin_name] = number
        pins.append({
            "name": pin_name,
            "number": number,
            "x": -body_width / 2 - 2.54,
            "y": y,
            "orientation": 0,
            "length": 2.54,
        })
        pin_num += 1

    # Right side pins
    for i, pin_name in enumerate(pin_names[left_count:]):
        y = top_y - i * pitch
        number = str(pin_num)
        pin_map[pin_name] = number
        pins.append({
            "name": pin_name,
            "number": number,
            "x": body_width / 2 + 2.54,
            "y": y,
            "orientation": 180,
            "length": 2.54,
        })
        pin_num += 1

    return pins, pin_map, body_width, body_height


def _lib_name(comp: Component) -> str:
    return f"{comp.ref}_SYM"


def _lib_symbol(comp: Component) -> tuple[str, dict[str, str], dict[str, tuple[float, float]]]:
    pins, pin_map, body_w, body_h = _pin_layout(comp)
    lib_name = _lib_name(comp)

    half_w = body_w / 2.0
    half_h = body_h / 2.0
    ref_text = _ref_prefix(comp.ref)

    lines = [
        f'    (symbol "{LIB_PREFIX}:{_q(lib_name)}"',
        '      (pin_names (offset 1.016))',
        '      (exclude_from_sim no)',
        '      (in_bom yes)',
        '      (on_board yes)',
        f'      (property "Reference" "{_q(ref_text)}" (at 0 {half_h + 1.27:.3f} 0)',
        '        (effects (font (size 1.27 1.27))))',
        f'      (property "Value" "{_q(comp.value)}" (at 0 {-half_h - 1.27:.3f} 0)',
        '        (effects (font (size 1.27 1.27))))',
        f'      (property "Footprint" "{_q(comp.footprint)}" (at 0 0 0)',
        '        (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Datasheet" "" (at 0 0 0)',
        '        (effects (font (size 1.27 1.27)) (hide yes)))',
        f'      (symbol "{_q(lib_name)}_0_1"',
        f'        (rectangle (start {-half_w:.3f} {-half_h:.3f}) (end {half_w:.3f} {half_h:.3f})',
        '          (stroke (width 0.254) (type default)) (fill (type background))))',
        f'      (symbol "{_q(lib_name)}_1_1"',
    ]

    pin_points: dict[str, tuple[float, float]] = {}
    for pin in pins:
        lines.extend([
            f'        (pin passive line (at {pin["x"]:.3f} {pin["y"]:.3f} {pin["orientation"]}) (length {pin["length"]:.3f})',
            f'          (name "{_q(pin["name"])}" (effects (font (size 0.762 0.762))))',
            f'          (number "{pin["number"]}" (effects (font (size 0.762 0.762)))))',
        ])
        pin_points[pin["name"]] = (pin["x"], pin["y"])

    lines.extend([
        '      )',
        '      (embedded_fonts no)',
        '    )',
    ])

    return "\n".join(lines), pin_map, pin_points


def _place_component(comp: Component, x: float, y: float, project: str,
                     sch_uuid: str, pin_numbers: list[str]) -> str:
    lib_name = _lib_name(comp)

    lines = [
        '  (symbol',
        f'    (lib_id "{LIB_PREFIX}:{_q(lib_name)}")',
        f'    (at {x:.3f} {y:.3f} 0)',
        '    (unit 1)',
        '    (exclude_from_sim no)',
        '    (in_bom yes)',
        '    (on_board yes)',
        '    (dnp no)',
        '    (fields_autoplaced yes)',
        f'    (uuid "{_uuid()}")',
        f'    (property "Reference" "{_q(comp.ref)}" (at {x:.3f} {y - 3.81:.3f} 0)',
        '      (effects (font (size 1.27 1.27))))',
        f'    (property "Value" "{_q(comp.value)}" (at {x:.3f} {y + 3.81:.3f} 0)',
        '      (effects (font (size 1.27 1.27))))',
        f'    (property "Footprint" "{_q(comp.footprint)}" (at {x:.3f} {y:.3f} 0)',
        '      (effects (font (size 1.27 1.27)) (hide yes)))',
        '    (property "Datasheet" "" (at 0 0 0)',
        '      (effects (font (size 1.27 1.27)) (hide yes)))',
    ]

    for pin_number in pin_numbers:
        lines.extend([
            f'    (pin "{pin_number}"',
            f'      (uuid "{_uuid()}")',
            '    )',
        ])

    lines.extend([
        '    (instances',
        f'      (project "{_q(project)}"',
        f'        (path "/{sch_uuid}"',
        f'          (reference "{_q(comp.ref)}")',
        '          (unit 1)',
        '        )',
        '      )',
        '    )',
        '  )',
    ])

    return "\n".join(lines)


def _wire(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        '  (wire\n'
        '    (pts\n'
        f'      (xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f})\n'
        '    )\n'
        '    (stroke (width 0) (type default))\n'
        f'    (uuid "{_uuid()}")\n'
        '  )'
    )


def _label(text: str, x: float, y: float) -> str:
    return (
        f'  (label "{_q(text)}"\n'
        f'    (at {x:.3f} {y:.3f} 0)\n'
        '    (effects (font (size 1.27 1.27)) (justify left bottom))\n'
        f'    (uuid "{_uuid()}")\n'
        '  )'
    )


def export_schematic(circuit: Circuit, output_path: str) -> str:
    """Export circuit to KiCad schematic file. Returns output path."""
    sch_uuid = _uuid()
    project = _project_name(circuit.name)

    components = [(r, c) for r, c in circuit.components.items() if not c.simulation_only]

    # Build symbol library entries and pin maps.
    lib_symbols: list[str] = []
    pin_num_by_ref: dict[str, dict[str, str]] = {}
    pin_point_by_ref: dict[str, dict[str, tuple[float, float]]] = {}
    for _, comp in components:
        lib_entry, pin_map, pin_points = _lib_symbol(comp)
        lib_symbols.append(lib_entry)
        pin_num_by_ref[comp.ref] = pin_map
        pin_point_by_ref[comp.ref] = pin_points

    # Grid placement.
    origin_x, origin_y = 100.0, 80.0
    cols = 4
    positions: dict[str, tuple[float, float]] = {}
    symbol_instances: list[str] = []
    for i, (ref, comp) in enumerate(components):
        x = origin_x + (i % cols) * COMPONENT_SPACING_X
        y = origin_y + (i // cols) * COMPONENT_SPACING_Y
        positions[ref] = (x, y)
        pin_numbers = list(pin_num_by_ref[ref].values())
        symbol_instances.append(_place_component(comp, x, y, project, sch_uuid, pin_numbers))

    # Net wiring and labels.
    wire_items: list[str] = []
    label_items: list[str] = []

    for net_name, net in circuit.nets.items():
        points: list[tuple[float, float]] = []
        for ref, pin_name in net.components:
            if ref not in positions or ref not in pin_point_by_ref:
                continue
            rel = pin_point_by_ref[ref].get(pin_name)
            if rel is None:
                continue
            cx, cy = positions[ref]
            points.append((cx + rel[0], cy + rel[1]))

        if not points:
            continue

        root_x, root_y = points[0]

        # Short local label near first connection point.
        label_items.append(_label(net_name, root_x + 1.27, root_y + 0.635))

        for x, y in points[1:]:
            if x == root_x or y == root_y:
                wire_items.append(_wire(root_x, root_y, x, y))
                continue

            # Orthogonal routing segment pair for readability.
            wire_items.append(_wire(root_x, root_y, x, root_y))
            wire_items.append(_wire(x, root_y, x, y))

    content = "\n".join([
        '(kicad_sch',
        '  (version 20250114)',
        '  (generator "pcb_llm_pipeline")',
        '  (generator_version "0.2")',
        f'  (uuid "{sch_uuid}")',
        '  (paper "A4")',
        '  (lib_symbols',
        "\n".join(lib_symbols),
        '  )',
        "\n".join(wire_items),
        "\n".join(label_items),
        "\n".join(symbol_instances),
        '  (sheet_instances',
        '    (path "/"',
        '      (page "1")',
        '    )',
        '  )',
        '  (embedded_fonts no)',
        ')',
        '',
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path
