"""FBX round-trip in a temporary empty background scene; never save the blend."""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector

out=Path(sys.argv[sys.argv.index('--')+1])
source=json.loads((out/'mesh_audit.json').read_text(encoding='utf-8'))
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
for stem in ('Architecture','OfficeCorner_TRIAL'):
    bpy.ops.import_scene.fbx(filepath=str(out/f'CityDesign_CurvedDistrict02_{stem}.fbx'),use_image_search=False)
mapping={'OOW_Curved_A':'Curved_A','OOW_Curved_B':'Curved_B','OOW_Curved_Bridge':'Curved_Bridge','OOW_Curved_Court':'Curved_Site','OOW_Office_Corner_TRIAL':'Office_Corner'}
records=[];errors=[]
objects=[o for o in scene.objects if o.type=='MESH']
if set(o.name for o in objects)!=set(mapping):errors.append('Unexpected mesh set')
for obj in objects:
    data=obj.data;data.calc_loop_triangles()
    positions=[obj.matrix_world@v.co for v in data.vertices]
    lower=[min(p[i] for p in positions) for i in range(3)];upper=[max(p[i] for p in positions) for i in range(3)]
    expected=source['collections'][mapping[obj.name]]
    delta=max(abs(value-expected['world_bounds'][field][i]) for field,values in [('min_m',lower),('max_m',upper)] for i,value in enumerate(values))
    normals=[n.vector for n in data.corner_normals]
    bad_normals=sum(not all(math.isfinite(v) for v in n) or abs(n.length-1)>1e-3 for n in normals)
    uv=[{'name':layer.name,'loops':len(layer.data),'complete':len(layer.data)==len(data.loops),'finite':all(math.isfinite(c) for p in layer.data for c in p.uv)} for layer in data.uv_layers]
    issues=[]
    if delta>1e-4:issues.append('Bounds differ from saved source by over 0.1mm')
    if len(data.loop_triangles)!=expected['triangles']:issues.append('Triangle count differs from source')
    if bad_normals or len(normals)!=len(data.loops):issues.append('Invalid or incomplete corner normals')
    if len(uv)!=2:issues.append('Expected exactly two UV channels')
    if any(not r['complete'] or not r['finite'] for r in uv):issues.append('UV channel incomplete or nonfinite')
    if any(not math.isfinite(c) for p in positions for c in p):issues.append('Nonfinite position')
    records.append({'name':obj.name,'triangles':len(data.loop_triangles),'world_bounds_blender_m':{'min':lower,'max':upper},'maximum_source_bounds_delta_m':delta,'invalid_corner_normals':bad_normals,'uv':uv,'errors':issues})
    errors.extend(f'{obj.name}: {issue}' for issue in issues)
report={'status':'FAIL' if errors else 'PASS','method':'Read both actual FBX files into factory-empty Blender 5.0.1 temporary scene; no save/render/UE.', 'one_unit_m':1,'objects':records,'errors':errors,'limitations':['Blender round-trip does not validate UE import settings or material conversion.','UV island overlap, shading quality, self-intersection and collision are not tested.']}
(out/'fbx_roundtrip_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('FBX_ROUNDTRIP_AUDIT',report['status'],flush=True)
if errors:raise RuntimeError('; '.join(errors))
