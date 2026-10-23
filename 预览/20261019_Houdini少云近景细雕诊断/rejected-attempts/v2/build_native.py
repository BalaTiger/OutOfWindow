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
hip=ROOT/'few-near-local128-v2.hip'
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
old_lower=np.array([-1000.,-800.,-500.]); old_voxel=np.array([15.625,12.5,7.8125])
occupied=np.argwhere(base>1e-4)[:,::-1]
lower=old_lower+occupied.min(0)*old_voxel-80
upper=old_lower+(occupied.max(0)+1)*old_voxel+80
voxel=(upper-lower)/128
assert np.allclose(lower,[-626.875,-505.,-337.8125])
assert np.allclose(upper,[564.375,442.5,369.0625])
empty=hou.Geometry(); attr=empty.addAttrib(hou.attribType.Prim,'name','')
v=empty.createVolume(128,128,128,hou.BoundingBox(*(lower.tolist()+upper.tolist())))
v.setAttribValue(attr,'density'); v.setAllVoxelsFromString(np.zeros((128,128,128),np.float32).tobytes())
empty.saveToFile(str(ROOT/'tight-grid-empty.bgeo.sc'))
grid=cloud.createNode('file','tight128_domain_only'); grid.parm('file').set(str(ROOT/'tight-grid-empty.bgeo.sc'))
control=cloud.createNode('volumewrangle','tight128_resample_control')
control.setInput(0,grid); control.setInput(1,source)
control.parm('snippet').set('@density=volumesample(1,"density",@P);')
candidate=cloud.createNode('volumewrangle','one_organic_fork_and_boundary_relief')
candidate.setInput(0,control); candidate.setInput(1,source)
candidate.parm('snippet').set((ROOT/'detail.vfl').read_text(encoding='utf8'))
sw=cloud.createNode('switch','ORIGINAL_0_GRID_CONTROL_1_SCULPT_2')
for i,node in enumerate((source,control,candidate)): sw.setInput(i,node)
sw.parm('input').set(2); sw.setDisplayFlag(True); sw.setRenderFlag(True)
cloud.layoutChildren()
arrays=[]
for node in (control,candidate):
    geometry=node.geometry()
    assert len(geometry.prims())==1 and tuple(geometry.prims()[0].resolution())==(128,128,128)
    arrays.append(np.frombuffer(geometry.prims()[0].allVoxelsAsString(),dtype=np.float32).copy().reshape(128,128,128))
ctl,fine=arrays
z,y,x=np.meshgrid(*[lower[i]+(np.arange(128)+.5)*voxel[i] for i in (2,1,0)],indexing='ij')
u=x*.82428549+y*.56617439; d=x*.56617439-y*.82428549; h=z+500
protect=(abs(u)<=330)&(h>=200)&(h<=680)&(d<=65)
def boundary(a):
    return float(max(a[:3].max(),a[-3:].max(),a[:,:3].max(),a[:,-3:].max(),a[:,:,:3].max(),a[:,:,-3:].max()))
def components(a,threshold):
    mask=(a>threshold).ravel().copy(); counts=[]
    for start in np.flatnonzero(mask):
        if not mask[start]: continue
        mask[start]=False; stack=[int(start)]; count=0
        while stack:
            i=stack.pop(); count+=1; ix=i%128; iy=(i//128)%128; iz=i//16384
            for valid,j in ((ix>0,i-1),(ix<127,i+1),(iy>0,i-128),(iy<127,i+128),(iz>0,i-16384),(iz<127,i+16384)):
                if valid and mask[j]: mask[j]=False; stack.append(j)
        counts.append(count)
    return sorted(counts,reverse=True)
report=dict(status='NATIVE_BUILD_GATES_PENDING',sources=expected['sources'],camera=expected['camera'],sunlight=expected['sunlight'],
    grid=[128]*3,localLower=lower.tolist(),localUpper=upper.tolist(),localVoxel=voxel.tolist(),
    originalVoxel=old_voxel.tolist(),volumeCountPerRoute=1,sourceMeshChanged=False,replicatedCloudCount=0,globalStretch=False,
    protectedRegion='abs(U)<=330,H=200..680,D<=65',protectedVoxelCount=int(protect.sum()),
    protectedMaxDelta=float(abs(fine[protect]-ctl[protect]).max()),
    densityIntegralChangeVsLocalControlPercent=100*(fine.sum(dtype=np.float64)/ctl.sum(dtype=np.float64)-1),
    controlIntegralChangeVsOriginalPercent=100*(ctl.sum(dtype=np.float64)*np.prod(voxel)/(base.sum(dtype=np.float64)*np.prod(old_voxel))-1),
    boundaryThreeLayersMax={'control':boundary(ctl),'candidate':boundary(fine)},
    originalSHA256=expected['baselineSHA256'],controlSHA256=hashlib.sha256(ctl.tobytes()).hexdigest(),candidateSHA256=hashlib.sha256(fine.tobytes()).hexdigest(),
    buildSeconds=time.monotonic()-started,rendered=False,detailVexSHA256=digest(ROOT/'detail.vfl'))
report['components']={name:{str(t):components(a,t) for t in (1e-4,.02)} for name,a in (('control',ctl),('candidate',fine))}
save('build-result.json',report)
assert np.isfinite(ctl).all() and np.isfinite(fine).all() and fine.min()>=0 and fine.max()<=1
assert report['protectedMaxDelta']==0
assert all(v==0 for v in report['boundaryThreeLayersMax'].values())
assert abs(report['densityIntegralChangeVsLocalControlPercent'])<12
assert abs(report['controlIntegralChangeVsOriginalPercent'])<2
assert all(len(c)==1 for v in report['components'].values() for c in v.values()), 'No post-hoc orphan removal'
control.geometry().saveToFile(str(ROOT/'tight128-control.bgeo.sc'))
candidate.geometry().saveToFile(str(ROOT/'tight128-candidate.bgeo.sc'))
np.savez_compressed(ROOT/'volume-comparison.npz',original=base,control=ctl,candidate=fine,lower=lower,upper=upper)
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
source.parm('file').set('$HIP/sample06-density.bgeo.sc'); grid.parm('file').set('$HIP/tight-grid-empty.bgeo.sc')
hou.node('/obj/sample06_control_B_repaired/accepted_control_mesh').parm('file').set('$HIP/sample06-control.bgeo.sc')
hou.hipFile.save(str(hip),save_to_recent_files=False)
hou.hipFile.clear(suppress_save_prompt=True); hou.hipFile.load(str(hip),suppress_save_prompt=True)
sw=hou.node('/obj/cloud_density/ORIGINAL_0_GRID_CONTROL_1_SCULPT_2')
assert all(parameters(hou.node(p))==v for p,v in report['fixedNodeParameters'].items())
for i,key in enumerate(('originalSHA256','controlSHA256','candidateSHA256')):
    sw.parm('input').set(i)
    assert hashlib.sha256(sw.geometry().prims()[0].allVoxelsAsString()).hexdigest()==report[key]
sw.parm('input').set(2); hou.hipFile.save(str(hip),save_to_recent_files=False)
report.update(status='NATIVE_THREE_ROUTE_HIP_RELOADED_ALL_GATES_PASSED',hipSHA256=digest(hip),sourceFilesUnchanged=all(digest(SOURCE/n)==v for n,v in expected['sources'].items()),buildSeconds=time.monotonic()-started)
assert report['sourceFilesUnchanged']; save('build-result.json',report); print(json.dumps(report))
