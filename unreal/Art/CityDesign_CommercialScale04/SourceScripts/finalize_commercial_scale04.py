"""Finish exact deck alignment, audit actual outputs, render the sole fixed CPU view."""
import bpy
import bmesh
import json
import math
import runpy
import sys
from pathlib import Path

out=Path(sys.argv[sys.argv.index('--')+1]);root=Path(__file__).parent
obj=bpy.data.objects['Bridge_Closed_Arched_Soffit_and_Deck']
level=18.54
for vertex in obj.data.vertices:
    if vertex.co.z>level+.05:vertex.co.z=level
bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free();obj.data.update()
for name in [layer.name for layer in obj.data.uv_layers]:obj.data.uv_layers.remove(obj.data.uv_layers[name])
layer=obj.data.uv_layers.new(name='UVMap')
for face in obj.data.polygons:
    axis=max(range(3),key=lambda i:abs(face.normal[i]))
    for li in face.loop_indices:
        p=obj.data.vertices[obj.data.loops[li].vertex_index].co
        layer.data[li].uv=((p.y,p.z) if axis==0 else (p.x,p.z) if axis==1 else (p.x,p.y));layer.data[li].uv/=1.2
obj.data.uv_layers.new(name='LightmapUV');obj.data.uv_layers.active=obj.data.uv_layers['LightmapUV']
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.015);bpy.ops.object.mode_set(mode='OBJECT')
obj.data.uv_layers.active=obj.data.uv_layers['UVMap'];obj.data.uv_layers['UVMap'].active_render=True

def run(name,args):
    sys.argv=[name,'--',*map(str,args)]
    try:runpy.run_path(str(root/name),run_name='__main__')
    except SystemExit as error:
        if error.code not in (None,0):raise

run('export_commercial_scale04.py',[out])
run('new_curved_validation.py',[out/'mesh_audit.json','--collections','Curved_A','Curved_B','Curved_Bridge','Curved_C','Curved_Site','Office_Window_Visible','--placeholder','Curved_C'])
if json.loads((out/'mesh_audit.json').read_text(encoding='utf-8'))['status']!='PASS':
    raise RuntimeError('Final commercial source audit failed; no final render.')
run('verify_commercial_scale04_geometry.py',[out])
run('verify_commercial_scale04_fbx.py',[out])
bpy.ops.wm.open_mainfile(filepath=str(out/'CityDesign_CommercialScale04.blend'))
run('render_commercial_scale04.py',[out,'final'])
print('COMMERCIAL_SCALE04_FINAL_CPU_COMPLETE',flush=True)
