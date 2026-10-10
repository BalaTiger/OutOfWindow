"""Complete modeled masonry jambs and a readable commercial identity fascia."""
import bpy
import bmesh
import math
import re
import runpy
import sys
from pathlib import Path

out=Path(sys.argv[sys.argv.index('--')+1])
scene=bpy.context.scene

def unwrap(obj):
    uv=obj.data.uv_layers.get('UVMap') or obj.data.uv_layers.new(name='UVMap')
    for face in obj.data.polygons:
        axis=max(range(3),key=lambda i:abs(face.normal[i]))
        for li in face.loop_indices:
            p=obj.matrix_world@obj.data.vertices[obj.data.loops[li].vertex_index].co
            uv.data[li].uv=((p.y,p.z) if axis==0 else (p.x,p.z) if axis==1 else (p.x,p.y))
            uv.data[li].uv/=1.2
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    uv1=obj.data.uv_layers.get('LightmapUV') or obj.data.uv_layers.new(name='LightmapUV')
    obj.data.uv_layers.active=uv1
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.03)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.uv_layers.active=uv
    uv.active_render=True

def frame(name,rectangles,collection,materials):
    if name in bpy.data.objects:
        return
    verts=[]
    faces=[]
    ring=((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
    for xmin,xmax,ymin,ymax,zmin,zmax in rectangles:
        offset=len(verts)
        verts.extend(((xmin,ymin,zmin),(xmax,ymin,zmin),(xmax,ymax,zmin),(xmin,ymax,zmin),
                      (xmin,ymin,zmax),(xmax,ymin,zmax),(xmax,ymax,zmax),(xmin,ymax,zmax)))
        faces.extend(tuple(offset+i for i in face) for face in ring)
    mesh=bpy.data.meshes.new(name+'_Mesh')
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.data.collections[collection].objects.link(obj)
    for mat in materials:
        mesh.materials.append(bpy.data.materials[mat])
    if len(materials)>1:
        for face in list(mesh.polygons)[18:]:
            face.material_index=1
    unwrap(obj)

for obj in list(bpy.data.collections['Neighbor_Architecture'].objects):
    match=re.fullmatch(r'Neighbor_F(\d+)_(Near_)?Bay(\d+)_Glass',obj.name)
    if not match:
        continue
    floor=int(match[1])
    near=bool(match[2])
    bay=int(match[3])
    z=6.9+4.8+(floor-1)*3.4
    if near:
        a=-48+bay*6.5
        b=a+6.5
        obj.dimensions=(4.6,.08,1.6)
        rects=[(a+.6,a+.95,75.94,77.45,z+.95,z+2.85),
               (b-.95,b-.6,75.94,77.45,z+.95,z+2.85),
               (a+.95,b-.95,75.94,77.45,z+2.65,z+2.85),
               (a+.95,b-.95,75.75,77.45,z+.95,z+1.05)]
    else:
        a=76+bay*6.8
        b=a+6.8
        obj.dimensions=(.08,4.7,1.6)
        rects=[(-23.45,-21.95,a+.65,a+1.05,z+.95,z+2.85),
               (-23.45,-21.95,b-1.05,b-.65,z+.95,z+2.85),
               (-23.45,-21.95,a+1.05,b-1.05,z+2.65,z+2.85),
               (-23.45,-21.67,a+1.05,b-1.05,z+.95,z+1.05)]
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    unwrap(obj)
    frame(obj.name.replace('_Glass','_Masonry_Reveal_Frame'),rects,'Neighbor_Architecture',
          ('Neighbor_01_Warm_Clay_Brick','Neighbor_02_Pale_Stone'))

frame('Mall_Main_Entry_Identity_Fascia',[(-23.64,-23.52,12,28,17.22,18.58)],'Mall_Architecture',('Mall_03_Precast_Ivory',))
bpy.data.objects['Mall_Commercial_Identity_Galleria'].location.x=-23.43
scene['Neighbor_East_Upper_Facade_Glass_Ratio']=(4.7*1.6)/(6.8*3.4)
print('FACADE_REVEALS_COMPLETE',flush=True)
runpy.run_path(str(out/'repair_text_and_export.py'),run_name='__main__')
