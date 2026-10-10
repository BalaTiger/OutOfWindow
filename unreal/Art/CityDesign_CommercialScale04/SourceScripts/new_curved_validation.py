"""Read-only stored-mesh audit for the scoped curved district sample.

Run in one background Blender process after saving the design:
  blender --background design.blend --python new_curved_validation.py -- report.json \
    --collections Curved_A Curved_B Curved_Bridge Curved_C Office_Corner \
    --placeholder Curved_C

Keep validate_city_sample.py beside this script. No mesh edits, save, render,
export, or evaluated-modifier expansion occur. Set audit_role="lettering" or
"glazing_sheet", or audit_open_allowed=True, only for intentional open pieces.
Optional: --envelope Curved_A=xmin,ymin,zmin,xmax,ymax,zmax (metres).
"""

import argparse
import importlib.util
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load_base():
    source = Path(__file__).with_name("validate_city_sample.py")
    spec = importlib.util.spec_from_file_location("city_mesh_audit", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def vector_valid(vector):
    values = tuple(float(v) for v in vector)
    return all(math.isfinite(v) for v in values) and abs(sum(v * v for v in values) - 1) <= 1e-4


def extra_checks(obj, record):
    mesh = obj.data
    role = str(obj.get("audit_role", "unspecified"))
    allow_open = bool(obj.get("audit_open_allowed", False)) or role in {"lettering", "glazing_sheet"}
    record["audit_role"] = role
    record["intentional_open_geometry"] = allow_open
    face_bad = sum(not vector_valid(p.normal) for p in mesh.polygons)
    corner_normals = getattr(mesh, "corner_normals", ())
    corner_bad = sum(not vector_valid(n.vector) for n in corner_normals)
    record["normal_vectors"] = {
        "face_count": len(mesh.polygons), "invalid_face_normals": face_bad,
        "corner_count": len(corner_normals), "invalid_corner_normals": corner_bad,
        "unit_length_tolerance_squared": 1e-4,
        "shading_intent_checked": False,
    }
    if face_bad or corner_bad or len(corner_normals) != len(mesh.loops):
        record["errors"].append("Face/corner normals are nonfinite, nonunit, or incomplete")
    determinant = record["world_transform_determinant"]
    if not math.isfinite(determinant) or determinant <= 0:
        record["errors"].append("World transform is singular, reflected, or nonfinite")
    if record["unassigned_material_faces"]:
        record["errors"].append("Some faces lack a valid material assignment")
    topology = record["topology"]
    if topology["boundary_edges"] and not allow_open:
        record["warnings"].append("Unclassified open boundaries; confirm intended sheet or close solid")
    if topology["wire_edges"] or topology["over_shared_edges"]:
        record["warnings"].append("Loose/wire or over-shared edges require inspection")
    used = {i for p in mesh.polygons for i in p.vertices}
    record["vertices_not_used_by_faces"] = len(mesh.vertices) - len(used)
    if record["vertices_not_used_by_faces"]:
        record["warnings"].append("Vertices not used by any face are present")
    record["material_face_counts"] = dict(Counter(
        record["material_slots"][p.material_index]
        if p.material_index < len(record["material_slots"]) and record["material_slots"][p.material_index]
        else "<unassigned>" for p in mesh.polygons
    ))
    return record


def parse_envelopes(entries, names):
    boxes = {}
    for entry in entries:
        name, values = entry.split("=", 1)
        limits = [float(v) for v in values.split(",")]
        if name not in names or len(limits) != 6 or not all(math.isfinite(v) for v in limits):
            raise ValueError("Envelope needs a scoped collection and six finite metre values")
        if any(limits[i] >= limits[i + 3] for i in range(3)):
            raise ValueError("Envelope maxima must exceed minima")
        boxes[name] = {"min_m": limits[:3], "max_m": limits[3:]}
    return boxes


def main(args):
    import bpy
    import json

    base = load_base()
    scene = bpy.context.scene
    units = scene.unit_settings
    unit_ok = units.system == "METRIC" and math.isclose(units.scale_length, 1, abs_tol=1e-9, rel_tol=0)
    errors = [] if unit_ok else ["Expected Metric units and one metre per Blender unit"]
    names = list(dict.fromkeys(args.collections))
    if any(name not in names for name in args.placeholder):
        raise ValueError("Every placeholder must be included in --collections")
    envelopes = parse_envelopes(args.envelope, names)
    records, members = {}, {}
    for name in names:
        collection = bpy.data.collections.get(name)
        objects = [obj for obj in collection.all_objects if obj.type == "MESH"] if collection else []
        members[name] = [obj.name for obj in objects]
        if not objects:
            errors.append("Missing or empty mesh collection: " + name)
        for obj in objects:
            if obj.name not in records:
                records[obj.name] = extra_checks(obj, base.inspect_object(obj, [], units.scale_length))
            records[obj.name]["collections"].append(name)
    objects = [records[name] for name in sorted(records)]
    total = base.summarize(objects)
    groups = {}
    envelope_reviews = []
    for name, object_names in members.items():
        summary = base.summarize([records[obj] for obj in object_names])
        summary["design_scope"] = "placeholder_mass_only" if name in args.placeholder else "external_sample"
        expected = envelopes.get(name)
        if expected and summary["world_bounds"]:
            actual = summary["world_bounds"]
            outside = any(actual["min_m"][i] < expected["min_m"][i] - 1e-4 or
                          actual["max_m"][i] > expected["max_m"][i] + 1e-4 for i in range(3))
            summary["planned_envelope_m"] = expected
            summary["outside_planned_envelope"] = outside
            if outside:
                envelope_reviews.append("Outside declared study envelope: " + name)
        groups[name] = summary
    status = "FAIL" if errors or total["objects_with_errors"] else "REVIEW" if total["objects_with_warnings"] or envelope_reviews else "PASS"
    report = {
        "schema_version": 2, "generated_utc": datetime.now(timezone.utc).isoformat(),
        "blend_file": bpy.data.filepath, "blender_version": bpy.app.version_string,
        "status": status, "technical_status_only": True, "read_only": True,
        "scope": "Stored meshes in explicitly selected collections; deduplicated totals",
        "units": {"system": units.system, "scale_length": units.scale_length,
                  "length_unit": units.length_unit, "one_metre_per_blender_unit": unit_ok},
        "coordinate_basis": "Blender world metres; no Unreal axis conversion",
        "scene_errors": errors, "envelope_reviews": envelope_reviews,
        "collections": groups, "total_unique_new_meshes": total,
        "open_geometry": {
            "intentionally_open_objects": [r["name"] for r in objects if r["intentional_open_geometry"] and r["topology"]["boundary_edges"]],
            "unclassified_open_objects": [r["name"] for r in objects if not r["intentional_open_geometry"] and r["topology"]["boundary_edges"]],
            "negative_closed_shells": total["negative_closed_shells"],
        },
        "objects": objects,
    }
    report["limitations"] = [
        "PASS describes stored technical data, never architectural or visual completion.",
        "Active modifiers are reported but not evaluated. Stored bounds may differ from an evaluated export.",
        "Unit normal vectors and winding do not prove smooth curve shading, seam continuity, or reflection quality.",
        "Closed-shell signed volume can identify reversed orientation; intentional cavities still require inspection.",
        "Intentional open lettering/sheets are separately reported; self-intersections and duplicate coplanar faces are not tested.",
        "UV0/UV1 completeness and finite areas do not prove island separation, lightmap readiness, seam quality, or texel density.",
        "Material surface totals include backs and interiors; they are not facade glazing ratios.",
        "Bounds do not establish bridge accessibility, structural plausibility, street setbacks, or camera visibility.",
        "C placeholder is not detailed architecture. Context, cameras, lighting, UE materials, collision and runtime cost are excluded.",
    ]
    destination = Path(args.output).expanduser().resolve()
    if destination.suffix.lower() != ".json" or (bpy.data.filepath and destination == Path(bpy.data.filepath).resolve()):
        raise ValueError("Output must be a .json report, never the loaded blend")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(base.json_safe(report), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Curved district stored-mesh audit:", status, "|", total["triangles"], "triangles |", destination)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--collections", nargs="+", required=True)
    parser.add_argument("--placeholder", nargs="+", default=[])
    parser.add_argument("--envelope", action="append", default=[])
    main(parser.parse_args(argv))
