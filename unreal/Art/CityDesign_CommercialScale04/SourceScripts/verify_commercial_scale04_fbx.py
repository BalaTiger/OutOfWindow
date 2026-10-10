"""Read actual exported FBX into an empty temporary Blender scene; never save."""
import bpy
import json
import math
import sys
from pathlib import Path

out = Path(sys.argv[sys.argv.index('--') + 1])
manifest = json.loads((out / 'export_manifest.json').read_text(encoding='utf-8'))
source = {record['name']: record for record in manifest['proxy_meshes']}
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1
for stem in ('Commercial', 'OfficeVisible'):
    bpy.ops.import_scene.fbx(filepath=str(out / ('CityDesign_CommercialScale04_' + stem + '.fbx')), use_image_search=False)
records = []
errors = []
objects = [obj for obj in scene.objects if obj.type == 'MESH']
if set(obj.name for obj in objects) != set(source):
    errors.append('Unexpected mesh set')
for obj in objects:
    if obj.name not in source:
        continue
    data = obj.data
    data.calc_loop_triangles()
    positions = [obj.matrix_world @ vertex.co for vertex in data.vertices]
    bounds = {key: [function(point[i] for point in positions) for i in range(3)]
              for key, function in [('min', min), ('max', max)]}
    expected = source[obj.name]
    delta = max(abs(value - expected['world_bounds_blender_m'][field][i])
                for field, values in bounds.items() for i, value in enumerate(values))
    normals = [item.vector for item in data.corner_normals]
    bad_normals = sum(not all(math.isfinite(c) for c in normal) or abs(normal.length - 1) > 1e-3 for normal in normals)
    uv = [{'name': layer.name, 'loops': len(layer.data),
           'complete': len(layer.data) == len(data.loops),
           'finite': all(math.isfinite(c) for item in layer.data for c in item.uv)} for layer in data.uv_layers]
    issues = []
    if delta > 1e-4:
        issues.append('Bounds differ from saved proxy by over 0.1mm')
    if len(data.loop_triangles) != expected['triangles']:
        issues.append('Triangle count differs from saved proxy')
    if bad_normals or len(normals) != len(data.loops):
        issues.append('Invalid or incomplete corner normals')
    if len(uv) != 2 or any(not record['complete'] or not record['finite'] for record in uv):
        issues.append('Expected two complete finite UV channels')
    if any(not math.isfinite(c) for point in positions for c in point):
        issues.append('Nonfinite position')
    records.append({'name': obj.name, 'triangles': len(data.loop_triangles),
                    'world_bounds_blender_m': bounds, 'maximum_source_bounds_delta_m': delta,
                    'invalid_corner_normals': bad_normals, 'uv': uv, 'errors': issues})
    errors.extend(obj.name + ': ' + issue for issue in issues)
report = {'status': 'FAIL' if errors else 'PASS',
          'method': 'Import both actual FBX files in factory-empty Blender 5.0.1 temporary background scene; no save/render/UE.',
          'one_unit_m': 1, 'objects': records, 'errors': errors,
          'limitations': ['Blender FBX round-trip does not validate UE importer or materials.',
                         'UV overlap, self-intersection, visual shading and collision not tested.']}
(out / 'fbx_roundtrip_audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('COMMERCIAL_SCALE04_FBX_AUDIT', report['status'], flush=True)
if errors:
    raise RuntimeError('; '.join(errors))
