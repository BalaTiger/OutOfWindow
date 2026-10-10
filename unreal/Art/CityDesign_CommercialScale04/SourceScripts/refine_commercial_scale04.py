"""Explicit finite corrections from the sole fixed-window pixel review.

Moves entrance signage within its existing header, shortens one reveal, gives
retail back-of-house bays real opaque cladding, and splits actual office panes
into a 550mm opaque spandrel and a vision pane. No camera or context movement.
"""
import bpy
import bmesh
import json
import math
import sys
from pathlib import Path
from mathutils import Vector

out = Path(sys.argv[sys.argv.index('--') + 1])
scene = bpy.context.scene
if scene.get('CommercialScale04_Refinement_Version'):
    raise RuntimeError('Refinement already applied; rebuild from protected baseline to repeat.')
old = bpy.data.collections.get('Export_CommercialScale04')
if old:
    for obj in list(old.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(old)


def bsdf(material):
    return next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')


def material(name, color, roughness, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = bsdf(mat)
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = metallic
    return mat


def normals(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def uv_contract(obj):
    for name in [layer.name for layer in obj.data.uv_layers]:
        obj.data.uv_layers.remove(obj.data.uv_layers[name])
    layer = obj.data.uv_layers.new(name='UVMap')
    for face in obj.data.polygons:
        axis = max(range(3), key=lambda i: abs(face.normal[i]))
        for li in face.loop_indices:
            p = obj.data.vertices[obj.data.loops[li].vertex_index].co
            layer.data[li].uv = ((p.y, p.z) if axis == 0 else (p.x, p.z) if axis == 1 else (p.x, p.y))
    obj.data.uv_layers.new(name='LightmapUV')
    obj.data.uv_layers.active = obj.data.uv_layers['LightmapUV']
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=.015)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.uv_layers.active = obj.data.uv_layers['UVMap']
    obj.data.uv_layers['UVMap'].active_render = True


shell = [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]


def make_mesh(name, vertices, faces, mat, collection):
    data = bpy.data.meshes.new(name + '_Mesh')
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.data.collections[collection].objects.link(obj)
    data.materials.append(mat)
    normals(obj)
    uv_contract(obj)
    return obj


changed = []
# Keep the portal width and tree positions. Reduce the projected depth of its
# north reveal and bring the doors closer to the street face, still recessed.
for name in ['A_MainEntry_North_Stone_Reveal']:
    obj = bpy.data.objects[name]
    for vertex in obj.data.vertices:
        if vertex.co.x < -23.8:
            vertex.co.x = -25.45 + (vertex.co.x + 29.0) * .15
    normals(obj)
    uv_contract(obj)
    changed.append(name)
for obj in bpy.data.collections['Curved_A'].objects:
    if obj.name.startswith(('A_MainEntry_Door', 'A_MainEntry_Stile', 'A_MainEntry_Transom', 'A_MainEntry_Handle')):
        for vertex in obj.data.vertices:
            vertex.co.x += 1.70
        normals(obj)
        uv_contract(obj)
        changed.append(obj.name)
for name in ['A_MainEntry_Interior_Warm_Back', 'A_MainEntry_Interior_Display']:
    obj = bpy.data.objects[name]
    for vertex in obj.data.vertices:
        vertex.co.x += 3.70
    normals(obj)
    uv_contract(obj)
    changed.append(name)
old = bpy.data.objects['A_MainEntry_GALLERIA']
bpy.data.objects.remove(old, do_unlink=True)
font = bpy.data.curves.new('A_MainEntry_ORBIT', 'FONT')
font.body = 'ORBIT'
font.size = .80
font.align_x = 'CENTER'
font.extrude = .015
font.bevel_depth = .003
font.bevel_resolution = 1
obj = bpy.data.objects.new('A_MainEntry_ORBIT', font)
bpy.data.collections['Curved_A'].objects.link(obj)
obj.location = (-23.315, 5.25, 7.04 + 3.36)
obj.rotation_euler = (math.pi / 2, 0, math.pi / 2)
font.materials.append(bpy.data.materials['View_Office_Recessed_Head'])
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.convert(target='MESH')
obj = bpy.context.object
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bm = bmesh.new()
bm.from_mesh(obj.data)
bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
bmesh.ops.triangulate(bm, faces=list(bm.faces))
def double_triangle_area(face):
    a,b,c = (tuple(vertex.co) for vertex in face.verts)
    ab = tuple(b[i]-a[i] for i in range(3))
    ac = tuple(c[i]-a[i] for i in range(3))
    cross = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
    return math.sqrt(sum(value*value for value in cross))*.5
bmesh.ops.delete(bm, geom=[face for face in bm.faces if double_triangle_area(face) <= 1e-9], context='FACES')
bmesh.ops.delete(bm, geom=[vertex for vertex in bm.verts if not vertex.link_faces], context='VERTS')
bm.to_mesh(obj.data)
bm.free()
obj['audit_role'] = 'lettering'
obj['audit_open_allowed'] = True
normals(obj)
uv_contract(obj)
# For letters a packed channel avoids projection degeneracy on tiny edge faces.
for dest, source in zip(obj.data.uv_layers['UVMap'].data, obj.data.uv_layers['LightmapUV'].data):
    dest.uv = source.uv
changed.append(obj.name)

stone = material('View_Retail_Service_Stone_60mm', (.34,.295,.23), .69)
bronze = material('View_Retail_Restaurant_Bronze_45mm', (.22,.175,.105), .40, .45)
cladding_records = []
for level, mat, thickness, ymin, ymax in [(0,stone,.060,6.8,16.0), (2,bronze,.045,7.5,14.0), (3,bronze,.045,7.5,14.0)]:
    source = bpy.data.objects[f'A_L{level}_Outer_Glass_ChordPanels']
    vertices = []
    faces = []
    selected_starts = []
    for start in range(0, len(source.data.vertices), 8):
        front = [source.data.vertices[start+i].co.copy() for i in range(4)]
        center = sum(front, Vector()) / 4
        if not (center.x > -32 and ymin < center.y < ymax):
            continue
        normal = (front[0] - source.data.vertices[start+4].co).normalized()
        offset = len(vertices)
        vertices.extend(front)
        vertices.extend(point - normal * thickness for point in front)
        faces.extend(tuple(offset+i for i in face) for face in shell)
        selected_starts.append(start)
    if not selected_starts:
        raise RuntimeError('No authored cladding bay selected at A level ' + str(level))
    selected_ids = {start+i for start in selected_starts for i in range(8)}
    remove_ids = [face.index for face in source.data.polygons if all(i in selected_ids for i in face.vertices)]
    bm = bmesh.new()
    bm.from_mesh(source.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in remove_ids], context='FACES_ONLY')
    bmesh.ops.delete(bm, geom=[vertex for vertex in bm.verts if not vertex.link_faces], context='VERTS')
    bm.to_mesh(source.data)
    bm.free()
    source.data.update()
    normals(source)
    # The retained original UVs survive face deletion; repack only UV1 on export.
    name = f'A_L{level}_Designed_Opaque_Service_Bays'
    obj = make_mesh(name, vertices, faces, mat, 'Curved_A')
    obj['Facade_Function'] = 'Stone retail service bay' if level == 0 else 'Opaque restaurant service frontage'
    cladding_records.append({'name':name, 'panels':len(selected_starts), 'thickness_m':thickness})

# Correct color path stays intact. Limit office reflectance and give floor zones
# a physical spandrel instead of recovering the invalid COLOR_0 multiplication.
for mat in bpy.data.materials:
    if mat.name.startswith('CityModern_Metal'):
        shader = bsdf(mat)
        shader.inputs['Base Color'].default_value = (.115,.145,.16,1)
        shader.inputs['Roughness'].default_value = .45
        shader.inputs['Metallic'].default_value = .40
shader = bsdf(bpy.data.materials['View_Office_Secondary_Aluminium'])
shader.inputs['Base Color'].default_value = (.16,.19,.205,1)
shader.inputs['Metallic'].default_value = .55
shader.inputs['Roughness'].default_value = .34
for i, color in enumerate([(.028,.062,.085),(.043,.077,.095),(.050,.082,.095),(.042,.057,.062)]):
    shader = bsdf(bpy.data.materials['View_Office_Glass_' + str(i)])
    shader.inputs['Base Color'].default_value = (*color,1)
    shader.inputs['Specular IOR Level'].default_value = .55
    shader.inputs['Coat Weight'].default_value = .12
    shader.inputs['Coat Roughness'].default_value = .13
spandrel = material('View_Office_Opaque_Spandrel_550mm', (.042,.068,.083), .34, .24)
office_records = []
for code in ('B07','B08','B13'):
    glass = bpy.data.objects[f'Office_{code}_Visible_Planar_Glass_32mm']
    vertices = []
    faces = []
    count = 0
    for start in range(0, len(glass.data.vertices), 8):
        front = [glass.data.vertices[start+i].co.copy() for i in range(4)]
        back = [glass.data.vertices[start+4+i].co.copy() for i in range(4)]
        z0 = min(point.z for point in front)
        z1 = max(point.z for point in front)
        height = .55
        if z1-z0 < height + 1.5:
            raise RuntimeError('Unexpected short vision pane ' + code)
        s = len(vertices)
        for point in front + back:
            p = point.copy()
            p.z = z0 + (height if point.z > z0+.1 else 0)
            vertices.append(p)
        faces.extend(tuple(s+i for i in face) for face in shell)
        for i in (0,1,4,5):
            glass.data.vertices[start+i].co.z += height
        count += 1
    normals(glass)
    uv_contract(glass)
    obj = make_mesh(f'Office_{code}_Opaque_Spandrel_550mm', vertices, faces, spandrel, 'Office_Window_Visible')
    obj['Construction'] = 'Actual source facade pane bottom 550mm; closed 32mm opaque panel, no massing change.'
    office_records.append({'building':code, 'opaque_panels':count, 'spandrel_height_m':.55})

scene.camera = bpy.data.objects['Review_Window_UE_VFOV54']
scene['CommercialScale04_Refinement_Version'] = 1
scene['Sample_Status'] = 'Fixed-window candidate with pixel-driven entrance, retail cladding and actual-office spandrel refinements; awaiting visual review.'
(out/'fixed_window_refinements.json').write_text(json.dumps({
    'basis':'Only window-draft.png actual 1280x720 pixels; no new close-up review.',
    'entrance':'Existing width unchanged. Shorter north reveal, doors 1.70m forward, ORBIT mark shifted within existing fascia; trees unchanged.',
    'changed_entrance_parts':changed,
    'opaque_commercial_bays':cladding_records,
    'office_spandrels':office_records,
    'color_path':'COLOR_0 mistake stays corrected; contrast from material reflectance and physical opaque spandrels.',
    'camera_or_original_asset_changes':False,
    'method':'Explicit editable mesh operations through background Blender; not GUI hand modeling.'
},indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'CityDesign_CommercialScale04.blend'))
print('WINDOW_SCALE03_PIXEL_REFINEMENTS_SAVED',flush=True)
