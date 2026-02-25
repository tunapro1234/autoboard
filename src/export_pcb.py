"""
Export Circuit to KiCad PCB (.kicad_pcb) format with footprints placed on a grid.
Then export to .dsn for Freerouting, and import .ses back.
"""

import uuid
import subprocess
import os
import re
import json
from .circuit import Circuit, Component

GRID_MM = 2.54
COMP_SPACING = 15.0  # mm between components


def _uuid() -> str:
    return str(uuid.uuid4())


# --- Footprint definitions ---
# Each footprint has:
#   pads: list of pad defs (number, x, y, size, drill, type="thru_hole"|"smd", shape, layers)
#   courtyard: bounding box
#   silk: silkscreen label

def _thru_pad(number, x, y, size=1.6, drill=0.8):
    return {"number": str(number), "x": x, "y": y, "size": size, "drill": drill,
            "type": "thru_hole", "shape": "circle", "layers": '"*.Cu" "*.Mask"'}

def _smd_pad(number, x, y, sx, sy):
    return {"number": str(number), "x": x, "y": y, "size": (sx, sy),
            "type": "smd", "shape": "rect", "layers": '"F.Cu" "F.Paste" "F.Mask"'}


# Simple through-hole footprint definitions (mm)
FOOTPRINTS = {
    "resistor": {
        "pads": [_thru_pad("1", 0, 0), _thru_pad("2", 0, 7.62)],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 9.62},
        "silk": "R",
    },
    "capacitor": {
        "pads": [_thru_pad("1", 0, 0), _thru_pad("2", 0, 5.08)],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 7.08},
        "silk": "C",
    },
    "led": {
        "pads": [_thru_pad("1", 0, 0), _thru_pad("2", 0, 5.08)],  # 1=K, 2=A
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 7.08},
        "silk": "D",
    },
    "diode": {
        "pads": [_thru_pad("1", 0, 0), _thru_pad("2", 0, 5.08)],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 7.08},
        "silk": "D",
    },
    "voltage_source": {
        "pads": [_thru_pad("1", 0, 0, 1.7, 1.0), _thru_pad("2", 0, 2.54, 1.7, 1.0)],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 4.54},
        "silk": "J",
    },
    # --- SMD Footprints for ESP32 dev board ---
    "resistor_0603": {
        "pads": [_smd_pad("1", -0.75, 0, 0.8, 0.8), _smd_pad("2", 0.75, 0, 0.8, 0.8)],
        "courtyard": {"x": -1.4, "y": -0.65, "w": 2.8, "h": 1.3},
        "silk": "R",
    },
    "capacitor_0603": {
        "pads": [_smd_pad("1", -0.75, 0, 0.8, 0.8), _smd_pad("2", 0.75, 0, 0.8, 0.8)],
        "courtyard": {"x": -1.4, "y": -0.65, "w": 2.8, "h": 1.3},
        "silk": "C",
    },
    "led_0603": {
        "pads": [_smd_pad("1", -0.75, 0, 0.8, 0.8), _smd_pad("2", 0.75, 0, 0.8, 0.8)],
        "courtyard": {"x": -1.4, "y": -0.65, "w": 2.8, "h": 1.3},
        "silk": "D",
    },
    # SOT-223 (AMS1117-3.3): 4 pads - 3 bottom + 1 large top tab
    "sot223": {
        "pads": [
            _smd_pad("1", -2.3, 3.15, 1.0, 1.5),   # GND (pin 1)
            _smd_pad("2", 0, 3.15, 1.0, 1.5),       # VOUT (pin 2)
            _smd_pad("3", 2.3, 3.15, 1.0, 1.5),     # VIN (pin 3)
            _smd_pad("4", 0, -3.15, 3.0, 1.5),      # Tab = VOUT (pin 4)
        ],
        "courtyard": {"x": -3.5, "y": -4.5, "w": 7.0, "h": 9.0},
        "silk": "U",
    },
    # SOT-23-6 (USBLC6-2SC6)
    "sot23_6": {
        "pads": [
            _smd_pad("1", -0.95, 1.1, 0.6, 0.7),    # I/O1
            _smd_pad("2", 0, 1.1, 0.6, 0.7),         # GND
            _smd_pad("3", 0.95, 1.1, 0.6, 0.7),      # I/O2
            _smd_pad("4", 0.95, -1.1, 0.6, 0.7),     # I/O2 (other side)
            _smd_pad("5", 0, -1.1, 0.6, 0.7),        # VBUS
            _smd_pad("6", -0.95, -1.1, 0.6, 0.7),    # I/O1 (other side)
        ],
        "courtyard": {"x": -1.6, "y": -1.8, "w": 3.2, "h": 3.6},
        "silk": "U",
    },
    # USB-C 16-pin connector (simplified: 2 CC + 2 D+ + 2 D- + VBUS + GND + shield)
    "usb_c": {
        "pads": [
            # Top row SMD
            _smd_pad("A1", -3.25, 0, 0.6, 1.2),     # GND
            _smd_pad("A4", -2.25, 0, 0.6, 1.2),     # VBUS
            _smd_pad("A5", -0.25, 0, 0.3, 1.2),     # CC1
            _smd_pad("A6", 0.25, 0, 0.3, 1.2),      # D+
            _smd_pad("A7", 1.0, 0, 0.3, 1.2),       # D-
            _smd_pad("A12", 3.25, 0, 0.6, 1.2),     # GND
            # Bottom row SMD
            _smd_pad("B1", -3.25, -0.8, 0.6, 1.2),  # GND
            _smd_pad("B4", -2.25, -0.8, 0.6, 1.2),  # VBUS
            _smd_pad("B5", -0.25, -0.8, 0.3, 1.2),  # CC2
            _smd_pad("B6", 0.25, -0.8, 0.3, 1.2),   # D+
            _smd_pad("B7", 1.0, -0.8, 0.3, 1.2),    # D-
            _smd_pad("B12", 3.25, -0.8, 0.6, 1.2),  # GND
            # Shield/mount thru-hole
            _thru_pad("S1", -4.32, -1.5, 1.0, 0.7),
            _thru_pad("S2", 4.32, -1.5, 1.0, 0.7),
            _thru_pad("S3", -4.32, -5.0, 1.0, 0.7),
            _thru_pad("S4", 4.32, -5.0, 1.0, 0.7),
        ],
        "courtyard": {"x": -5.0, "y": -6.0, "w": 10.0, "h": 7.5},
        "silk": "J",
    },
    # 6x6mm tactile switch
    "switch": {
        "pads": [
            _thru_pad("1", -3.25, 0, 1.6, 1.0),
            _thru_pad("2", 3.25, 0, 1.6, 1.0),
        ],
        "courtyard": {"x": -4.0, "y": -3.5, "w": 8.0, "h": 7.0},
        "silk": "SW",
    },
    # 1x20 pin header (vertical, 2.54mm pitch)
    "pin_header_20": {
        "pads": [_thru_pad(str(i+1), 0, i * 2.54, 1.7, 1.0) for i in range(20)],
        "courtyard": {"x": -1.5, "y": -1.27, "w": 3.0, "h": 20 * 2.54},
        "silk": "J",
    },
    # ESP32-S3-WROOM-1 module footprint (18x25.5mm)
    # 41 pads: 39 edge pads + 1 GND pad (large center pad)
    "esp32s3": {
        "pads": (
            # Left side (pin 1-14): bottom to top
            [_smd_pad(str(i+1), -9.0, 10.75 - i * 1.27, 1.5, 0.7) for i in range(14)] +
            # Bottom side (pin 15-24): left to right
            [_smd_pad(str(i+15), -7.5 + i * 1.27, -12.25, 0.7, 1.5) for i in range(10)] +
            # Right side (pin 25-38): bottom to top
            [_smd_pad(str(i+25), 9.0, -10.75 + i * 1.27, 1.5, 0.7) for i in range(14)] +
            # Top center (pin 39): antenna keep-out side
            [_smd_pad("39", 0, 12.25, 0.7, 1.5)] +
            # Large center GND pad
            [_smd_pad("GND", 0, -2.0, 6.0, 6.0)]
        ),
        "courtyard": {"x": -10.0, "y": -13.5, "w": 20.0, "h": 27.0},
        "silk": "U",
    },
}

# Map component kind + pin name to pad number
PIN_TO_PAD = {
    "resistor": {"1": "1", "2": "2"},
    "capacitor": {"1": "1", "2": "2"},
    "led": {"K": "1", "A": "2"},
    "diode": {"K": "1", "A": "2"},
    "voltage_source": {"+": "1", "-": "2"},
    # SMD versions use same pin mapping
    "resistor_0603": {"1": "1", "2": "2"},
    "capacitor_0603": {"1": "1", "2": "2"},
    "led_0603": {"K": "1", "A": "2"},
    "switch": {"1": "1", "2": "2"},
    # SOT-223 (AMS1117): pin names map to pad numbers
    "ams1117": {"GND": "1", "VOUT": "2", "VIN": "3", "TAB": "4"},
    # SOT-23-6 (USBLC6-2SC6)
    "usblc6": {"IO1_A": "1", "GND": "2", "IO2_A": "3",
               "IO2_B": "4", "VBUS": "5", "IO1_B": "6"},
    # USB-C: pin name -> pad number mapping
    "usb_c": {
        "GND_A1": "A1", "VBUS_A": "A4", "CC1": "A5", "DP_A": "A6", "DN_A": "A7", "GND_A12": "A12",
        "GND_B1": "B1", "VBUS_B": "B4", "CC2": "B5", "DP_B": "B6", "DN_B": "B7", "GND_B12": "B12",
        "SHIELD1": "S1", "SHIELD2": "S2", "SHIELD3": "S3", "SHIELD4": "S4",
    },
    # 1x20 pin header: pin names are "1" through "20"
    "pin_header_20": {str(i+1): str(i+1) for i in range(20)},
    # ESP32-S3 module: 41 pins — pin name matches pad number
    "esp32s3": {str(i+1): str(i+1) for i in range(39)},
}
# Add ESP32 GND pad
PIN_TO_PAD["esp32s3"]["GND"] = "GND"


def _get_footprint_kind(comp: Component) -> str:
    """Determine which footprint definition to use for a component."""
    # If component has an explicit footprint hint, use it
    if comp.footprint and comp.footprint in FOOTPRINTS:
        return comp.footprint
    # Otherwise map by kind
    return comp.kind


def export_pcb(circuit: Circuit, output_path: str,
               board_width: float = 50.0, board_height: float = 50.0,
               traces: list[dict] = None,
               placement: dict[str, tuple[float, float]] = None) -> str:
    """Export circuit to a KiCad PCB file with components placed in a grid.

    traces: optional list of {"net": name, "layer": layer, "width": mm, "points": [(x,y),...]}
    placement: optional dict of ref -> (x, y) for custom placement
    """

    board_uuid = _uuid()

    # Build net list
    net_names = list(circuit.nets.keys())
    net_section = '  (net 0 "")\n'
    net_map = {"": 0}
    for i, name in enumerate(net_names, start=1):
        net_section += f'  (net {i} "{name}")\n'
        net_map[name] = i

    # Place footprints
    footprint_sections = []
    start_x, start_y = 120.0, 80.0
    cols = 4

    pcb_idx = 0
    for ref, comp in circuit.components.items():
        if comp.simulation_only:
            continue

        if placement and ref in placement:
            cx, cy = placement[ref]
        else:
            col = pcb_idx % cols
            row = pcb_idx // cols
            cx = start_x + col * COMP_SPACING
            cy = start_y + row * COMP_SPACING
        pcb_idx += 1

        fp_kind = _get_footprint_kind(comp)
        fp_def = FOOTPRINTS.get(fp_kind)
        if not fp_def:
            continue

        pin_map = PIN_TO_PAD.get(fp_kind, {})
        fp = _build_footprint(ref, comp, fp_def, pin_map, cx, cy, net_map, fp_kind)
        footprint_sections.append(fp)

    # Build trace segments
    trace_sections = []
    if traces:
        for t in traces:
            net_idx = net_map.get(t["net"], 0)
            layer = t.get("layer", "F.Cu")
            width = t.get("width", 0.25)
            points = t["points"]
            for i in range(len(points) - 1):
                x1, y1 = points[i]
                x2, y2 = points[i + 1]
                trace_sections.append(
                    f'  (segment (start {x1} {y1}) (end {x2} {y2}) '
                    f'(width {width}) (layer "{layer}") (net {net_idx}) (uuid {_uuid()}))'
                )

    content = f"""(kicad_pcb (version 20221018) (generator "pcb_llm_pipeline")

  (general
    (thickness 1.6)
    (legacy_teardrops no)
  )

  (paper "A4")

  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user "B.Mask")
    (39 "F.Mask" user "F.Mask")
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1")
    (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user "B.Fabrication")
    (49 "F.Fab" user "F.Fabrication")
  )

  (setup
    (pad_to_mask_clearance 0)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros false)
      (usegerberextensions false)
      (usegerberattributes true)
      (usegerberadvancedattributes true)
      (creategerberjobfile true)
      (svgprecision 4)
      (plotframeref false)
      (viasonmask false)
      (mode 1)
      (useauxorigin false)
      (hpglpennumber 1)
      (hpglpenspeed 20)
      (hpglpendiameter 15.000000)
      (pdf_front_fp_property_popups true)
      (pdf_back_fp_property_popups true)
      (dxfpolygonmode true)
      (dxfimperialunits true)
      (dxfusepcbnewfont true)
      (psnegative false)
      (psa4output false)
      (plotreference true)
      (plotvalue true)
      (plotfptext true)
      (plotinvisibletext false)
      (sketchpadsonfab false)
      (subtractmaskfromsilk false)
      (outputformat 1)
      (mirror false)
      (drillshape 1)
      (scaleselection 1)
      (outputdirectory "")
    )
  )

{net_section}
  (gr_rect (start {start_x - 10} {start_y - 10}) (end {start_x + board_width} {start_y + board_height})
    (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts") (uuid {_uuid()}))

{chr(10).join(footprint_sections)}

{chr(10).join(trace_sections)}

)
"""

    with open(output_path, "w") as f:
        f.write(content)

    return output_path


def _build_footprint(ref: str, comp: Component, fp_def: dict, pin_map: dict,
                     cx: float, cy: float, net_map: dict,
                     fp_kind: str = None) -> str:
    """Build a footprint S-expression for placement in the PCB."""
    if fp_kind is None:
        fp_kind = comp.kind

    pads = []
    for pad_def in fp_def["pads"]:
        # Find which net this pad connects to
        net_name = ""
        for pin_name, pad_num in pin_map.items():
            if pad_num == pad_def["number"] and pin_name in comp.pins:
                net_name = comp.pins[pin_name]
                break

        net_idx = net_map.get(net_name, 0)
        net_str = f'"{net_name}"' if net_name else '""'

        pad_type = pad_def.get("type", "thru_hole")
        pad_shape = pad_def.get("shape", "circle")
        layers = pad_def.get("layers", '"*.Cu" "*.Mask"')

        if pad_type == "smd":
            # SMD pad with potentially rectangular size
            size = pad_def["size"]
            if isinstance(size, tuple):
                sx, sy = size
            else:
                sx = sy = size
            pads.append(f"""    (pad "{pad_def["number"]}" smd {pad_shape} (at {pad_def["x"]} {pad_def["y"]}) (size {sx} {sy})
      (layers {layers})
      (net {net_idx} {net_str})
      (uuid {_uuid()}))""")
        else:
            # Through-hole pad
            size = pad_def["size"]
            drill = pad_def["drill"]
            pads.append(f"""    (pad "{pad_def["number"]}" thru_hole {pad_shape} (at {pad_def["x"]} {pad_def["y"]}) (size {size} {size}) (drill {drill})
      (layers {layers})
      (net {net_idx} {net_str})
      (uuid {_uuid()}))""")

    cy_def = fp_def["courtyard"]

    return f"""  (footprint "pcb_llm:{fp_kind}" (layer "F.Cu")
    (uuid {_uuid()})
    (at {cx} {cy})
    (property "Reference" "{ref}" (at 0 -2.5) (layer "F.SilkS") (uuid {_uuid()})
      (effects (font (size 1 1) (thickness 0.15))))
    (property "Value" "{comp.value}" (at 0 {cy_def["h"] + 1.5}) (layer "F.Fab") (uuid {_uuid()})
      (effects (font (size 1 1) (thickness 0.15))))
    (fp_rect (start {cy_def["x"]} {cy_def["y"]}) (end {cy_def["x"] + cy_def["w"]} {cy_def["y"] + cy_def["h"]})
      (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd") (uuid {_uuid()}))
    (fp_text user "{fp_def["silk"]}" (at 0 {cy_def["h"] / 2}) (layer "F.SilkS") (uuid {_uuid()})
      (effects (font (size 1 1) (thickness 0.15))))
{chr(10).join(pads)}
  )"""


def run_freerouting(pcb_path: str, output_dir: str = None) -> dict:
    """
    Export PCB to DSN, run Freerouting headless, import SES back.
    Returns dict with status and paths.
    """
    if output_dir is None:
        output_dir = os.path.dirname(pcb_path)

    dsn_path = os.path.join(output_dir, "circuit.dsn")
    ses_path = os.path.join(output_dir, "circuit.ses")

    result = {
        "success": False,
        "pcb_path": pcb_path,
        "dsn_path": dsn_path,
        "ses_path": ses_path,
        "errors": [],
    }

    # Try pcbnew Python export
    try:
        dsn_content = _pcb_to_dsn_simple(pcb_path)
        with open(dsn_path, "w") as f:
            f.write(dsn_content)
    except Exception as e:
        result["errors"].append(f"DSN export failed: {e}")
        return result

    # Run Freerouting headless
    cmd = [
        "freerouting",
        "-de", dsn_path,
        "-do", ses_path,
        "-mp", "20",
        "--gui.enabled=false",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        result["freerouting_stdout"] = proc.stdout
        result["freerouting_stderr"] = proc.stderr

        if os.path.exists(ses_path):
            result["success"] = True
        else:
            result["errors"].append("Freerouting did not produce output .ses file")
            result["errors"].append(proc.stderr[-500:] if proc.stderr else "no stderr")
    except subprocess.TimeoutExpired:
        result["errors"].append("Freerouting timed out after 300s")
    except Exception as e:
        result["errors"].append(f"Freerouting failed: {e}")

    return result


def parse_ses_routes(ses_path: str) -> list[dict]:
    """Parse freerouting .ses file and extract trace routes as mm coordinates."""
    with open(ses_path) as f:
        content = f.read()

    # Auto-detect scale
    place_match = re.search(r'\(place \w+ (\d+) (\d+)', content)
    if place_match:
        raw_x = int(place_match.group(1))
        if raw_x > 10_000_000:
            scale = 1_000_000  # nanometers
        elif raw_x > 100_000:
            scale = 1_000  # micrometers
        else:
            scale = 1  # already mm
    else:
        scale = 1_000_000  # default to nm

    # Collect all traces per net
    raw_traces = []
    net_blocks = re.findall(
        r'\(net\s+(\S+)\s*((?:\s*\(wire\s*\(path.*?\)\s*\))+)\s*\)',
        content, re.DOTALL
    )

    for net_name, wire_block in net_blocks:
        net_name = net_name.strip('"')

        paths = re.findall(
            r'\(path\s+(\S+)\s+(\d+)\s+([\d\s]+)\)',
            wire_block
        )

        for layer, width_raw, coords_raw in paths:
            width_mm = int(width_raw) / scale

            nums = [int(x) for x in coords_raw.split()]
            points = []
            for i in range(0, len(nums), 2):
                x_mm = nums[i] / scale
                y_mm = nums[i + 1] / scale
                points.append((round(x_mm, 4), round(y_mm, 4)))

            if len(points) >= 2:
                raw_traces.append({
                    "net": net_name,
                    "layer": layer,
                    "width": round(width_mm, 4),
                    "points": points,
                })

    # Deduplicate
    seen = set()
    traces = []
    for t in raw_traces:
        pts = tuple(t["points"])
        pts_rev = tuple(reversed(t["points"]))
        key = (t["net"], min(pts, pts_rev))

        if key in seen:
            continue
        seen.add(key)

        # Force all traces to B.Cu (no via support in MVP)
        t["layer"] = "B.Cu"
        traces.append(t)

    return traces


def full_pipeline(circuit: Circuit, output_dir: str,
                  board_width: float = 50.0, board_height: float = 50.0,
                  placement: dict[str, tuple[float, float]] = None) -> dict:
    """
    Full pipeline: export unrouted PCB -> DSN -> freerouting -> parse SES -> routed PCB.
    Returns dict with all results and paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    result = {"steps": {}, "success": False}

    # Step 1: Export unrouted PCB
    unrouted_path = os.path.join(output_dir, "unrouted.kicad_pcb")
    export_pcb(circuit, unrouted_path, board_width, board_height,
               placement=placement)
    result["steps"]["export_unrouted"] = {"path": unrouted_path, "ok": True}

    # Step 2: Generate DSN
    dsn_path = os.path.join(output_dir, "circuit.dsn")
    try:
        dsn_content = _pcb_to_dsn_simple(unrouted_path)
        with open(dsn_path, "w") as f:
            f.write(dsn_content)
        result["steps"]["dsn_export"] = {"path": dsn_path, "ok": True}
    except Exception as e:
        result["steps"]["dsn_export"] = {"error": str(e), "ok": False}
        return result

    # Step 3: Run freerouting
    ses_path = os.path.join(output_dir, "circuit.ses")
    cmd = ["freerouting", "-de", dsn_path, "-do", ses_path,
           "-mp", "20", "--gui.enabled=false"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        ok = os.path.exists(ses_path)
        result["steps"]["freerouting"] = {
            "path": ses_path, "ok": ok,
            "stdout": proc.stdout[-300:] if proc.stdout else "",
            "stderr": proc.stderr[-300:] if proc.stderr else "",
        }
        if not ok:
            return result
    except Exception as e:
        result["steps"]["freerouting"] = {"error": str(e), "ok": False}
        return result

    # Step 4: Parse SES routes
    traces = parse_ses_routes(ses_path)
    result["steps"]["parse_ses"] = {"trace_count": len(traces), "ok": len(traces) > 0}

    # Step 5: Export routed PCB with traces
    routed_path = os.path.join(output_dir, "routed.kicad_pcb")
    export_pcb(circuit, routed_path, board_width, board_height,
               traces=traces, placement=placement)
    result["steps"]["export_routed"] = {"path": routed_path, "ok": True}

    # Step 6: DRC check
    drc_json = os.path.join(output_dir, "drc_report.json")
    try:
        drc_proc = subprocess.run(
            ["kicad-cli", "pcb", "drc", "--format", "json",
             "--severity-all", "-o", drc_json, routed_path],
            capture_output=True, text=True, timeout=30
        )
        drc_text = drc_proc.stdout + drc_proc.stderr

        error_violations = 0
        unconnected_items = 0
        if os.path.exists(drc_json):
            try:
                with open(drc_json) as f:
                    drc_data = json.load(f)
                error_violations = sum(
                    1 for v in drc_data.get("violations", [])
                    if v.get("severity", "").lower() == "error"
                )
                unconnected_items = sum(
                    1 for u in drc_data.get("unconnected_items", [])
                    if u.get("severity", "").lower() == "error"
                )
            except Exception:
                # Keep fallback behavior from CLI text when JSON can't be parsed.
                error_violations = 1 if "error" in drc_text.lower() else 0
                unconnected_items = 0 if "0 unconnected" in drc_text else 1

        result["steps"]["drc"] = {
            "path": drc_json, "output": drc_text.strip(),
            "ok": drc_proc.returncode == 0 and error_violations == 0 and unconnected_items == 0,
        }
    except Exception as e:
        result["steps"]["drc"] = {"error": str(e), "ok": False}

    # Step 7: Gerber export (manufacturing files)
    gerber_dir = os.path.join(output_dir, "gerber")
    os.makedirs(gerber_dir, exist_ok=True)
    try:
        subprocess.run(
            ["kicad-cli", "pcb", "export", "gerbers",
             "--layers", "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
             "-o", gerber_dir + "/", routed_path],
            capture_output=True, text=True, timeout=30
        )
        subprocess.run(
            ["kicad-cli", "pcb", "export", "drill",
             "-o", gerber_dir + "/", routed_path],
            capture_output=True, text=True, timeout=30
        )
        gerber_files = [f for f in os.listdir(gerber_dir) if not f.startswith('.')]
        result["steps"]["gerber"] = {
            "path": gerber_dir, "file_count": len(gerber_files),
            "ok": len(gerber_files) >= 5,
        }
    except Exception as e:
        result["steps"]["gerber"] = {"error": str(e), "ok": False}

    # Step 8: Render outputs
    renders = {}
    for fmt, cmd_args in [
        ("svg", ["kicad-cli", "pcb", "export", "svg",
                 "--layers", "F.Cu,B.Cu,Edge.Cuts,F.SilkS",
                 "--mode-single", "--exclude-drawing-sheet",
                 "-o", os.path.join(output_dir, "routed.svg"), routed_path]),
        ("3d_top", ["kicad-cli", "pcb", "render",
                    "-o", os.path.join(output_dir, "routed_3d_top.png"),
                    "--side", "top", "--quality", "basic",
                    "--background", "opaque", "-w", "1200", routed_path]),
        ("3d_bottom", ["kicad-cli", "pcb", "render",
                       "-o", os.path.join(output_dir, "routed_3d_bottom.png"),
                       "--side", "bottom", "--quality", "basic",
                       "--background", "opaque", "-w", "1200", routed_path]),
    ]:
        try:
            subprocess.run(cmd_args, capture_output=True, text=True, timeout=30)
            out_path = cmd_args[cmd_args.index("-o") + 1]
            renders[fmt] = {"path": out_path, "ok": os.path.exists(out_path)}
        except Exception as e:
            renders[fmt] = {"error": str(e), "ok": False}

    result["steps"]["render"] = renders
    result["success"] = all(
        s.get("ok", False) for s in result["steps"].values()
        if isinstance(s, dict) and "ok" in s
    )
    return result


def _pcb_to_dsn_simple(pcb_path: str) -> str:
    """
    Generate a minimal Specctra DSN file from our PCB.
    Supports both through-hole and SMD footprints.
    """
    with open(pcb_path) as f:
        pcb_content = f.read()

    # Extract top-level net declarations only (not pad-level net references)
    nets = re.findall(r'^\s{2}\(net (\d+) "([^"]*)"\)', pcb_content, re.MULTILINE)

    # Board outline
    rect_match = re.search(r'gr_rect \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\)', pcb_content)
    if rect_match:
        bx1 = float(rect_match.group(1))
        by1 = float(rect_match.group(2))
        bx2 = float(rect_match.group(3))
        by2 = float(rect_match.group(4))
    else:
        bx1, by1, bx2, by2 = 100, 70, 170, 140

    RES = 1000  # units per mm

    def mm(v): return int(v * RES)

    dsn_lines = [
        f'(pcb "circuit.dsn"',
        f'  (parser',
        f'    (string_quote ")',
        f'    (space_in_quoted_tokens on)',
        f'    (host_cad "KiCad")',
        f'    (host_version "9.0.7")',
        f'  )',
        f'  (resolution mm {RES})',
        f'  (unit mm)',
        f'  (structure',
        f'    (layer F.Cu',
        f'      (type signal)',
        f'      (property',
        f'        (index 0)',
        f'      )',
        f'    )',
        f'    (layer B.Cu',
        f'      (type signal)',
        f'      (property',
        f'        (index 1)',
        f'      )',
        f'    )',
        f'    (boundary',
        f'      (path pcb 0 {mm(bx1)} {mm(by1)} {mm(bx2)} {mm(by1)} {mm(bx2)} {mm(by2)} {mm(bx1)} {mm(by2)} {mm(bx1)} {mm(by1)})',
        f'    )',
        f'    (via "Via[0-1]_800:400_um")',
        f'    (rule',
        f'      (width 250)',
        f'      (clearance 200)',
        f'      (clearance 200 (type default_smd))',
        f'    )',
        f'  )',
    ]

    # Placement section
    dsn_lines.append('  (placement')

    # Parse footprints — handle both thru_hole and smd pads
    pad_pattern_thru = re.compile(
        r'\(pad "([^"]+)" thru_hole (\w+) \(at ([\d.e-]+) ([\d.e-]+)\) '
        r'\(size ([\d.e-]+) ([\d.e-]+)\) \(drill ([\d.e-]+)\).*?'
        r'\(net (\d+) "([^"]*)"\)',
        re.DOTALL
    )
    pad_pattern_smd = re.compile(
        r'\(pad "([^"]+)" smd (\w+) \(at ([\d.e-]+) ([\d.e-]+)\) '
        r'\(size ([\d.e-]+) ([\d.e-]+)\).*?'
        r'\(net (\d+) "([^"]*)"\)',
        re.DOTALL
    )

    # Find all footprints
    fp_blocks = pcb_content.split('(footprint "pcb_llm:')[1:]

    component_pads = {}  # ref -> [(pad_num, net_name, rel_x, rel_y, size_x, size_y, drill, is_smd)]
    fp_kinds = {}  # ref -> kind

    for block in fp_blocks:
        kind_match = re.match(r'(\w+)', block)
        at_match = re.search(r'\(at ([\d.e-]+) ([\d.e-]+)\)', block)
        ref_match = re.search(r'property "Reference" "([^"]+)"', block)

        if not (kind_match and at_match and ref_match):
            continue

        kind = kind_match.group(1)
        fx = float(at_match.group(1))
        fy = float(at_match.group(2))
        ref = ref_match.group(1)
        fp_kinds[ref] = kind

        dsn_lines.append(f'    (component "pcb_llm:{kind}"')
        dsn_lines.append(f'      (place {ref} {mm(fx)} {mm(fy)} front 0)')
        dsn_lines.append(f'    )')

        # Collect pads
        component_pads[ref] = []
        for pm in pad_pattern_thru.finditer(block):
            pad_num = pm.group(1)
            px = float(pm.group(3))
            py = float(pm.group(4))
            sx = float(pm.group(5))
            sy = float(pm.group(6))
            drill = float(pm.group(7))
            net_name = pm.group(9)
            component_pads[ref].append((pad_num, net_name, px, py, sx, sy, drill, False))

        for pm in pad_pattern_smd.finditer(block):
            pad_num = pm.group(1)
            px = float(pm.group(3))
            py = float(pm.group(4))
            sx = float(pm.group(5))
            sy = float(pm.group(6))
            net_name = pm.group(8)
            component_pads[ref].append((pad_num, net_name, px, py, sx, sy, 0, True))

    dsn_lines.append('  )')

    # Library section
    dsn_lines.append('  (library')

    # Define images (footprints) — group by kind
    seen_kinds = set()
    for block in fp_blocks:
        kind_match = re.match(r'(\w+)', block)
        if not kind_match:
            continue
        kind = kind_match.group(1)
        if kind in seen_kinds:
            continue
        seen_kinds.add(kind)

        fp_def = FOOTPRINTS.get(kind)
        if not fp_def:
            continue

        dsn_lines.append(f'    (image "pcb_llm:{kind}"')
        for pad_def in fp_def["pads"]:
            pad_type = pad_def.get("type", "thru_hole")
            size = pad_def["size"]
            if isinstance(size, tuple):
                sx, sy = size
            else:
                sx = sy = size
            size_um = int(max(sx, sy) * 1000)

            if pad_type == "smd":
                padstack_name = f"SMDPad_{int(sx*1000)}x{int(sy*1000)}_um"
            else:
                padstack_name = f"Round[A]Pad_{size_um}_um"

            dsn_lines.append(f'      (pin "{padstack_name}" {pad_def["number"]} {mm(pad_def["x"])} {mm(pad_def["y"])})')
        dsn_lines.append(f'    )')

    # Padstack definitions — collect unique padstacks
    padstack_set = set()
    for kind in seen_kinds:
        fp_def = FOOTPRINTS.get(kind)
        if not fp_def:
            continue
        for pad_def in fp_def["pads"]:
            pad_type = pad_def.get("type", "thru_hole")
            size = pad_def["size"]
            if isinstance(size, tuple):
                sx, sy = size
            else:
                sx = sy = size

            if pad_type == "smd":
                padstack_set.add(("smd", int(sx*1000), int(sy*1000)))
            else:
                padstack_set.add(("thru", int(sx*1000), int(pad_def["drill"]*1000)))

    for ps in sorted(padstack_set):
        if ps[0] == "thru":
            size_um = ps[1]
            dsn_lines.append(f'    (padstack "Round[A]Pad_{size_um}_um"')
            dsn_lines.append(f'      (shape (circle F.Cu {size_um}))')
            dsn_lines.append(f'      (shape (circle B.Cu {size_um}))')
            dsn_lines.append(f'      (attach off)')
            dsn_lines.append(f'    )')
        else:
            sx_um, sy_um = ps[1], ps[2]
            dsn_lines.append(f'    (padstack "SMDPad_{sx_um}x{sy_um}_um"')
            dsn_lines.append(f'      (shape (rect F.Cu {-sx_um//2} {-sy_um//2} {sx_um//2} {sy_um//2}))')
            dsn_lines.append(f'      (attach off)')
            dsn_lines.append(f'    )')

    # Via padstack
    dsn_lines.append(f'    (padstack "Via[0-1]_800:400_um"')
    dsn_lines.append(f'      (shape (circle F.Cu 800))')
    dsn_lines.append(f'      (shape (circle B.Cu 800))')
    dsn_lines.append(f'      (attach off)')
    dsn_lines.append(f'    )')

    dsn_lines.append('  )')

    # Network section
    dsn_lines.append('  (network')
    for net_idx, net_name in nets:
        if not net_name:
            continue
        # Find pins connected to this net
        pins = []
        for ref, pads in component_pads.items():
            for pad_num, pnet, px, py, sx, sy, dr, is_smd in pads:
                if pnet == net_name:
                    pins.append(f'{ref}-{pad_num}')

        if pins:
            dsn_lines.append(f'    (net "{net_name}"')
            dsn_lines.append(f'      (pins {" ".join(pins)})')
            dsn_lines.append(f'    )')

    dsn_lines.append('    (class kicad_default ""')
    for net_idx, net_name in nets:
        if net_name:
            dsn_lines.append(f'      (add_net "{net_name}")')
    dsn_lines.append('      (circuit')
    dsn_lines.append('        (use_via "Via[0-1]_800:400_um")')
    dsn_lines.append('      )')
    dsn_lines.append('      (rule')
    dsn_lines.append('        (width 250)')
    dsn_lines.append('        (clearance 200)')
    dsn_lines.append('      )')
    dsn_lines.append('    )')

    dsn_lines.append('  )')
    dsn_lines.append(')')

    return '\n'.join(dsn_lines)
