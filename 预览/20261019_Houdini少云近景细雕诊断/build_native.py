"""Prepared, not executed: create a tight-grid three-way native Houdini specimen."""
import sys
if sys.flags.optimize: raise RuntimeError('Optimized Python disables required validation')
handshake=sys.stdin.readline().strip()
if handshake != 'go': raise RuntimeError('Resource job handshake was not received')
import hou, numpy as np, json, hashlib, shutil, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PRIOR=ROOT.parent/'houdini-few-near-20261019'
SOURCE=ROOT.parent/'resume-20261014/cloud-candidate/houdini-cloud01-20261016'
hou.setMaxThreads(2)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data): (ROOT/name).write_text(json.dumps(data,indent=2),encoding='utf8')
def parameters(node):
    values={}
    for parm in node.parms():
        value=parm.eval()
        if isinstance(value,str): value=parm.unexpandedString()
        if isinstance(value,(int,float,str)): values[parm.name()]=value
    return values
expected=json.loads((PRIOR/'native-result.json').read_text(encoding='utf8'))
assert all(digest(SOURCE/n)==h for n,h in expected['sources'].items())
hip=ROOT/'REJECTED-few-near-local128-v5.hip'
assert not hip.exists(), 'A native result already exists; do not overwrite it'
started=time.monotonic()
for name in ('sample06-density.bgeo.sc','sample06-control.bgeo.sc'):
    assert not (ROOT/name).exists()
    shutil.copyfile(SOURCE/name,ROOT/name)
hou.hipFile.load(str(SOURCE/'cloud01-sample06-review.hip'),suppress_save_prompt=True)
source_camera=parameters(hou.node('/obj/fixed_photo_camera'))
source_light=parameters(hou.node('/obj/original_sun_direction'))
source_material=parameters(hou.node('/shop/white_cloud_scatter'))
cloud=hou.node('/obj/cloud_density')
source=cloud.node('density65_exact_sample06')
source.parm('file').set(str(ROOT/'sample06-density.bgeo.sc'))
hou.node('/obj/sample06_control_B_repaired/accepted_control_mesh').parm('file').set(str(ROOT/'sample06-control.bgeo.sc'))
primitive=source.geometry().prims()[0]
assert tuple(primitive.resolution())==(128,128,128)
base=np.frombuffer(primitive.allVoxelsAsString(),dtype=np.float32).copy().reshape(128,128,128)
assert hashlib.sha256(base.tobytes()).hexdigest()==expected['baselineSHA256']

FAILED=ROOT.parent/'houdini-few-near-20261019-local128-v5'
failure=json.loads((FAILED/'build-result.json').read_text(encoding='utf8'))
assert failure['status']=='NATIVE_BUILD_GATES_PENDING'
assert any(len(c)>1 for route in failure['components'].values() for c in route.values())
data=np.load(FAILED/'diagnostic-volume-comparison.npz')
lower=data['lower']; upper=data['upper']
assert np.array_equal(base,data['original'])
for name,key in [('control','controlSHA256'),('candidate','candidateSHA256')]:
    a=data[name]
    assert a.shape==(128,128,128) and hashlib.sha256(a.tobytes()).hexdigest()==failure[key]
    geo=hou.Geometry(); attr=geo.addAttrib(hou.attribType.Prim,'name','')
    volume=geo.createVolume(128,128,128,hou.BoundingBox(*(lower.tolist()+upper.tolist())))
    volume.setAttribValue(attr,'density'); volume.setAllVoxelsFromString(a.tobytes())
    geo.saveToFile(str(ROOT/(name+'.bgeo.sc')))
control=cloud.createNode('file','diagnostic_grid_control')
candidate=cloud.createNode('file','REJECTED_v5_candidate_no_cleanup')
for node,name in ((control,'control'),(candidate,'candidate')):node.parm('file').set(str(ROOT/(name+'.bgeo.sc')))
sw=cloud.createNode('switch','ORIGINAL_0_GRID_CONTROL_1_REJECTED_2')
for i,node in enumerate((source,control,candidate)):sw.setInput(i,node)
sw.parm('input').set(2);sw.setDisplayFlag(True);sw.setRenderFlag(True)
cloud.layoutChildren()
report=dict(status='REJECTED_DIAGNOSTIC_SAVE_PENDING',accepted=False,topologyAccepted=False,
    reason='Local128 v5 failed strict connected-volume gates. This scene only visualizes exact frozen arrays; no orphan removal or softened gate.',
    sources=expected['sources'],camera=expected['camera'],sunlight=expected['sunlight'],
    originalSHA256=failure['originalSHA256'],controlSHA256=failure['controlSHA256'],candidateSHA256=failure['candidateSHA256'],
    inheritedFailure=failure,sourceFailureSHA256=digest(FAILED/'build-result.json'),
    volumeCountPerRoute=1,sourceMeshChanged=False,replicatedCloudCount=0,globalStretch=False)
cam=hou.node('/obj/fixed_photo_camera'); light=hou.node('/obj/original_sun_direction')
assert list(cam.worldTransform().asTuple())==expected['camera']
assert list(light.worldTransform().asTuple())==expected['sunlight']
cam.parm('resx').set(2560); cam.parm('resy').set(1440)
for name,value in dict(cropl=100/2560,cropr=450/2560,cropb=1-315/1440,cropt=1-190/1440).items(): cam.parm(name).set(value)
allowed_camera_changes={'resx','resy','cropl','cropr','cropb','cropt'}
assert all(parameters(cam)[k]==v for k,v in source_camera.items() if k not in allowed_camera_changes)
assert parameters(light)==source_light
assert parameters(hou.node('/shop/white_cloud_scatter'))==source_material
report['fixedNodeParameters']={p:parameters(hou.node(p)) for p in ('/obj/fixed_photo_camera','/obj/original_sun_direction','/shop/white_cloud_scatter')}
rop=hou.node('/out/cloud01_cpu_preview')
for name,value in expected['renderSettings'].items(): rop.parm(name).set(value)
rop.parm('soho_pipecmd').set('mantra -j 2'); rop.parm('vm_picture').set('$HIP/candidate.exr')
source.parm('file').set('$HIP/sample06-density.bgeo.sc')
control.parm('file').set('$HIP/control.bgeo.sc');candidate.parm('file').set('$HIP/candidate.bgeo.sc')
hou.node('/obj/sample06_control_B_repaired/accepted_control_mesh').parm('file').set('$HIP/sample06-control.bgeo.sc')
hou.hipFile.save(str(hip),save_to_recent_files=False)
hou.hipFile.clear(suppress_save_prompt=True); hou.hipFile.load(str(hip),suppress_save_prompt=True)
sw=hou.node('/obj/cloud_density/ORIGINAL_0_GRID_CONTROL_1_REJECTED_2')
assert all(parameters(hou.node(p))==v for p,v in report['fixedNodeParameters'].items())
for i,key in enumerate(('originalSHA256','controlSHA256','candidateSHA256')):
    sw.parm('input').set(i)
    assert hashlib.sha256(sw.geometry().prims()[0].allVoxelsAsString()).hexdigest()==report[key]
sw.parm('input').set(2); hou.hipFile.save(str(hip),save_to_recent_files=False)
report.update(status='REJECTED_CANDIDATE_SAVED_FOR_VISUAL_DIAGNOSIS_ONLY',hipSHA256=digest(hip),sourceFilesUnchanged=all(digest(SOURCE/n)==v for n,v in expected['sources'].items()),buildSeconds=time.monotonic()-started)
assert report['sourceFilesUnchanged']; save('build-result.json',report); print(json.dumps(report))
