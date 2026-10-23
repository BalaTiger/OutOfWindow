"""Recover only a failed JSON receipt; exact frozen arrays must remain unchanged."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
source=(ROOT/'offline_density.py').read_text(encoding='utf8')
expected='c7ab990d864e424f6055233d03313da3ac5f961f0371a78c33395e2573e88aaa'
assert hashlib.sha256((ROOT/'offline_density.py').read_bytes()).hexdigest()==expected
assert not (ROOT/'offline-result.json').exists()
frozen={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('density-comparison.npz','opacity-preflight.npz')}
old="""if (ROOT/'offline-start.json').exists(): raise RuntimeError('A previous attempt exists; preserve it')
with (ROOT/'offline-start.json').open('x',encoding='utf8') as f:
    json.dump(dict(pid=os.getpid(),stage='ONE_ADDITIVE_OFFLINE_SPECIMEN',nativeProcessesStarted=False),f)"""
assert source.count(old)==1
source=source.replace(old,"assert (ROOT/'offline-start.json').exists(), 'Recovery requires the original attempt'")
oldsave="def save(name,value): (ROOT/name).write_text(json.dumps(value,indent=2),encoding='utf8')"
newsave="""def normalize(x):
    if isinstance(x,np.generic): return x.item()
    raise TypeError(type(x).__name__)
def save(name,value):
    encoded=json.dumps(value,indent=2,default=normalize)
    if name=='authored-branches.json':
        assert json.loads((ROOT/name).read_text(encoding='utf8'))==json.loads(encoded)
        return
    assert name=='offline-result.json' and not (ROOT/name).exists()
    (ROOT/name).write_text(encoded,encoding='utf8')
def verify_frozen(path,**arrays):
    stored=np.load(path)
    assert set(stored.files)==set(arrays)
    assert all(np.array_equal(stored[k],v) for k,v in arrays.items()), 'Frozen candidate/projection mismatch'
"""
assert source.count(oldsave)==1
source=source.replace(oldsave,newsave).replace('np.savez_compressed(ROOT/','verify_frozen(ROOT/')
source=source.replace("report['seconds']=time.monotonic()-START;", "report['recovery']={'reason':'NumPy bool serialization failure','originalScriptSHA256':'"+expected+"','method':'Recompute identical deterministic checks and require every frozen density/projection value to match; do not rewrite arrays'}; report['seconds']=time.monotonic()-START;")
source=source.replace("print(json.dumps(report,indent=2))","print(json.dumps(report,indent=2,default=normalize))")
code=0
try:exec(compile(source,str(ROOT/'offline_density.py'),'exec'),dict(__file__=str(ROOT/'offline_density.py'),__name__='__recovery__'))
except SystemExit as ex:code=ex.code
assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==sha for n,sha in frozen.items())
(ROOT/'report-recovery.json').write_text(json.dumps(dict(status='FROZEN_ARRAYS_UNCHANGED',originalScriptSHA256=expected,frozenSHA256=frozen,gateExitCode=code),indent=2),encoding='utf8')
raise SystemExit(code)
