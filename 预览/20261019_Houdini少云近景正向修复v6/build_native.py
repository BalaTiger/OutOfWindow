"""Save one additive experiment only after offline density/projection gates."""
import sys
if sys.flags.optimize: raise RuntimeError('Validation requires non-optimized Python')
if sys.stdin.readline().strip()!='go': raise RuntimeError('Resource job handshake missing')
import hou,numpy as np,json,hashlib,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'resume-20261014/cloud-candidate/houdini-cloud01-20261016'
PRIOR=ROOT.parent/'houdini-few-near-20261019'
DIAG=ROOT.parent/'houdini-few-near-20261019-diagnostic-v5'
hou.setMaxThreads(2)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def parameters(node):
    out={}
    for p in node.parms():
        v=p.eval()
        if isinstance(v,str): v=p.unexpandedString()
        if isinstance(v,(int,float,str)):out[p.name()]=v
    return out
expected=json.loads((PRIOR/'native-result.json').read_text(encoding='utf8'))
old=json.loads((DIAG/'build-result.json').read_text(encoding='utf8'))
pre=json.loads((ROOT/'offline-result.json').read_text(encoding='utf8'))
assert pre['gatesPassed'] is True
assert all(digest(SOURCE/n)==h for n,h in expected['sources'].items())
data=np.load(ROOT/'density-comparison.npz')
lower=data['lower'];upper=data['upper']
assert np.array_equal(lower,[-626.875,-505.,-337.8125])
assert np.array_equal(upper,[564.375,442.5,369.0625])
arrays={n:np.ascontiguousarray(data[n],dtype=np.float32) for n in ('original','control','candidate')}
hashes={n+'SHA256':hashlib.sha256(a.tobytes()).hexdigest() for n,a in arrays.items()}
assert all(pre[k]==v for k,v in hashes.items()), 'Offline gates must refer to these exact arrays'
assert hashes['originalSHA256']==old['originalSHA256']
assert hashes['controlSHA256']==old['controlSHA256']
assert np.all(arrays['candidate']>=arrays['control']), 'The original trunk cannot lose density'
assert np.isfinite(arrays['candidate']).all()
assert arrays['candidate'].shape==(128,128,128)
hip=ROOT/'EXPERIMENT-few-near-positive-v6.hip'
assert not hip.exists()
started=time.monotonic()
for n in ('sample06-density.bgeo.sc','sample06-control.bgeo.sc'):
    assert not (ROOT/n).exists()
    shutil.copyfile(SOURCE/n,ROOT/n)
hou.hipFile.load(str(SOURCE/'cloud01-sample06-review.hip'),suppress_save_prompt=True)
cloud=hou.node('/obj/cloud_density')
source=cloud.node('density65_exact_sample06')
source.parm('file').set(str(ROOT/'sample06-density.bgeo.sc'))
hou.node('/obj/sample06_control_B_repaired/accepted_control_mesh').parm('file').set(str(ROOT/'sample06-control.bgeo.sc'))
assert hashlib.sha256(source.geometry().prims()[0].allVoxelsAsString()).hexdigest()==hashes['originalSHA256']
nodes=[source]
for n in ('control','candidate'):
    geo=hou.Geometry();attr=geo.addAttrib(hou.attribType.Prim,'name','')
    volume=geo.createVolume(128,128,128,hou.BoundingBox(*(lower.tolist()+upper.tolist())))
    volume.setAttribValue(attr,'density');volume.setAllVoxelsFromString(arrays[n].tobytes())
    geo.saveToFile(str(ROOT/(n+'.bgeo.sc')))
    node=cloud.createNode('file','grid_control' if n=='control' else 'positive_multiscale_local_experiment')
    node.parm('file').set(str(ROOT/(n+'.bgeo.sc')));nodes.append(node)
sw=cloud.createNode('switch','ORIGINAL_0_GRID_CONTROL_1_ADDITIVE_2')
for i,n in enumerate(nodes):sw.setInput(i,n)
sw.parm('input').set(2);sw.setDisplayFlag(True);sw.setRenderFlag(True);cloud.layoutChildren()
cam=hou.node('/obj/fixed_photo_camera')
cam.parm('resx').set(2560);cam.parm('resy').set(1440)
for k,v in dict(cropl=100/2560,cropr=450/2560,cropb=1-315/1440,cropt=1-190/1440).items():cam.parm(k).set(v)
assert all(parameters(hou.node(p))==v for p,v in old['fixedNodeParameters'].items())
rop=hou.node('/out/cloud01_cpu_preview')
for k,v in expected['renderSettings'].items():rop.parm(k).set(v)
rop.parm('soho_pipecmd').set('mantra -j 2');rop.parm('vm_picture').set('$HIP/candidate.exr')
for n,name in zip(nodes,('sample06-density','control','candidate')):n.parm('file').set('$HIP/'+name+'.bgeo.sc')
hou.node('/obj/sample06_control_B_repaired/accepted_control_mesh').parm('file').set('$HIP/sample06-control.bgeo.sc')
hou.hipFile.save(str(hip),save_to_recent_files=False)
hou.hipFile.clear(suppress_save_prompt=True);hou.hipFile.load(str(hip),suppress_save_prompt=True)
sw=hou.node('/obj/cloud_density/ORIGINAL_0_GRID_CONTROL_1_ADDITIVE_2')
assert all(parameters(hou.node(p))==v for p,v in old['fixedNodeParameters'].items())
for i,n in enumerate(('original','control','candidate')):
    sw.parm('input').set(i)
    assert hashlib.sha256(sw.geometry().prims()[0].allVoxelsAsString()).hexdigest()==hashes[n+'SHA256']
sw.parm('input').set(2);hou.hipFile.save(str(hip),save_to_recent_files=False)
report=dict(status='NATIVE_BUILT_PENDING_VISUAL_REVIEW',accepted=False,topologyAccepted=True,
    sources=expected['sources'],camera=old['camera'],sunlight=old['sunlight'],
    fixedNodeParameters=old['fixedNodeParameters'],volumeCountPerRoute=1,
    sourceMeshChanged=False,replicatedCloudCount=0,globalStretch=False,
    method='Preserve every control voxel; local positive multiscale geometry only',
    densityReducedVoxelCount=int(np.count_nonzero(arrays['candidate']<arrays['control'])),
    offlineReportSHA256=digest(ROOT/'offline-result.json'),hipSHA256=digest(hip),
    buildSeconds=time.monotonic()-started,sourceFilesUnchanged=all(digest(SOURCE/n)==h for n,h in expected['sources'].items()),**hashes)
assert report['sourceFilesUnchanged']
(ROOT/'build-result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('fixedNodeParameters','camera','sunlight')}))
