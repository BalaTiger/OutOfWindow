"""Authored Galaxy-informed A/B sample, explicit mesh editing; no random city generator.

Runs in background Blender. Saves a new independent blend; never saves the source blend.
"""
import bpy
import bmesh
import math
import json
import sys
from pathlib import Path
from mathutils import Vector

OUT=Path(sys.argv[sys.argv.index('--')+1])
BASE=Path(r'C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\CityDesign_WindowScale03\CityDesign_WindowScale03_CHECKPOINT_BASE_ONLY.blend')
bpy.ops.wm.open_mainfile(filepath=str(BASE))
scene=bpy.context.scene
G=6.9
PAVE=7.04
for name in ('Curved_A','Curved_B','Curved_Bridge','Curved_C','Curved_Site','Office_Corner','Export_Curved_Batched'):
    coll=bpy.data.collections.get(name)
    if coll:
        for obj in list(coll.all_objects): bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.collections.remove(coll)
# The old rooftop tree placements belonged to the removed Mall01 roofs.
old_roof_trees=[obj for obj in bpy.data.objects if obj.type=='EMPTY' and 'Licensed_Linden_Placement' in obj.name and obj.location.z>G+2]
for obj in old_roof_trees:
    for child in list(obj.children): bpy.data.objects.remove(child,do_unlink=True)
    bpy.data.objects.remove(obj,do_unlink=True)
for obj in list(bpy.data.objects):
    if obj.type=='CAMERA' and obj.name!='Review_Window_UE_VFOV54': bpy.data.objects.remove(obj,do_unlink=True)
scene.unit_settings.system='METRIC'
scene.unit_settings.scale_length=1
scene.unit_settings.length_unit='METERS'
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=16
scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED'
scene.render.threads=1
scene.view_settings.view_transform='AgX'
scene.view_settings.look='AgX - Medium High Contrast'

def collection(name):
    c=bpy.data.collections.new(name);scene.collection.children.link(c);return c
A=collection('Curved_A')
B=collection('Curved_B')
BRIDGE=collection('Curved_Bridge')
C=collection('Curved_C')
SITE=collection('Curved_Site')
OFFICE=collection('Office_Window_Visible')
active=A

def mat(name,color,rough=.5,metal=0,trans=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    bs=next((node for node in m.node_tree.nodes if node.type=='BSDF_PRINCIPLED'),None)
    if bs is None:bs=m.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
    bs.name='Principled BSDF'
    output=next((node for node in m.node_tree.nodes if node.type=='OUTPUT_MATERIAL'),None)
    if output is None:output=m.node_tree.nodes.new('ShaderNodeOutputMaterial')
    m.node_tree.links.new(bs.outputs['BSDF'],output.inputs['Surface'])
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough
    bs.inputs['Metallic'].default_value=metal
    bs.inputs['Transmission Weight'].default_value=trans
    bs.inputs['IOR'].default_value=1.46
    return m
white=mat('Curve_01_Satin_Aluminium_Pearl',(.61,.635,.62),.51,.06)
soffit=mat('Curve_02_Soffit_Warm_Pale',(.32,.35,.34),.66,.04)
frame=mat('Curve_03_Graphite_Frames',(.15,.175,.18),.32,.55)
glass=mat('Curve_04_Retail_Glass',(.18,.225,.235),.17,0,.60)
glass_inner=mat('Curve_05_Courtyard_Glass',(.28,.34,.34),.14,0,.4)
dark=mat('Curve_06_Interior_Shadow',(.115,.108,.093),.76)
floor_mat=mat('Curve_07_Floor_Limestone',(.52,.49,.43),.74)
paving=mat('Curve_08_Court_Paving',(.39,.39,.36),.82)
roof_mat=mat('Curve_09_Roof_Grey',(.15,.17,.16),.84)
wood=mat('Curve_10_Cafe_Wood',(.23,.14,.075),.58)
soil=mat('Curve_11_Planter_Soil',(.045,.055,.035),1)
plant=mat('Curve_12_Planting_Green',(.10,.18,.065),.95)
light=mat('Curve_13_Interior_Warm',(.68,.46,.25),.6)
bs=light.node_tree.nodes.get('Principled BSDF');bs.inputs['Emission Color'].default_value=(.9,.63,.30,1);bs.inputs['Emission Strength'].default_value=.25
placeholder=mat('C_Only_Skyline_Blockout_Not_Finished',(.40,.44,.47),.65)
oglass=mat('Office_01_Vision_Glass',(.34,.43,.48),.095,0,.32)
ospandrel=mat('Office_02_Opaque_Spandrel_Glass',(.16,.21,.245),.20,.08)
ometal=mat('Office_03_Silver_Aluminium',(.38,.43,.46),.27,.78)
ointerior=mat('Office_04_Interior_Quiet',(.22,.20,.17),.8)
oblind=mat('Office_05_Interior_Blinds',(.45,.44,.38),.72)

def mesh(name,verts,faces,material,smooth=False,role='architectural_solid'):
    data=bpy.data.meshes.new(name+'_Mesh');data.from_pydata(verts,[],faces);data.update()
    obj=bpy.data.objects.new(name,data);active.objects.link(obj)
    data.materials.append(material);obj['audit_role']=role
    bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free();data.update()
    for p in data.polygons:p.use_smooth=smooth
    return obj

def box(name,x0,x1,y0,y1,z0,z1,material,bevel=0):
    v=[(x,y,z) for z in (z0,z1) for y in (y0,y1) for x in (x0,x1)]
    f=[(0,2,3,1),(4,5,7,6),(0,1,5,4),(1,3,7,5),(3,2,6,7),(2,0,4,6)]
    obj=mesh(name,v,f,material)
    if bevel:
        bpy.context.view_layer.objects.active=obj;mod=obj.modifiers.new('Small construction edge','BEVEL');mod.width=bevel;mod.segments=2
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj

def bezier(points,steps):
    p=[Vector(v) for v in points];out=[]
    for i in range(0,len(p)-1,3):
        a,b,c,d=p[i:i+4]
        for j in range(steps):
            t=j/steps;out.append((1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d)
    area=sum(out[i].x*out[(i+1)%len(out)].y-out[(i+1)%len(out)].x*out[i].y for i in range(len(out)))
    if area<0:out.reverse()
    return out

# Explicit non-symmetric control outlines. A's far east edge curves back over y20..27.
a_outline=bezier([(-54,12),(-54,23),(-46,28),(-40,27),(-35,27),(-33.5,24.5),(-34,21),(-34,17),(-26,13),(-25,6),(-24.5,-1),(-34,-3),(-43,-1),(-50,0),(-54,5),(-54,12)],48)
b_outline=bezier([(-67,52),(-67,64),(-58,69),(-48,68),(-39,67),(-29,61),(-29,51),(-29,43),(-35,35),(-43,34),(-49,33),(-67,36),(-67,52)],48)
profiles_A=[(.14,1,1,0,0),(4.65,1,.995,-.10,.20),(8.80,.97,.985,-.35,.35),(12.95,.92,.96,-.70,.55),(17.10,.84,.89,-1.10,.80),(21.25,.73,.80,-1.70,1.25)]
profiles_B=[(.14,1,1,0,0),(4.65,1,1,-.10,0),(8.80,.99,.99,-.20,-.15),(13.15,.97,.96,-.40,-.30),(17.50,.93,.93,-.55,-.45),(21.85,.86,.87,-.65,-.65),(26.20,.76,.79,-.50,-1)]

def outline_at(base,center,profile):
    z,sx,sy,dx,dy=profile
    return [Vector((center[0]+(p.x-center[0])*sx+dx,center[1]+(p.y-center[1])*sy+dy)) for p in base]
def courtyard_loop(outer,center,rx,ry,profile):
    z,sx,sy,dx,dy=profile
    c=Vector((center[0]+dx,center[1]+dy));result=[]
    for p in outer:
        d=p-c;scale=math.sqrt((d.x/(rx*sx))**2+(d.y/(ry*sy))**2)
        result.append(c+d/scale)
    return result
def offset(loop,d):
    result=[];n=len(loop)
    for i,p in enumerate(loop):
        tangent=(loop[(i+1)%n]-loop[(i-1)%n]).normalized()
        result.append(p+Vector((tangent.y,-tangent.x))*d)
    return result
def lerp_loop(a,b,t):return [p.lerp(q,t) for p,q in zip(a,b)]

def ring_slab(name,outer,inner,z,thick,material):
    n=len(outer);v=[(p.x,p.y,h) for h in (z-thick,z) for loop in (outer,inner) for p in loop];f=[]
    for i in range(n):
        j=(i+1)%n
        f.extend([(2*n+i,2*n+j,3*n+j,3*n+i),(i,n+i,n+j,j),(i,j,2*n+j,2*n+i),(n+i,3*n+i,3*n+j,n+j)])
    return mesh(name,v,f,material)

def ribbon(name,loop,z,material=white):
    # Closed rolled band: actual front face, top return and underside, never an infinitely thin sheet.
    cross=[(-.25,-.19),(.25,-.19),(.39,-.14),(.39,.62),(.30,.70),(-.25,.70)]
    n=len(loop);v=[]
    for d,h in cross:v.extend((p.x,p.y,z+h) for p in offset(loop,d))
    f=[]
    for k in range(len(cross)):
        q=(k+1)%len(cross)
        for i in range(n):j=(i+1)%n;f.append((k*n+i,k*n+j,q*n+j,q*n+i))
    obj=mesh(name,v,f,material,True)
    obj.data.materials.append(soffit)
    for polygon in obj.data.polygons:
        if polygon.index//n in (0,5):polygon.material_index=1
    for edge in obj.data.edges:
        if edge.vertices[0]//n==edge.vertices[1]//n:edge.use_edge_sharp=True
    return obj

def pane_components(name,bottom,top,z0,z1,material,stride=2,inset=.38):
    n=len(bottom);v=[];f=[]
    for i in range(0,n,stride):
        j=(i+stride)%n
        a=bottom[i].lerp(bottom[j],.035);b=bottom[i].lerp(bottom[j],.965)
        c=top[i].lerp(top[j],.035);d=top[i].lerp(top[j],.965)
        tangent=(b-a).normalized();normal=Vector((tangent.y,-tangent.x))
        a-=normal*inset;b-=normal*inset;c-=normal*inset;d-=normal*inset
        s=len(v)
        front=[Vector((a.x,a.y,z0)),Vector((b.x,b.y,z0)),Vector((d.x,d.y,z1)),Vector((c.x,c.y,z1))]
        centre=sum(front,Vector())/4
        plane_normal=(front[1]-front[0]).cross((front[2]+front[3])/2-(front[0]+front[1])/2).normalized()
        front=[p-plane_normal*(p-centre).dot(plane_normal) for p in front]
        v.extend(front);v.extend(p-plane_normal*.045 for p in front)
        f.extend(tuple(s+k for k in face) for face in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])
    return mesh(name,v,f,material,False,'glazing')

def bars_on_facade(name,lower,upper,z0,z1,stride=2,depth=.16,width=.065,material=frame,inset=.16):
    n=len(lower);v=[];f=[]
    cube_faces=[(0,2,3,1),(4,5,7,6),(0,1,5,4),(1,3,7,5),(3,2,6,7),(2,0,4,6)]
    for i in range(0,n,stride):
        tangent=(lower[(i+1)%n]-lower[(i-1)%n]).normalized();normal=Vector((tangent.y,-tangent.x))
        p=lower[i]-normal*inset;q=upper[i]-normal*inset;s=len(v)
        for z,center in ((z0,p),(z1,q)):
            for d in (-depth/2,depth/2):
                for w in (-width/2,width/2):
                    r=center+normal*d+tangent*w;v.append((r.x,r.y,z))
        f.extend(tuple(s+k for k in face) for face in cube_faces)
    return mesh(name,v,f,material)

def transom(name,loop,z,material=frame):
    # A narrow, closed construction rail, with deliberate segmented sides.
    a=offset(loop,-.25);b=offset(loop,-.34)
    return ring_slab(name,a,b,z,.07,material)

def building(letter,base,center,profiles,inner_center,radii):
    loops=[outline_at(base,center,p) for p in profiles]
    holes=[courtyard_loop(outer,inner_center,*radii,p) for outer,p in zip(loops,profiles)]
    for k,(p,outer,inner) in enumerate(zip(profiles,loops,holes)):
        z=G+p[0]
        ring_slab(f'{letter}_L{k}_FloorPlate_OpenAtrium',outer,inner,z,.28,floor_mat)
        ribbon(f'{letter}_L{k}_Continuous_Curved_Band',outer,z)
        if k<len(profiles)-1:
            p2=profiles[k+1];out2=loops[k+1];hole2=holes[k+1]
            za=z+.30;zb=G+p2[0]-.28
            if k==len(profiles)-2:
                lo=out2;hi=out2  # A real upper setback pavilion, leaving a terrace on the lower plate.
            else:
                lo=lerp_loop(outer,out2,.12);hi=lerp_loop(outer,out2,.90)
            pane_components(f'{letter}_L{k}_Outer_Glass_ChordPanels',lo,hi,za,zb,glass,3 if letter=='A' else 2)
            bars_on_facade(f'{letter}_L{k}_Outer_Mullions',lo,hi,za,zb,3 if letter=='A' else 2)
            transom(f'{letter}_L{k}_Outer_Glass_Head',hi,zb+.03)
            if k==0:transom(f'{letter}_L{k}_Retail_Transom',lo,za+3.05)
            # Inner courtyard glass sits on the opposite side of the ring.
            ilo=list(reversed(lerp_loop(inner,hole2,.12)));ihi=list(reversed(lerp_loop(inner,hole2,.90)))
            pane_components(f'{letter}_L{k}_Atrium_Glass',ilo,ihi,za,zb,glass_inner,4,.06)
            bars_on_facade(f'{letter}_L{k}_Atrium_Frames',ilo,ihi,za,zb,4,.12,.055,frame,.01)
            # Physical opaque occupied zones inside: backings/counters, not a featureless dark fill shell.
        else:
            ring_slab(f'{letter}_Roof_Finished_Membrane',offset(outer,-.60),offset(inner,.10),z+.06,.055,roof_mat)
            ribbon(f'{letter}_Roof_Inner_Courtyard_Coping',list(reversed(inner)),z+.01)
    return loops,holes

active=A
aloops,aholes=building('A',a_outline,(-40,12),profiles_A,(-41,10),(3.5,4.0))
active=B
bloops,bholes=building('B',b_outline,(-48,51),profiles_B,(-49,51),(6.2,7.8))

# One bridge bends toward the street and flares into both commercial floor bands.
active=BRIDGE
bridge_control=[Vector((-36,23)),Vector((-32.4,23)),Vector((-29.5,25.9)),Vector((-29.5,29.5)),Vector((-29.5,33.1)),Vector((-33.5,36.5)),Vector((-39.5,36.5))]
def bridge_point(t):
    i=0 if t<=.5 else 3;u=t*2 if t<=.5 else (t-.5)*2
    a,b,c,d=bridge_control[i:i+4];return (1-u)**3*a+3*(1-u)**2*u*b+3*(1-u)*u*u*c+u**3*d
def bridge_tangent(t):
    i=0 if t<=.5 else 3;u=t*2 if t<=.5 else (t-.5)*2
    a,b,c,d=bridge_control[i:i+4];return (3*(1-u)**2*(b-a)+6*(1-u)*u*(c-b)+3*u*u*(d-c)).normalized()
bridge_path=[bridge_point(i/48) for i in range(49)]
bridge_sides=[]
for sign in (-1,1):
    side=[]
    for i,p in enumerate(bridge_path):
        t=i/48;tan=bridge_tangent(t);n=Vector((-tan.y,tan.x));width=4.4+1.8*(abs(2*t-1)**3)
        side.append(p+n*sign*width/2)
    bridge_sides.append(side)
bridge_z=G+8.8

def sweep_solid(name,left,right,zbottom,ztop,material):
    count=len(left);v=[]
    for i,(l,r) in enumerate(zip(left,right)):
        z0=zbottom(i/(count-1)) if callable(zbottom) else zbottom
        z1=ztop(i/(count-1)) if callable(ztop) else ztop
        v.extend([(l.x,l.y,z0),(r.x,r.y,z0),(r.x,r.y,z1),(l.x,l.y,z1)])
    f=[(0,3,2,1),(4*(count-1),4*(count-1)+1,4*(count-1)+2,4*(count-1)+3)]
    for i in range(count-1):
        for k in range(4):j=(k+1)%4;f.append((4*i+k,4*(i+1)+k,4*(i+1)+j,4*i+j))
    obj=mesh(name,v,f,material,True)
    # Preserve the architectural deck/soffit corners while smoothing along the bend.
    for edge in obj.data.edges:
        a,b=edge.vertices
        if a%4==b%4 or (a//4==b//4 and a//4 in (0,count-1)):
            edge.use_edge_sharp=True
    return obj

left,right=bridge_sides
sweep_solid('Bridge_Closed_Arched_Soffit_and_Deck',left,right,lambda t:bridge_z-.42-.12*math.sin(math.pi*t)**2,bridge_z+.12,white)
sweep_solid('Bridge_Upper_Curved_Roof',left,right,bridge_z+3.65,bridge_z+3.95,white)
for side_id,side in enumerate((left,right)):
    # Same continuous curving profile, with glass physically set behind its opaque edge bands.
    normals=[]
    for i in range(len(side)):
        tangent=(side[min(i+1,len(side)-1)]-side[max(i-1,0)]).normalized();normals.append(Vector((-tangent.y,tangent.x))*(-1 if side_id==0 else 1))
    inner=[p-n*.38 for p,n in zip(side,normals)];outer=[p+n*.02 for p,n in zip(side,normals)]
    sweep_solid(f'Bridge_Side{side_id}_Lower_Continuous_Fascia',inner,outer,bridge_z+.04,bridge_z+0.65,white)
    sweep_solid(f'Bridge_Side{side_id}_Upper_Fascia',inner,outer,bridge_z+3.52,bridge_z+3.95,white)
    verts=[];faces=[]
    for i in range(0,len(side)-1,2):
        p=inner[i];q=inner[min(i+2,len(side)-1)];n=normals[i];s=len(verts)
        vv=[(p.x,p.y,bridge_z+0.65),(q.x,q.y,bridge_z+0.65),(q.x,q.y,bridge_z+3.51),(p.x,p.y,bridge_z+3.51)]
        verts.extend(vv);verts.extend((x-n.x*.045,y-n.y*.045,z) for x,y,z in vv)
        faces.extend(tuple(s+k for k in f) for f in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])
    mesh(f'Bridge_Side{side_id}_Segmented_Glass',verts,faces,glass)
    for i in range(0,len(side),4):
        p=inner[i];box(f'Bridge_Side{side_id}_Mullion_{i:02}',p.x-.035,p.x+.035,p.y-.07,p.y+.07,bridge_z+0.65,bridge_z+3.53,frame,.009)

# C is intentionally an unfenestrated, separately named skyline placeholder.
active=C
cbase=bezier([(-52,92),(-52,102),(-43,107),(-35,106),(-27,105),(-24,98),(-24,91),(-24,81),(-28,76),(-39,76),(-48,76),(-52,83),(-52,92)],20)
c0=outline_at(cbase,(-38,91),(0,1,1,0,0));c1=outline_at(cbase,(-38,91),(36,.73,.82,-1,.2))
n=len(c0);v=[(p.x,p.y,z) for loop,z in ((c0,G),(c1,G+36)) for p in loop];f=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
mesh('C_NOT_FINISHED_Curved_Massing_Only',v,f,placeholder,True,'placeholder')

# Paved opening has a real floor and remains open, not a planter-filled substitute for space.
active=SITE
box('Court_Pavement_Threshold',-54,-22,22,37.5,G+.08,PAVE,paving)
box('B_Atrium_Ground_Paving',-55,-43,43,60,G+.08,PAVE,paving)
box('A_Atrium_Ground_Paving',-45,-37,5,15,G+.08,PAVE,paving)
for x,y,w in ((-46,30,3.0),(-57,36,2.7),(-25.6,19,2.5)):
    box(f'Court_Stone_Bench_{x}_{y}',x-w/2,x+w/2,y-.36,y+.36,PAVE,PAVE+.45,floor_mat,.055)

# Old isolated office trial is removed; detail the actual visible source buildings instead.
# Construction details follow the approved forms; no whole-city or full-office expansion.
joint=mat('Curve_14_Cladding_Panel_Joints',(.23,.27,.26),.70)
def cylinder(name,x,y,z0,z1,r,material):
    n=12;v=[(x+r*math.cos(2*math.pi*i/n),y+r*math.sin(2*math.pi*i/n),z) for z in (z0,z1) for i in range(n)]
    f=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return mesh(name,v,f,material,True)
for coll,letter,loops,holes,profiles in ((A,'A',aloops,aholes,profiles_A),(B,'B',bloops,bholes,profiles_B)):
    active=coll
    for k,(outer,inner,p) in enumerate(zip(loops,holes,profiles)):
        bars_on_facade(f'{letter}_L{k}_Aluminium_Panel_Joints',outer,outer,G+p[0]-.10,G+p[0]+.57,8,.022,.035,joint,-.407)
        if k<len(profiles)-1:
            for index in ((8,28,48,68,88) if letter=='A' else (0,12,24,36,48,60,72,84)):
                point=outer[index%len(outer)].lerp(inner[index%len(inner)],.30)
                cylinder(f'{letter}_L{k}_Interior_Column_{index}',point.x,point.y,G+p[0],G+profiles[k+1][0]-.29,.25,soffit)

def cut_glass_opening(obj,predicate):
    remove=[]
    for start in range(0,len(obj.data.vertices),8):
        ids=list(range(start,min(start+8,len(obj.data.vertices))))
        center=sum((obj.data.vertices[i].co for i in ids),Vector())/len(ids)
        if predicate(center):remove.extend(ids)
    bm=bmesh.new();bm.from_mesh(obj.data);bm.verts.ensure_lookup_table();dead=[bm.verts[i] for i in remove]
    bmesh.ops.delete(bm,geom=dead,context='VERTS');bm.to_mesh(obj.data);bm.free();obj.data.update()
cut_glass_opening(bpy.data.objects['A_L0_Outer_Glass_ChordPanels'],lambda p:p.x>-36 and 17.8<p.y<24.2)
cut_glass_opening(bpy.data.objects['B_L0_Outer_Glass_ChordPanels'],lambda p:-46<p.x<-35.5 and p.y<38)
cut_glass_opening(bpy.data.objects['A_L0_Outer_Mullions'],lambda p:p.x>-36 and 17.8<p.y<24.2)
cut_glass_opening(bpy.data.objects['B_L0_Outer_Mullions'],lambda p:-46<p.x<-35.5 and p.y<38)
for transom_name in ('A_L0_Retail_Transom','B_L0_Retail_Transom'):
    bpy.data.objects.remove(bpy.data.objects[transom_name],do_unlink=True)
active=A
box('A_Entry_Recess_South_Jamb',-35.8,-33.4,18.05,18.35,PAVE,PAVE+4.12,soffit)
box('A_Entry_Recess_North_Jamb',-35.8,-33.4,22.60,22.90,PAVE,PAVE+4.12,soffit)
box('A_Entry_Recess_Head',-35.8,-33.4,18.05,22.9,PAVE+3.90,PAVE+4.12,soffit)
for door,a,b in ((1,18.4,20.45),(2,20.55,22.55)):
    box(f'A_Entry_Door{door}_Glass',-35.54,-35.49,a,b,PAVE+.03,PAVE+2.75,glass)
    for y in (a,b):box(f'A_Entry_Door{door}_Stile_{y}',-35.41,-35.28,y-.035,y+.035,PAVE,PAVE+2.82,frame,.008)
    box(f'A_Entry_Door{door}_Handle',-35.18,-35.10,b-.24,b-.19,PAVE+1.0,PAVE+1.85,frame,.015)
box('A_Entry_Interior_Counter',-39.2,-38.2,18.5,22.2,PAVE,PAVE+1.1,wood,.025)
box('A_Entry_Interior_Rear',-40.2,-40.0,18.3,22.7,PAVE,PAVE+3.9,dark)

active=B
box('B_Entry_West_Reveal',-45.8,-45.5,34.4,37.7,PAVE,PAVE+4.12,soffit)
box('B_Entry_East_Reveal',-37.6,-37.3,35.2,37.7,PAVE,PAVE+4.12,soffit)
box('B_Entry_Recess_Soffit',-45.8,-37.3,34.4,37.7,PAVE+3.90,PAVE+4.12,soffit)
for door in range(4):
    x=-45.4+door*1.94
    box(f'B_Entry_Door{door}_Glass',x+.04,x+1.90,37.61,37.66,PAVE+.03,PAVE+2.80,glass)
    box(f'B_Entry_Door{door}_Frame',x-.025,x+.025,37.45,37.65,PAVE,PAVE+2.86,frame,.008)
    box(f'B_Entry_Door{door}_Handle',x+1.68,x+1.73,37.29,37.39,PAVE+1.0,PAVE+1.85,frame,.012)
box('B_Entry_Interior_Rear',-45.5,-37.5,42.8,43.05,PAVE,PAVE+3.90,dark)
box('B_Entry_Concierge_Counter',-44.6,-38.6,40.4,41.25,PAVE,PAVE+1.1,wood,.03)
box('B_Entry_Warm_Ceiling',-45.0,-38.0,37.8,42.4,PAVE+3.90,PAVE+3.96,light)

# Named terrace furniture and roof screens, designed only at the visible places.
active=A
terrace_z=G+17.10
box('A_Terrace_Bench_Near',-45.5,-42.5,.90,1.45,terrace_z,terrace_z+.45,wood,.04)
box('A_Terrace_Planter_Near',-40.8,-37.5,.75,1.6,terrace_z,terrace_z+.65,floor_mat,.035)
box('A_Terrace_Planter_Soil',-40.65,-37.65,.89,1.45,terrace_z+.62,terrace_z+.66,soil)
for x in (-40.25,-39.45,-38.65,-37.95):
    box(f'A_Terrace_Low_Plant_{x}',x-.26,x+.26,1.05,1.36,terrace_z+.66,terrace_z+1.03,plant,.14)
transom('A_Terrace_Metal_Coping',offset(aloops[-2],.30),terrace_z+.74,frame)
box('A_Roof_Service_Screen',-47,-44,12.7,16.5,G+21.31,G+22.20,white,.04)
for y in (13.05,13.40,13.75,14.10,14.45,14.80,15.15,15.50,15.85,16.20):
    box(f'A_Roof_Service_Louvre_{y}',-47.02,-46.97,y,y+.12,G+21.47,G+22.05,frame)
active=B
box('B_Roof_Service_Screen',-60.4,-56.8,48,54.5,G+26.26,G+27.60,white,.04)
for y in (48.4,49.1,49.8,50.5,51.2,51.9,52.6,53.3):
    box(f'B_Roof_Service_Louvre_{y}',-60.43,-60.36,y,y+.15,G+26.51,G+27.35,frame)
transom('B_Terrace_Metal_Coping',offset(bloops[-2],.30),G+21.85+.74,frame)

def lettering(name,text,position,size,rotation):
    data=bpy.data.curves.new(name,'FONT');data.body=text;data.size=size;data.align_x='CENTER';data.extrude=.015;data.bevel_depth=.003;data.bevel_resolution=1
    obj=bpy.data.objects.new(name,data);active.objects.link(obj);obj.location=position;obj.rotation_euler=rotation;data.materials.append(frame)
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj;bpy.ops.object.convert(target='MESH')
    obj=bpy.context.object;bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6);bmesh.ops.triangulate(bm,faces=list(bm.faces))
    dead=[f for f in bm.faces if f.calc_area()<=1e-10];bmesh.ops.delete(bm,geom=dead,context='FACES')
    bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context='VERTS')
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free()
    obj['audit_role']='lettering';obj['audit_open_allowed']=True;return obj
active=B
box('B_Entry_Identity_Fascia',-45.1,-37.7,32.75,33.0,PAVE+3.92,PAVE+4.55,white,.035)
for x in (-44.5,-38.3):box(f'B_Entry_Identity_Bracket_{x}',x-.08,x+.08,32.97,35.2,PAVE+4.05,PAVE+4.20,frame)
lettering('B_Entry_ORBIT_GALLERIA','ORBIT GALLERIA',(-41.4,32.70,PAVE+4.02),.78,(math.pi/2,0,0))

exec(Path(__file__).with_name('window_scale03_details.py').read_text(encoding='utf-8'),globals())
scene.camera=bpy.data.objects['Review_Window_UE_VFOV54']

bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'CityDesign_WindowScale03_geometry_checkpoint.blend'))
# Physical metre UV0 and a separate packed UV1 for every editable part.
for coll in (A,B,BRIDGE,C,SITE,OFFICE):
    for obj in coll.objects:
        # FONT conversion may create an automatic UV layer; rebuild an exact two-layer contract.
        for layer_name in [layer.name for layer in obj.data.uv_layers]:obj.data.uv_layers.remove(obj.data.uv_layers[layer_name])
        uv=obj.data.uv_layers.new(name='UVMap');obj.data.uv_layers.active=uv
        for face in obj.data.polygons:
            axis=max(range(3),key=lambda i:abs(face.normal[i]))
            for li in face.loop_indices:
                p=obj.data.vertices[obj.data.loops[li].vertex_index].co
                uv.data[li].uv=((p.y,p.z) if axis==0 else (p.x,p.z) if axis==1 else (p.x,p.y));uv.data[li].uv/=1.2
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
        uv1=obj.data.uv_layers.new(name='LightmapUV');obj.data.uv_layers.active=uv1
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.015);bpy.ops.object.mode_set(mode='OBJECT')
        # New layers/edit-mode can invalidate RNA layer references; reacquire by name.
        uv=obj.data.uv_layers['UVMap'];uv1=obj.data.uv_layers['LightmapUV']
        if obj.get('audit_role')=='lettering':
            for dest,source in zip(uv.data,uv1.data):dest.uv=source.uv
        obj.data.uv_layers.active=uv;uv.active_render=True

scene['Design_Method']='Individually designed control sections and direct editable mesh operations; no random generation; not GUI hand modeling.'
scene['Reference']='Galaxy SOHO official built photographs (Hufton + Crow / Iwan Baan), main reference; target-v3 for window scale.'
scene['Sample_Status']='Window-only scale/detail candidate; A+B and bridge redesigned; actual B07/B08/B13 facade details; C stored but hidden. Awaiting visual review.'
scene['Coordinates']='Blender metres; UE cm=(100*x,-100*y,100*z).'
scene['Integration_Status']='Independent blend only, no UE import, no deployment.'
scene['Bridge_Deck_Absolute_Z_m']=bridge_z
scene['Bridge_Min_Clearance_Above_Pavement_m']=bridge_z-.54-PAVE
scene['Materials']='Candidate PBR and source-office preview adaptation; original source materials/assets remain unchanged.'
manifest={'method':scene['Design_Method'],'reference':{'main':'https://www.zha.com/projects/architecture/galaxy-soho?disclaimer=true','photographers':['Hufton + Crow','Iwan Baan'],'not_copied_geometry':True},'camera':{'blender_position':[26,-42,37],'target':[-22,115,19],'vertical_fov':54,'aspect':'16:9'},'profile_controls':{'A':profiles_A,'B':profiles_B},'bridge':{'deck_absolute_z_m':bridge_z,'minimum_underdeck_clearance_m':scene['Bridge_Min_Clearance_Above_Pavement_m'],'control_points_blender_xy':[list(p) for p in bridge_control]},'scope':scene['Sample_Status'],'collections':{c.name:len(c.objects) for c in (A,B,BRIDGE,C,SITE,OFFICE)},'stage':'New bounded geometry and actual-office details saved; fixed-window CPU preview pending.'}
(OUT/'design_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'CityDesign_WindowScale03.blend'))
print('CURVED_SPATIAL_SAMPLE_SAVED',flush=True)
