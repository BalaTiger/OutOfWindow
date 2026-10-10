"""Bounded, designed screen-view details; executed in the authored building script."""
# More breadth on A's near part and B's rear; retain the bridge sight-line notch.
for coll in (A,B):
    for obj in coll.objects:
        if obj.get('audit_role')=='lettering':continue
        for v in obj.data.vertices:
            if coll==A:
                v.co.x=-40+(v.co.x+40)*1.10-.80
                if v.co.y<18:v.co.y=18+(v.co.y-18)*1.35
            elif v.co.y>45:v.co.y=45+(v.co.y-45)*1.30
        if obj.get('audit_role')=='glazing':
            for start in range(0,len(obj.data.vertices),8):
                front=[obj.data.vertices[start+i].co.copy() for i in range(4)]
                center=sum(front,Vector())/4
                normal=(front[1]-front[0]).cross((front[2]+front[3])/2-(front[0]+front[1])/2).normalized()
                projected=[p-normal*(p-center).dot(normal) for p in front]
                for i,p in enumerate(projected):obj.data.vertices[start+i].co=p;obj.data.vertices[start+4+i].co=p-normal*.045
        bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free();obj.data.update()
C.hide_render=True
C['Window_View_Status']='Stored massing only; hidden from this candidate review.'

# A proper main commercial threshold, readable from the sole window camera.
active=A
cut_glass_opening(bpy.data.objects['A_L0_Outer_Glass_ChordPanels'],lambda p:p.x>-29 and -2.2<p.y<6.4)
cut_glass_opening(bpy.data.objects['A_L0_Outer_Mullions'],lambda p:p.x>-29 and -2.2<p.y<6.4)
entry_stone=mat('View_Entry_Warm_Stone',(.38,.34,.27),.68)
entry_glass=mat('View_Entry_Clear_Glass',(.22,.245,.25),.13,0,.58)
entry_inside=mat('View_Entry_Interior_Panel',(.28,.19,.11),.68)
box('A_MainEntry_South_Stone_Reveal',-29.0,-23.55,-2.45,-2.12,PAVE,PAVE+3.96,entry_stone,.025)
box('A_MainEntry_North_Stone_Reveal',-29.0,-23.55,6.35,6.68,PAVE,PAVE+3.96,entry_stone,.025)
box('A_MainEntry_Canopy_Thin_Return',-29.0,-23.45,-2.45,6.68,PAVE+3.84,PAVE+4.02,white,.022)
box('A_MainEntry_Identity_Fascia',-23.50,-23.35,-2.30,6.52,PAVE+3.28,PAVE+3.98,white,.018)
for bay in range(4):
    y=-1.98+bay*2.06
    box(f'A_MainEntry_Door{bay}',-27.40,-27.355,y+.055,y+2.00,PAVE+.02,PAVE+2.78,entry_glass)
    box(f'A_MainEntry_Stile{bay}',-27.30,-27.24,y-.027,y+.027,PAVE,PAVE+3.76,frame,.007)
    box(f'A_MainEntry_Transom{bay}',-27.40,-27.355,y+.055,y+2.00,PAVE+2.87,PAVE+3.72,entry_glass)
    box(f'A_MainEntry_Handle{bay}',-27.19,-27.14,y+1.76,y+1.80,PAVE+.95,PAVE+1.65,frame,.009)
box('A_MainEntry_Transom_Rail',-27.30,-27.24,-1.98,6.26,PAVE+2.78,PAVE+2.87,frame,.008)
box('A_MainEntry_Interior_Warm_Back',-31.3,-31.1,-2.0,6.3,PAVE,PAVE+3.70,entry_inside)
box('A_MainEntry_Interior_Display',-30.5,-29.9,-1.5,5.6,PAVE,PAVE+1.18,wood,.025)
lettering('A_MainEntry_GALLERIA','GALLERIA',(-23.315,2.10,PAVE+3.36),.80,(math.pi/2,0,math.pi/2))

# Remove the GLB-only night colour multiplication from candidate daylight preview.
# UE uses COLOR_0 for emission; only the independent scene is adjusted here.
adapted=[]
for material in bpy.data.materials:
    if not material.name.startswith(('CityModern_','Glass_Lit_CityModern_')) or not material.use_nodes:continue
    bs=next((node for node in material.node_tree.nodes if node.type=='BSDF_PRINCIPLED'),None)
    if not bs:continue
    for link in list(bs.inputs['Base Color'].links):material.node_tree.links.remove(link)
    bs.inputs['Base Color'].default_value=material.diffuse_color
    if material.name.startswith('CityModern_Metal'):
        bs.inputs['Base Color'].default_value=(.24,.28,.29,1);bs.inputs['Roughness'].default_value=.34;bs.inputs['Metallic'].default_value=.68
    if material.name.startswith('CityModern_Hero_Glass'):
        bs.inputs['Base Color'].default_value=(.027,.049,.062,1);bs.inputs['Metallic'].default_value=0;bs.inputs['Roughness'].default_value=.12;bs.inputs['Specular IOR Level'].default_value=.75
    adapted.append(material.name)

# Work on the actual source office surfaces, not a floating three-floor patch.
active=OFFICE
office_metal=mat('View_Office_Secondary_Aluminium',(.28,.32,.33),.29,.72)
office_head=mat('View_Office_Recessed_Head',(.14,.19,.21),.36,.40)
office_glasses=[mat('View_Office_Glass_'+str(i),c,r,0,0) for i,(c,r) in enumerate([
    ((.045,.085,.11),.12),((.065,.105,.125),.145),((.075,.115,.125),.17),((.060,.081,.082),.18)])]
for material in office_glasses:
    bs=material.node_tree.nodes.get('Principled BSDF');bs.inputs['Specular IOR Level'].default_value=.70;bs.inputs['Coat Weight'].default_value=.24;bs.inputs['Coat Roughness'].default_value=.07

def append_box(v,f,lo,hi):
    s=len(v);v.extend((x,y,z) for z in (lo[2],hi[2]) for y in (lo[1],hi[1]) for x in (lo[0],hi[0]))
    f.extend(tuple(s+i for i in face) for face in [(0,2,3,1),(4,5,7,6),(0,1,5,4),(1,3,7,5),(3,2,6,7),(2,0,4,6)])

office_records=[]
cam=bpy.data.objects['Review_Window_UE_VFOV54']
for code in ('B07','B08','B13'):
    source=next(obj for obj in bpy.data.collections['Existing_City_Context'].objects if obj.type=='MESH' and obj.name.startswith('CityModern_'+code+'_'))
    data=source.data;world=source.matrix_world
    glass_ids={index for index,material in enumerate(data.materials) if material and 'glass' in material.name.lower()}
    faces=[p for p in data.polygons if p.material_index in glass_ids]
    # Imported GLB may split the two triangles' indices; recover panes by positions.
    keys={i:tuple(round(float(c),5) for c in world@data.vertices[i].co) for p in faces for i in p.vertices}
    positions_by_key={keys[i]:world@data.vertices[i].co for i in keys}
    links={};face_by_vert={}
    for p in faces:
        face_keys={keys[i] for i in p.vertices}
        for key in face_keys:
            links.setdefault(key,set()).update(face_keys);face_by_vert.setdefault(key,set()).add(p.index)
    remaining=set(links);components=[]
    while remaining:
        seed=remaining.pop();group={seed};stack=[seed]
        while stack:
            for other in links[stack.pop()]:
                if other in remaining:remaining.remove(other);group.add(other);stack.append(other)
        components.append(group)
    gv=[];gf=[];mi=[];fv=[];ff=[];hv=[];hf=[];remove_faces=set();pane_count=0
    for group in components:
        positions=[positions_by_key[key] for key in group]
        if len(positions)!=4:continue
        lo=[min(p[i] for p in positions) for i in range(3)];hi=[max(p[i] for p in positions) for i in range(3)]
        axis=0 if hi[0]-lo[0]<1e-5 else 1 if hi[1]-lo[1]<1e-5 else -1
        if axis<0:continue
        center=sum(positions,Vector())/4
        face_ids=set().union(*(face_by_vert[key] for key in group))
        building_center=sum((world@Vector(point) for point in source.bound_box),Vector())/8
        normal=Vector();normal[axis]=1 if center[axis]>building_center[axis] else -1
        if normal.dot(cam.location-center)<=.01:continue
        other=1-axis;mid=(lo[other]+hi[other])/2;plane=center[axis]
        # Explicit vertical office zones with modest material differences, not noise.
        zone=0 if center.z<22 else 1 if center.z<32 else 2
        if code=='B13':zone=1 if center[other]<(-73 if other==0 else 87) else 0
        remove_faces.update(face_ids);pane_count+=1
        for a,b in ((lo[other],mid-.025),(mid+.025,hi[other])):
            s=len(gv);front=[]
            for h,t in ((lo[2],a),(lo[2],b),(hi[2],b),(hi[2],a)):
                point=Vector();point[axis]=plane;point[other]=t;point.z=h;front.append(point)
            gv.extend(front);gv.extend(point-normal*.032 for point in front)
            gf.extend(tuple(s+i for i in face) for face in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])
            mi.extend([zone]*6)
        frame_lo=lo[:];frame_hi=hi[:]
        center_axis=plane+normal[axis]*(.20 if code=='B07' else .075)
        frame_lo[axis]=center_axis-.08;frame_hi[axis]=center_axis+.08
        frame_lo[other]=mid-.026;frame_hi[other]=mid+.026
        append_box(fv,ff,frame_lo,frame_hi)
        head_lo=lo[:];head_hi=hi[:]
        head_lo[axis]=plane+normal[axis]*.025-.03;head_hi[axis]=head_lo[axis]+.06
        head_lo[2]=hi[2]-.63;head_hi[2]=head_lo[2]+.043
        append_box(hv,hf,head_lo,head_hi)
    if not pane_count:raise RuntimeError('No visible office panes selected: '+code)
    obj=mesh('Office_'+code+'_Visible_Planar_Glass_32mm',gv,gf,office_glasses[0])
    for material in office_glasses[1:]:obj.data.materials.append(material)
    for polygon,index in zip(obj.data.polygons,mi):polygon.material_index=index
    obj['Visible_Source_Panes']=pane_count;obj['Construction']='Each original 2.8-2.9m pane split into two closed panes, actual source plane retained.'
    mesh('Office_'+code+'_Secondary_Mullions_52mm',fv,ff,office_metal)
    mesh('Office_'+code+'_Recessed_Head_Rails_43mm',hv,hf,office_head)
    bm=bmesh.new();bm.from_mesh(data);bm.faces.ensure_lookup_table();bmesh.ops.delete(bm,geom=[bm.faces[i] for i in sorted(remove_faces)],context='FACES_ONLY')
    bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context='VERTS');bm.to_mesh(data);bm.free();data.update()
    office_records.append({'building':code,'source_mesh':source.name,'original_visible_panes_replaced':pane_count,'new_closed_half_panes':pane_count*2,'mullion_width_m':.052,'glass_thickness_m':.032})

# Small applied bevels at actual visible tower corners; no change in building mass.
for code,x,y,z0,z1 in [('B07_Lower',25,-7,12.1,28.6),('B07_Upper',29.55,-2.2,28.75,39.9),('B08',27,36.5,12.1,54.9),('B13',-59,69,12.1,70.9)]:
    box('Office_'+code+'_Corner_Aluminium_Cap',x-.105,x+.105,y-.125,y+.085,z0,z1,office_metal,.015)
scene['Office_View_Changes']=json.dumps(office_records)
(OUT/'office_candidate_changes.json').write_text(json.dumps({'actual_office_surfaces':office_records,'candidate_preview_materials_adapted':adapted,'not_ue_verified':True},indent=2),encoding='utf-8')
