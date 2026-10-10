"""Explicit architectural design, executed as Blender mesh edits; no random city generation.

Run Blender --background --factory-startup --threads 4 --python this.py -- OUTPUT.
The old City is read-only context. This script only saves new files under OUTPUT.
"""
import bpy
import bmesh
import math
import json
import sys
from pathlib import Path
from mathutils import Vector

OUT = Path(sys.argv[sys.argv.index('--') + 1])
SOURCE = Path(r'C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\City')
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1
scene.unit_settings.length_unit = 'METERS'
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.threads_mode = 'FIXED'
scene.render.threads = 4
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False

def collection(name):
    coll = bpy.data.collections.new(name)
    scene.collection.children.link(coll)
    return coll

mall = collection('Mall_Architecture')
neighbor = collection('Neighbor_Architecture')
context = collection('Existing_City_Context')
planting = collection('Licensed_Planting')
lighting = collection('Lighting')
cameras = collection('Cameras')
active_collection = mall

def move_to(obj, coll):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    coll.objects.link(obj)

def material(name, color, roughness=.6, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    mat.use_backface_culling = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return mat

stone = material('Mall_01_Limestone', (.58,.51,.39), .7)
ceramic = material('Mall_02_Terracotta_Ceramic', (.35,.12,.055), .48)
ivory = material('Mall_03_Precast_Ivory', (.70,.66,.55), .65)
bronze = material('Mall_04_Bronze', (.25,.15,.075), .3, .8)
glass = material('Mall_05_Glass', (.11,.19,.20), .15)
glass.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value = .55
glass.node_tree.nodes.get('Principled BSDF').inputs['IOR'].default_value = 1.45
dark = material('Mall_06_Interior_Dark', (.095,.084,.069), .75)
paving = material('Mall_07_Concrete_Paving', (.30,.30,.275), .85)
wood = material('Mall_08_Warm_Oak', (.24,.115,.045), .6)
roof = material('Mall_09_Roof_Membrane', (.15,.16,.15), .85)
soil = material('Mall_10_Planter_Soil', (.065,.055,.035), 1)
light = material('Mall_11_Luminous_Soffit', (.95,.67,.32), .4)
light.node_tree.nodes.get('Principled BSDF').inputs['Emission Color'].default_value = (.95,.65,.27,1)
light.node_tree.nodes.get('Principled BSDF').inputs['Emission Strength'].default_value = .7
brick = material('Neighbor_01_Warm_Clay_Brick', (.31,.19,.115), .8)
nstone = material('Neighbor_02_Pale_Stone', (.56,.53,.46), .72)
nglass = material('Neighbor_03_Glass', (.075,.13,.145), .17)
nglass.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value = .35
nmetal = material('Neighbor_04_Charcoal_Metal', (.06,.072,.075), .32, .75)

# Original shader approximation, not a measured brick scan. UVs retain metre-scale coursing.
brick_nodes=brick.node_tree.nodes
brick_links=brick.node_tree.links
brick_coord=brick_nodes.new('ShaderNodeUVMap')
brick_coord.uv_map='UVMap'
brick_tex=brick_nodes.new('ShaderNodeTexBrick')
brick_tex.inputs['Scale'].default_value=1.2
brick_tex.inputs['Mortar Size'].default_value=.009
brick_tex.inputs['Brick Width'].default_value=.30
brick_tex.inputs['Row Height'].default_value=.075
brick_tex.inputs['Color1'].default_value=(.38,.22,.115,1)
brick_tex.inputs['Color2'].default_value=(.25,.14,.072,1)
brick_tex.inputs['Mortar'].default_value=(.22,.205,.18,1)
brick_links.new(brick_coord.outputs['UV'],brick_tex.inputs['Vector'])
brick_links.new(brick_tex.outputs['Color'],brick_nodes.get('Principled BSDF').inputs['Base Color'])
brick_bump=brick_nodes.new('ShaderNodeBump')
brick_bump.inputs['Strength'].default_value=.22
brick_bump.inputs['Distance'].default_value=.008
brick_links.new(brick_tex.outputs['Fac'],brick_bump.inputs['Height'])
brick_links.new(brick_bump.outputs['Normal'],brick_nodes.get('Principled BSDF').inputs['Normal'])

# Existing licensed travertine, with physical tiling; no downloaded texture is introduced.
nodes = stone.node_tree.nodes
links = stone.node_tree.links
tex = nodes.new('ShaderNodeTexImage')
tex.image = bpy.data.images.load(str(SOURCE / 'Facade/Travertine001_2K-JPG_Color.jpg'))
coord = nodes.new('ShaderNodeUVMap')
coord.uv_map='UVMap'
links.new(coord.outputs['UV'], tex.inputs['Vector'])
mix = nodes.new('ShaderNodeMixRGB')
mix.blend_type = 'MULTIPLY'
mix.inputs[0].default_value = .38
mix.inputs[2].default_value = (.66,.61,.49,1)
links.new(tex.outputs['Color'], mix.inputs[1])
# A direct image link is supported consistently by GLB exporters; preserve the source colors.
links.new(tex.outputs['Color'], nodes.get('Principled BSDF').inputs['Base Color'])

def finish(obj, mat, bevel=0):
    move_to(obj, active_collection)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Authored edge bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 2
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj

def box(name, bounds, mat, bevel=.025):
    xmin,xmax,ymin,ymax,zmin,zmax = bounds
    assert xmax>xmin and ymax>ymin and zmax>zmin, (name,bounds)
    bpy.ops.mesh.primitive_cube_add(size=1, location=((xmin+xmax)/2,(ymin+ymax)/2,(zmin+zmax)/2))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (xmax-xmin,ymax-ymin,zmax-zmin)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, mat, bevel)

def prism(name, outline, zmin, zmax, mat, bevel=.04):
    vertices = [(x,y,z) for z in (zmin,zmax) for x,y in outline]
    n = len(outline)
    faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    mesh = bpy.data.meshes.new(name+'_Mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    active_collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    result = finish(obj,mat,bevel)
    obj.select_set(False)
    return result

def bar(name, start, end, radius, mat):
    delta = Vector(end)-Vector(start)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=radius, depth=delta.length,
        location=(Vector(start)+Vector(end))/2)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = delta.to_track_quat('Z','Y').to_euler()
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    return finish(obj,mat)

G = 6.9
# The commercial footprint has a clipped arrival corner, not a box with fake facade lines.
outline = [(-68,-10),(-30,-10),(-24,-4),(-24,62),(-68,62)]
prism('Mall_Foundation_Clipped_Corner', outline, G-.35, G+.12, stone)
prism('Mall_Arrival_Plaza', [(-39,-18),(-19,-18),(-19,2),(-24,2),(-24,-4),(-30,-10),(-39,-10)],
      G-.08,G+.03,paving,.035)
box('Mall_West_Anchor_Wall',(-68,-67.45,-10,62,G,G+21.7),stone)
box('Mall_North_Service_Wall',(-68,-24,61.45,62,G,G+21.7),ceramic)
box('Mall_Anchor_East_Interior_Wall',(-42.5,-42,-10,62,G,G+21.2),dark)
box('Mall_Anchor_Near_Solid_Return',(-68,-45,-10,-9.5,G,G+20.9),stone)

# Slabs retain a real central double-height entrance void and a terrace setback above.
for level,height in enumerate((0,5.4,10.2,15.0,19.8)):
    z=G+height
    if level in (1,2):
        for label,rect in [('anchor',(-67.5,-42.5,-9.5,61.5)),
                           ('near_gallery',(-42.5,-24.3,-4,10)),
                           ('far_gallery',(-42.5,-24.3,30,61.5)),
                           ('inner_bridge',(-42.5,-38.5,10,30))]:
            box(f'Mall_L{level}_{label}_Slab',(*rect,z-.22,z),ivory,.045)
    else:
        prism(f'Mall_L{level}_Continuous_Slab',outline,z-.25,z,ivory,.055)

# Ground shopfronts: separate doors, glazing, piers and a readable continuous pedestrian canopy.
for bay,(a,b) in enumerate(((-4,3),(3,10),(30,38),(38,46),(46,54),(54,61))):
    box(f'Mall_Shop_{bay+1}_Glass',(-24.72,-24.64,a+.4,b-.4,G+.55,G+4.6),glass,.012)
    for y in (a+.3,b-.3):
        box(f'Mall_Shop_{bay+1}_Stone_Pier_{y:.1f}',(-25.05,-23.85,y-.22,y+.22,G,G+5.4),stone,.05)
    for y in (a+(b-a)*.33,a+(b-a)*.66):
        box(f'Mall_Shop_{bay+1}_Bronze_Mullion_{y:.1f}',(-24.56,-24.46,y-.035,y+.035,G+.5,G+4.68),bronze,.01)
    box(f'Mall_Shop_{bay+1}_Transom',(-24.56,-24.44,a+.4,b-.4,G+3.15,G+3.25),bronze,.01)
    box(f'Mall_Shop_{bay+1}_Plinth',(-24.8,-24.25,a,b,G,G+.5),stone,.04)
    box(f'Mall_Shop_{bay+1}_Sign_Fascia',(-24.8,-23.9,a,b,G+4.67,G+5.35),ceramic,.045)
    box(f'Mall_Shop_{bay+1}_Interior_Counter',(-28.8,-27.8,a+1.1,b-1.1,G,G+1.15),wood,.04)
    box(f'Mall_Shop_{bay+1}_Rear_Interior',(-33.1,-32.85,a,b,G,G+4.6),dark,.02)
box('Mall_Continuous_Shop_Canopy',(-24.8,-21.65,-4,61,G+5.30,G+5.53),bronze,.04)
box('Mall_Canopy_Luminous_Recess',(-24.25,-22.05,-3.7,60.7,G+5.25,G+5.28),light,.005)

# Upper-level ceramic and stone facade bays; large opaque wall proportion differs from office towers.
upper_bays = [(-4,4),(4,12),(12,20),(20,28),(28,36),(36,44),(44,52),(52,60)]
facade_area = 0
glass_area = 0
for level,base in enumerate((5.4,10.2,15.0),start=1):
    for bay,(a,b) in enumerate(upper_bays):
        if level==1 and 10<a+4<30:
            continue
        z=G+base
        box(f'Mall_L{level}_Bay{bay+1}_Ceramic_Spandrel',(-25.0,-23.9,a,b,z,z+1.0),ceramic,.045)
        box(f'Mall_L{level}_Bay{bay+1}_Ivory_Head',(-25.0,-23.88,a,b,z+3.9,z+4.8),ivory,.045)
        for y in (a,b):
            box(f'Mall_L{level}_Bay{bay+1}_Pier_{y}',(-25.1,-23.75,y-.6,y+.6,z+1,z+3.9),stone,.045)
        box(f'Mall_L{level}_Bay{bay+1}_Deep_Glass',(-25.28,-25.20,a+.75,b-.75,z+1.15,z+3.75),glass,.01)
        box(f'Mall_L{level}_Bay{bay+1}_Interior_Shadow',(-28.85,-28.6,a+.65,b-.65,z+1,z+3.9),dark,.025)
        for y in (a+2.9,a+5.1):
            box(f'Mall_L{level}_Bay{bay+1}_Mullion_{y}',(-24.93,-24.85,y-.04,y+.04,z+1.12,z+3.78),bronze,.01)
        box(f'Mall_L{level}_Bay{bay+1}_Projecting_Sill',(-25.2,-23.45,a+.3,b-.3,z+.88,z+1.05),stone,.04)
        facade_area+=(b-a)*4.8
        glass_area+=(b-a-1.5)*2.6

# A true recessed portal, two-storey glazed entrance, deep jambs and folded canopy.
for y in (10,30):
    box(f'Mall_Main_Entry_Stone_Jamb_{y}',(-28.4,-23.7,y-.72,y+.72,G,G+10.15),stone,.055)
box('Mall_Main_Entry_Recessed_Glass',(-27.6,-27.48,10.8,29.2,G+.10,G+9.65),glass,.015)
box('Mall_Main_Entry_Head',(-28.5,-23.45,9.5,30.5,G+9.7,G+10.25),ivory,.05)
box('Mall_Main_Entry_Portal_Floor',(-28.5,-20.9,10.5,29.5,G+.04,G+.14),stone,.035)
for y in (14,18,22,26):
    box(f'Mall_Main_Entry_Vertical_{y}',(-27.34,-27.21,y-.08,y+.08,G+.15,G+9.68),bronze,.012)
for y in (18,22):
    box(f'Mall_Main_Entry_Door_Handle_{y}',(-27.14,-27.07,y-.045,y+.045,G+1.05,G+2.0),bronze,.01)
for z in (G+3.1,G+6.2):
    box(f'Mall_Main_Entry_Transom_{z}',(-27.35,-27.18,10.7,29.3,z,z+.13),bronze,.012)
# A six-sided canopy plan, stepped leading edge and an angled pair of metal support arms.
prism('Mall_Main_Entry_Folded_Canopy',[(-27.8,9),(-21.4,9),(-19.8,12),(-19.8,28),(-21.4,31),(-27.8,31)],
      G+5.75,G+6.12,bronze,.04)
prism('Mall_Main_Entry_Canopy_Soffit',[(-26.8,10),(-21.7,10),(-20.2,12.5),(-20.2,27.5),(-21.7,30),(-26.8,30)],
      G+5.69,G+5.74,light,.015)
for y in (10.1,29.9):
    bar(f'Mall_Entry_Suspension_{y}',(-24.7,y,G+9.3),(-20.6,y,G+6.1),.095,bronze)
box('Mall_Entry_Upper_Interior_Balcony',(-37.8,-29.6,10.8,29.2,G+5.05,G+5.3),ivory,.04)
box('Mall_Entry_Interior_Rear_Wall',(-38.0,-37.8,10.8,29.2,G,G+10.0),dark,.025)
bar('Mall_Entry_Interior_Balcony_Rail',(-29.6,11,G+6.4),(-29.6,29,G+6.4),.055,bronze)

# Anchor facade ceramic ribs break up the long solid wall without copying the office window grid.
for y in (-6,0,6,12,18,24,30,36,42,48,54,60):
    box(f'Mall_West_Anchor_Rib_{y}',(-68.16,-67.4,y-.075,y+.075,G+.6,G+21.0),ceramic,.025)
for x in (-64,-58,-52,-46):
    box(f'Mall_Near_Anchor_Vertical_Stone_{x}',(x-.5,x+.5,-10.18,-9.4,G+.7,G+20.7),ivory,.035)
box('Mall_Near_Anchor_Bronze_Art_Panel',(-62.5,-51,-10.24,-10.19,G+6.8,G+14.4),bronze,.012)
for x in (-62,-60.6,-59.2,-57.8,-56.4,-55,-53.6,-52.2):
    box(f'Mall_Art_Panel_Ceramic_Fin_{x}',(x-.075,x+.075,-10.44,-10.2,G+7,G+14.2),ceramic,.02)

# Corner cafe has its own street-facing glazing and visible canopy under the clipped corner.
box('Mall_Corner_Cafe_Near_Glass',(-44.7,-30.5,-9.25,-9.17,G+.55,G+4.6),glass,.01)
box('Mall_Corner_Cafe_Near_Head',(-45.0,-30.0,-10.1,-9,G+4.65,G+5.35),ceramic,.035)
for x in (-44.5,-40.8,-37.1,-33.4,-30.6):
    box(f'Mall_Corner_Cafe_Stone_Pier_{x}',(x-.14,x+.14,-9.75,-9.05,G+.45,G+4.7),stone,.03)
box('Mall_Corner_Cafe_Canopy',(-45,-30,-12.1,-9.0,G+5.30,G+5.52),bronze,.035)

# Close the upper cafe return and the clipped corner; they are real exterior walls.
for level,base in enumerate((5.4,10.2,15.0),start=1):
    z=G+base
    box(f'Mall_L{level}_Near_Return_Clay_Spandrel',(-45,-30,-10.0,-9.5,z,z+1.0),ceramic,.035)
    box(f'Mall_L{level}_Near_Return_Stone_Head',(-45,-30,-10.0,-9.5,z+3.9,z+4.8),ivory,.035)
    for bay,(a,b) in enumerate(((-45,-37.5),(-37.5,-30))):
        box(f'Mall_L{level}_Near_Return_Bay{bay}_Glass',(a+.65,b-.65,-8.95,-8.87,z+1.15,z+3.75),glass,.01)
        box(f'Mall_L{level}_Near_Return_Bay{bay}_Shadow',(a+.65,b-.65,-6.9,-6.65,z+1,z+3.9),dark,.02)
        box(f'Mall_L{level}_Near_Return_Bay{bay}_Sill',(a+.3,b-.3,-10.25,-8.75,z+.88,z+1.05),stone,.035)
    for x in (-45,-37.5,-30):
        box(f'Mall_L{level}_Near_Return_Pier_{x}',(x-.55,x+.55,-10.1,-9.25,z+1,z+3.9),stone,.04)
prism('Mall_Clipped_Corner_Ceramic_Blade',[(-30,-10),(-24,-4),(-24.48,-4),(-30,-9.52)],
      G,G+19.8,ceramic,.025)

def lettering(name,body,position,rotation,size,mat):
    data=bpy.data.curves.new(name,'FONT')
    data.body=body
    data.align_x='CENTER'
    data.size=size
    data.extrude=.018
    data.bevel_depth=.003
    data.bevel_resolution=1
    obj=bpy.data.objects.new(name,data)
    active_collection.objects.link(obj)
    obj.location=position
    obj.rotation_euler=rotation
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.convert(target='MESH')
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    bm=bmesh.new()
    bm.from_mesh(bpy.context.object.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
    bmesh.ops.dissolve_degenerate(bm,dist=.000001,edges=list(bm.edges))
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(bpy.context.object.data)
    bm.free()
    bpy.context.object.data.update()
    return finish(bpy.context.object,mat)

lettering('Mall_Commercial_Identity_Galleria','G A L L E R I A',(-23.69,20,G+10.48),
          (math.pi/2,0,math.pi/2),1.05,bronze)
lettering('Mall_Corner_Identity_The_Arcade','THE ARCADE',(-56.9,-10.49,G+10.1),
          (math.pi/2,0,0),.70,ivory)

# Upper dining pavilion and a usable setback terrace have actual floor, parapet and planting beds.
box('Mall_Roof_Anchor_Membrane',(-67.5,-43,-9.3,61.3,G+19.8,G+20.1),roof,.02)
box('Mall_Dining_Pavilion_Stone_Back',(-56,-55.5,3,44,G+20,G+24.2),stone,.04)
box('Mall_Dining_Pavilion_Near_Wall',(-56,-35,2.5,3,G+20,G+24.2),ceramic,.04)
box('Mall_Dining_Pavilion_Far_Wall',(-56,-35,43.5,44,G+20,G+24.2),ceramic,.04)
box('Mall_Dining_Pavilion_Glass',(-35.5,-35.42,3.5,43,G+20.3,G+23.75),glass,.012)
for y in (4,10.5,17,23.5,30,36.5,43):
    box(f'Mall_Dining_Pavilion_Frame_{y}',(-35.25,-35.12,y-.055,y+.055,G+20.15,G+23.85),bronze,.012)
box('Mall_Dining_Pavilion_Overhanging_Roof',(-56.9,-33.5,1.6,44.8,G+24.0,G+24.4),ivory,.055)
box('Mall_Terrace_Stone_Deck',(-35.3,-24.3,-3.5,59.5,G+19.8,G+19.95),stone,.035)
box('Mall_Terrace_Street_Parapet',(-24.9,-24.25,-3.5,60,G+19.95,G+20.95),ivory,.045)
box('Mall_Terrace_Street_Cornice',(-25.15,-23.65,-4,60.5,G+19.75,G+20.0),stone,.055)
for index,(a,b) in enumerate(((-2,9),(33,44),(47,58))):
    box(f'Mall_Terrace_Planter{index}_Body',(-27.1,-25.0,a,b,G+19.95,G+20.6),stone,.035)
    box(f'Mall_Terrace_Planter{index}_Soil',(-26.92,-25.17,a+.18,b-.18,G+20.60,G+20.64),soil,.01)
for y in (14,23,40,51):
    box(f'Mall_Terrace_Bench_{y}',(-32.6,-30.9,y-.55,y+.55,G+19.95,G+20.45),wood,.055)
box('Mall_Roof_Service_Screen',(-64,-58,48,58,G+20.1,G+22.6),bronze,.04)
for y in (48.5,50,51.5,53,54.5,56,57.5):
    box(f'Mall_Service_Screen_Reveal_{y}',(-57.98,-57.94,y-.35,y+.35,G+20.5,G+22.3),dark,.01)

# Adjacent warm masonry building: two joined wings, recessed private windows and a setback top.
active_collection=neighbor
box('Neighbor_Foundation',(-48.0,-22.0,76,110,G-.3,G+.1),nstone,.045)
box('Neighbor_West_Enclosure',(-48,-47.5,76,110,G,G+38.9),brick,.04)
box('Neighbor_Far_Enclosure',(-48,-22,109.5,110,G,G+38.9),brick,.04)
box('Neighbor_Interior_East_Back',(-25,-24.7,76.5,109.5,G,G+38.9),dark,.025)
box('Neighbor_Interior_Near_Back',(-47.5,-24.7,78.6,78.9,G,G+38.9),dark,.025)
box('Neighbor_Ground_East_Glass',(-22.55,-22.48,77,109,G+.6,G+4.35),nglass,.012)
box('Neighbor_Ground_Near_Glass',(-47,-23,76.5,76.58,G+.6,G+4.35),nglass,.012)
for y in (76.5,83,89.5,96,102.5,109):
    box(f'Neighbor_Retail_Stone_Pier_{y}',(-23.0,-21.85,y-.25,y+.25,G,G+4.75),nstone,.04)
box('Neighbor_Retail_East_Canopy',(-23.1,-20.4,76,110,G+4.65,G+4.9),nmetal,.035)
box('Neighbor_Retail_Near_Canopy',(-48,-22,74.4,76.9,G+4.65,G+4.9),nmetal,.035)
n_facade_area=0
n_glass_area=0
for floor in range(10):
    z=G+4.8+floor*3.4
    box(f'Neighbor_F{floor+1}_Floor',(-47.6,-22.35,76.4,109.6,z-.17,z),nstone,.025)
    box(f'Neighbor_F{floor+1}_East_Brick_Spandrel',(-22.9,-21.95,76,110,z,z+.85),brick,.035)
    box(f'Neighbor_F{floor+1}_East_Stone_Head',(-22.9,-21.95,76,110,z+2.85,z+3.4),nstone,.035)
    box(f'Neighbor_F{floor+1}_Near_Brick_Spandrel',(-48,-22,75.94,76.9,z,z+.85),brick,.035)
    box(f'Neighbor_F{floor+1}_Near_Stone_Head',(-48,-22,75.94,76.9,z+2.85,z+3.4),nstone,.035)
    for bay,(a,b) in enumerate(((76,82.8),(82.8,89.6),(89.6,96.4),(96.4,103.2),(103.2,110))):
        for y in (a,b):
            box(f'Neighbor_F{floor+1}_Bay{bay}_Clay_Pier_{y}',(-22.85,-21.95,y-.65,y+.65,z+.85,z+2.85),brick,.035)
        box(f'Neighbor_F{floor+1}_Bay{bay}_Glass',(-23.43,-23.35,a+.95,b-.95,z+1.0,z+2.7),nglass,.008)
        box(f'Neighbor_F{floor+1}_Bay{bay}_Stone_Sill',(-23.4,-21.67,a+.65,b-.65,z+.75,z+.95),nstone,.035)
        box(f'Neighbor_F{floor+1}_Bay{bay}_Metal_Division',(-23.2,-23.10,(a+b)/2-.05,(a+b)/2+.05,z+1,z+2.75),nmetal,.01)
        n_facade_area+=(b-a)*3.4
        n_glass_area+=(b-a-1.9)*1.7
    for bay,(a,b) in enumerate(((-48,-41.5),(-41.5,-35),(-35,-28.5),(-28.5,-22))):
        for x in (a,b):
            box(f'Neighbor_F{floor+1}_Near_Bay{bay}_Pier_{x}',(x-.6,x+.6,75.94,76.9,z+.85,z+2.85),brick,.035)
        box(f'Neighbor_F{floor+1}_Near_Bay{bay}_Glass',(a+.85,b-.85,77.35,77.43,z+1,z+2.7),nglass,.008)
        box(f'Neighbor_F{floor+1}_Near_Bay{bay}_Sill',(a+.6,b-.6,75.75,77.45,z+.75,z+.95),nstone,.03)
    # Paired balconies only on alternating bands of a single bay, intentionally asymmetrical.
    if floor in (1,3,5,7):
        box(f'Neighbor_F{floor+1}_Balcony_Deck',(-22.4,-19.85,89.9,96.0,z-.10,z+.12),nstone,.035)
        box(f'Neighbor_F{floor+1}_Balcony_Opaque_Front',(-20.05,-19.90,90,95.9,z+.12,z+.80),brick,.03)
        bar(f'Neighbor_F{floor+1}_Balcony_Top_Rail',(-19.97,90,z+1.05),(-19.97,95.9,z+1.05),.035,nmetal)
        for y in (90,92,94,95.9):
            bar(f'Neighbor_F{floor+1}_Balcony_Post_{y}',(-19.97,y,z+.80),(-19.97,y,z+1.06),.028,nmetal)

for y in (76.35,109.65):
    box(f'Neighbor_East_Corner_Stone_Pier_{y}',(-23.3,-21.6,y-.45,y+.45,G+4.8,G+38.8),nstone,.045)
box('Neighbor_Roof_Main_Coping',(-48.3,-21.7,75.7,110.3,G+38.7,G+39.05),nstone,.06)
box('Neighbor_Setback_Penthouse',(-45,-25,80,106,G+39,G+43.7),brick,.06)
box('Neighbor_Setback_Near_Glass',(-42.5,-27.5,79.78,79.86,G+39.7,G+42.9),nglass,.012)
box('Neighbor_Setback_East_Glass',(-24.98,-24.9,82,103,G+39.7,G+42.9),nglass,.012)
box('Neighbor_Setback_Roof',(-45.5,-24.4,79.5,106.5,G+43.6,G+44.0),nstone,.05)
box('Neighbor_Terrace_East_Parapet',(-22.6,-22,77,109,G+39.0,G+40),nstone,.04)
box('Neighbor_Terrace_Near_Parapet',(-47,-22.3,76,76.6,G+39,G+40),nstone,.04)
box('Neighbor_Roof_HVAC_1',(-43,-40,101,104,G+44,G+45.1),nmetal,.07)
box('Neighbor_Roof_HVAC_2',(-38,-35,101,104,G+44,G+45.1),nmetal,.07)

# Author UV0 from physical metre coordinates. UV1 is a separate packed lightmap layout.
for coll in (mall,neighbor):
    for obj in coll.objects:
        if obj.type!='MESH':
            continue
        uv=obj.data.uv_layers.get('UVMap') or obj.data.uv_layers.new(name='UVMap')
        obj.data.uv_layers.active=uv
        for face in obj.data.polygons:
            axis=max(range(3),key=lambda i:abs(face.normal[i]))
            for li in face.loop_indices:
                p=obj.matrix_world@obj.data.vertices[obj.data.loops[li].vertex_index].co
                uv.data[li].uv=((p.y,p.z) if axis==0 else (p.x,p.z) if axis==1 else (p.x,p.y))
                uv.data[li].uv/=1.2
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active=obj
        uv1=obj.data.uv_layers.new(name='LightmapUV')
        obj.data.uv_layers.active=uv1
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.03)
        bpy.ops.object.mode_set(mode='OBJECT')
        obj.data.uv_layers.active=uv
        uv.active_render=True

# Bake the original brick shader once into a small tile, so exports carry the same surface.
texture_dir=OUT/'Textures'
texture_dir.mkdir(exist_ok=True)
for coll in (mall,neighbor):
    coll.hide_render=True
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_plane_add(size=1.2)
bake_plane=bpy.context.object
bake_plane.name='Temporary_Brick_Texture_Bake_Plane'
bake_plane.data.materials.append(brick)
old_samples=scene.cycles.samples
scene.cycles.samples=1
scene.render.bake.margin=8
bpy.context.view_layer.update()
baked=[]
for label,bake_type,colorspace in (('BaseColor','DIFFUSE','sRGB'),('Normal','NORMAL','Non-Color')):
    img=bpy.data.images.new('Neighbor_Brick_'+label,width=512,height=512,alpha=False)
    img.colorspace_settings.name=colorspace
    sink=brick_nodes.new('ShaderNodeTexImage')
    sink.image=img
    brick_nodes.active=sink
    bpy.ops.object.bake(type=bake_type,pass_filter={'COLOR'} if bake_type=='DIFFUSE' else set())
    img.filepath_raw=str(texture_dir/('Neighbor_Brick_'+label+'.png'))
    img.file_format='PNG'
    img.save()
    baked.append(sink)
bpy.data.objects.remove(bake_plane,do_unlink=True)
for coll in (mall,neighbor):
    coll.hide_render=False
scene.cycles.samples=old_samples
for sink in baked:
    brick_links.new(brick_coord.outputs['UV'],sink.inputs['Vector'])
brick_links.new(baked[0].outputs['Color'],brick_nodes.get('Principled BSDF').inputs['Base Color'])
normal_map=brick_nodes.new('ShaderNodeNormalMap')
normal_map.uv_map='UVMap'
brick_links.new(baked[1].outputs['Color'],normal_map.inputs['Color'])
brick_links.new(normal_map.outputs['Normal'],brick_nodes.get('Principled BSDF').inputs['Normal'])
print('ARCHITECTURE_AND_TEXTURES_COMPLETE',flush=True)

def import_context(file,coll):
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE/file))
    new=set(bpy.data.objects)-before
    for obj in new:
        move_to(obj,coll)
    return new

old=import_context('modern-city.glb',context)
for obj in list(old):
    if any(name in obj.name for name in ('CityModern_B01_','CityModern_B02_','CityModern_B03_')):
        bpy.data.objects.remove(obj,do_unlink=True)
    elif obj.name.startswith('CityModern_Skyline'):
        obj.scale=(.65,.60,1.5)
        obj.location=(0,120,-3.45)
import_context('city-sidewalk.glb',context)
import_context('city-road-markings.glb',context)
active_collection=context
asphalt=material('Context_Road_Asphalt',(.06,.07,.073),.9)
box('Context_Road_Surface',(-18.4,18.4,-40,420,G-.15,G-.03),asphalt,0)
box('Context_Ground_Backdrop',(-2000,2000,-2000,2000,G-.45,G-.3),paving,0)

# Reuse licensed planting in four deliberately placed foreground positions and three terrace beds.
tree_objs=import_context('OOW_City_Linden.glb',planting)
tree_meshes=[o for o in tree_objs if o.type=='MESH']
tree_parent=bpy.data.objects.new('Licensed_Bistro_Linden_Master',None)
planting.objects.link(tree_parent)
for obj in tree_meshes:
    obj.parent=tree_parent
tree_parent.location=(-20.3,-5,G)
tree_parent.scale=(.78,)*3
for index,(x,y,z,scale) in enumerate(((-20.3,40,G,.78),(-20.3,68,G,.78),(-20.3,117,G,.78),
                                     (-26,3,G+20.65,.32),(-26,39,G+20.65,.30),(-26,53,G+20.65,.32))):
    root=tree_parent.copy()
    root.name=f'Licensed_Linden_Placement_{index+1}'
    planting.objects.link(root)
    root.location=(x,y,z)
    root.scale=(scale,)*3
    for source_obj in tree_meshes:
        clone=source_obj.copy()
        clone.data=source_obj.data
        planting.objects.link(clone)
        clone.parent=root

# Same fixed window view as City, kept separately from an architectural review camera.
def camera(name,position,target,vertical_fov):
    data=bpy.data.cameras.new(name)
    data.type='PERSP'
    data.sensor_fit='VERTICAL'
    data.sensor_height=24
    data.lens=24/(2*math.tan(math.radians(vertical_fov/2)))
    data.clip_start=.1
    data.clip_end=4000
    obj=bpy.data.objects.new(name,data)
    cameras.objects.link(obj)
    obj.location=position
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    return obj

window=camera('Review_Window_UE_VFOV54',(26,-42,37),(-22,115,19),54)
close=camera('Review_Mall_Close',(18,-24,24),(-39,17,18.5),48)
near=camera('Review_Neighbor_Close',(9,45,32),(-31,94,28),47)
world=bpy.data.worlds.new('Review_Daylight')
scene.world=world
world.use_nodes=True
sky=world.node_tree.nodes.new('ShaderNodeTexSky')
sky.sky_type='MULTIPLE_SCATTERING'
sky.sun_elevation=math.radians(35)
sky.sun_rotation=math.radians(-45)
sky.sun_disc=False
world.node_tree.links.new(sky.outputs['Color'],world.node_tree.nodes.get('Background').inputs['Color'])
world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.35
data=bpy.data.lights.new('Review_Sun','SUN')
data.energy=2.6
data.angle=math.radians(1.4)
obj=bpy.data.objects.new('Review_Sun',data)
lighting.objects.link(obj)
obj.rotation_euler=Vector((-1,1,-1.5)).to_track_quat('-Z','Y').to_euler()
data=bpy.data.lights.new('Entry_Interior_Warm_Fill','AREA')
data.energy=750
data.color=(1,.72,.40)
data.shape='RECTANGLE'
data.size=8
data.size_y=12
obj=bpy.data.objects.new('Entry_Interior_Warm_Fill',data)
lighting.objects.link(obj)
obj.location=(-33,20,G+9.4)

scene['Design_Method']='Explicit building designs executed as Blender mesh operations; not GUI hand modeling.'
scene['Reference']='city-window-target-v3.png; accepted AI art direction, never used as a scene background.'
scene['Source_Context']='Read-only original City GLB, original sidewalk and road marks; B01/B02/B03 removed only in this blend.'
scene['Coordinates']='Blender metres (gltf x,-gltf z,gltf y); UE cm = (100*x,-100*y,100*z).'
scene['Integration_Status']='Independent asset sample. Not imported into UE, not deployed.'
scene['Material_Provenance']='Original color materials and brick shader approximation; ambientCG Travertine001 CC0; licensed ORCA/Bistro linden CC BY4.0.'
scene['Mall_Upper_Facade_Glass_Ratio']=glass_area/facade_area
scene['Neighbor_East_Upper_Facade_Glass_Ratio']=n_glass_area/n_facade_area

report={
    'method':scene['Design_Method'],
    'reference':'city-window-target-v3.png',
    'coordinates':scene['Coordinates'],
    'camera':{'blenderMetres':[26,-42,37],'target':[-22,115,19],'verticalFov':54,'aspect':'16:9'},
    'facadeDesignArea':{
        'mallUpperEast':{'grossSquareMetres':facade_area,'glazedSquareMetres':glass_area,'ratio':glass_area/facade_area},
        'neighborUpperEast':{'grossSquareMetres':n_facade_area,'glazedSquareMetres':n_glass_area,'ratio':n_glass_area/n_facade_area},
        'note':'Opening rectangles on named principal upper elevations; excludes side/back/roof, entrance and shopfronts; not a whole-building glass percentage.'},
    'collectionObjects':{c.name:len(c.objects) for c in (mall,neighbor,context,planting)},
    'scope':'Editable original meshes, standalone blend, CPU review; original City map and build scripts untouched.'}
(OUT/'design_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

# The editable parts stay intact. Two hidden export copies consolidate by building and material.
export_collection=collection('Export_Architecture_Batched')
export_meshes=[]
for coll,name,pivot in ((mall,'OOW_Mall01_Architecture',(-46,26,G)),
                        (neighbor,'OOW_Neighbor01_Architecture',(-35,93,G))):
    bpy.ops.object.select_all(action='DESELECT')
    copies=[]
    for source_obj in coll.objects:
        if source_obj.type!='MESH':
            continue
        clone=source_obj.copy()
        clone.data=source_obj.data.copy()
        export_collection.objects.link(clone)
        clone.select_set(True)
        copies.append(clone)
    bpy.context.view_layer.objects.active=copies[0]
    bpy.ops.object.join()
    joined=bpy.context.object
    joined.name=name
    joined.data.name=name+'_Mesh'
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    for vert in joined.data.vertices:
        vert.co-=Vector(pivot)
    joined.location=pivot
    joined.data.uv_layers.active=joined.data.uv_layers['LightmapUV']
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.002)
    bpy.ops.object.mode_set(mode='OBJECT')
    joined.data.uv_layers.active=joined.data.uv_layers['UVMap']
    joined.data.uv_layers['UVMap'].active_render=True
    export_meshes.append(joined)
bpy.ops.file.pack_all()
bpy.ops.file.pack_all()

# Export new architecture only. Preserve named building parts and both UV layers.
bpy.ops.object.select_all(action='DESELECT')
for obj in export_meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active=export_meshes[0]
bpy.ops.export_scene.gltf(filepath=str(OUT/'CityDesign_Mall01_Architecture.glb'),export_format='GLB',use_selection=True,
    export_apply=False,export_texcoords=True,export_normals=True,export_materials='EXPORT',export_cameras=False)
bpy.ops.export_scene.fbx(filepath=str(OUT/'CityDesign_Mall01_Architecture.fbx'),use_selection=True,
    object_types={'MESH'},apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',
    axis_forward='-Y',axis_up='Z',use_mesh_modifiers=False,add_leaf_bones=False,path_mode='COPY',embed_textures=True)
bpy.ops.object.select_all(action='DESELECT')
export_collection.hide_render=True
export_collection.hide_viewport=True
scene.camera=window
scene.render.resolution_x=960
scene.render.resolution_y=540
scene.render.filepath=str(OUT/'preview-window.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'CityDesign_Mall01.blend'))
print('SAMPLE_SAVED',str(OUT/'CityDesign_Mall01.blend'),flush=True)
print('Run render_saved_sample.py from a fresh Blender process for CPU previews.',flush=True)
