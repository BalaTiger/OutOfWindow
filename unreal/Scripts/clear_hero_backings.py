"""Remove only the source interior backing that obstructs the hero interiors.

Generated copies retain source vertices and attributes; only triangle indices change.
apply(root) uses the already loaded Alley world; its caller saves the level.
--self-test checks source fingerprints and retained geometry without writing files.
"""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_window_interiors as windows

DEST = '/Game/Scenes/Alley/HeroBackings'
RECIPE = 'hero-backings-v2'
SOURCE_GLB_NAME = 'alley-hero-backings-v2.glb'
# Only authored interior shells: components 0/23 served the original lower
# openings; 2 is the middle front room, 7 the upper front room, 8 the right lower
# room. Preserve building-detail mullions, wood frames and every exterior face.
TARGETS = {
    'OOW_00768_paris_building_09_17': (
        'f9a9ad99752d9111ca36eff31ac60045940639ec498730ab8e432eaefc9d3870',
        248, set(range(10)) | set(range(20, 30)) | set(range(70, 90)) | set(range(238, 248))),
}


def generate(root, write=True):
    root = Path(root)
    doc, blob = windows.read_glb(root / 'Migration/Exported/alley.glb')
    out = {'asset': {'version': '2.0', 'generator': RECIPE}, 'scene': 0,
           'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [], 'accessors': [],
           'bufferViews': [], 'buffers': [],
           'materials': [{'name': 'OOW_HeroBacking_ImportPlaceholder'}],
           'extensionsUsed': ['KHR_mesh_quantization'],
           'extensionsRequired': ['KHR_mesh_quantization']}
    data, records = bytearray(), []

    def put(raw, source_index, count=None, target=34962):
        data.extend(b'\0' * (-len(data) % 4))
        accessor = copy.deepcopy(doc['accessors'][source_index])
        accessor['bufferView'], accessor['byteOffset'] = len(out['bufferViews']), 0
        if count is not None:
            accessor['count'] = count
            accessor.pop('min', None)
            accessor.pop('max', None)
        out['bufferViews'].append({'buffer': 0, 'byteOffset': len(data),
                                   'byteLength': len(raw), 'target': target})
        data.extend(raw)
        out['accessors'].append(accessor)
        return len(out['accessors']) - 1

    for name, (expected_hash, expected_triangles, removed) in TARGETS.items():
        node = next(node for node in doc['nodes'] if node.get('name') == name)
        primitives = doc['meshes'][node['mesh']]['primitives']
        assert len(primitives) == 1 and primitives[0].get('mode', 4) == 4, name
        source = primitives[0]
        assert doc['materials'][source['material']]['name'] == 'MASTER_Room_Interior', 'Never trim an exterior/frame material'
        fingerprint = hashlib.sha256()
        raw_attributes = {}
        for semantic, index in sorted({**source['attributes'], 'INDICES': source['indices']}.items()):
            raw = b''.join(windows.read_accessor(doc, blob, index)[0])
            fingerprint.update(semantic.encode())
            fingerprint.update(raw)
            raw_attributes[semantic] = raw
        assert fingerprint.hexdigest() == expected_hash, 'Revalidate source component IDs: ' + name
        raw_indices, indices = windows.read_accessor(doc, blob, source['indices'])
        assert len(indices) == expected_triangles * 3 and max(removed) < expected_triangles
        retained = [i for i in range(expected_triangles) if i not in removed]
        kept_indices = b''.join(raw_indices[t * 3 + corner] for t in retained for corner in range(3))
        primitive = {'material': 0, 'attributes': {semantic: put(raw_attributes[semantic], index)
                     for semantic, index in source['attributes'].items()}}
        primitive['indices'] = put(kept_indices, source['indices'], len(retained) * 3, 34963)
        # Retain the prior clearance asset for rollback when the recipe changes.
        asset_name = 'OOWHeroClear_' + RECIPE.rsplit('-', 1)[-1] + '_' + name
        out['scenes'][0]['nodes'].append(len(out['nodes']))
        out['nodes'].append({'name': asset_name, 'mesh': len(out['meshes'])})
        out['meshes'].append({'name': asset_name, 'primitives': [primitive]})
        records.append({'actor': name, 'assetName': asset_name,
                        'sourceGeometryHash': expected_hash,
                        'sourceMaterial': doc['materials'][source['material']]['name'],
                        'sourceTriangles': expected_triangles, 'removedTriangleIds': sorted(removed),
                        'retainedTriangles': len(retained), 'sourceVertices': doc['accessors'][source['attributes']['POSITION']]['count']})
    data.extend(b'\0' * (-len(data) % 4))
    out['buffers'] = [{'byteLength': len(data)}]
    encoded = json.dumps(out, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    glb = (struct.pack('<III', 0x46546C67, 2, 28 + len(encoded) + len(data))
           + struct.pack('<II', len(encoded), 0x4E4F534A) + encoded
           + struct.pack('<II', len(data), 0x004E4942) + data)
    report = {'recipe': RECIPE, 'appliedToUnreal': False,
              'generatedSha256': hashlib.sha256(glb).hexdigest(), 'actors': records}
    output = root / 'Migration/Generated' / SOURCE_GLB_NAME
    if write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(glb)
        (root / 'Migration/hero-backings.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return output, report, out, bytes(data)


def apply(root):
    """Replace the backing mesh, preserving actor/component state."""
    import unreal as u
    root = Path(root)
    source, report, _, _ = generate(root)
    actors = {actor.get_actor_label(): actor for actor in
              u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
              if isinstance(actor, u.StaticMeshActor)}
    mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    targets = []
    for entry in report['actors']:
        actor = actors[entry['actor']]
        comp = actor.static_mesh_component
        assert comp.get_num_materials() == 1 and comp.get_material(0), entry['actor']
        old = comp.static_mesh
        original = str(u.EditorAssetLibrary.get_metadata_tag(old, 'OOWHeroBackingOriginalMesh'))
        if not original or original == 'None':
            original = old.get_path_name()
        targets.append((entry, comp, old, comp.get_material(0), original))
    expected = report['generatedSha256']
    needs_import = any(str(u.EditorAssetLibrary.get_metadata_tag(old, 'OOWHeroBackingGeometry')) != expected
                       for _, _, old, _, _ in targets)
    imported = {}
    if needs_import:
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        params = u.ImportAssetParameters()
        params.is_automated, params.replace_existing = True, True
        imported = {asset.get_name(): asset for asset in
                    (manager.import_asset(DEST, manager.create_source_data(str(source)), params) or [])
                    if isinstance(asset, u.StaticMesh)}
        # A single-mesh GLB is named after its source file by Interchange, even
        # when the glTF node/mesh has an explicit different name.
        if len(imported) == 1 and len(report['actors']) == 1:
            only = next(iter(imported.values()))
            entry = report['actors'][0]
            assert only.get_num_triangles(0) == entry['retainedTriangles'], 'Imported backing geometry is stale'
            imported[entry['assetName']] = only
        for entry in report['actors']:
            name = entry['assetName']
            if name not in imported:
                # Interchange may reuse unchanged assets without returning them.
                base = DEST + '/' + source.stem + '/StaticMeshes/'
                mesh = u.load_asset(base + name) or u.load_asset(base + source.stem)
                assert isinstance(mesh, u.StaticMesh), 'Missing backing mesh import: ' + str(sorted(imported))
                assert mesh.get_num_triangles(0) == entry['retainedTriangles'], 'Stale backing geometry'
                imported[name] = mesh
    for entry, comp, old, material, original in targets:
        mesh = imported[entry['assetName']] if needs_import else old
        if needs_import:
            build = mesh_editor.get_lod_build_settings(old, 0)
            build.set_editor_property('generate_lightmap_u_vs', False)
            mesh_editor.set_lod_build_settings(mesh, 0, build)
            mesh_editor.set_nanite_settings(mesh, old.get_editor_property('nanite_settings'), True)
            mesh.set_material(0, material)
            for key, value in {'OOWHeroBackingGeometry': expected,
                               'OOWHeroBackingOriginalMesh': original,
                               'OOWHeroBackingSource': entry['actor'], 'OOWRecipe': RECIPE}.items():
                u.EditorAssetLibrary.set_metadata_tag(mesh, key, value)
            u.EditorAssetLibrary.save_loaded_asset(mesh)
            comp.set_static_mesh(mesh)
            comp.set_material(0, material)
        entry.update(unrealMesh=mesh.get_path_name(), originalMesh=original,
                     unrealMaterial=material.get_path_name())
    report['appliedToUnreal'] = True
    (root / 'Migration/hero-backings.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def self_test(root):
    _, report, generated, blob = generate(root, write=False)
    source, source_blob = windows.read_glb(Path(root) / 'Migration/Exported/alley.glb')
    assert [entry['actor'] for entry in report['actors']] == ['OOW_00768_paris_building_09_17']
    assert [entry['retainedTriangles'] for entry in report['actors']] == [198]
    for entry, mesh in zip(report['actors'], generated['meshes']):
        node = next(node for node in source['nodes'] if node.get('name') == entry['actor'])
        before = source['meshes'][node['mesh']]['primitives'][0]
        after = mesh['primitives'][0]
        assert set(before['attributes']) == set(after['attributes'])
        for semantic, index in before['attributes'].items():
            assert windows.read_accessor(source, source_blob, index)[0] == windows.read_accessor(generated, blob, after['attributes'][semantic])[0]
        old_indices = windows.read_accessor(source, source_blob, before['indices'])[1]
        new_indices = windows.read_accessor(generated, blob, after['indices'])[1]
        removed = set(entry['removedTriangleIds'])
        assert new_indices == [index for offset, index in enumerate(old_indices) if offset // 3 not in removed]
    print(json.dumps({'passed': True, 'sourceTriangles': [248],
                      'removedTriangles': [50], 'retainedTriangles': [198], 'attributesPreserved': True}))


if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    if '--self-test' in sys.argv:
        self_test(root)
    elif '--generate-only' in sys.argv:
        print(json.dumps(generate(root)[1]))
    else:
        import unreal as u
        levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
        assert levels.load_level('/Game/Maps/Alley'), 'Cannot load Alley'
        apply(root)
        assert levels.save_current_level(), 'Cannot save Alley'
