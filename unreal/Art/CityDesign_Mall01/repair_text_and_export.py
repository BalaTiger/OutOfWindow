"""Weld converted type outlines, remove degenerate edges, refresh two export meshes."""
import bpy
import bmesh
import math
import sys
from pathlib import Path
from mathutils import Vector

out=Path(sys.argv[sys.argv.index('--')+1])
scene=bpy.context.scene
for name in ('Mall_Corner_Identity_The_Arcade','Mall_Commercial_Identity_Galleria'):
    obj=bpy.data.objects[name]
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
    bmesh.ops.dissolve_degenerate(bm,dist=.000001,edges=list(bm.edges))
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    dead=[]
    for face in bm.faces:
        points=[obj.matrix_world@v.co for v in face.verts]
        if (points[1]-points[0]).cross(points[2]-points[0]).length/2<=1e-12:
            dead.append(face)
    bmesh.ops.delete(bm,geom=dead,context='FACES')
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    obj.data.uv_layers.active=obj.data.uv_layers['LightmapUV']
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.01)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.uv_layers.active=obj.data.uv_layers['UVMap']
    obj.data.uv_layers['UVMap'].active_render=True

export=bpy.data.collections['Export_Architecture_Batched']
export.hide_render=False
export.hide_viewport=False
for obj in list(export.objects):
    bpy.data.objects.remove(obj,do_unlink=True)
meshes=[]
for source,name,pivot in (('Mall_Architecture','OOW_Mall01_Architecture',(-46,26,6.9)),
                          ('Neighbor_Architecture','OOW_Neighbor01_Architecture',(-35,93,6.9))):
    bpy.ops.object.select_all(action='DESELECT')
    copies=[]
    for original in bpy.data.collections[source].objects:
        if original.type!='MESH':
            continue
        clone=original.copy()
        clone.data=original.data.copy()
        export.objects.link(clone)
        clone.select_set(True)
        copies.append(clone)
    bpy.context.view_layer.objects.active=copies[0]
    bpy.ops.object.join()
    obj=bpy.context.object
    obj.name=name
    obj.data.name=name+'_Mesh'
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    for vert in obj.data.vertices:
        vert.co-=Vector(pivot)
    obj.location=pivot
    obj.data.uv_layers.active=obj.data.uv_layers['LightmapUV']
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.002)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.uv_layers.active=obj.data.uv_layers['UVMap']
    obj.data.uv_layers['UVMap'].active_render=True
    meshes.append(obj)
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active=meshes[0]
bpy.ops.export_scene.gltf(filepath=str(out/'CityDesign_Mall01_Architecture.glb'),export_format='GLB',use_selection=True,
    export_apply=False,export_texcoords=True,export_normals=True,export_materials='EXPORT',export_cameras=False)
bpy.ops.export_scene.fbx(filepath=str(out/'CityDesign_Mall01_Architecture.fbx'),use_selection=True,
    object_types={'MESH'},apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',
    axis_forward='-Y',axis_up='Z',use_mesh_modifiers=False,add_leaf_bones=False,path_mode='COPY',embed_textures=True)
bpy.ops.object.select_all(action='DESELECT')
export.hide_render=True
export.hide_viewport=True
bpy.ops.wm.save_as_mainfile(filepath=str(out/'CityDesign_Mall01.blend'))
print('TEXT_TOPOLOGY_AND_EXPORT_REPAIRED',flush=True)
