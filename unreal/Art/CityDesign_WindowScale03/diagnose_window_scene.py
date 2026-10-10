"""Read-only measurements of the actual saved camera and visible source meshes."""
import bpy
import json
import re
import sys
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

out=Path(sys.argv[sys.argv.index('--')+1])
scene=bpy.context.scene
cam=bpy.data.objects['Review_Window_UE_VFOV54']
width,height=2560,1440
def bounds(points):
    lo=[min(p[k] for p in points) for k in range(3)];hi=[max(p[k] for p in points) for k in range(3)]
    return {'min':lo,'max':hi,'dimensions':[hi[k]-lo[k] for k in range(3)]}
def project(points):
    view=[world_to_camera_view(scene,cam,p) for p in points]
    return {'min_px':[min(p.x for p in view)*width,(1-max(p.y for p in view))*height], 'max_px':[max(p.x for p in view)*width,(1-min(p.y for p in view))*height], 'camera_depth_m':[min(p.z for p in view),max(p.z for p in view)]}
objects=[];groups={}
for collname in ('Curved_A','Curved_B','Curved_Bridge','Curved_C','Existing_City_Context'):
    coll=bpy.data.collections[collname]
    for obj in coll.all_objects:
        if obj.type!='MESH':continue
        points=[obj.matrix_world@Vector(v) for v in obj.bound_box]
        record={'name':obj.name,'collection':collname,'bounds_m':bounds(points),'projected_box_1440p':project(points),'materials':[m.name for m in obj.data.materials if m],'polygons':len(obj.data.polygons),'smooth_faces':sum(p.use_smooth for p in obj.data.polygons)}
        objects.append(record)
        match=re.search(r'CityModern_(B\d+)_',obj.name)
        group=match.group(1) if match else collname
        groups.setdefault(group,[]).extend(points)
report={'read_only':True,'blend':bpy.data.filepath,'camera':{'position':list(cam.location),'rotation':list(cam.rotation_euler),'lens_mm':cam.data.lens,'sensor_fit':cam.data.sensor_fit,'sensor_height_mm':cam.data.sensor_height,'view_frame':[list(v) for v in cam.data.view_frame(scene=scene)],'screen_budget':[width,height]},'groups':{k:{'bounds_m':bounds(p),'projected_box_1440p':project(p)} for k,p in groups.items()},'objects':objects,'limitations':['Projected bounding boxes are not actual visibility or occlusion areas.','No render, save or modifications. Source textures/UE shader appearance are not captured by these mesh measurements.']}
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print('FIXED_WINDOW_DIAGNOSIS_RECORDED',len(objects),flush=True)
