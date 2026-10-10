"""Read-only stored-mesh audit; never saves or edits the loaded .blend.

Usage: blender --background sample.blend --python validate_city_sample.py -- report.json
Stdlib check (no Blender): python validate_city_sample.py --self-test
Open attachments are recorded, not failed. Glass areas include all named-Glass
surfaces (including backs/interiors), not a measured exterior facade ratio.
"""

import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

TARGET_COLLECTIONS = ("Mall_Architecture", "Neighbor_Architecture")
AREA_EPS = 1e-12  # square metres / square UV units
VOLUME_EPS = 1e-9  # cubic metres


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def triangle_area(a, b, c):
    n = cross(sub(b, a), sub(c, a))
    return math.sqrt(dot(n, n)) / 2


def triangle_volume(a, b, c, origin=(0, 0, 0)):
    return dot(sub(a, origin), cross(sub(b, origin), sub(c, origin))) / 6


def uv_area(a, b, c):
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2


def bounds(points):
    finite = [p for p in points if all(math.isfinite(v) for v in p)]
    if not finite:
        return None
    low = [min(p[i] for p in finite) for i in range(3)]
    high = [max(p[i] for p in finite) for i in range(3)]
    return {"min_m": low, "max_m": high, "dimensions_m": sub(high, low)}


def topology(faces, edges):
    """Count incidence and connected surface shells, including winding conflicts."""
    uses = {tuple(sorted(edge)): [] for edge in edges}
    face_edges = []
    for index, face in enumerate(faces):
        ring = list(zip(face, face[1:] + face[:1]))
        face_edges.append([tuple(sorted(edge)) for edge in ring])
        for a, b in ring:
            uses.setdefault(tuple(sorted((a, b))), []).append((index, a, b))
    seen = set()
    components = []
    for start in range(len(faces)):
        if start in seen:
            continue
        pending = [start]
        seen.add(start)
        members = []
        component_edges = set()
        while pending:
            face = pending.pop()
            members.append(face)
            for edge in face_edges[face]:
                component_edges.add(edge)
                for neighbor, _, _ in uses[edge]:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        pending.append(neighbor)
        conflicts = sum(len(uses[e]) == 2 and uses[e][0][1:] == uses[e][1][1:] for e in component_edges)
        components.append({
            "face_indices": members,
            "closed": bool(component_edges) and all(len(uses[e]) == 2 for e in component_edges),
            "winding_conflict_edges": conflicts,
        })
    counts = Counter(len(v) for v in uses.values())
    return {
        "wire_edges": counts[0],
        "boundary_edges": counts[1],
        "over_shared_edges": sum(n for k, n in counts.items() if k > 2),
        "nonmanifold_edges": sum(n for k, n in counts.items() if k != 2),
        "winding_conflict_edges": sum(c["winding_conflict_edges"] for c in components),
        "components": components,
    }


def uv_report(mesh, triangles, index):
    if len(mesh.uv_layers) <= index:
        return {"present": False}
    layer = mesh.uv_layers[index]
    coords = [tuple(loop.uv) for loop in layer.data]
    finite = all(math.isfinite(v) for uv in coords for v in uv)
    complete = len(coords) == len(mesh.loops)
    areas = [uv_area(*(coords[i] for i in tri.loops)) for tri in triangles] if complete and finite else []
    return {
        "present": True,
        "name": layer.name,
        "loop_count": len(coords),
        "complete": complete,
        "finite": finite,
        "valid_area": bool(areas) and sum(areas) > AREA_EPS,
        "summed_triangle_area_uv2": sum(areas),
        "zero_area_triangles": sum(a <= AREA_EPS for a in areas),
        "outside_unit_square_loops": sum(any(v < 0 or v > 1 for v in uv) for uv in coords),
        "overlap_checked": False,
    }


def inspect_object(obj, memberships, metre_scale):
    mesh = obj.data
    # Only refresh Blender's triangulation cache; no mesh edits or save operators.
    mesh.calc_loop_triangles()
    triangles = list(mesh.loop_triangles)
    points = [tuple(float(v) * metre_scale for v in (obj.matrix_world @ vert.co)) for vert in mesh.vertices]
    finite = all(math.isfinite(v) for p in points for v in p)
    box = bounds(points)
    origin = tuple((a + b) / 2 for a, b in zip(box["min_m"], box["max_m"])) if box else (0, 0, 0)
    faces = [list(poly.vertices) for poly in mesh.polygons]
    edge_info = topology(faces, [tuple(e.vertices) for e in mesh.edges])
    areas_by_face = [0.0] * len(faces)
    volumes_by_face = [0.0] * len(faces)
    material_areas = defaultdict(float)
    zero_triangles = 0
    invalid_material_faces = set()
    materials = [slot.material.name if slot.material else None for slot in obj.material_slots]
    for tri in triangles:
        a, b, c = (points[i] for i in tri.vertices)
        area = triangle_area(a, b, c)
        zero_triangles += area <= AREA_EPS
        areas_by_face[tri.polygon_index] += area
        volumes_by_face[tri.polygon_index] += triangle_volume(a, b, c, origin)
        material_index = mesh.polygons[tri.polygon_index].material_index
        if material_index >= len(materials) or materials[material_index] is None:
            invalid_material_faces.add(tri.polygon_index)
            material = "<unassigned>"
        else:
            material = materials[material_index]
        material_areas[material] += area
    shells = []
    for index, component in enumerate(edge_info.pop("components")):
        volume = sum(volumes_by_face[i] for i in component["face_indices"])
        shells.append({
            "index": index,
            "faces": len(component["face_indices"]),
            "closed": component["closed"],
            "winding_conflict_edges": component["winding_conflict_edges"],
            "signed_volume_m3": volume if component["closed"] else None,
            "negative_signed_volume": component["closed"] and volume < -VOLUME_EPS,
            "near_zero_closed_volume": component["closed"] and abs(volume) <= VOLUME_EPS,
            "normal_orientation": ("inconsistent" if component["winding_conflict_edges"] else
                                   "inward_or_cavity" if component["closed"] and volume < -VOLUME_EPS else
                                   "outward" if component["closed"] and volume > VOLUME_EPS else "undetermined"),
        })
    uv0, uv1 = (uv_report(mesh, triangles, i) for i in range(2))
    applied = all(math.isfinite(v) and abs(v - 1) <= 1e-6 for v in obj.scale)
    modifiers = [m.name + ":" + m.type for m in obj.modifiers if m.show_viewport or m.show_render]
    errors, warnings, notes = [], [], []
    if not finite:
        errors.append("Nonfinite world geometry")
    if not len(faces):
        errors.append("Mesh has no faces")
    zero_faces = sum(a <= AREA_EPS for a in areas_by_face)
    if zero_faces or zero_triangles:
        errors.append("Zero-area polygons or triangles")
    if not uv0.get("present") or not uv0.get("complete") or not uv0.get("finite") or not uv0.get("valid_area"):
        errors.append("UV0 missing, incomplete, nonfinite, or has no valid area")
    if not applied:
        warnings.append("Object scale is not applied")
    if not uv1.get("present"):
        warnings.append("UV1 absent; lightmap readiness needs review")
    elif not uv1.get("complete") or not uv1.get("finite") or not uv1.get("valid_area") or uv1.get("zero_area_triangles"):
        warnings.append("UV1 is incomplete, nonfinite, or has degenerate area")
    if uv0.get("zero_area_triangles", 0):
        warnings.append("UV0 has degenerate triangles")
    if invalid_material_faces:
        warnings.append("Faces reference empty or missing material slots")
    if edge_info["winding_conflict_edges"]:
        warnings.append("Adjacent faces have inconsistent winding")
    if any(s["negative_signed_volume"] for s in shells):
        warnings.append("Closed shell has negative signed volume; inspect inward normals/cavity intent")
    if any(s["near_zero_closed_volume"] for s in shells):
        warnings.append("Closed shell has near-zero volume")
    if edge_info["nonmanifold_edges"]:
        notes.append("Open/wire/over-shared edges recorded; architectural attachments may intentionally be open")
    if modifiers:
        warnings.append("Active modifiers exist; report measures stored mesh, not evaluated export")
    surface = sum(material_areas.values())
    glass = sum(a for name, a in material_areas.items() if "glass" in name.lower())
    return {
        "name": obj.name, "mesh": mesh.name, "collections": memberships,
        "vertices": len(mesh.vertices), "edges": len(mesh.edges), "polygons": len(faces), "triangles": len(triangles),
        "world_bounds": box, "finite_geometry": finite,
        "object_scale": tuple(obj.scale), "scale_applied": applied,
        "world_transform_determinant": obj.matrix_world.to_3x3().determinant(),
        "material_slots": materials, "unassigned_material_faces": len(invalid_material_faces),
        "surface_area_m2": surface, "material_area_m2": dict(sorted(material_areas.items())),
        "glass_named_surface_area_m2": glass,
        "glass_fraction_of_all_mesh_surfaces": glass / surface if surface > AREA_EPS else None,
        "zero_area_polygons": zero_faces, "zero_area_triangles": zero_triangles,
        "uv0": uv0, "uv1": uv1, "topology": edge_info, "surface_components": shells,
        "active_modifiers": modifiers, "errors": errors, "warnings": warnings, "notes": notes,
    }


def summarize(objects):
    points = [tuple(b[k]) for obj in objects if (b := obj["world_bounds"]) for k in ("min_m", "max_m")]
    materials = defaultdict(float)
    for obj in objects:
        for name, area in obj["material_area_m2"].items():
            materials[name] += area
    return {
        "mesh_objects": len(objects), "world_bounds": bounds(points),
        "vertices": sum(obj["vertices"] for obj in objects),
        "polygons": sum(obj["polygons"] for obj in objects),
        "triangles": sum(obj["triangles"] for obj in objects),
        "surface_area_m2": sum(obj["surface_area_m2"] for obj in objects),
        "glass_named_surface_area_m2": sum(obj["glass_named_surface_area_m2"] for obj in objects),
        "material_area_m2": dict(sorted(materials.items())),
        "objects_with_errors": sum(bool(obj["errors"]) for obj in objects),
        "objects_with_warnings": sum(bool(obj["warnings"]) for obj in objects),
        "negative_closed_shells": sum(sum(s["negative_signed_volume"] for s in obj["surface_components"]) for obj in objects),
    }


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    return value


def main(output):
    import bpy

    units = bpy.context.scene.unit_settings
    unit_ok = units.system == "METRIC" and math.isclose(units.scale_length, 1, rel_tol=0, abs_tol=1e-9)
    errors = [] if unit_ok else ["Scene must use Metric with 1 metre per Blender unit (scale_length=1)"]
    records, collection_members = {}, {}
    for name in TARGET_COLLECTIONS:
        collection = bpy.data.collections.get(name)
        if collection is None:
            errors.append("Missing required collection: " + name)
            collection_members[name] = []
            continue
        members = [obj for obj in collection.all_objects if obj.type == "MESH"]
        if not members:
            errors.append("Required collection contains no meshes: " + name)
        collection_members[name] = [obj.name for obj in members]
        for obj in members:
            if obj.name not in records:
                memberships = [n for n in TARGET_COLLECTIONS if bpy.data.collections.get(n) and obj.name in bpy.data.collections[n].all_objects]
                records[obj.name] = inspect_object(obj, memberships, units.scale_length)
    objects = [records[name] for name in sorted(records)]
    total = summarize(objects)
    status = "FAIL" if errors or total["objects_with_errors"] else "REVIEW" if total["objects_with_warnings"] else "PASS"
    context = bpy.data.collections.get("Existing_City_Context")
    report = {
        "schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
        "blend_file": bpy.data.filepath, "blender_version": bpy.app.version_string,
        "audit_scope": "Stored mesh data in Mall_Architecture and Neighbor_Architecture, including child collections; unique totals",
        "read_only": True, "modifiers_evaluated": False,
        "coordinate_basis": "Blender world coordinates in metres; no axis conversion performed",
        "units": {"system": units.system, "scale_length": units.scale_length, "length_unit": units.length_unit,
                  "one_metre_per_blender_unit": unit_ok},
        "status": status, "scene_errors": errors,
        "collections": {name: summarize([records[n] for n in members]) for name, members in collection_members.items()},
        "total_unique_new_meshes": total, "objects": objects,
        "excluded": {"Existing_City_Context": {"strict_checks": False, "objects": len(context.all_objects) if context else 0},
                     "Cameras": "Not audited", "Lighting": "Not audited"},
        "limitations": [
            "Glass-named material surface areas include all faces; exact visible exterior glazing ratio requires facade selection or image review.",
            "Signed volume establishes closed-shell orientation, not design intent; an intentional cavity can have inward winding.",
            "Normal orientation is derived from face winding; custom split shading normals are not validated.",
            "Open attachments are recorded and do not automatically fail. Self-intersections and UV overlaps are not tested.",
            "Stored meshes are counted before modifiers; UV1 presence does not prove nonoverlapping lightmap UVs.",
        ],
    }
    destination = Path(output).expanduser().resolve()
    if destination.suffix.lower() == ".blend" or (bpy.data.filepath and destination == Path(bpy.data.filepath).resolve()):
        raise ValueError("Report destination must not overwrite a .blend file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(json_safe(report), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("City sample audit:", status, "|", total["triangles"], "triangles |", destination)


def self_test():
    assert math.isclose(triangle_area((0, 0, 0), (2, 0, 0), (0, 3, 0)), 3)
    assert math.isclose(uv_area((0, 0), (1, 0), (0, 1)), 0.5)
    cube = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    closed = topology([list(f) for f in cube], [])
    assert closed["nonmanifold_edges"] == 0 and closed["winding_conflict_edges"] == 0
    assert len(closed["components"]) == 1 and closed["components"][0]["closed"]
    opened = topology([list(f) for f in cube[:-1]], [])
    assert opened["boundary_edges"] == 4 and not opened["components"][0]["closed"]
    flipped = topology([list(f) for f in cube[:-1]] + [list(reversed(cube[-1]))], [])
    assert flipped["winding_conflict_edges"] == 4
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    cube_volume = sum(triangle_volume(verts[f[0]], verts[f[i]], verts[f[i + 1]]) for f in cube for i in range(1, len(f) - 1))
    assert math.isclose(cube_volume, 1)
    assert math.isclose(triangle_volume((1, 0, 0), (0, 1, 0), (0, 0, 1)), 1 / 6)
    assert math.isclose(triangle_volume((1, 0, 0), (0, 0, 1), (0, 1, 0)), -1 / 6)
    assert json_safe({"bad": float("nan"), "good": 1}) == {"bad": None, "good": 1}
    print("Self-check passed: triangle/UV area, closed/open topology, winding, signed volume, finite JSON")


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if arguments == ["--self-test"]:
        self_test()
    elif len(arguments) == 1:
        main(arguments[0])
    else:
        raise SystemExit("Usage: blender --background sample.blend --python validate_city_sample.py -- report.json")
