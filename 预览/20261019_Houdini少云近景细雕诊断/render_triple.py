"""Render one specimen's original/control/candidate sequentially; no UI."""
import sys
if sys.flags.optimize: raise RuntimeError('Optimized Python disables required validation')
handshake=sys.stdin.readline().strip()
if handshake != 'go': raise RuntimeError('Resource job handshake was not received')
import hou,json,hashlib,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'resume-20261014/cloud-candidate/houdini-cloud01-20261016'
prior=json.loads((ROOT.parent/'houdini-few-near-20261019/native-result.json').read_text(encoding='utf8'))
build=json.loads((ROOT/'build-result.json').read_text(encoding='utf8'))
assert build['status']=='REJECTED_CANDIDATE_SAVED_FOR_VISUAL_DIAGNOSIS_ONLY'
hou.setMaxThreads(2)
hou.hipFile.load(str(ROOT/'REJECTED-few-near-local128-v5.hip'),suppress_save_prompt=True)
sw=hou.node('/obj/cloud_density/ORIGINAL_0_GRID_CONTROL_1_REJECTED_2'); rop=hou.node('/out/cloud01_cpu_preview')
result=dict(status='TRIPLE_RENDER_STARTED',actualRenders=[],sameParameterValues=True,
    fairComparison='control vs candidate share the identical grid and sampling; original vs control additionally includes the grid-dependent sampling change',
    gridIsNotNewGeometry=True,lightingAndMaterialChanged=False,displayGain=1)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(): (ROOT/'render-result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
def parameters(node):
    values={}
    for parm in node.parms():
        value=parm.eval()
        if isinstance(value,str): value=parm.unexpandedString()
        if isinstance(value,(int,float,str)): values[parm.name()]=value
    return values
for i,name,key in ((0,'original','originalSHA256'),(1,'control','controlSHA256'),(2,'candidate','candidateSHA256')):
    assert not (ROOT/(name+'.exr')).exists()
    assert list(hou.node('/obj/fixed_photo_camera').worldTransform().asTuple())==build['camera']
    assert list(hou.node('/obj/original_sun_direction').worldTransform().asTuple())==build['sunlight']
    assert all(rop.parm(k).eval()==v for k,v in prior['renderSettings'].items())
    assert all(parameters(hou.node(p))==v for p,v in build['fixedNodeParameters'].items())
    sw.parm('input').set(i)
    assert hashlib.sha256(sw.geometry().prims()[0].allVoxelsAsString()).hexdigest()==build[key]
    rop.parm('vm_picture').set('$HIP/'+name+'.exr'); write()
    started=time.monotonic(); rop.render(); out=ROOT/(name+'.exr')
    assert out.exists() and out.stat().st_size>0
    result['actualRenders'].append(dict(name=name,seconds=time.monotonic()-started,bytes=out.stat().st_size,sha256=digest(out))); write()
sw.parm('input').set(2)
result.update(status='REJECTED_THREE_ROUTE_RENDER_COMPLETED',sourceFilesUnchanged=all(digest(SOURCE/n)==v for n,v in build['sources'].items()))
assert result['sourceFilesUnchanged']; write(); print(json.dumps(result))
