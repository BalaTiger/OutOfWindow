"""Consolidate explicit candidate parts for transport; keep editable originals.

Commercial A/B/bridge/court and the three actual visible source offices only.
No generators, no edits to the old City files, no UE import or deployment.
"""
import bpy
import json
import math
import sys
from pathlib import Path

out = Path(sys.argv[sys.argv.index('--') + 1])
scene = bpy.context.scene
old = bpy.data.collections.get('Export_CommercialScale04')
if old:
    for obj in list(old.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(old)
export = bpy.data.collections.new('Export_CommercialScale04')
scene.collection.children.link(export)
proxies = []
records = []


def clone_with_two_uvs(source, clear_colors=False):
    clone = source.copy()
    clone.data = source.data.copy()
    export.objects.link(clone)
    clone.hide_set(False)
    clone.hide_render = False
    clone.select_set(True)
    data = clone.data
    uv = data.uv_layers.get('UVMap')
    if uv is None and data.uv_layers:
        uv = data.uv_layers[0]
    old_uv = [tuple(item.uv) for item in uv.data] if uv else None
    for name in [layer.name for layer in data.uv_layers]:
        data.uv_layers.remove(data.uv_layers[name])
    layer = data.uv_layers.new(name='UVMap')
    if old_uv is not None:
        for dest, value in zip(layer.data, old_uv):
            dest.uv = value
    else:
        for face in data.polygons:
            axis = max(range(3), key=lambda i: abs(face.normal[i]))
            for li in face.loop_indices:
                p = data.vertices[data.loops[li].vertex_index].co
                layer.data[li].uv = ((p.y, p.z) if axis == 0 else
                                     (p.x, p.z) if axis == 1 else (p.x, p.y))
    data.uv_layers.new(name='LightmapUV')
    if clear_colors:
        for name in [attribute.name for attribute in data.color_attributes]:
            data.color_attributes.remove(data.color_attributes[name])
    return clone


def consolidate(name, sources, office=False):
    if not sources:
        raise RuntimeError('Empty export group: ' + name)
    bpy.ops.object.select_all(action='DESELECT')
    clones = [clone_with_two_uvs(source, office) for source in sources]
    bpy.context.view_layer.objects.active = clones[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.data.uv_layers.active = obj.data.uv_layers['LightmapUV']
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=.012)
    bpy.ops.object.mode_set(mode='OBJECT')
    # RNA references from before edit mode are deliberately not reused.
    obj.data.uv_layers.active = obj.data.uv_layers['UVMap']
    obj.data.uv_layers['UVMap'].active_render = True
    obj['Export_Source_Parts'] = json.dumps([source.name for source in sources])
    obj['Coordinates'] = 'Blender metres; glTF standard Y-up; FBX unit scale enabled.'
    obj['Candidate_Only'] = True
    obj.data.calc_loop_triangles()
    positions = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    records.append({
        'name': name,
        'source_parts': [source.name for source in sources],
        'vertices': len(obj.data.vertices),
        'polygons': len(obj.data.polygons),
        'triangles': len(obj.data.loop_triangles),
        'materials': [m.name for m in obj.data.materials if m],
        'uv_layers': [layer.name for layer in obj.data.uv_layers],
        'color_attributes': [a.name for a in obj.data.color_attributes],
        'world_bounds_blender_m': {
            'min': [min(point[i] for point in positions) for i in range(3)],
            'max': [max(point[i] for point in positions) for i in range(3)],
        },
    })
    proxies.append(obj)
    return obj


commercial = []
for collname, name in [('Curved_A', 'OOW_Curved_A'),
                       ('Curved_B', 'OOW_Curved_B'),
                       ('Curved_Bridge', 'OOW_Curved_Bridge'),
                       ('Curved_Site', 'OOW_Curved_Court')]:
    commercial.append(consolidate(name, [obj for obj in bpy.data.collections[collname].objects if obj.type == 'MESH']))

office_parts = bpy.data.collections['Office_Window_Visible']
offices = []
for code, source_name in [('B07', 'CityModern_B07_terrace'),
                          ('B08', 'CityModern_B08_glass'),
                          ('B13', 'CityModern_B13_glass')]:
    source = bpy.data.objects[source_name]
    parts = [source] + [obj for obj in office_parts.objects
                       if obj.type == 'MESH' and obj.name.startswith('Office_' + code + '_')]
    offices.append(consolidate('OOW_View_Office_' + code, parts, office=True))


def write(base, objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(out / (base + '.glb')),
        export_format='GLB', use_selection=True, export_apply=True,
        export_texcoords=True, export_normals=True, export_materials='EXPORT',
        export_cameras=False, export_lights=False, export_animations=False)
    bpy.ops.export_scene.fbx(filepath=str(out / (base + '.fbx')),
        use_selection=True, object_types={'MESH'}, apply_unit_scale=True,
        global_scale=1, axis_forward='-Z', axis_up='Y', use_mesh_modifiers=True,
        mesh_smooth_type='FACE', add_leaf_bones=False, bake_anim=False,
        path_mode='AUTO', use_custom_props=True)


write('CityDesign_CommercialScale04_Commercial', commercial)
write('CityDesign_CommercialScale04_OfficeVisible', offices)
for obj in proxies:
    obj.hide_render = True
    obj.hide_set(True)
export.hide_render = True
scene.camera = bpy.data.objects['Review_Window_UE_VFOV54']
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.threads_mode = 'FIXED'
scene.render.threads = 1
scene.render.resolution_x = 2560
scene.render.resolution_y = 1440
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(out / 'preview-window.png')
scene['Sample_Status'] = 'Fixed-window candidate exported, technical checks separate from user visual acceptance.'
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'CityDesign_CommercialScale04.blend'))
(out / 'export_manifest.json').write_text(json.dumps({
    'commercial_file': 'CityDesign_CommercialScale04_Commercial.glb',
    'office_file': 'CityDesign_CommercialScale04_OfficeVisible.glb',
    'commercial_instances': 4, 'office_instances': 3,
    'included_commercial': ['Curved_A', 'Curved_B', 'Curved_Bridge', 'Curved_Site'],
    'included_offices': ['B07', 'B08', 'B13'],
    'excluded': ['Curved_C', 'other city context', 'licensed trees', 'cameras', 'lights'],
    'proxy_meshes': records,
    'office_color_attributes': 'Removed on export clones only: original COLOR_0 is a UE night-emission payload, not daytime albedo.',
    'office_backs': 'Original simple source surfaces retained; no claim of full-office volumetric reconstruction.',
    'uv1': 'Repacked for each consolidated exported object. Island overlap and UE lightmaps have not been independently tested.',
    'integration': 'No UE import, map changes or deployment.'
}, indent=2), encoding='utf-8')
print('COMMERCIAL_SCALE04_EXPORTS_COMPLETE', flush=True)
