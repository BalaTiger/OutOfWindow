"""Generate/import only Coast's corrected sand mesh, preserving scene placement.

Source: Three buildCoast/addTerrain (seed 118, east 18m/far 24m transition).
The local geometry is rebuilt deterministically from the original heightfield;
running twice, or after a fresh Three export, never applies the taper twice.
Run with UnrealEditor-Cmd -run=pythonscript. --self-test needs only Python.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ACTOR = 'OOW_00000_Mesh'
NAME = 'OOW_CoastSand_Shoreline_v1'
DEST = '/Game/Scenes/Coast/Repairs'


def smoothstep(a, b, x):
    t = max(0., min(1., (x - a) / (b - a)))
    return t * t * (3. - 2. * t)


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def height(x, y, taper=True):
    seed, phases = 118, []
    for _ in range(3):
        seed = (seed * 1664525 + 1013904223) & 0xffffffff
        phases.append(seed / 4294967296. * 8.)
    broad = math.sin(x * .045 + phases[0]) * math.cos(y * .038 + phases[1])
    rolling = math.sin((x + y) * .022 + phases[2]) + math.cos((x - y) * .017)
    calm = smoothstep(5., 38., abs(y - 210. * .42))
    original = float32((broad * .62 + rolling * .38) * 3.4 * (.35 + calm * .65))
    keep = (1. - smoothstep(41., 59., x)) * (1. - smoothstep(81., 105., y))
    return float32(min(original, -.1 + (original + .1) * keep)) if taper and keep < 1 else original


def read_glb(path):
    with path.open('rb') as f:
        magic, version, _ = struct.unpack('<III', f.read(12))
        assert magic == 0x46546C67 and version == 2
        size, chunk = struct.unpack('<II', f.read(8))
        assert chunk == 0x4E4F534A
        document = json.loads(f.read(size))
        size, chunk = struct.unpack('<II', f.read(8))
        assert chunk == 0x004E4942
        return document, f.read(size)


def accessor_bytes(document, blob, index):
    accessor = document['accessors'][index]
    assert 'sparse' not in accessor and not accessor.get('normalized', False)
    view = document['bufferViews'][accessor['bufferView']]
    width = {5121: 1, 5123: 2, 5125: 4, 5126: 4}[accessor['componentType']]
    size = width * {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[accessor['type']]
    start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    stride = view.get('byteStride', size)
    return b''.join(blob[start + i * stride:start + i * stride + size] for i in range(accessor['count']))


def generate(root, write=True):
    document, blob = read_glb(root / 'Migration' / 'Exported' / 'coast.glb')
    node = next(n for n in document['nodes'] if n.get('name') == ACTOR)
    assert all(abs(a - b) < .0001 for a, b in zip(node['matrix'][12:15], [-55, -1.3, -45]))
    mesh = document['meshes'][node['mesh']]
    assert len(mesh['primitives']) == 1
    primitive = mesh['primitives'][0]
    attributes = primitive['attributes']
    positions = list(struct.iter_unpack('<fff', accessor_bytes(document, blob, attributes['POSITION'])))
    assert len(positions) == 121 * 121
    assert min(p[0] for p in positions) == -59 and max(p[0] for p in positions) == 59
    assert min(p[1] for p in positions) == -105 and max(p[1] for p in positions) == 105
    # Accept original or already corrected exports, rejecting another terrain.
    assert all(min(abs(z - height(x, y, False)), abs(z - height(x, y))) < .00002 for x, y, z in positions)
    fixed = [(x, y, height(x, y)) for x, y, _ in positions]
    interior = [i for i, (x, y, _) in enumerate(positions) if x <= 41 and y <= 81]
    assert all(fixed[i] == positions[i] for i in interior)
    assert all(p[2] <= -.09999 for p in fixed if p[0] == 59 or p[1] == 105)
    index_data = accessor_bytes(document, blob, primitive['indices'])
    index_type = document['accessors'][primitive['indices']]['componentType']
    indices = [v[0] for v in struct.iter_unpack({5121: '<B', 5123: '<H', 5125: '<I'}[index_type], index_data)]
    normals = [[0., 0., 0.] for _ in fixed]
    for a, b, c in zip(indices[0::3], indices[1::3], indices[2::3]):
        ab = [fixed[b][i] - fixed[a][i] for i in range(3)]
        ac = [fixed[c][i] - fixed[a][i] for i in range(3)]
        cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
        for vertex in (a, b, c):
            for axis in range(3):
                normals[vertex][axis] += cross[axis]
    for normal in normals:
        length = math.sqrt(sum(v * v for v in normal))
        assert length > 0
        normal[:] = [v / length for v in normal]
    out = {'asset': {'version': '2.0', 'generator': 'OutOfWindow coastline repair v1'},
           'scenes': [{'nodes': [0]}], 'scene': 0,
           'nodes': [{'name': NAME, 'mesh': 0}],
           'meshes': [{'name': NAME, 'primitives': [{'attributes': {}, 'material': 0}]}],
           'materials': [{'name': 'OOW_Sand_ImportPlaceholder', 'pbrMetallicRoughness': {'metallicFactor': 0, 'roughnessFactor': 1}}],
           'accessors': [], 'bufferViews': [], 'buffers': []}
    data = bytearray()

    def add_accessor(original_index, raw, target, bounds=None):
        data.extend(b'\0' * ((-len(data)) % 4))
        view = len(out['bufferViews'])
        out['bufferViews'].append({'buffer': 0, 'byteOffset': len(data), 'byteLength': len(raw), 'target': target})
        data.extend(raw)
        accessor = copy.deepcopy(document['accessors'][original_index])
        accessor['bufferView'], accessor['byteOffset'] = view, 0
        accessor.pop('min', None)
        accessor.pop('max', None)
        if bounds:
            accessor['min'], accessor['max'] = bounds
        out['accessors'].append(accessor)
        return len(out['accessors']) - 1

    result_primitive = out['meshes'][0]['primitives'][0]
    for semantic, index in attributes.items():
        if semantic == 'TANGENT':
            continue  # Interchange recomputes tangents against corrected normals.
        raw = accessor_bytes(document, blob, index)
        bounds = None
        if semantic == 'POSITION':
            raw = b''.join(struct.pack('<fff', *p) for p in fixed)
            bounds = ([min(p[i] for p in fixed) for i in range(3)], [max(p[i] for p in fixed) for i in range(3)])
        elif semantic == 'NORMAL':
            raw = b''.join(struct.pack('<fff', *n) for n in normals)
        result_primitive['attributes'][semantic] = add_accessor(index, raw, 34962, bounds)
    result_primitive['indices'] = add_accessor(primitive['indices'], index_data, 34963)
    data.extend(b'\0' * ((-len(data)) % 4))
    out['buffers'] = [{'byteLength': len(data)}]
    encoded = json.dumps(out, separators=(',', ':')).encode()
    encoded += b' ' * ((-len(encoded)) % 4)
    output = struct.pack('<III', 0x46546C67, 2, 28 + len(encoded) + len(data)) + struct.pack('<II', len(encoded), 0x4E4F534A) + encoded + struct.pack('<II', len(data), 0x004E4942) + data
    path = root / 'Migration' / 'Generated' / (NAME + '.glb')
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(output)
    uv = accessor_bytes(document, blob, attributes['TEXCOORD_0'])
    report = {'sourceActor': ACTOR, 'vertices': len(fixed), 'triangles': len(indices) // 3,
              'unchangedInteriorVertices': len(interior), 'changedHeights': sum(a != b for a, b in zip(positions, fixed)),
              'taperedVertices': sum(z != height(x, y, False) for x, y, z in fixed),
              'maxBorderWorldHeightM': max(p[2] - 1.3 for p in fixed if p[0] == 59 or p[1] == 105),
              'uvSha256': hashlib.sha256(uv).hexdigest(), 'generatedSha256': hashlib.sha256(output).hexdigest()}
    assert accessor_bytes(out, data, result_primitive['attributes']['TEXCOORD_0']) == uv
    return path, report


def main():
    import unreal as u
    root = Path(u.Paths.project_dir()).parent
    generated, report = generate(root)
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    if not levels.load_level('/Game/Maps/Coast'):
        raise RuntimeError('Cannot load Coast')
    actor = next(a for a in actors.get_all_level_actors() if a.get_actor_label() == ACTOR)
    comp = actor.static_mesh_component
    old_mesh = comp.static_mesh
    original_path = str(u.EditorAssetLibrary.get_metadata_tag(old_mesh, 'OOWOriginalMesh')) or old_mesh.get_path_name()
    material = comp.get_material(0)
    old_bounds = comp.get_local_bounds()
    def placement(item):
        location, rotation, scale = item.get_actor_location(), item.get_actor_rotation(), item.get_actor_scale3d()
        return {'location': [location.x, location.y, location.z],
                'rotation': [rotation.pitch, rotation.yaw, rotation.roll], 'scale': [scale.x, scale.y, scale.z]}
    before = placement(actor)
    other_placements = {a.get_actor_label(): placement(a) for a in actors.get_all_level_actors()
                        if isinstance(a, u.StaticMeshActor) and a != actor}
    if str(u.EditorAssetLibrary.get_metadata_tag(old_mesh, 'OOWCoastRepair')) != report['generatedSha256']:
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        params = u.ImportAssetParameters()
        params.is_automated, params.replace_existing = True, True
        imported = manager.import_asset(DEST, manager.create_source_data(str(generated)), params)
        meshes = [asset for asset in (imported or []) if isinstance(asset, u.StaticMesh)]
        if len(meshes) != 1:
            raise RuntimeError('Expected exactly one imported sand mesh: ' + str(imported))
        mesh = meshes[0]
        mesh.set_material(0, material)  # no dependency on the unsaved import placeholder
        comp.set_static_mesh(mesh)
        comp.set_material(0, material)
        after_bounds = comp.get_local_bounds()
        for old, new in zip(old_bounds, after_bounds):
            assert abs(old.x - new.x) < .02 and abs(old.z - new.z) < .02, 'Local horizontal dimensions changed'
        assert placement(actor) == before, 'Actor transform changed'
        settings = old_mesh.get_editor_property('nanite_settings')
        settings.enabled = True
        mesh_editor.set_nanite_settings(mesh, settings, True)
        u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWCoastRepair', report['generatedSha256'])
        u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWOriginalMesh', original_path)
        u.EditorAssetLibrary.save_loaded_asset(mesh)
        levels.save_current_level()
    # Also repair a previously generated asset's unused placeholder slot.
    if comp.static_mesh.get_material(0) != material:
        comp.static_mesh.set_material(0, material)
        u.EditorAssetLibrary.save_loaded_asset(comp.static_mesh)
    assert other_placements == {a.get_actor_label(): placement(a) for a in actors.get_all_level_actors()
                                if isinstance(a, u.StaticMeshActor) and a != actor}
    report.update({'originalMesh': original_path, 'repairedMesh': comp.static_mesh.get_path_name(),
                   'preservedMaterial': comp.get_material(0).get_path_name(), 'actorTransform': before})
    (root / 'Migration' / 'coast-shoreline-repair.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_COAST_SHORELINE_COMPLETE ' + json.dumps(report))


def self_test():
    root = Path(__file__).resolve().parent.parent
    _, first = generate(root, write=False)
    _, second = generate(root, write=False)
    assert first == second
    assert first['taperedVertices'] > 0 and first['unchangedInteriorVertices'] > 10000
    assert first['maxBorderWorldHeightM'] <= -1.39999
    print(json.dumps(first, indent=2))


if __name__ == '__main__':
    self_test() if '--self-test' in sys.argv else main()
