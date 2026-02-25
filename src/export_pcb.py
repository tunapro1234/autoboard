"""
Export Circuit to KiCad PCB (.kicad_pcb) format with footprints placed on a grid.
Then export to .dsn for Freerouting, and import .ses back.
"""

import uuid
import subprocess
import os
import re
from .circuit import Circuit, Component

GRID_MM = 2.54
COMP_SPACING = 15.0  # mm between components


def _uuid() -> str:
    return str(uuid.uuid4())


# Simple through-hole footprint definitions (mm)
FOOTPRINTS = {
    "resistor": {
        "pads": [
            {"number": "1", "x": 0, "y": 0, "size": 1.6, "drill": 0.8},
            {"number": "2", "x": 0, "y": 7.62, "size": 1.6, "drill": 0.8},
        ],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 9.62},
        "silk": "R",
    },
    "capacitor": {
        "pads": [
            {"number": "1", "x": 0, "y": 0, "size": 1.6, "drill": 0.8},
            {"number": "2", "x": 0, "y": 5.08, "size": 1.6, "drill": 0.8},
        ],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 7.08},
        "silk": "C",
    },
    "led": {
        "pads": [
            {"number": "1", "x": 0, "y": 0, "size": 1.6, "drill": 0.8},   # K
            {"number": "2", "x": 0, "y": 5.08, "size": 1.6, "drill": 0.8}, # A
        ],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 7.08},
        "silk": "D",
    },
    "diode": {
        "pads": [
            {"number": "1", "x": 0, "y": 0, "size": 1.6, "drill": 0.8},
            {"number": "2", "x": 0, "y": 5.08, "size": 1.6, "drill": 0.8},
        ],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 7.08},
        "silk": "D",
    },
    "voltage_source": {
        # 2-pin header for power connector
        "pads": [
            {"number": "1", "x": 0, "y": 0, "size": 1.7, "drill": 1.0},
            {"number": "2", "x": 0, "y": 2.54, "size": 1.7, "drill": 1.0},
        ],
        "courtyard": {"x": -1.5, "y": -1.0, "w": 3.0, "h": 4.54},
        "silk": "J",
    },
}

# Map component kind + pin name to pad number
PIN_TO_PAD = {
    "resistor": {"1": "1", "2": "2"},
    "capacitor": {"1": "1", "2": "2"},
    "led": {"K": "1", "A": "2"},
    "diode": {"K": "1", "A": "2"},
    "voltage_source": {"+": "1", "-": "2"},
}


def export_pcb(circuit: Circuit, output_path: str,
               board_width: float = 50.0, board_height: float = 50.0,
               traces: list[dict] = None) -> str:
    """Export circuit to a KiCad PCB file with components placed in a grid.

    traces: optional list of {"net": name, "layer": layer, "width": mm, "points": [(x,y),...]}
    """

    board_uuid = _uuid()

    # Build net list
    net_names = list(circuit.nets.keys())
    net_section = '  (net 0 "")\n'
    net_map = {"": 0}
    for i, name in enumerate(net_names, start=1):
        net_section += f'  (net {i} "{name}")\n'
        net_map[name] = i

    # Place footprints in a grid
    footprint_sections = []
    start_x, start_y = 120.0, 80.0
    cols = 4

    for idx, (ref, comp) in enumerate(circuit.components.items()):
        col = idx % cols
        row = idx // cols
        cx = start_x + col * COMP_SPACING
        cy = start_y + row * COMP_SPACING

        fp_def = FOOTPRINTS.get(comp.kind)
        if not fp_def:
            continue

        pin_map = PIN_TO_PAD.get(comp.kind, {})
        fp = _build_footprint(ref, comp, fp_def, pin_map, cx, cy, net_map)
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
                     cx: float, cy: float, net_map: dict) -> str:
    """Build a footprint S-expression for placement in the PCB."""

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

        pads.append(f"""    (pad "{pad_def["number"]}" thru_hole circle (at {pad_def["x"]} {pad_def["y"]}) (size {pad_def["size"]} {pad_def["size"]}) (drill {pad_def["drill"]})
      (layers "*.Cu" "*.Mask")
      (net {net_idx} {net_str})
      (uuid {_uuid()}))""")

    cy_def = fp_def["courtyard"]

    return f"""  (footprint "pcb_llm:{comp.kind}" (layer "F.Cu")
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

    # Step 1: Export .kicad_pcb → .dsn via kicad-cli
    # KiCad doesn't have direct DSN export via CLI, so we use pcbnew Python
    # For now, try kicad-cli pcb export
    # Actually kicad-cli doesn't export DSN. We need to write DSN ourselves or use pcbnew scripting.
    # Let's try the pcbnew Python module first.

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

    # Step 2: Run Freerouting headless
    cmd = [
        "freerouting",
        "-de", dsn_path,
        "-do", ses_path,
        "-mp", "20",
        "--gui.enabled=false",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        result["freerouting_stdout"] = proc.stdout
        result["freerouting_stderr"] = proc.stderr

        if os.path.exists(ses_path):
            result["success"] = True
        else:
            result["errors"].append("Freerouting did not produce output .ses file")
            result["errors"].append(proc.stderr[-500:] if proc.stderr else "no stderr")
    except subprocess.TimeoutExpired:
        result["errors"].append("Freerouting timed out after 120s")
    except Exception as e:
        result["errors"].append(f"Freerouting failed: {e}")

    return result


def parse_ses_routes(ses_path: str) -> list[dict]:
    """Parse freerouting .ses file and extract trace routes as mm coordinates."""
    with open(ses_path) as f:
        content = f.read()

    # Auto-detect scale: find a placement coordinate and compare to known position.
    # Freerouting outputs in nanometers regardless of the resolution field.
    # Detect by looking at the routes resolution or by checking coordinate magnitude.
    place_match = re.search(r'\(place \w+ (\d+) (\d+)', content)
    if place_match:
        raw_x = int(place_match.group(1))
        # Our components start at x=120mm. If raw_x is ~120000000, scale is 1e6.
        # If raw_x is ~120000, scale is 1e3.
        if raw_x > 10_000_000:
            scale = 1_000_000  # nanometers
        elif raw_x > 100_000:
            scale = 1_000  # micrometers
        else:
            scale = 1  # already mm
    else:
        scale = 1_000_000  # default to nm

    # Collect all traces per net, merging layers to avoid via issues
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

    # Deduplicate: remove traces that are exact reverses of another trace
    # and merge multi-layer traces onto B.Cu (since we don't support vias yet)
    seen = set()
    traces = []
    for t in raw_traces:
        # Create a canonical key: sorted endpoints
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
                  board_width: float = 50.0, board_height: float = 50.0) -> dict:
    """
    Full pipeline: export unrouted PCB → DSN → freerouting → parse SES → routed PCB.
    Returns dict with all results and paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    result = {"steps": {}, "success": False}

    # Step 1: Export unrouted PCB
    unrouted_path = os.path.join(output_dir, "unrouted.kicad_pcb")
    export_pcb(circuit, unrouted_path, board_width, board_height)
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
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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
    export_pcb(circuit, routed_path, board_width, board_height, traces=traces)
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
        violations = drc_text.count("violation")
        unconnected = "0 unconnected" in drc_text or "Found 0 unconnected" in drc_text
        result["steps"]["drc"] = {
            "path": drc_json, "output": drc_text.strip(),
            "ok": "0 violations" in drc_text and unconnected,
        }
    except Exception as e:
        result["steps"]["drc"] = {"error": str(e), "ok": False}

    # Step 7: Render outputs
    renders = {}
    for fmt, cmd_args in [
        ("svg", ["kicad-cli", "pcb", "export", "svg",
                 "--layers", "F.Cu,B.Cu,Edge.Cuts,F.SilkS",
                 "--mode-single", "--exclude-drawing-sheet",
                 "-o", os.path.join(output_dir, "routed.svg"), routed_path]),
        ("3d_png", ["kicad-cli", "pcb", "render",
                    "-o", os.path.join(output_dir, "routed_3d.png"),
                    "--side", "top", "--quality", "basic",
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
    This is a simplified version - real DSN export is complex.
    We parse our own PCB file since we know its structure.
    """
    # For MVP: read the PCB we just generated and convert to DSN
    # This is a simplified DSN that freerouting can understand

    with open(pcb_path) as f:
        pcb_content = f.read()

    # Parse nets, components, pads from our known format
    # Since we generated the PCB ourselves, we know the structure
    import re

    # Extract nets
    nets = re.findall(r'\(net (\d+) "([^"]*)"\)', pcb_content)

    # Extract footprints with positions and pads
    # This is simplified - we'll build DSN from our Circuit object instead
    # For now, create a minimal DSN

    # Board outline - find Edge.Cuts rect
    rect_match = re.search(r'gr_rect \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\)', pcb_content)
    if rect_match:
        bx1 = float(rect_match.group(1))
        by1 = float(rect_match.group(2))
        bx2 = float(rect_match.group(3))
        by2 = float(rect_match.group(4))
    else:
        bx1, by1, bx2, by2 = 100, 70, 170, 140

    # Convert mm to DSN units (10 * mils, i.e. 1mm = 393.7 units... actually DSN uses mils * 10 = 0.1mil)
    # Freerouting uses resolution 1000 per mm typically
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

    # Parse footprints
    fp_pattern = re.compile(
        r'footprint "pcb_llm:(\w+)".*?\(at ([\d.]+) ([\d.]+)\).*?'
        r'property "Reference" "(\w+)".*?'
        r'property "Value" "([^"]*)"',
        re.DOTALL
    )

    pad_pattern = re.compile(
        r'\(pad "(\d+)" thru_hole circle \(at ([\d.]+) ([\d.]+)\) '
        r'\(size ([\d.]+) ([\d.]+)\) \(drill ([\d.]+)\).*?'
        r'\(net (\d+) "([^"]*)"\)',
        re.DOTALL
    )

    # Find all footprints
    fp_blocks = pcb_content.split('(footprint "pcb_llm:')[1:]

    component_pads = {}  # ref -> [(pad_num, net_name, rel_x, rel_y, size, drill)]

    for block in fp_blocks:
        kind_match = re.match(r'(\w+)', block)
        at_match = re.search(r'\(at ([\d.]+) ([\d.]+)\)', block)
        ref_match = re.search(r'property "Reference" "(\w+)"', block)

        if not (kind_match and at_match and ref_match):
            continue

        kind = kind_match.group(1)
        fx = float(at_match.group(1))
        fy = float(at_match.group(2))
        ref = ref_match.group(1)

        dsn_lines.append(f'    (component "pcb_llm:{kind}"')
        dsn_lines.append(f'      (place {ref} {mm(fx)} {mm(fy)} front 0)')
        dsn_lines.append(f'    )')

        # Collect pads
        component_pads[ref] = []
        for pm in pad_pattern.finditer(block):
            pad_num = pm.group(1)
            px = float(pm.group(2))
            py = float(pm.group(3))
            size = float(pm.group(4))
            drill = float(pm.group(6))
            net_idx = int(pm.group(7))
            net_name = pm.group(8)
            component_pads[ref].append((pad_num, net_name, px, py, size, drill))

    dsn_lines.append('  )')

    # Library section - define padstacks
    dsn_lines.append('  (library')
    # Define images (footprints)
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
            dsn_lines.append(f'      (pin "Round[A]Pad_{int(pad_def["size"]*1000)}_um" {pad_def["number"]} {mm(pad_def["x"])} {mm(pad_def["y"])})')
        dsn_lines.append(f'    )')

    # Padstack definitions
    for size in [1600, 1700]:
        dsn_lines.append(f'    (padstack "Round[A]Pad_{size}_um"')
        dsn_lines.append(f'      (shape (circle F.Cu {size}))')
        dsn_lines.append(f'      (shape (circle B.Cu {size}))')
        dsn_lines.append(f'      (attach off)')
        dsn_lines.append(f'    )')

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
            for pad_num, pnet, px, py, sz, dr in pads:
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
