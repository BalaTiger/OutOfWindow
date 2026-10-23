"""Render only the one new candidate; reuse exact verified original/control EXRs."""
import sys
if sys.flags.optimize:raise RuntimeError('Validation requires non-optimized Python')
if sys.stdin.readline().strip()!='go':raise RuntimeError('Resource job handshake missing')
import hou,json,hashlib,time,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DIAG=ROOT.parent/'houdini-few-near-20261019-diagnostic-v5'
SOURCE=ROOT.parent/'resume-20261014/cloud-candidate/houdini-cloud01-20261016'
build=json.loads((ROOT/'build-result.json').read_text(encoding='utf8'))
old=json.loads((DIAG/'build-result.json').read_text(encoding='utf8'))
oldrender=json.loads((DIAG/'render-result.json').read_text(encoding='utf8'))
prior=json.loads((ROOT.parent/'houdini-few-near-20261019/native-result.json').read_text(encoding='utf8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def parameters(node):
    out={}
    for p in node.parms():
        v=p.eval()
        if isinstance(v,str):v=p.unexpandedString()
        if isinstance(v,(int,float,str)):out[p.name()]=v
    return out
assert build['status']=='NATIVE_BUILT_PENDING_VISUAL_REVIEW'
assert build['fixedNodeParameters']==old['fixedNodeParameters']
assert all(build[k]==old[k] for k in ('originalSHA256','controlSHA256'))
assert digest(ROOT/'EXPERIMENT-few-near-positive-v6.hip')==build['hipSHA256']
hou.setMaxThreads(2)
hou.hipFile.load(str(ROOT/'EXPERIMENT-few-near-positive-v6.hip'),suppress_save_prompt=True)
sw=hou.node('/obj/cloud_density/ORIGINAL_0_GRID_CONTROL_1_ADDITIVE_2')
rop=hou.node('/out/cloud01_cpu_preview')
assert all(parameters(hou.node(p))==v for p,v in build['fixedNodeParameters'].items())
assert all(rop.parm(k).eval()==v for k,v in prior['renderSettings'].items())
result=dict(status='CANDIDATE_RENDER_STARTED',actualRenders=[],newRenderCount=1,
    sameParameterValues=True,lightingAndMaterialChanged=False,displayGain=1,accepted=False,
    fairComparison='Exact control grid, camera, material and lighting retained. Original/control raw EXRs reused from prior verified native render.')
for i,n in enumerate(('original','control')):
    sw.parm('input').set(i)
    assert hashlib.sha256(sw.geometry().prims()[0].allVoxelsAsString()).hexdigest()==build[n+'SHA256']
    receipt=next(x for x in oldrender['actualRenders'] if x['name']==n)
    assert digest(DIAG/(n+'.exr'))==receipt['sha256']
    assert not (ROOT/(n+'.exr')).exists()
    shutil.copyfile(DIAG/(n+'.exr'),ROOT/(n+'.exr'))
    result['actualRenders'].append(dict(receipt,reused=True,source=str(DIAG/(n+'.exr'))))
def write():(ROOT/'render-result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
sw.parm('input').set(2)
assert hashlib.sha256(sw.geometry().prims()[0].allVoxelsAsString()).hexdigest()==build['candidateSHA256']
out=ROOT/'candidate.exr';assert not out.exists()
rop.parm('vm_picture').set('$HIP/candidate.exr');write()
started=time.monotonic();rop.render()
assert out.exists() and out.stat().st_size>0
result['actualRenders'].append(dict(name='candidate',seconds=time.monotonic()-started,bytes=out.stat().st_size,sha256=digest(out),reused=False))
result.update(status='SINGLE_CANDIDATE_RENDER_COMPLETED',sourceFilesUnchanged=all(digest(SOURCE/n)==h for n,h in build['sources'].items()))
assert result['sourceFilesUnchanged'];write();print(json.dumps(result))
