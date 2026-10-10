"""Export only approved architecture and the separate office trial; exclude C/context.
Keeps original named editable meshes and adds hidden, consolidated export copies.
"""
import bpy
import math
import json
import sys
from pathlib import Path

out=Path(sys.argv[sys.argv.index('--')+1])
old=bpy.data.collections.get('Export_Curved_Batched')
if old:
    for obj in list(old.objects):bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.collections.remove(old)
export=bpy.data.collections.new('Export_Curved_Batched');bpy.context.scene.collection.children.link(export)
proxies=[]
for collname,name in [('Curved_A','OOW_Curved_A'),('Curved_B','OOW_Curved_B'),('Curved_Bridge','OOW_Curved_Bridge'),('Curved_Site','OOW_Curved_Court'),('Office_Corner','OOW_Office_Corner_TRIAL')]:
    coll=bpy.data.collections[collname];coll.hide_render=False
    bpy.ops.object.select_all(action='DESELECT');copies=[]
    for source in coll.objects:
        if source.type!='MESH':continue
        clone=source.copy();clone.data=source.data.copy();export.objects.link(clone);clone.hide_set(False);clone.hide_render=False;clone.select_set(True);copies.append(clone)
    bpy.context.view_layer.objects.active=copies[0];bpy.ops.object.join();obj=bpy.context.object;obj.name=name
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    uv1=obj.data.uv_layers.get('LightmapUV');obj.data.uv_layers.active=uv1
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.012);bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.uv_layers.active=obj.data.uv_layers['UVMap'];obj.data.uv_layers['UVMap'].active_render=True
    obj['Source_Collection']=collname;proxies.append(obj)
    for original in coll.objects:original.select_set(False)
bpy.data.collections['Office_Corner'].hide_render=True

def select(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
def write(base,objects):
    select(objects)
    bpy.ops.export_scene.gltf(filepath=str(out/(base+'.glb')),export_format='GLB',use_selection=True,export_apply=True,export_texcoords=True,export_normals=True,export_materials='EXPORT',export_cameras=False,export_lights=False,export_animations=False)
    bpy.ops.export_scene.fbx(filepath=str(out/(base+'.fbx')),use_selection=True,object_types={'MESH'},apply_unit_scale=True,global_scale=1,axis_forward='-Z',axis_up='Y',use_mesh_modifiers=True,mesh_smooth_type='FACE',add_leaf_bones=False,bake_anim=False,path_mode='AUTO',use_custom_props=True)
write('CityDesign_CurvedDistrict02_Architecture',proxies[:-1])
write('CityDesign_CurvedDistrict02_OfficeCorner_TRIAL',proxies[-1:])
for obj in proxies:obj.hide_render=True;obj.hide_set(True)
export.hide_render=True
bpy.context.scene.camera=bpy.data.objects['Review_Window_UE_VFOV54']
bpy.ops.wm.save_as_mainfile(filepath=str(out/'CityDesign_CurvedDistrict02.blend'))
report={'architecture_file':'CityDesign_CurvedDistrict02_Architecture.glb','office_file':'CityDesign_CurvedDistrict02_OfficeCorner_TRIAL.glb','included_architecture':['Curved_A','Curved_B','Curved_Bridge','Curved_Site'],'excluded':['Curved_C','Existing_City_Context','Licensed_Planting','Lighting','Cameras'],'proxy_meshes':[{ 'name':obj.name,'vertices':len(obj.data.vertices),'polygons':len(obj.data.polygons),'materials':[m.name for m in obj.data.materials if m] } for obj in proxies],'uv1':'Repacked independently per whole exported object; overlap not independently proven.'}
(out/'export_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('CURVED_EXPORTS_COMPLETE',flush=True)
