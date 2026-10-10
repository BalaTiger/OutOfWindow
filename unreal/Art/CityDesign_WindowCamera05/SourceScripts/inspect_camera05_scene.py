import bpy,json,re,sys
from pathlib import Path
from mathutils import Vector
out=Path(sys.argv[sys.argv.index('--')+1])
groups={};objects=[]
for obj in bpy.context.scene.objects:
    if obj.type not in ('MESH','CAMERA'):continue
    if obj.type=='CAMERA':
        objects.append({'name':obj.name,'type':obj.type,'location':list(obj.location),'rotation_deg':[__import__('math').degrees(a) for a in obj.rotation_euler]});continue
    p=[obj.matrix_world@Vector(v) for v in obj.bound_box]
    rec={'name':obj.name,'collections':[c.name for c in obj.users_collection],'render':not obj.hide_render,'bounds':{'min':[min(v[k] for v in p) for k in range(3)],'max':[max(v[k] for v in p) for k in range(3)]},'vertices':len(obj.data.vertices),'polygons':len(obj.data.polygons)}
    objects.append(rec)
    m=re.search(r'CityModern_(B\d+)_',obj.name)
    if m:groups.setdefault(m.group(1),[]).extend(p)
report={'source':bpy.data.filepath,'collections':list(bpy.data.collections.keys()),'city_groups':{k:{'min':[min(v[i] for v in p) for i in range(3)],'max':[max(v[i] for v in p) for i in range(3)]} for k,p in groups.items()},'objects':objects}
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print('CAMERA05_SCENE_INSPECTED',flush=True)
