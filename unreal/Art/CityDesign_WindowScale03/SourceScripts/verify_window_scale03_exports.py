"""Independent stdlib audit of the two scoped Blender GLB exports.

Usage:
  python verify_window_scale03_exports.py Commercial.glb OfficeVisible.glb \
    --output export_audit.json

Reads both exports, writes only the requested JSON report, and exits nonzero on
failure. Never launches Blender/UE or changes either input. GLB data is decoded
independently from the saved .blend audit; overlap/self-intersection are not tested.
"""

import argparse
import hashlib
import json
import math
import re
import struct
from datetime import datetime, timezone
from pathlib import Path


FORMATS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
REQUIRED = {"POSITION": "VEC3", "NORMAL": "VEC3", "TEXCOORD_0": "VEC2", "TEXCOORD_1": "VEC2"}
FORBIDDEN_NAME = re.compile(r"context|placeholder|not[_ .-]*finished|skyline[_ .-]*blockout|(^|[_ .-])c($|[_ .-])", re.I)
AREA_EPS = 1e-12  # square metres, after node transforms
NORMAL_EPS = 1e-3


def load_glb(path):
    raw = path.read_bytes()
    if len(raw) < 20:
        raise ValueError("GLB is too short")
    magic, version, length = struct.unpack_from("<4sII", raw)
    if magic != b"glTF" or version != 2 or length != len(raw):
        raise ValueError("Invalid GLB v2 header or total byte length")
    chunks, cursor = [], 12
    while cursor < len(raw):
        if cursor + 8 > len(raw):
            raise ValueError("Truncated GLB chunk header")
        size, kind = struct.unpack_from("<II", raw, cursor)
        cursor += 8
        if size % 4 or cursor + size > len(raw):
            raise ValueError("Invalid GLB chunk size/alignment")
        chunks.append((kind, raw[cursor:cursor + size]))
        cursor += size
    if not chunks or chunks[0][0] != 0x4E4F534A:
        raise ValueError("GLB must start with the JSON chunk")
    json_chunks = [data for kind, data in chunks if kind == 0x4E4F534A]
    bin_chunks = [data for kind, data in chunks if kind == 0x004E4942]
    if len(json_chunks) != 1 or len(bin_chunks) != 1:
        raise ValueError("Expected one JSON chunk and one embedded BIN chunk")
    document = json.loads(json_chunks[0].decode("utf-8").rstrip(" \t\r\n\0"))
    if document.get("asset", {}).get("version") != "2.0":
        raise ValueError("Expected glTF asset version 2.0")
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or buffers[0].get("uri"):
        raise ValueError("Expected one embedded buffer; external buffers are outside this audit")
    declared = buffers[0]["byteLength"]
    if declared < 0 or declared > len(bin_chunks[0]) or len(bin_chunks[0]) - declared > 3:
        raise ValueError("BIN length differs from declared embedded buffer length")
    return document, bin_chunks[0][:declared], raw


def decode_rows(document, binary, view_index, offset, count, component_type, width, normalized=False):
    views = document.get("bufferViews", [])
    if not isinstance(view_index, int) or not 0 <= view_index < len(views):
        raise ValueError("Invalid bufferView reference")
    view = views[view_index]
    if view.get("buffer", 0) != 0:
        raise ValueError("bufferView references an unsupported buffer")
    fmt = "<" + FORMATS[component_type] * width
    element_size = struct.calcsize(fmt)
    stride = view.get("byteStride", element_size)
    view_offset, view_length = view.get("byteOffset", 0), view["byteLength"]
    required = (count - 1) * stride + element_size if count else 0
    if count < 0 or stride < element_size or offset < 0 or view_offset < 0 or view_length < 0:
        raise ValueError("Invalid accessor/view count, stride, or offset")
    if offset + required > view_length or view_offset + view_length > len(binary):
        raise ValueError("Accessor extends outside its bufferView or embedded BIN")
    rows = [struct.unpack_from(fmt, binary, view_offset + offset + i * stride) for i in range(count)]
    if normalized and component_type != 5126:
        maximum = {5120: 127, 5121: 255, 5122: 32767, 5123: 65535, 5125: 4294967295}[component_type]
        signed = component_type in (5120, 5122)
        rows = [tuple(max(v / maximum, -1) if signed else v / maximum for v in row) for row in rows]
    return rows


def accessor(document, binary, index):
    entries = document.get("accessors", [])
    if not isinstance(index, int) or not 0 <= index < len(entries):
        raise ValueError("Invalid accessor reference")
    entry = entries[index]
    width = COMPONENTS[entry["type"]]
    kind, count = entry["componentType"], entry["count"]
    if "bufferView" in entry:
        rows = decode_rows(document, binary, entry["bufferView"], entry.get("byteOffset", 0),
                           count, kind, width, entry.get("normalized", False))
    else:
        rows = [(0,) * width for _ in range(count)]
    sparse = entry.get("sparse")
    if sparse:
        si, sv, number = sparse["indices"], sparse["values"], sparse["count"]
        if si["componentType"] not in (5121, 5123, 5125) or not 0 <= number <= count:
            raise ValueError("Invalid sparse accessor index type/count")
        indices = decode_rows(document, binary, si["bufferView"], si.get("byteOffset", 0), number, si["componentType"], 1)
        values = decode_rows(document, binary, sv["bufferView"], sv.get("byteOffset", 0), number, kind, width, entry.get("normalized", False))
        previous = -1
        for (vertex,), value in zip(indices, values):
            if not previous < vertex < count:
                raise ValueError("Sparse indices are unsorted, repeated, or outside the accessor")
            rows[vertex], previous = value, vertex
    return entry, rows


def identity():
    return [[float(r == c) for c in range(4)] for r in range(4)]


def multiply(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def node_matrix(node):
    if "matrix" in node:
        if any(key in node for key in ("translation", "rotation", "scale")) or len(node["matrix"]) != 16:
            raise ValueError("Node has an invalid matrix/TRS combination")
        matrix = [[node["matrix"][c * 4 + r] for c in range(4)] for r in range(4)]
    else:
        translation = node.get("translation", [0, 0, 0])
        scale = node.get("scale", [1, 1, 1])
        rotation = node.get("rotation", [0, 0, 0, 1])
        if len(translation) != 3 or len(scale) != 3 or len(rotation) != 4:
            raise ValueError("Node TRS vector lengths are invalid")
        if not all(math.isfinite(v) for v in translation + scale + rotation):
            raise ValueError("Node TRS contains nonfinite values")
        if abs(sum(v*v for v in rotation) - 1) > 1e-3:
            raise ValueError("Node rotation quaternion is not unit length")
        x, y, z, w = rotation
        matrix = [
            [(1-2*y*y-2*z*z)*scale[0], (2*x*y-2*z*w)*scale[1], (2*x*z+2*y*w)*scale[2], translation[0]],
            [(2*x*y+2*z*w)*scale[0], (1-2*x*x-2*z*z)*scale[1], (2*y*z-2*x*w)*scale[2], translation[1]],
            [(2*x*z-2*y*w)*scale[0], (2*y*z+2*x*w)*scale[1], (1-2*x*x-2*y*y)*scale[2], translation[2]],
            [0, 0, 0, 1],
        ]
    if not all(math.isfinite(v) for row in matrix for v in row):
        raise ValueError("Node matrix contains nonfinite values")
    if any(abs(a-b) > 1e-6 for a, b in zip(matrix[3], [0, 0, 0, 1])):
        raise ValueError("Node transform is not affine")
    return matrix


def determinant(matrix):
    a, b, c = [row[:3] for row in matrix[:3]]
    return a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])


def transform(matrix, point):
    return tuple(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3] for r in range(3))


def bounds(points):
    if not points:
        return None
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    return {"min_m": low, "max_m": high, "dimensions_m": [high[i]-low[i] for i in range(3)]}


def triangle_area(a, b, c):
    u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
    cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    return math.sqrt(sum(value*value for value in cross))/2


def scene_instances(document):
    scenes, nodes = document.get("scenes", []), document.get("nodes", [])
    scene_index = document.get("scene", 0)
    if not scenes or not 0 <= scene_index < len(scenes):
        raise ValueError("Missing valid default scene")
    visited, instances = set(), []

    def visit(index, parent):
        if not isinstance(index, int) or not 0 <= index < len(nodes) or index in visited:
            raise ValueError("Scene graph has invalid/repeated node references or a cycle")
        visited.add(index)
        node = nodes[index]
        world = multiply(parent, node_matrix(node))
        if "mesh" in node:
            if not 0 <= node["mesh"] < len(document.get("meshes", [])):
                raise ValueError("Node mesh reference is outside the meshes array")
            instances.append((index, node, world))
        for child in node.get("children", []):
            visit(child, world)

    for root in scenes[scene_index].get("nodes", []):
        visit(root, identity())
    return instances


def inspect_primitive(document, binary, primitive, world, prefix, errors):
    attributes = primitive.get("attributes", {})
    rows, checks = {}, {}
    for semantic, expected in REQUIRED.items():
        if semantic not in attributes:
            errors.append(prefix + ": missing " + semantic)
            continue
        entry, values = accessor(document, binary, attributes[semantic])
        finite = all(math.isfinite(value) for row in values for value in row)
        checks[semantic] = {"accessor": attributes[semantic], "count": len(values),
                            "type": entry["type"], "component_type": entry["componentType"], "finite": finite}
        if entry["type"] != expected or not finite:
            errors.append(prefix + ": invalid shape or nonfinite " + semantic)
        elif semantic in ("POSITION", "NORMAL") and entry["componentType"] != 5126:
            errors.append(prefix + ": POSITION/NORMAL must be FLOAT for this export audit")
        rows[semantic] = values
    if "POSITION" not in rows or checks["POSITION"]["type"] != "VEC3" or not checks["POSITION"]["finite"]:
        return {"attributes": checks}, []
    count = len(rows["POSITION"])
    if not count:
        errors.append(prefix + ": no vertices")
    for semantic in rows:
        if len(rows[semantic]) != count:
            errors.append(prefix + ": " + semantic + " count differs from POSITION")
    if "NORMAL" in rows:
        bad_normals = sum(not all(math.isfinite(v) for v in normal) or
                          abs(math.sqrt(sum(v*v for v in normal))-1) > NORMAL_EPS for normal in rows["NORMAL"])
        checks["NORMAL"]["nonunit_or_nonfinite_count"] = bad_normals
        if bad_normals:
            errors.append(prefix + ": nonunit or nonfinite stored normals")
    for semantic in ("TEXCOORD_0", "TEXCOORD_1"):
        if semantic in rows:
            checks[semantic]["outside_unit_square_vertices"] = sum(any(v < -1e-6 or v > 1+1e-6 for v in uv) for uv in rows[semantic])
            checks[semantic]["overlap_checked"] = False
    material_index = primitive.get("material")
    if not isinstance(material_index, int) or not 0 <= material_index < len(document.get("materials", [])):
        errors.append(prefix + ": missing or invalid material section")
    if primitive.get("mode", 4) != 4:
        errors.append(prefix + ": expected TRIANGLES mode")
        return {"attributes": checks, "material": material_index}, []
    if "indices" in primitive:
        entry, values = accessor(document, binary, primitive["indices"])
        if entry["type"] != "SCALAR" or entry["componentType"] not in (5121, 5123, 5125) or entry.get("normalized"):
            errors.append(prefix + ": invalid index accessor type")
            return {"attributes": checks, "material": material_index}, []
        indices = [row[0] for row in values]
    else:
        indices = list(range(count))
    invalid_indices = sum(not isinstance(i, int) or not 0 <= i < count for i in indices)
    if invalid_indices or len(indices) % 3:
        errors.append(prefix + ": out-of-bounds indices or incomplete triangle index triplet")
    points = [transform(world, p) for p in rows["POSITION"]]
    world_finite = all(math.isfinite(v) for point in points for v in point)
    if not world_finite:
        errors.append(prefix + ": nonfinite transformed positions")
    areas = []
    if not invalid_indices and not len(indices) % 3 and world_finite:
        areas = [triangle_area(*(points[indices[i+j]] for j in range(3))) for i in range(0, len(indices), 3)]
    zero = sum(area <= AREA_EPS or not math.isfinite(area) for area in areas)
    if zero:
        errors.append(prefix + ": degenerate/nonfinite world-space triangles")
    return {
        "attributes": checks, "material": material_index, "vertices": count,
        "indices_present": "indices" in primitive, "indices": len(indices),
        "out_of_bounds_indices": invalid_indices, "triangles": len(indices)//3,
        "world_positions_finite": world_finite, "zero_or_nonfinite_area_triangles": zero,
        "minimum_triangle_area_m2": min(areas) if areas else None,
        "gltf_world_bounds_m": bounds(points) if world_finite else None,
    }, points if world_finite else []


def audit_file(path, label, expected_meshes):
    result = {"scope": label, "path": str(path), "expected_mesh_count": expected_meshes, "errors": []}
    errors = result["errors"]
    try:
        document, binary, raw = load_glb(path)
        result.update({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                       "gltf_version": document["asset"]["version"], "generator": document["asset"].get("generator")})
        nodes, meshes = document.get("nodes", []), document.get("meshes", [])
        forbidden = [item.get("name", "") for item in nodes + meshes if FORBIDDEN_NAME.search(item.get("name", ""))]
        cameras = len(document.get("cameras", []))
        lights = len(document.get("extensions", {}).get("KHR_lights_punctual", {}).get("lights", []))
        camera_nodes = sum("camera" in node for node in nodes)
        light_nodes = sum("KHR_lights_punctual" in node.get("extensions", {}) for node in nodes)
        result["scope_exclusions"] = {"forbidden_names": forbidden, "cameras": cameras,
                                     "camera_nodes": camera_nodes, "punctual_lights": lights, "light_nodes": light_nodes}
        if forbidden or cameras or lights or camera_nodes or light_nodes:
            errors.append("Export contains C/placeholder/context names, cameras, or punctual lights")
        if len(meshes) != expected_meshes:
            errors.append("Unexpected number of mesh definitions")
        instances = scene_instances(document)
        if len(instances) != expected_meshes or len({node["mesh"] for _, node, _ in instances}) != expected_meshes:
            errors.append("Unexpected number of reachable distinct mesh instances")
        records, all_points = [], []
        for node_index, node, world in instances:
            mesh_index = node["mesh"]
            mesh = meshes[mesh_index]
            name = node.get("name", "node_" + str(node_index))
            det = determinant(world)
            if not math.isfinite(det) or det <= 1e-12:
                errors.append(name + ": reflected, singular, or nonfinite world transform")
            primitives = []
            for index, primitive in enumerate(mesh.get("primitives", [])):
                record, points = inspect_primitive(document, binary, primitive, world, name + "/primitive_" + str(index), errors)
                primitives.append(record)
                all_points.extend(points)
            if not primitives:
                errors.append(name + ": mesh has no primitive sections")
            records.append({"node_index": node_index, "node": name, "mesh_index": mesh_index,
                            "mesh": mesh.get("name"), "world_matrix_rows": world,
                            "world_transform_determinant": det, "primitives": primitives,
                            "triangles": sum(p.get("triangles", 0) for p in primitives)})
        result["counts"] = {"nodes": len(nodes), "meshes": len(meshes), "reachable_mesh_nodes": len(instances),
                            "primitive_sections": sum(len(record["primitives"]) for record in records),
                            "materials": len(document.get("materials", [])), "images": len(document.get("images", [])),
                            "textures": len(document.get("textures", [])), "triangles": sum(r["triangles"] for r in records)}
        result["material_names"] = [m.get("name") for m in document.get("materials", [])]
        result["meshes"] = records
        result["gltf_world_bounds_m"] = bounds(all_points)
        result["blender_world_bounds_m"] = bounds([(x, -z, y) for x, y, z in all_points])
        result["ue_world_bounds_m"] = bounds([(x, z, y) for x, y, z in all_points])
    except (OSError, ValueError, KeyError, IndexError, TypeError, OverflowError, struct.error) as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
    result["status"] = "FAIL" if errors else "PASS"
    return result


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value



OFFICE_NAMES = ["OOW_View_Office_B07", "OOW_View_Office_B08", "OOW_View_Office_B13"]
COMMERCIAL_NAMES = ["OOW_Curved_A", "OOW_Curved_B", "OOW_Curved_Bridge", "OOW_Curved_Court"]


def check_names_and_channels(record, path, expected_names, no_color0):
    errors = record["errors"]
    actual = [mesh["node"] for mesh in record.get("meshes", [])]
    matched = sorted(actual) == sorted(expected_names) and len(actual) == len(set(actual))
    record["name_check"] = {"expected_mesh_node_names": expected_names,
                            "actual_mesh_node_names": actual, "exact_match": matched,
                            "mesh_datablock_names": [mesh.get("mesh") for mesh in record.get("meshes", [])]}
    if not matched:
        errors.append("Exported mesh node names do not exactly match the scoped names")
    outside = sum(primitive.get("attributes", {}).get("TEXCOORD_1", {}).get("outside_unit_square_vertices", 0)
                  for mesh in record.get("meshes", []) for primitive in mesh.get("primitives", []))
    record["uv1_unit_square_check"] = {"outside_vertices": outside, "tolerance": 1e-6,
                                       "overlap_checked": False, "blender_uv_layer_names_available_in_gltf": False}
    if outside:
        errors.append("TEXCOORD_1 extends outside the packed unit square")
    if "sha256" in record:
        try:
            document, _, raw = load_glb(path)
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                errors.append("Input changed between binary data and scope checks")
            color0 = [{"mesh": mesh.get("name"), "primitive": index}
                      for mesh in document.get("meshes", [])
                      for index, primitive in enumerate(mesh.get("primitives", []))
                      if "COLOR_0" in primitive.get("attributes", {})]
            record["color0_check"] = {"required_absent": no_color0, "primitive_count": len(color0), "primitives": color0}
            if no_color0 and color0:
                errors.append("OfficeVisible contains COLOR_0 despite the clean export-clone requirement")
        except (OSError, ValueError, KeyError, IndexError, TypeError, struct.error) as exc:
            errors.append("Additional scope check: " + type(exc).__name__ + ": " + str(exc))
    record["status"] = "FAIL" if errors else "PASS"
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commercial", type=Path)
    parser.add_argument("office_visible", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commercial-names", nargs=4, default=COMMERCIAL_NAMES,
                        help="Exact commercial mesh node names; default uses OOW_Curved_A/B/Bridge/Court")
    args = parser.parse_args()
    paths = [args.commercial.expanduser().resolve(), args.office_visible.expanduser().resolve()]
    output = args.output.expanduser().resolve()
    if output.suffix.lower() != ".json" or output in paths:
        parser.error("--output must be a separate .json report")
    if len(set(args.commercial_names)) != 4:
        parser.error("The four commercial names must be distinct")
    records = [
        check_names_and_channels(audit_file(paths[0], "A+B+Bridge+Court, excluding C and context", 4),
                                 paths[0], args.commercial_names, False),
        check_names_and_channels(audit_file(paths[1], "Three actual whole office buildings B07/B08/B13 with visible facade improvements", 3),
                                 paths[1], OFFICE_NAMES, True),
    ]
    status = "PASS" if all(record["status"] == "PASS" for record in records) else "FAIL"
    report = {
        "schema_version": 2,
        "audit_type": "Independent WindowScale03 GLB byte/JSON audit using Python standard library",
        "generated_utc": datetime.now(timezone.utc).isoformat(), "status": status,
        "technical_status_only": True, "inputs_read_only": True, "files": records,
        "expected_scope": {"commercial_objects_and_meshes": 4, "office_objects_and_meshes": 3,
                           "office_geometry": "Whole B07/B08/B13 exports include improved visible facade and original nonvisible source geometry",
                           "excluded": ["Other city/context geometry", "C placeholder", "Cameras", "Punctual lights", "Separate office corner trial"]},
        "tolerances": {"zero_triangle_area_m2": AREA_EPS, "stored_normal_length": NORMAL_EPS},
        "units_and_axes": {
            "gltf": "glTF 2.0 positions are metres, right-handed +Y up; transformed world bounds are reported",
            "blender_bounds_conversion": "(glTF x, -glTF z, glTF y)",
            "ue_bounds_conversion": "(glTF x, glTF z, glTF y), metres; multiply by 100 for UE centimetres",
            "intended_physical_scale_verified": False,
        },
        "limitations": [
            "No Blender, UE, render, model edit or export operation is performed.",
            "Expected node names, distinct mesh counts and camera/light fields verify the serialized scope; renamed or disguised extra geometry inside a valid named mesh cannot be detected automatically.",
            "Office buildings intentionally retain their original nonvisible source geometry; those faces are included in counts and bounds rather than treated as forbidden context.",
            "UV0/UV1 mean glTF TEXCOORD_0/TEXCOORD_1. GLB does not retain Blender layer names, so it cannot prove the layers were called UVMap/LightmapUV.",
            "Finite UV data and UV1 inside the unit square do not prove lightmap readiness, island separation or texel density. UV overlaps are not tested.",
            "Self-intersections, duplicate/coplanar surfaces, watertightness, facade engineering and new glass thickness are not tested; source-mesh checks handle glass thickness separately.",
            "Stored unit normals do not establish smooth curve reflections, intended split-normal shading or material fidelity.",
            "COLOR_0 absence in OfficeVisible confirms the export cleanup only; it does not prove correct saved UE materials or night emission behavior.",
            "Metre units and valid triangles do not prove intended real-world dimensions or fixed-window visual quality. Technical PASS is not final art approval.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(json_safe(report), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for record in records:
        print(record["status"], "|", record["path"], "|", record.get("counts", {}).get("triangles", "unavailable"), "triangles")
        for error in record["errors"]:
            print("  " + error)
    print("WindowScale03 GLB export audit:", status, "|", output)
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
