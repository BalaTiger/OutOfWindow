"""Two authored, fixed interior camera candidates; commercial geometry stays frozen."""
import bpy,sys,math,json,hashlib,struct,argparse
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
SOURCE=Path(r'C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\CityDesign_CommercialScale04\CityDesign_CommercialScale04.blend')
OUT=Path(r'C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\CityDesign_WindowCamera05')
CONFIGS=[
 {'id':'A','host':'CityModern_B08_glass','file':'Camera05_A_B08.blend','eye':[27.5,49.0,53.2076923077],'target':[-52.0,21.0,26.5],'vfov':52.0,'floor':51.6076923077,'ceiling':54.9,'west':26.0,'south':36.5,'window_y':[46.7,53.1],'room_xmax':32.5,'corner':False,'floor_basis':'B08 tower base12.1 +12*(42.8/13); top facade segment, authored local FF, not a pre-existing interior slab'},
 {'id':'B','host':'CityModern_B09_fins','file':'Camera05_B_B09.blend','eye':[25.05,86.5,63.2],'target':[-50.0,28.0,34.0],'vfov':52.0,'floor':61.6,'ceiling':64.9,'west':23.5,'south':83.0,'window_y':[83.0,91.4],'room_xmax':30.0,'corner':True,'floor_basis':'B09 last tower facade segment61.6..64.9, 3.3m pitch, authored local FF, not a pre-existing interior slab'}
]
parser=argparse.ArgumentParser()
parser.add_argument('--candidate',choices=['A','B'],default='A')
parser.add_argument('--geometry-only',action='store_true')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
LOW_PREVIEW={'width':640,'height':360,'samples':8,'threads':2,'engine':'CYCLES','device':'CPU','one_candidate_only':True}

def digest(obj):
 h=hashlib.sha256();h.update(obj.type.encode())
 for row in obj.matrix_world:
  for a in row:h.update(struct.pack('<d',a))
 h.update(bytes([obj.hide_render]))
 if obj.type=='MESH':
  m=obj.data
  for v in m.vertices:h.update(struct.pack('<3d',*v.co))
  for p in m.polygons:
   h.update(struct.pack('<ii?',len(p.vertices),p.material_index,p.use_smooth))
   for i in p.vertices:h.update(struct.pack('<i',i))
  for uv in m.uv_layers:
   h.update(uv.name.encode())
   for q in uv.data:h.update(struct.pack('<2d',*q.uv))
  for mat in m.materials:h.update((mat.name if mat else '').encode())
 elif obj.type=='CAMERA':
  for a in (obj.data.lens,obj.data.sensor_width,obj.data.sensor_height,obj.data.shift_x,obj.data.shift_y):h.update(struct.pack('<d',a))
 return h.hexdigest()

def material(name,color,rough=.65,metal=0,glass=False):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 m.node_tree.nodes.clear();p=m.node_tree.nodes.new('ShaderNodeBsdfPrincipled');out=m.node_tree.nodes.new('ShaderNodeOutputMaterial');m.node_tree.links.new(p.outputs['BSDF'],out.inputs['Surface']);p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
 if glass:p.inputs['Transmission Weight'].default_value=1;p.inputs['IOR'].default_value=1.45
 return m

def box(name,b,coll,mat=None):
 x0,x1,y0,y1,z0,z1=b
 v=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
 f=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
 m=bpy.data.meshes.new(name+'_Mesh');m.from_pydata(v,[],f);m.update();o=bpy.data.objects.new(name,m);coll.objects.link(o)
 if mat:m.materials.append(mat)
 return o

def cut_room(host,c,cfg):
 w=cfg['west'];f=cfg['floor'];s=cfg['south'];yl,yh=cfg['window_y'];z0=f+.22;z1=cfg['ceiling']-.18
 host.data=host.data.copy()
 # Boolean removes the actual opaque core and external pane only in this room aperture.
 bounds=(w-1.5,cfg['room_xmax']+.15,(s-1.5 if cfg['corner'] else yl),yh,z0,z1)
 cutter=box('Window05_'+cfg['id']+'_Aperture_Cutter',bounds,c)
 bpy.context.view_layer.objects.active=host;host.select_set(True)
 mod=host.modifiers.new('Local_Window05_Real_Aperture','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter;mod.use_self=True
 bpy.ops.object.modifier_apply(modifier=mod.name);host.select_set(False)
 bpy.data.objects.remove(cutter,do_unlink=True)
 return bounds

def build(cfg):
 bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
 scene=bpy.context.scene
 frozen={o.name:digest(o) for o in scene.objects if o.type in ('MESH','CAMERA')}
 coll=bpy.data.collections.new('Window05_'+cfg['id']+'_Authored_Interior');scene.collection.children.link(coll)
 wall=material('Window05_'+cfg['id']+'_Warm_Painted_Reveal',(.24,.225,.20),.8)
 stone=material('Window05_'+cfg['id']+'_Stone_Sill',(.22,.205,.18),.65)
 frame=material('Window05_'+cfg['id']+'_Dark_Bronze_Frame',(.038,.044,.046),.42,.55)
 floor_mat=material('Window05_'+cfg['id']+'_Interior_Floor',(.145,.13,.11),.72)
 clear=material('Window05_'+cfg['id']+'_Clear_Closed_Window',(.98,.99,1),.012,glass=True)
 host=bpy.data.objects[cfg['host']];cut_bounds=cut_room(host,coll,cfg)
 allowed_local_hosts=[cfg['host']]
 prefix='Office_'+cfg['host'].split('_')[1]+'_'
 part_names=[o.name for o in bpy.data.collections['Office_Window_Visible'].all_objects]
 for part_name in part_names:
  part=bpy.data.objects.get(part_name)
  if part is None:continue
  if part.type!='MESH' or not part.name.startswith(prefix):continue
  pts=[part.matrix_world@Vector(v) for v in part.bound_box]
  intersects=all(min(v[k] for v in pts)<cut_bounds[2*k+1] and max(v[k] for v in pts)>cut_bounds[2*k] for k in range(3))
  if intersects:cut_room(part,coll,cfg);allowed_local_hosts.append(part.name)
 w=cfg['west'];f=cfg['floor'];top=cfg['ceiling'];yl,yh=cfg['window_y'];back=cfg['room_xmax'];low=f+.22;high=top-.18
 room_south=cfg['south'] if cfg['corner'] else yl-.22
 # All room planes stay world horizontal/vertical, independent of camera pitch.
 box('Window05_'+cfg['id']+'_Horizontal_Floor',(w,back,room_south,yh+.22,f-.16,f),coll,floor_mat)
 box('Window05_'+cfg['id']+'_Horizontal_Ceiling',(w,back,room_south,yh+.22,top,top+.18),coll,wall)
 box('Window05_'+cfg['id']+'_Interior_Back_Wall',(back-.18,back,room_south,yh+.22,f,top),coll,wall)
 box('Window05_'+cfg['id']+'_North_Room_Wall',(w,back,yh,yh+.22,f,top),coll,wall)
 if not cfg['corner']:box('Window05_'+cfg['id']+'_South_Room_Wall',(w,back,yl-.22,yl,f,top),coll,wall)
 box('Window05_'+cfg['id']+'_West_Low_Wall',(w-.18,w+.28,yl,yh,f,low-.06),coll,wall)
 box('Window05_'+cfg['id']+'_Deep_West_Sill',(w-.28,w+.46,yl,yh,low-.06,low),coll,stone)
 box('Window05_'+cfg['id']+'_West_Head_Reveal',(w-.18,w+.35,yl,yh,high,top),coll,wall)
 box('Window05_'+cfg['id']+'_West_Glass',(w+.026,w+.038,yl+.045,yh-.045,low+.06,high-.06),coll,clear)
 box('Window05_'+cfg['id']+'_West_Base_Frame',(w-.012,w+.105,yl,yh,low,low+.06),coll,frame)
 box('Window05_'+cfg['id']+'_West_Head_Frame',(w-.012,w+.105,yl,yh,high-.06,high),coll,frame)
 box('Window05_'+cfg['id']+'_North_Jamb',(w-.025,w+.14,yh-.065,yh,low,high),coll,frame)
 if cfg['corner']:
  s=cfg['south'];end=back-.25
  box('Window05_'+cfg['id']+'_South_Low_Wall',(w,end,s-.18,s+.28,f,low-.06),coll,wall)
  box('Window05_'+cfg['id']+'_Deep_South_Sill',(w,end,s-.28,s+.46,low-.06,low),coll,stone)
  box('Window05_'+cfg['id']+'_South_Head_Reveal',(w,end,s-.18,s+.35,high,top),coll,wall)
  box('Window05_'+cfg['id']+'_South_Glass',(w+.045,end-.045,s+.026,s+.038,low+.06,high-.06),coll,clear)
  box('Window05_'+cfg['id']+'_South_Base_Frame',(w,end,s-.012,s+.105,low,low+.06),coll,frame)
  box('Window05_'+cfg['id']+'_South_Head_Frame',(w,end,s-.012,s+.105,high-.06,high),coll,frame)
  box('Window05_'+cfg['id']+'_Corner_Post',(w-.025,w+.075,s-.025,s+.075,low,high),coll,frame)
  box('Window05_'+cfg['id']+'_South_End_Jamb',(end-.065,end,s-.025,s+.14,low,high),coll,frame)
 else:box('Window05_'+cfg['id']+'_South_Jamb',(w-.025,w+.14,yl,yl+.065,low,high),coll,frame)
 camdata=bpy.data.cameras.new('Window05_'+cfg['id']+'_Fixed_Camera');camdata.sensor_fit='VERTICAL';camdata.sensor_height=24;camdata.lens=12/math.tan(math.radians(cfg['vfov']/2));camdata.clip_start=.025;camdata.clip_end=3000
 cam=bpy.data.objects.new(camdata.name,camdata);bpy.data.collections['Cameras'].objects.link(cam);cam.location=cfg['eye'];forward=Vector(cfg['target'])-cam.location;cam.rotation_euler=forward.to_track_quat('-Z','Y').to_euler();scene.camera=cam
 scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.render.threads_mode='FIXED';scene.render.threads=LOW_PREVIEW['threads'];scene.cycles.use_denoising=True;scene.cycles.samples=LOW_PREVIEW['samples'];scene.render.resolution_x=LOW_PREVIEW['width'];scene.render.resolution_y=LOW_PREVIEW['height'];scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.render.use_border=False;scene.render.use_crop_to_border=False;scene.render.filepath=str(OUT/('preview-'+cfg['id']+'-low.png'))
 scene.cycles.denoising_use_gpu=False;scene.cycles.preview_denoising_use_gpu=False
 scene['Camera05_Method']='Fixed standing interior viewpoint in existing host volume; authored local real aperture, horizontal FF/slab/sill; commercial geometry unchanged; no crop, no motion.'
 scene['Camera05_Host_Local_Aperture_Only']=cfg['host'];scene['Camera05_Floor_Absolute_m']=f
 scene.view_settings.view_transform='AgX'
 bpy.context.view_layer.update()
 after={n:digest(bpy.data.objects[n]) for n in frozen};changed=[n for n in frozen if frozen[n]!=after[n]]
 assert cfg['host'] in changed and set(changed).issubset(set(allowed_local_hosts)),changed
 indoor=w<cam.location.x<back and room_south<cam.location.y<yh and f<cam.location.z<top
 assert indoor and abs(cam.location.z-f-1.6)<1e-4,{'inside':indoor,'eye':list(cam.location),'floor':f,'standing_height':cam.location.z-f}
 assert scene.render.use_border==False and scene.render.use_crop_to_border==False
 tilt=math.degrees(math.atan2(-forward.z,math.hypot(forward.x,forward.y)))
 projected={}
 for collname in ['Curved_A','Curved_B','Curved_Bridge']:
  pts=[o.matrix_world@Vector(v) for o in bpy.data.collections[collname].all_objects if o.type=='MESH' for v in o.bound_box]
  pv=[world_to_camera_view(scene,cam,p) for p in pts]
  projected[collname]={'min_normalized':[min(v.x for v in pv),min(v.y for v in pv)],'max_normalized':[max(v.x for v in pv),max(v.y for v in pv)],'min_depth_m':min(v.z for v in pv)}
 ray=forward.normalized();success,p,n,index,obj,mat=scene.ray_cast(bpy.context.evaluated_depsgraph_get(),cam.location,ray,distance=2000)
 assert success and obj.name=='Window05_'+cfg['id']+'_West_Glass',{'unexpected_near_occluder':obj.name if obj else None,'point':list(p) if success else None}
 deps=bpy.context.evaluated_depsgraph_get();ray_rows=[]
 for fy in [.12,.3,.5,.7,.88]:
  for fz in [.17,.5,.83]:
   q=Vector((w+.032,yl+.12+(yh-yl-.24)*fy,low+.12+(high-low-.24)*fz));dr=(q-cam.location).normalized()
   hit,loc,norm,face,part,matrix=scene.ray_cast(deps,cam.location,dr,distance=2000)
   first=part.name if hit else None;outside=None;origin=loc+dr*.045 if hit else cam.location
   for _ in range(32):
    hit2,loc2,norm2,face2,part2,matrix2=scene.ray_cast(deps,origin,dr,distance=2000)
    if not hit2:break
    if not part2.hide_render and not part2.name.startswith('Window05_'+cfg['id']+'_West_Glass'):
     outside=part2.name;break
    origin=loc2+dr*.045
   ok=first=='Window05_'+cfg['id']+'_West_Glass' and outside!=cfg['host'] and not (outside and outside.startswith(prefix))
   ray_rows.append({'target_on_glazing_m':list(q),'first_surface':first,'first_renderable_after_closed_glass':outside,'local_host_not_blocking':ok})
 ray_audit={'status':'PASS' if all(r['local_host_not_blocking'] for r in ray_rows) else 'FAIL','method':'15 physical aperture sample rays; first hit must be new clear glass, subsequent visible opaque surface must not be host detail','render_performed':False,'rays':ray_rows,'allowed_local_host_parts':allowed_local_hosts,'limitations':['Geometric line of sight only; no radiance/sky/ground composition or appearance approval.']}
 (OUT/('aperture-ray-audit-'+cfg['id']+'.json')).write_text(json.dumps(ray_audit,indent=2),encoding='utf-8')
 assert ray_audit['status']=='PASS',ray_audit
 rec={**cfg,'eye_UE_cm':[100*cfg['eye'][0],-100*cfg['eye'][1],100*cfg['eye'][2]],'target_UE_cm':[100*cfg['target'][0],-100*cfg['target'][1],100*cfg['target'][2]],'height_above_ground_m':cfg['eye'][2]-6.9,'standing_eye_above_authored_FF_m':cam.location.z-f,'downward_pitch_deg':tilt,'horizontal_fov_deg':math.degrees(2*math.atan(math.tan(math.radians(cfg['vfov']/2))*16/9)),'lens_mm':camdata.lens,'lens_shift_xy':[camdata.shift_x,camdata.shift_y],'roll_deg':0.0,'aspect':'16:9','full_sensor_no_crop':True,'preview_budget':LOW_PREVIEW,'host_local_core_aperture_box_m':cut_bounds,'west_glazing_thickness_m':.012,'window_sill_above_FF_m':.22,'window_head_below_ceiling_m':.18,'host_contains_eye_in_authored_room':indoor,'central_ray_first_surface':{'hit':success,'object':obj.name if obj else None,'point_m':list(p) if success else None},'projected_commercial_bounds':projected,'original_objects_changed_in_copy':changed,'original_object_count_checked':len(frozen),'commercial_and_other_original_objects_match_fingerprints':True,'original_camera_data_unchanged':True}
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/cfg['file']),check_existing=False)
 (OUT/('camera-'+cfg['id']+'.json')).write_text(json.dumps(rec,indent=2),encoding='utf-8')
 (OUT/('geometry-lock-'+cfg['id']+'.json')).write_text(json.dumps({'status':'PASS','source':str(SOURCE),'candidate':cfg['file'],'method':'positions, polygon indices/material slots/smooth flags, matrices, UV layers and camera parameters SHA256; source files protected separately','allowed_local_host_aperture':allowed_local_hosts,'changed_original_objects_in_copy':changed,'unchanged_original_object_count':len(frozen)-len(changed),'fingerprints_before':frozen,'fingerprints_after':after,'limitations':['Only host aperture and new interior geometry differ. Material names/slots verified; no appearance rewrite performed. Technical identity does not imply visual approval.']},indent=2),encoding='utf-8')
 if args.geometry_only:
  print('CAMERA05_GEOMETRY_ONLY_COMPLETE',cfg['id'],'rays',len(ray_rows),'changed',changed,flush=True)
  return
 print('CAMERA05_FIXED_CPU_START',cfg['id'],cfg['eye'],'pitch',tilt,flush=True)
 bpy.ops.render.render(write_still=True)
 print('CAMERA05_FIXED_CPU_SAVED',cfg['id'],flush=True)

build(next(c for c in CONFIGS if c['id']==args.candidate))
print('CAMERA05_ONE_GEOMETRY_CANDIDATE_COMPLETE' if args.geometry_only else 'CAMERA05_ONE_LOW_FIXED_CANDIDATE_COMPLETE',args.candidate,flush=True)
