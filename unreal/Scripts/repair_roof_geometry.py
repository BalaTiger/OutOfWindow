"""Restore nine Alley roofs and add bounded slate relief to the matching hip pair.

Run after import_scenes.py, before or after surface-material generation.
Only the explicit affected roof actors change meshes; their actor transforms,
weather material and Nanite settings stay intact. No textures are reimported.
--self-test is CPU-only; --generate-only also writes the GLB and evidence JSON.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_window_interiors import read_glb, read_accessor, sub, cross, dot, unit, length
from roof_slate_relief import add_relief, audit_float32, RECIPE as RELIEF_RECIPE

DEST = '/Game/Scenes/Alley/Repairs'
RECIPE = 'roof-source-geometry-v1'
TARGETS = [
    (303, 1, 'OOW_00329_Paris_Building_01_paris_building_01_128_1_1'),
    (312, 0, 'OOW_00338_Paris_Building_01_paris_building_01_199'),
    (317, 0, 'OOW_00343_Paris_Building_01_paris_building_01_204'),
    (318, 0, 'OOW_00344_Paris_Building_01_paris_building_01_205'),
    (324, 0, 'OOW_00350_Paris_Building_01_paris_building_01_211'),
    (448, 0, 'OOW_00487_paris_building_03_mirrored_6'),
    (458, 0, 'OOW_00497_paris_building_03_mirrored_6__2_'),
    (554, 0, 'OOW_00607_paris_building_05_71'),
    (624, 0, 'OOW_00690_paris_building_05_71__2_'),
]


def bounds(points):
    return [[min(point[k] for point in points), max(point[k] for point in points)] for k in range(3)]


def normal_alignment(positions, normals, indices, triangles):
    values = []
    for triangle in triangles:
        ids = indices[triangle*3:triangle*3+3]
        a, b, c = [positions[index] for index in ids]
        face = unit(cross(sub(b, a), sub(c, a)))
        values.append([dot(face, unit(normals[index])) for index in ids])
    return values


def normal_metrics(positions, normals, indices, world_scale):
    area_sum, angle_sum, damaged_area, worst = 0., 0., 0., 0.
    for start in range(0, len(indices), 3):
        ids = indices[start:start+3]
        a, b, c = [positions[index] for index in ids]
        surface = cross(sub(b, a), sub(c, a))
        area, face = length(surface) * .5 * world_scale**2, unit(surface)
        if area < 1e-10: continue
        angles = [math.degrees(math.acos(max(-1., min(1., dot(face, unit(normals[index])))))) for index in ids]
        area_sum += area
        angle_sum += area * sum(angles)/3
        damaged_area += area if max(angles) > 20 else 0.
        worst = max(worst, *angles)
    return {'areaWeightedMeanAngleDegrees': angle_sum/area_sum, 'maximumCornerAngleDegrees': worst,
            'areaWithCornerAbove20DegreesFraction': damaged_area/area_sum, 'surfaceAreaSquareMeters': area_sum}


def load_inputs(root):
    source_dir = root.parent / 'public' / 'assets' / 'orca' / 'bistro'
    original = json.loads((source_dir / 'bistro-exterior.gltf').read_text(encoding='utf-8'))
    assert len(original['buffers']) == 1 and original['buffers'][0]['uri'] == 'exterior.runtime.bin'
    blob = (source_dir / 'exterior.runtime.bin').read_bytes()
    exported, export_blob = read_glb(root / 'Migration' / 'Exported' / 'alley.glb')
    manifest = json.loads((root / 'Migration' / 'scene-manifest.json').read_text(encoding='utf-8'))
    alley = next(scene for scene in manifest['scenes'] if scene['id'] == 'alley')
    wrapper = next(instance['worldTransformThree'] for instance in alley['assetInstances']
                   if instance['id'] == 'alley_bistro_near_001')
    return original, blob, exported, export_blob, wrapper


def generate(root, target, inputs, write=True):
    original, blob, exported, export_blob, wrapper = inputs
    mesh_index, primitive_index, actor = target
    has_relief = mesh_index in (448, 458)
    recipe = RELIEF_RECIPE if has_relief else RECIPE
    name = ('OOW_Roof_Slate_v2_%d_%d' if has_relief else 'OOW_Roof_Original_v1_%d_%d') % (mesh_index, primitive_index)
    original_node = next(node for node in original['nodes'] if node.get('mesh') == mesh_index)
    assert set(original_node) == {'name', 'mesh'}
    source_mesh = original['meshes'][mesh_index]
    primitive = source_mesh['primitives'][primitive_index]
    assert primitive.get('mode', 4) == 4
    source_material = original['materials'][primitive['material']]['name']
    assert 'roof' in source_material.lower(), 'Only the roof primitive may be restored'
    raw = {semantic: b''.join(read_accessor(original, blob, index)[0])
           for semantic, index in primitive['attributes'].items()}
    positions = read_accessor(original, blob, primitive['attributes']['POSITION'])[1]
    normals = read_accessor(original, blob, primitive['attributes']['NORMAL'])[1]
    index_raw, index_values = read_accessor(original, blob, primitive['indices'])
    index_raw = b''.join(index_raw)
    indices = [value[0] for value in index_values]
    node = next(node for node in exported['nodes'] if node.get('name') == actor)
    matrix = node['matrix']
    assert all(abs(matrix[i]) < 1e-10 for i in (1, 2, 4, 6, 8, 9))
    assert matrix[0] > 0 and max(abs(matrix[0]-matrix[i]) for i in (5, 10)) < 1e-9
    old = exported['meshes'][node['mesh']]['primitives'][0]
    old_positions = read_accessor(exported, export_blob, old['attributes']['POSITION'])[1]
    old_normals = read_accessor(exported, export_blob, old['attributes']['NORMAL'])[1]
    old_indices = [value[0] for value in read_accessor(exported, export_blob, old['indices'])[1]]

    assert wrapper['quaternionXYZW'] == [0, 0, 0, 1]
    assert max(wrapper['scale']) - min(wrapper['scale']) < 1e-12 and wrapper['scale'][0] > 0
    world = [tuple(point[k]*wrapper['scale'][k] + wrapper['positionMeters'][k] for k in range(3))
             for point in positions]
    # Invert only the exported quantization node. UE keeps this actor's existing
    # transform, so a second wrapper transform here would move the whole roof.
    local = [struct.unpack('<fff', struct.pack('<fff',
              *((point[k]-matrix[12+k])/matrix[k*5] for k in range(3)))) for point in world]
    restored_world = [tuple(point[k]*matrix[k*5]+matrix[12+k] for k in range(3)) for point in local]
    old_world = [tuple(point[k]*matrix[k*5]+matrix[12+k] for k in range(3)) for point in old_positions]
    source_precision_error = max(length(sub(a, b)) for a, b in zip(world, restored_world))
    old_bounds, restored_bounds = bounds(old_world), bounds(restored_world)
    bound_delta = max(abs(a-b) for aa, bb in zip(old_bounds, restored_bounds) for a, b in zip(aa, bb))
    nearest_source_distance = max(min(length(sub(point, source)) for source in world) for point in old_world)
    assert source_precision_error < .00001
    # Decimation removed narrow source edges on the smaller roofs (up to 14mm).
    # Keep the original vertices, while independently checking that all retained
    # export vertices still map to their source within quantization precision.
    bounds_tolerance = .003 if mesh_index in (448, 458) else .02
    assert bound_delta < bounds_tolerance, 'Source roof bounds do not align: %s (%f m)' % (actor, bound_delta)
    assert nearest_source_distance < .003, 'Retained roof source vertices do not align'
    correct = normal_metrics(local, normals, indices, matrix[0])
    damaged = normal_metrics(old_positions, old_normals, old_indices, matrix[0])

    digest = hashlib.sha256(recipe.encode())
    for semantic in sorted(raw):
        digest.update(semantic.encode()); digest.update(raw[semantic])
    digest.update(index_raw)
    digest.update(json.dumps({'wrapper': wrapper, 'exportMatrix': matrix}, sort_keys=True).encode())
    source_hash = digest.hexdigest()
    out = {'asset': {'version': '2.0', 'generator': recipe}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'name': name, 'mesh': 0}], 'meshes': [{'name': name, 'primitives': [{'attributes': {}, 'material': 0}]}],
           'materials': [{'name': source_material, 'pbrMetallicRoughness': {'metallicFactor': 0, 'roughnessFactor': .9}}],
           'accessors': [], 'bufferViews': [], 'buffers': []}
    data = bytearray()

    def put(index, values, target, position_bounds=None):
        data.extend(b'\0' * ((-len(data)) % 4))
        view = len(out['bufferViews'])
        out['bufferViews'].append({'buffer': 0, 'byteOffset': len(data), 'byteLength': len(values), 'target': target})
        data.extend(values)
        accessor = copy.deepcopy(original['accessors'][index])
        accessor.update(bufferView=view, byteOffset=0)
        if position_bounds:
            accessor['min'] = [value[0] for value in position_bounds]
            accessor['max'] = [value[1] for value in position_bounds]
        out['accessors'].append(accessor)
        return len(out['accessors'])-1

    baseline_vertices, baseline_triangles = len(local), len(indices)//3
    baseline_main_dots = normal_alignment(local, normals, indices, (2, 3)) if has_relief else None
    relief = None
    if has_relief:
        source_points, source_indices = world, indices
        source_uvs = read_accessor(original, blob, primitive['attributes']['TEXCOORD_0'])[1]
        world, normals, source_uvs, indices, relief = add_relief(world, normals, source_uvs, indices)
        local = [struct.unpack('<fff', struct.pack('<fff',
                  *((point[k]-matrix[12+k])/matrix[k*5] for k in range(3)))) for point in world]
        restored_world = [tuple(point[k]*matrix[k*5]+matrix[12+k] for k in range(3)) for point in local]
        restored_bounds = bounds(restored_world)
        geometry_raw = {'NORMAL': b''.join(struct.pack('<fff', *normal) for normal in normals),
                        'TEXCOORD_0': b''.join(struct.pack('<ff', *uv) for uv in source_uvs)}
        index_raw = struct.pack('<%dI' % len(indices), *indices)
    else:
        geometry_raw = raw
    result = out['meshes'][0]['primitives'][0]
    assert original['accessors'][primitive['attributes']['POSITION']]['componentType'] == 5126
    for semantic, index in primitive['attributes'].items():
        values = b''.join(struct.pack('<fff', *point) for point in local) if semantic == 'POSITION' else geometry_raw[semantic]
        result['attributes'][semantic] = put(index, values, 34962, bounds(local) if semantic == 'POSITION' else None)
        if has_relief:
            accessor = out['accessors'][result['attributes'][semantic]]
            accessor['count'] = len(local)
            if semantic != 'POSITION':
                accessor.pop('min', None); accessor.pop('max', None)
    result['indices'] = put(primitive['indices'], index_raw, 34963)
    if has_relief:
        index_accessor = out['accessors'][result['indices']]
        index_accessor.update(componentType=5125, count=len(indices), min=[min(indices)], max=[max(indices)])
        relief['float32Audit'] = audit_float32(read_accessor(out, data, result['attributes']['POSITION'])[1],
                                             [value[0] for value in read_accessor(out, data, result['indices'])[1]],
                                             matrix, source_points, source_indices)
    # Unmodified roofs remain byte-for-byte; relief roofs retain source charts
    # through interpolation, with normals transformed for the new surface.
    for semantic in ('NORMAL', 'TEXCOORD_0'):
        assert b''.join(read_accessor(out, data, result['attributes'][semantic])[0]) == geometry_raw[semantic]
    data.extend(b'\0' * ((-len(data)) % 4))
    out['buffers'] = [{'byteLength': len(data)}]
    encoded = json.dumps(out, separators=(',', ':')).encode()
    encoded += b' ' * ((-len(encoded)) % 4)
    glb = struct.pack('<III', 0x46546C67, 2, 28+len(encoded)+len(data)) + struct.pack('<II', len(encoded), 0x4E4F534A) + encoded + struct.pack('<II', len(data), 0x004E4942) + data
    path = root / 'Migration' / 'Generated' / (name + '.glb')
    report = {'recipe': recipe, 'actor': actor, 'assetName': name, 'sourceMeshIndex': mesh_index,
              'sourcePrimitiveIndex': primitive_index, 'sourceMeshName': source_mesh['name'],
              'sourceMaterial': source_material, 'vertices': len(local), 'triangles': len(indices)//3,
              'beforeVertices': len(old_positions), 'beforeTriangles': len(old_indices)//3,
              'sourceGeometryHash': source_hash, 'generatedSha256': hashlib.sha256(glb).hexdigest(),
              'uvSha256': hashlib.sha256(raw['TEXCOORD_0']).hexdigest(), 'normalSha256': hashlib.sha256(raw['NORMAL']).hexdigest(),
              'sourceNormalsAndUVPreserved': not has_relief, 'sourcePositionMaxErrorMeters': source_precision_error,
              'sourceBaselineVertices': baseline_vertices, 'sourceBaselineTriangles': baseline_triangles,
              'exportBoundsMaxDeltaMeters': bound_delta, 'exportBoundsToleranceMeters': bounds_tolerance,
              'exportVertexNearestSourceMaxMeters': nearest_source_distance,
              'worldBoundsMeters': restored_bounds, 'exportLocalBounds': bounds(local),
              'restoredNormalAlignment': correct, 'simplifiedNormalAlignment': damaged,
              'materialPolicy': 'Reuse the actor current UE weather material; no texture import'}
    if has_relief:
        report['relief'] = relief
        report['sourceBaselineNormalAlignment'] = correct
        report['generatedNormalAlignment'] = normal_metrics(local, normals, indices, matrix[0])
        report['sourceNormalUVPolicy'] = 'Source hashes and baseline diagnostic retained; generated UVs interpolate original charts, displaced normals recomputed within original hard-edge groups'
        report['originalMainFaceNormalDots'] = baseline_main_dots
        assert min(value for values in report['originalMainFaceNormalDots'] for value in values) > .999
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(glb)
    return path, report


def generate_all(root, write=True):
    inputs = load_inputs(root)
    generated = [generate(root, target, inputs, write) for target in TARGETS]
    report = {'recipe': RELIEF_RECIPE, 'actors': [entry for _, entry in generated], 'actorCount': len(generated),
              'trianglesBefore': sum(entry['beforeTriangles'] for _, entry in generated),
              'trianglesAfter': sum(entry['triangles'] for _, entry in generated),
              'verticesAfter': sum(entry['vertices'] for _, entry in generated),
              'sourceBaselineTriangles': sum(entry['sourceBaselineTriangles'] for _, entry in generated),
              'reliefActorCount': sum('relief' in entry for _, entry in generated)}
    if write:
        (root / 'Migration' / 'roof-geometry-repair.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return generated, report


def main():
    import unreal as u
    root = Path(u.Paths.project_dir()).parent
    generated, report = generate_all(root)
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    if not levels.load_level('/Game/Maps/Alley'):
        raise RuntimeError('Cannot load Alley')
    static = [actor for actor in actors.get_all_level_actors() if isinstance(actor, u.StaticMeshActor)]
    by_label = {actor.get_actor_label(): actor for actor in static}

    def placement(actor):
        p, r, s = actor.get_actor_location(), actor.get_actor_rotation(), actor.get_actor_scale3d()
        return [p.x, p.y, p.z, r.pitch, r.yaw, r.roll, s.x, s.y, s.z]

    before = {actor.get_actor_label(): {'transform': placement(actor), 'mesh': actor.static_mesh_component.static_mesh.get_path_name()}
              for actor in static if actor.static_mesh_component.static_mesh}
    replacements = []
    for source, entry in generated:
        target = by_label[entry['actor']]
        comp, transform = target.static_mesh_component, placement(target)
        old = comp.static_mesh
        assert comp.get_num_materials() == 1
        material = comp.get_material(0)
        original_path = str(u.EditorAssetLibrary.get_metadata_tag(old, 'OOWRoofOriginalMesh')) or old.get_path_name()
        # UE nested struct properties are references: copy before editing so the
        # old actor asset remains untouched until all replacements are ready.
        nanite, build = old.get_editor_property('nanite_settings').copy(), editor.get_lod_build_settings(old, 0).copy()
        relief_policy = {'fallback_target': u.NaniteFallbackTarget.PERCENT_TRIANGLES,
                         'fallback_percent_triangles': 1., 'fallback_relative_error': 0.,
                         'keep_percent_triangles': 1., 'trim_relative_error': 0.,
                         'generate_fallback': u.NaniteGenerateFallback.ENABLED} if 'relief' in entry else {}
        nanite_changed = any(nanite.get_editor_property(key) != value for key, value in relief_policy.items())
        for key, value in relief_policy.items(): nanite.set_editor_property(key, value)
        repaired = old
        reused = str(u.EditorAssetLibrary.get_metadata_tag(old, 'OOWRoofRepairSource')) == entry['sourceGeometryHash']
        if not reused:
            manager = u.InterchangeManager.get_interchange_manager_scripted()
            options = u.ImportAssetParameters()
            options.is_automated, options.replace_existing = True, True
            imported = manager.import_asset(DEST, manager.create_source_data(str(source)), options)
            meshes = [asset for asset in (imported or []) if isinstance(asset, u.StaticMesh)]
            assert len(meshes) == 1 and meshes[0].get_name() == entry['assetName']
            repaired = meshes[0]
            imported_nanite = repaired.get_editor_property('nanite_settings')
            entry['importedMeshState'] = {'asset': repaired.get_path_name(), 'triangles': repaired.get_num_triangles(0),
                                          'naniteEnabled': bool(imported_nanite.enabled),
                                          'fallbackTarget': str(imported_nanite.fallback_target),
                                          'fallbackPercent': float(imported_nanite.fallback_percent_triangles),
                                          'fallbackError': float(imported_nanite.fallback_relative_error),
                                          'removeDegenerates': bool(build.get_editor_property('remove_degenerates'))}
            u.log('OOW_ROOF_IMPORTED ' + json.dumps(entry['importedMeshState']))
            build.set_editor_property('recompute_normals', False)
            build.set_editor_property('recompute_tangents', True)
            build.set_editor_property('use_mikk_t_space', True)
            build.set_editor_property('use_full_precision_u_vs', True)
            build.set_editor_property('generate_lightmap_u_vs', False)
            editor.set_lod_build_settings(repaired, 0, build)
            # An Interchange import can already have Nanite enabled. Its default
            # fallback is not the unreduced source count; apply the requested
            # policy before validating the render/fallback triangle count.
            if relief_policy:
                editor.set_nanite_settings(repaired, nanite, True)
            actual_triangles = repaired.get_num_triangles(0)
            u.log('OOW_ROOF_TRIANGLES ' + json.dumps({'asset': repaired.get_path_name(),
                    'expected': entry['triangles'], 'actual': actual_triangles,
                    'naniteEnabled': bool(repaired.get_editor_property('nanite_settings').enabled)}))
            assert actual_triangles == entry['triangles'], '%s: expected %d triangles, got %d' % (repaired.get_path_name(), entry['triangles'], actual_triangles)
            bound = repaired.get_bounding_box()
            expected = entry['exportLocalBounds']
            for axis, source_axis in (('x', 0), ('y', 2), ('z', 1)):
                assert abs(getattr(bound.min, axis)-expected[source_axis][0]*100) < .01
                assert abs(getattr(bound.max, axis)-expected[source_axis][1]*100) < .01
            repaired.set_material(0, material)
            if not relief_policy:
                editor.set_nanite_settings(repaired, nanite, True)
            assert repaired.get_editor_property('nanite_settings').enabled == nanite.enabled
            u.EditorAssetLibrary.set_metadata_tag(repaired, 'OOWRoofRepairSource', entry['sourceGeometryHash'])
            u.EditorAssetLibrary.set_metadata_tag(repaired, 'OOWRoofOriginalMesh', original_path)
            assert u.EditorAssetLibrary.save_loaded_asset(repaired)
        elif nanite_changed:
            editor.set_nanite_settings(repaired, nanite, True)
            assert u.EditorAssetLibrary.save_loaded_asset(repaired)
        for key, value in relief_policy.items():
            assert repaired.get_editor_property('nanite_settings').get_editor_property(key) == value
        assert not editor.get_lod_build_settings(repaired, 0).get_editor_property('recompute_normals')
        replacements.append((target, repaired, material))
        entry.update(appliedToUnreal=True, originalMesh=original_path, repairedMesh=repaired.get_path_name(),
                     material=material.get_path_name(), actorTransform=transform, reused=reused,
                     naniteEnabled=bool(repaired.get_editor_property('nanite_settings').enabled))
        if relief_policy:
            entry['naniteReliefPolicy'] = {key: str(value) if key in ('fallback_target', 'generate_fallback') else value
                                           for key, value in relief_policy.items()}
            entry['fallbackTrianglesReadback'] = repaired.get_num_triangles(0)
            assert entry['fallbackTrianglesReadback'] == entry['triangles'], 'Relief fallback lost generated triangles'
            try:
                entry['rayTracingProxyEnabled'] = bool(repaired.get_editor_property('ray_tracing_proxy_settings').enabled)
            except Exception as error:
                entry['rayTracingProxyEnabled'] = None
                entry['rayTracingProxyPropertyUnavailable'] = str(error)
            assert entry['rayTracingProxyEnabled'] is not True, 'Relief mesh unexpectedly uses a separate ray-tracing proxy'
    # Assign only after all nine source/import validations have succeeded.
    for target, repaired, material in replacements:
        target.static_mesh_component.set_static_mesh(repaired)
        target.static_mesh_component.set_material(0, material)
        assert target.static_mesh_component.get_material(0) == material
    target_labels = {entry['actor'] for _, entry in generated}
    for actor in static:
        label = actor.get_actor_label()
        if label in before:
            assert placement(actor) == before[label]['transform']
            if label not in target_labels:
                assert actor.static_mesh_component.static_mesh.get_path_name() == before[label]['mesh']
    assert levels.save_current_level()
    report.update(appliedToUnreal=True, actorTransformsUnchanged=len(before),
                  otherActorsUnchanged=len(before)-len(generated))
    (root / 'Migration' / 'roof-geometry-repair.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_ROOF_GEOMETRY_REPAIR ' + json.dumps(report))


def self_test(write=False):
    root = Path(__file__).resolve().parent.parent
    _, report = generate_all(root, write)
    _, repeated = generate_all(root, False)
    assert report == repeated
    assert report['actorCount'] == 9 and report['trianglesBefore'] == 537
    assert report['sourceBaselineTriangles'] == 794 and report['reliefActorCount'] == 2
    assert len({entry['actor'] for entry in report['actors']}) == 9
    assert report['actors'][0]['sourcePrimitiveIndex'] == 1 and report['actors'][0]['triangles'] == 88
    for entry in report['actors']:
        if entry['sourceMeshIndex'] in (448, 458):
            assert not entry['sourceNormalsAndUVPreserved']
            assert entry['relief']['unexpectedBoundaryEdges'] == 0
            assert entry['relief']['generatedNonManifoldEdges'] == 0
            assert entry['relief']['maxDisplacementMeters'] < .05
        else:
            assert entry['sourceNormalsAndUVPreserved']
        assert entry['sourcePositionMaxErrorMeters'] < .00001
    print(json.dumps({**{key: report[key] for key in ('recipe', 'actorCount', 'trianglesBefore', 'trianglesAfter', 'verticesAfter')},
                      'deterministic': True, 'generatedFilesWritten': write,
                      'actors': [{key: entry[key] for key in ('actor', 'beforeTriangles', 'triangles',
                          'exportBoundsMaxDeltaMeters', 'sourcePositionMaxErrorMeters',
                          'simplifiedNormalAlignment', 'restoredNormalAlignment')} for entry in report['actors']]}, indent=2))


if __name__ == '__main__':
    if '--self-test' in sys.argv or '--generate-only' in sys.argv:
        self_test('--generate-only' in sys.argv)
    else:
        main()
