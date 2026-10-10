"""Record local deliverables and check protected inputs; does not touch source art."""
import json
import hashlib
import struct
import sys
from pathlib import Path
from datetime import datetime, timezone

out=Path(sys.argv[1]);project=out.parents[2]
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
baseline=read(out/'protected-baseline.json')
checks=[]
for item in baseline:
    path=project/item['relative_path']
    digest=hashlib.sha256(path.read_bytes()).hexdigest().upper()
    checks.append({**item,'after_sha256':digest,'unchanged':digest==item['sha256']})
write('protected-input-checks.json',{'checked_utc':datetime.now(timezone.utc).isoformat(),'all_unchanged':all(r['unchanged'] for r in checks),'files':checks,'note':'Existing worktree edits from other tasks were retained; no commit/push/deploy.'})
mesh=read(out/'mesh_audit.json');glb=read(out/'export_audit.json');fbx=read(out/'fbx_roundtrip_audit.json')
previews=[]
for file in ('preview-window.png','preview-overall.png','preview-courtyard.png','preview-office.png'):
    data=(out/file).read_bytes();w,h=struct.unpack('>II',data[16:24]);previews.append({'file':file,'width':w,'height':h,'method':'Cycles CPU, one fixed render thread, 32 samples, denoised','pixels_inspected':True})
manifest=read(out/'design_manifest.json')
manifest.update({'stage':'Reviewable local sample saved/exported; four actual CPU previews inspected; no UE integration or deployment.','technical_audit':{'source_status':mesh['status'],'glb_status':glb['status'],'fbx_roundtrip_status':fbx['status'],'source_triangles_with_C':mesh['total_unique_new_meshes']['triangles'],'architecture_triangles':69708,'office_trial_triangles':9252},'previews':previews,'scope_limits':['C remains an unfenestrated skyline placeholder and is excluded from exports.','Office corner is a three-floor independent trial, hidden in the default window view.','Background Blender mesh editing was authorized; this is not GUI hand modeling.','Source UV/normal checks and export checks do not validate UE runtime or architectural compliance.','Target 1440p distant detail not signed off by 720p window preview.']})
write('design_manifest.json',manifest)
references=read(out.parent/'CityDesign_CurvedDistrict02_Study'/'reference_sources.json')
galaxy=next(x for x in references['selected_built_references'] if x['name']=='Galaxy SOHO')
write('reference_index.json',{'main_reference':galaxy,'local_photos_location':'../CityDesign_CurvedDistrict02_Study/References/galaxy-soho/','other_study_references':'Not the main shape reference for this sample.'})
write('PLAN.json',{'task':'Independent A+B commercial architecture review sample','completed':['Inspect built Galaxy photographs and fixed-window pixels','Author A/B editable geometry, one bridge/court, C blockout and separate office trial','Correct bridge sweep curvature and shading; make 648 glass panels planar','Save separate architecture/office GLB and FBX packages','Inspect four actual CPU previews and validate source/export geometry','Verify 11 protected files; preserve previous samples and worktree edits'],'next_requires_main_thread_coordination':['UE import and map trial','GPU render or desktop application launch'],'not_performed':['City/WindowDirector/cloud/shared-build edits','deployment','git commit/push']})
files=[]
for path in sorted(out.iterdir()):
    if path.is_file() and path.name!='file-list.json':
        files.append({'relative_path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
write('file-list.json',{'directory':str(out),'generated_utc':datetime.now(timezone.utc).isoformat(),'files':files})
print('DELIVERABLES_RECORDED',len(files),'files | protected unchanged:',all(r['unchanged'] for r in checks))
