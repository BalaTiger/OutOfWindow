"""Read-only stdlib dimensional audit of original visible City office meshes.
Uses the sibling GLB binary reader; never executes modeling or UE scripts.
Writes original_office_geometry_audit.json in this script's workspace only.
"""
import ast
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from verify_curved_exports import accessor, bounds, load_glb, scene_instances, transform


PROJECT = Path(r"C:\Users\zhuzi\Documents\OutOfWindow")
ART = PROJECT / "unreal/Art/City"
SCRIPTS = PROJECT / "unreal/Scripts"
TARGETS = {"B04", "B05", "B06", "B07", "B08"}


def source_buildings(text):
    section = re.search(r"const buildings = \[(.*?)\n\];", text, re.S).group(1)
    return [ast.literal_eval("[" + row + "]") for row in re.findall(r"\[([^\[\]]+)\]", section)]


def source_levels(row):
    x, z, w, d, h, style, stone = row
    levels = [{"part": "podium", "base_glTF_y_m": 6.9, "width_x_m": w+4, "depth_glTF_z_m": d+4,
               "floors": 1, "height_m": 5.2, "floor_spacing_m": 5.2}]
    tower = h-5.2
    if style == "terrace":
        lower = math.floor(tower*.62/3.3+.5)*3.3
        levels.append({"part": "lower_tower", "base_glTF_y_m": 12.1, "width_x_m": w, "depth_glTF_z_m": d,
                       "floors": math.floor(lower/3.3+.5), "height_m": lower, "floor_spacing_m": 3.3})
        upper = tower-lower-.15
        floors = max(2, math.floor((tower-lower)/3.3+.5))
        levels.append({"part": "setback_upper_tower", "base_glTF_y_m": 12.1+lower+.15,
                       "width_x_m": w*.78, "depth_glTF_z_m": d*.76, "floors": floors,
                       "height_m": upper, "floor_spacing_m": upper/floors,
                       "centre_x_m": x + (1 if x > 0 else -1)*w*.065, "centre_glTF_z_m": z-d*.04})
    else:
        floors = math.floor(tower/3.3+.5)
        levels.append({"part": "tower", "base_glTF_y_m": 12.1, "width_x_m": w, "depth_glTF_z_m": d,
                       "floors": floors, "height_m": tower, "floor_spacing_m": tower/floors})
    return levels


def components(points, indices):
    """Weld coordinates at 10 micrometres, then connect triangles by common edges.
    This recovers separate source modules approximately; it is not an exact part-ID audit.
    """
    keys = [tuple(round(v, 5) for v in point) for point in points]
    tris = [indices[i:i+3] for i in range(0, len(indices), 3)]
    parent = list(range(len(tris)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = {}
    for i, triangle in enumerate(tris):
        vertices = [keys[v] for v in triangle]
        for a, b in zip(vertices, vertices[1:]+vertices[:1]):
            edge = tuple(sorted((a,b)))
            if a == b:
                continue
            if edge in edges:
                parent[root(i)] = root(edges[edge])
            else:
                edges[edge] = i
    groups = defaultdict(list)
    for i, triangle in enumerate(tris):
        groups[root(i)].append(triangle)
    result = []
    for triangles in groups.values():
        used = {v for triangle in triangles for v in triangle}
        box = bounds([points[v] for v in used])
        result.append({"triangles": len(triangles), "bounds_glTF_m": box,
                       "dimensions_x_height_depth_m": box["dimensions_m"]})
    return result


def group_dimensions(modules, predicate):
    selected = [module for module in modules if predicate(module["dimensions_x_height_depth_m"])]
    counter = Counter((module["material"],) + tuple(round(v, 5) for v in module["dimensions_x_height_depth_m"]) for module in selected)
    return [{"material": key[0], "dimensions_x_height_depth_m": key[1:], "count": count}
            for key, count in sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))]


def main():
    document, binary, raw = load_glb(ART / "modern-city.glb")
    metadata = json.loads((ART / "modern-city.json").read_text(encoding="utf-8"))
    source = (SCRIPTS / "prepare_modern_city.mjs").read_text(encoding="utf-8")
    rows = source_buildings(source)
    cache = {}

    def values(index):
        if index not in cache:
            cache[index] = accessor(document, binary, index)[1]
        return cache[index]

    records = []
    for _, node, world in scene_instances(document):
        match = re.match(r"CityModern_(B\d+)_", node.get("name", ""))
        if not match or match[1] not in TARGETS:
            continue
        building = match[1]
        index = int(building[1:])-1
        row = rows[index]
        original_meta = next(entry for entry in metadata["buildings"] if entry["name"] == node["name"])
        mesh = document["meshes"][node["mesh"]]
        all_points, modules, panes, material_records = [], [], [], []
        non_glass_color_nonzero = 0
        for primitive in mesh["primitives"]:
            attrs = primitive["attributes"]
            local = values(attrs["POSITION"])
            points = [transform(world, point) for point in local]
            indices = [entry[0] for entry in values(primitive["indices"])]
            used = sorted(set(indices))
            selected = [points[i] for i in used]
            all_points.extend(selected)
            material = document["materials"][primitive["material"]]
            name = material["name"]
            colors = values(attrs["COLOR_0"]) if "COLOR_0" in attrs else []
            if "Glass" not in name:
                non_glass_color_nonzero += sum(any(abs(v) > 1e-8 for v in colors[i]) for i in used) if colors else 0
            material_records.append({"name": name, "indexed_triangles": len(indices)//3,
                                     "bounds_glTF_m": bounds(selected), "pbr": material.get("pbrMetallicRoughness"),
                                     "alpha_mode": material.get("alphaMode", "OPAQUE"),
                                     "has_transmission_extension": "KHR_materials_transmission" in material.get("extensions", {}),
                                     "color0_present": bool(colors),
                                     "color0_indexed_range": [min(v for i in used for v in colors[i]), max(v for i in used for v in colors[i])] if colors and used else None})
            if "Glass" in name:
                if len(indices)%6:
                    raise ValueError("Original glazing index group is not divisible into two-triangle panes")
                normals = values(attrs["NORMAL"])
                for start in range(0, len(indices), 6):
                    pane_indices = indices[start:start+6]
                    pane = [points[i] for i in pane_indices]
                    box = bounds(pane)
                    normal = normals[pane_indices[0]]
                    axis = max(range(3), key=lambda i: abs(normal[i]))
                    side = ("+" if normal[axis] > 0 else "-") + "XYZ"[axis]
                    panes.append({"material": name, "glTF_face_normal_axis": side,
                                  "centre_y_m": (box["min_m"][1]+box["max_m"][1])/2,
                                  "width_m": max(box["dimensions_m"][0], box["dimensions_m"][2]),
                                  "height_m": box["dimensions_m"][1],
                                  "normal_axis_thickness_m": box["dimensions_m"][axis],
                                  "bounds_glTF_m": box})
            else:
                for module in components(points, indices):
                    module["material"] = name
                    modules.append(module)
        pane_groups = Counter((pane["glTF_face_normal_axis"], round(pane["centre_y_m"],5),
                               round(pane["width_m"],5), round(pane["height_m"],5)) for pane in panes)
        levels = source_levels(row)
        for level in levels:
            level_panes = [pane for pane in panes if level["base_glTF_y_m"] <= pane["centre_y_m"] <= level["base_glTF_y_m"]+level["height_m"]]
            centres = sorted({round(pane["centre_y_m"],5) for pane in level_panes})
            level["actual_glb_glazing_row_centres_y_m"] = centres
            level["actual_glb_glazing_row_spacings_m"] = [round(b-a,5) for a,b in zip(centres,centres[1:])]
            level["actual_glb_pane_count"] = len(level_panes)
            level["actual_glb_pane_widths_m"] = sorted({round(pane["width_m"],5) for pane in level_panes})
            level["actual_glb_pane_heights_m"] = sorted({round(pane["height_m"],5) for pane in level_panes})
        box = bounds(all_points)
        records.append({
            "building": building, "node": node["name"], "style": row[5], "hero": bool(original_meta.get("hero")),
            "glTF_world_matrix_rows": world, "bounds_glTF_m": box,
            "bounds_blender_m": bounds([(x,-z,y) for x,y,z in all_points]),
            "bounds_UE_m": bounds([(x,z,y) for x,y,z in all_points]),
            "height_from_nominal_ground_m": box["max_m"][1]-6.9,
            "metadata_height_from_ground_m": original_meta["height"],
            "source_main_tower_width_depth_height_m": [row[2],row[3],row[4]],
            "source_nominal_podium_width_depth_m": [row[2]+4,row[3]+4],
            "floor_segments": levels, "triangles": sum(m["indexed_triangles"] for m in material_records),
            "glass_panes": len(panes), "maximum_glass_normal_axis_thickness_m": max(p["normal_axis_thickness_m"] for p in panes),
            "glass_pane_groups": [{"glTF_face_normal_axis":k[0], "centre_y_m":k[1], "pane_width_m":k[2], "pane_height_m":k[3], "count":n} for k,n in sorted(pane_groups.items())],
            "recovered_opaque_module_count": len(modules),
            "upright_module_dimension_groups": group_dimensions(modules, lambda d: d[1]>3 and max(d[0],d[2])<.8),
            "horizontal_slab_module_dimension_groups": group_dimensions(modules, lambda d: d[1]<=.46 and d[0]>5 and d[2]>5),
            "opaque_backing_box_dimension_groups": group_dimensions(modules, lambda d: d[1]>3 and d[0]>5 and d[2]>5),
            "non_glass_color0_nonzero_indexed_vertices": non_glass_color_nonzero,
            "materials": material_records,
        })
    report = {
        "audit_type": "Read-only original city visible office geometry and source parameter audit",
        "generated_utc": datetime.now(timezone.utc).isoformat(), "blender_or_ue_started": False,
        "original_inputs": [{"path": str(path), "sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for path in
                            [ART/"modern-city.glb",ART/"modern-city.json",SCRIPTS/"prepare_modern_city.mjs",SCRIPTS/"build_city_lookdev.py",SCRIPTS/"batch_city_geometry.py"]],
        "units": "Metres from original metadata and glTF specification; all selected GLB node transforms are reported",
        "glb_generator": document["asset"].get("generator"),
        "glb_image_count": len(document.get("images",[])), "glb_texture_count": len(document.get("textures",[])),
        "source_facade_parameters_m": {
            "hero_glass_recess_from_nominal_skin":.24, "other_glass_recess_from_nominal_skin":.105,
            "hero_backing_face_behind_pane":.02, "other_backing_face_behind_pane":.015,
            "normal_hero_mullion_width_depth":[.06,.30], "normal_other_mullion_width_depth":[.075,.19],
            "hero_corner_mullion_width_depth":[.17,.30], "other_corner_width":.25,
            "alternating_fin_width_depth":[.18,.52], "hero_floor_band_height_inner_outer":[.11,.18],
            "other_floor_band_height_inner_outer":[.19,.27], "hero_chamfer_max":.035,
            "target_bay_spacing":2.9, "nominal_tower_floor_spacing":3.3,
        },
        "source_material_behavior": {
            "all_glb_near_glass": "Opaque, no transmission; source consists of zero-thickness planes in front of metal backing boxes",
            "generic_glb_glass_roughness":.18, "generic_glb_hero_metallic":.60,"generic_glb_other_glass_metallic":.65,
            "ue_B07_hero_override": {"metallic":0,"specular":.75,"roughness_parameter_default":.12,
                                    "dry_roughness_formula_range":[.1025,.1375],"fully_wet_formula_range":[.0875,.1225],
                                    "pane_waviness_normal_amplitude":.0025,
                                    "not_saved_material_verification":True},
            "ue_other_near_glass_roughness_dry_wet_default":[.18,.1152],
            "color0": "Night emission payload; non-glass vertices black. Generic glTF viewers may multiply COLOR_0 into BaseColor; native UE material builder reads it only for office emission.",
            "uv1": "Hero pane constant seed; all other geometry x=0. This original UV1 is not a lightmap unwrap.",
        },
        "build_and_batch_source_behavior": {
            "selected_B04_B05_B06_B07_B08_explicit_extra_scale":None,
            "only_skyline_extra_UE_scale":[.65,.60,1.5],"only_skyline_extra_UE_translation_cm":[0,-12000,-345],
            "batching": "Copies effective world transforms and asserts each instance matches before source actor removal; source code evidence only",
            "saved_map_transforms_verified":False,
        },
        "buildings": sorted(records,key=lambda record:record["building"]),
        "limitations": [
            "No current UE level, serialized actor transform, material instance, Nanite result, or packaged scene is inspected.",
            "Source formulas are cross-checked with original GLB glazing and reconstructed opaque-module dimensions; current project runtime overrides may differ.",
            "Opaque modules are recovered by coordinate welding at 0.00001m and shared triangle edges. Touching/coincident modules may merge; these are approximate component statistics, not original part identities.",
            "Glass panes are recovered as consecutive six-index groups, matching the original source authoring and its exported checks.",
            "Dimensions establish the original metre-scale geometry, not successful visual perception of scale in the fixed window camera.",
            "No visible-pixel coverage, occlusion, photographic comparison, material appearance, UV overlap or mesh self-intersection test is performed.",
            "Triangle counts are bookkeeping; they do not establish modeling quality or final completion.",
        ],
    }
    destination = Path(__file__).with_name("original_office_geometry_audit.json")
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("Original office geometry audit:",destination)
    for record in report["buildings"]:
        print(record["building"],"bounds X/height/depth",[round(v,3) for v in record["bounds_glTF_m"]["dimensions_m"]],
              "height above ground",round(record["height_from_nominal_ground_m"],3),"glass panes",record["glass_panes"],
              "maximum glass plane thickness",record["maximum_glass_normal_axis_thickness_m"])


if __name__ == "__main__":
    main()
