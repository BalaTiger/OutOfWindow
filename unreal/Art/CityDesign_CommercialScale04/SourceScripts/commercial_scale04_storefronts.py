"""Rebuild the upper storefront space while keeping doors and fittings at human scale."""
import bpy
import bmesh
import json
import math
import sys
from pathlib import Path

out=Path(sys.argv[sys.argv.index('--')+1])
PAVE=7.04
FIRST_FF=13.04
frames=bpy.data.materials['View_Office_Recessed_Head']
glass=bpy.data.materials['View_Entry_Clear_Glass']
made=[]


def normals(obj):
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free();obj.data.update()


def uvs(obj):
    for name in [layer.name for layer in obj.data.uv_layers]:obj.data.uv_layers.remove(obj.data.uv_layers[name])
    layer=obj.data.uv_layers.new(name='UVMap')
    for face in obj.data.polygons:
        axis=max(range(3),key=lambda i:abs(face.normal[i]))
        for li in face.loop_indices:
            p=obj.data.vertices[obj.data.loops[li].vertex_index].co
            layer.data[li].uv=((p.y,p.z) if axis==0 else (p.x,p.z) if axis==1 else (p.x,p.y))
    obj.data.uv_layers.new(name='LightmapUV');obj.data.uv_layers.active=obj.data.uv_layers['LightmapUV']
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.015);bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.uv_layers.active=obj.data.uv_layers['UVMap'];obj.data.uv_layers['UVMap'].active_render=True


def box(name,lo,hi,material,collection):
    vertices=[(x,y,z) for z in (lo[2],hi[2]) for y in (lo[1],hi[1]) for x in (lo[0],hi[0])]
    faces=[(0,2,3,1),(4,5,7,6),(0,1,5,4),(1,3,7,5),(3,2,6,7),(2,0,4,6)]
    data=bpy.data.meshes.new(name+'_Mesh');data.from_pydata(vertices,[],faces);data.update()
    obj=bpy.data.objects.new(name,data);bpy.data.collections[collection].objects.link(obj);data.materials.append(material)
    obj['audit_role']='architectural_solid';normals(obj);uvs(obj);made.append(name);return obj


# The ground commercial floor rises from 4.51 to 6.0m. The 2.78m door plane,
# header/canopy and handles keep their sizes; new upper glass occupies the gap.
box('A_MainEntry_Upper_Clerestory_Storefront',(-25.70,-1.98,PAVE+4.07),(-25.655,6.26,FIRST_FF-.30),glass,'Curved_A')
for y in (-1.98,.08,2.14,4.20,6.26):
    box('A_MainEntry_Upper_Clerestory_Frame_'+str(y),(-25.65,y-.027,PAVE+4.02),(-25.59,y+.027,FIRST_FF-.27),frames,'Curved_A')
box('A_CourtEntry_Upper_Clerestory_Storefront',(-35.88,18.35,PAVE+4.15),(-35.835,22.60,FIRST_FF-.30),glass,'Curved_A')
for y in (18.35,20.48,22.60):
    box('A_CourtEntry_Upper_Frame_'+str(y),(-35.82,y-.027,PAVE+4.12),(-35.76,y+.027,FIRST_FF-.27),frames,'Curved_A')
box('B_Entry_Upper_Clerestory_Storefront',(-45.4,37.55,PAVE+4.15),(-37.45,37.595,FIRST_FF-.30),glass,'Curved_B')
for x in (-45.4,-43.42,-41.44,-39.46,-37.45):
    box('B_Entry_Upper_Clerestory_Frame_'+str(x),(x-.027,37.50,PAVE+4.12),(x+.027,37.56,FIRST_FF-.27),frames,'Curved_B')

# Interior ceiling/back panel changes are localized: counters remain 1.1/1.18m.
for name,old_top in [('A_MainEntry_Interior_Warm_Back',PAVE+3.70),('A_Entry_Interior_Rear',PAVE+3.90),('B_Entry_Interior_Rear',PAVE+3.90)]:
    obj=bpy.data.objects[name]
    for vertex in obj.data.vertices:
        if vertex.co.z>old_top-.03:vertex.co.z=PAVE+5.40
    normals(obj);uvs(obj)
obj=bpy.data.objects['B_Entry_Warm_Ceiling']
for vertex in obj.data.vertices:vertex.co.z+=1.50
normals(obj);uvs(obj)

scene=bpy.context.scene
scene.camera=bpy.data.objects['Review_Window_UE_VFOV54']
scene['Commercial_Height_Design']='First6.0m; standard5.5m; A5 occupied levels28.0m roof above PAVE, B6levels33.5m; floor-to-floor, not net ceiling heights.'
scene['Commercial_Scale_Evidence']='commercial_height_evidence.json; RBS actual commercial podium6.0/5.5m and official Galaxy commercial vs office separation.'
scene['Human_Scale_Fittings']='Doors2.78m, frames52-65mm, band0.89m, bridge cabin3.65m, terrace guard1.10m. No global XYZ stretch.'
(out/'storefront_revision.json').write_text(json.dumps({'new_parts':made,'first_floor_to_floor_m':6.0,'door_height_m':2.78,'clerestory_top_absolute_m':FIRST_FF-.30,'net_ceiling_height_claimed':False,'office_massing_changed':False},indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'CityDesign_CommercialScale04.blend'))
print('COMMERCIAL_SCALE04_STOREFRONTS_SAVED',flush=True)
