"""Finish the independent candidate, verify, then render only its fixed window."""
import bpy
import bmesh
import json
import math
import runpy
import sys
from pathlib import Path

out = Path(sys.argv[sys.argv.index('--') + 1])
root = Path(__file__).parent
obj = bpy.data.objects['A_MainEntry_ORBIT']
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
# Translation/rotation at export can collapse sub-pixel font bevel triangles in
# float32. Apply first so cleaning measures actual stored world coordinates.
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bm = bmesh.new()
bm.from_mesh(obj.data)
before = len(bm.faces)
def double_triangle_area(face):
    a,b,c = (tuple(vertex.co) for vertex in face.verts)
    ab = tuple(b[i]-a[i] for i in range(3))
    ac = tuple(c[i]-a[i] for i in range(3))
    cross = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
    return math.sqrt(sum(value*value for value in cross))*.5
bmesh.ops.delete(bm, geom=[face for face in bm.faces if double_triangle_area(face) <= 1e-9], context='FACES')
bmesh.ops.delete(bm, geom=[vertex for vertex in bm.verts if not vertex.link_faces], context='VERTS')
bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
removed = before - len(bm.faces)
bm.to_mesh(obj.data)
bm.free()
obj.data.update()
obj.data.uv_layers.active = obj.data.uv_layers['LightmapUV']
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=.015)
bpy.ops.object.mode_set(mode='OBJECT')
for dest, source in zip(obj.data.uv_layers['UVMap'].data, obj.data.uv_layers['LightmapUV'].data):
    dest.uv = source.uv
obj.data.uv_layers.active = obj.data.uv_layers['UVMap']
obj.data.uv_layers['UVMap'].active_render = True
(out/'lettering_cleanup.json').write_text(json.dumps({
    'object':obj.name,'faces_removed':removed,'threshold_square_metres':1e-9,
    'method':'Apply font transform, use double-precision cross-product on stored coordinates to remove only collapsed bevel faces, repack dual UV.',
    'review_view_unchanged':True
},indent=2),encoding='utf-8')


def script(name, args):
    sys.argv = [name, '--', *map(str, args)]
    try:
        runpy.run_path(str(root/name), run_name='__main__')
    except SystemExit as error:
        if error.code not in (None, 0):
            raise


script('export_window_scale03.py', [out])
script('new_curved_validation.py', [out/'mesh_audit.json', '--collections',
    'Curved_A','Curved_B','Curved_Bridge','Curved_C','Curved_Site','Office_Window_Visible',
    '--placeholder','Curved_C'])
report = json.loads((out/'mesh_audit.json').read_text(encoding='utf-8'))
if report['status'] != 'PASS':
    raise RuntimeError('Final source audit failed; no final render started.')
script('verify_window_scale03_fbx.py', [out])
# FBX was read in a disposable scene. Restore the saved candidate for its only
# final image; temporary import scene is never saved over the editable model.
bpy.ops.wm.open_mainfile(filepath=str(out/'CityDesign_WindowScale03.blend'))
script('render_window_scale03.py', [out, 'final'])
print('WINDOW_SCALE03_FINAL_CPU_COMPLETE', flush=True)
