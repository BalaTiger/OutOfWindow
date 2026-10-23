"""One additive specimen; NumPy only. Prepared for the parent's single offline run.

No Houdini imports, renderer, source mutation, orphan removal or parameter search.
"""
import os,sys,time,json,hashlib,ctypes
from pathlib import Path
if sys.flags.optimize: raise RuntimeError('Validation requires non-optimized Python')
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[name]='1'
import numpy as np
ROOT=Path(__file__).resolve().parent
FAILED=ROOT.parent/'houdini-few-near-20261019-local128-v5'
PRIOR=ROOT.parent/'houdini-few-near-20261019'
SOURCE=ROOT.parent/'resume-20261014/cloud-candidate/houdini-cloud01-20261016'
SPEC=Path('C:/Users/zhuzi/Documents/Codex/2026-10-07/task-5/cloud-single-reference-specimen-20261014/composition.json')
START=time.monotonic()
if os.name=='nt':
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    kernel.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
    kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    handle=kernel.GetCurrentProcess()
    if not kernel.SetProcessAffinityMask(handle,3): raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.SetPriorityClass(handle,0x4000): raise ctypes.WinError(ctypes.get_last_error())
def guard():
    if time.monotonic()-START>180: raise RuntimeError('180 second offline deadline')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def array_hash(a): return hashlib.sha256(a.tobytes()).hexdigest()
def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1); return t*t*(3-2*t)
def save(name,value): (ROOT/name).write_text(json.dumps(value,indent=2),encoding='utf8')
if (ROOT/'offline-start.json').exists(): raise RuntimeError('A previous attempt exists; preserve it')
with (ROOT/'offline-start.json').open('x',encoding='utf8') as f:
    json.dump(dict(pid=os.getpid(),stage='ONE_ADDITIVE_OFFLINE_SPECIMEN',nativeProcessesStarted=False),f)
prior=json.loads((PRIOR/'native-result.json').read_text(encoding='utf8'))
failure=json.loads((FAILED/'build-result.json').read_text(encoding='utf8'))
source_hashes={name:digest(SOURCE/name) for name in prior['sources']}
if source_hashes!=prior['sources']: raise RuntimeError('Original source SHA changed')
input_path=FAILED/'diagnostic-volume-comparison.npz'; input_sha=digest(input_path)
data=np.load(input_path)
original=data['original'].astype(np.float32,copy=True)
control=data['control'].astype(np.float32,copy=True)
lower=data['lower'].astype(float); upper=data['upper'].astype(float); voxel=(upper-lower)/128
if array_hash(original)!=failure['originalSHA256'] or array_hash(control)!=failure['controlSHA256']:
    raise RuntimeError('Original/control arrays differ from frozen v5 input')
assert original.shape==control.shape==(128,128,128)
del data
candidate=control.copy()
old_lower=np.array([-1000.,-800.,-500.]); old_upper=np.array([1000.,800.,500.])

# Each authored sweep has a dense root. Unequal directions/radii/heights; no
# repeated crown asset, no global scaling. Every later twig attaches before it
# is merged, never repaired after a connectivity failure.
branches=[
 dict(name='left_asymmetric_buttress',seed=117,nodes=[
  [-420,-10,465,44,62,43],[-474,-80,496,50,60,52],
  [-510,-105,548,43,56,62],[-478,-127,590,46,63,47],[-430,-80,631,39,57,44]]),
 dict(name='left_short_oblique_return',seed=331,nodes=[
  [-478,-127,590,29,35,32],[-492,-182,622,26,30,30],[-460,-173,642,23,28,27]]),
 dict(name='middle_unequal_crest',seed=593,nodes=[
  [-40,120,635,42,58,47],[-68,105,674,39,52,42],
  [-85,70,706,44,47,38],[-58,-5,732,34,39,29]]),
 dict(name='right_low_forward_ridge',seed=907,nodes=[
  [370,35,435,32,48,35],[391,-35,452,36,44,37],
  [412,-115,475,30,39,31],[385,-176,456,42,35,28]])]
save('authored-branches.json',dict(branches=branches,noiseScales=[97,43,23],noiseAmplitudes=[.10,.055,.025],
    unchangedTrunk=True,construction='max(control,rooted positive sweep union)',
    limitation='Additions cannot remove the old straight boundary; B foreground remains exact.'))

def sample(grid,points,lo,hi):
    shape=points.shape[:-1]; q=(points.reshape(-1,3)-lo)/((hi-lo)/128)-.5
    idx=np.floor(q).astype(np.int32); frac=q-idx; out=np.zeros(len(q),np.float32)
    for dz in (0,1):
      for dy in (0,1):
       for dx in (0,1):
        corner=idx+np.array([dx,dy,dz]); valid=np.all((corner>=0)&(corner<128),axis=1)
        j=np.clip(corner,0,127); weight=np.prod(np.where(np.array([dx,dy,dz]),frac,1-frac),axis=1)
        out+=grid[j[:,2],j[:,1],j[:,0]]*weight*valid
    return out.reshape(shape)
def udh_to_xyz(points):
    u,d,h=np.asarray(points).T
    return np.stack((.82428549*u+.56617439*d,.56617439*u-.82428549*d,h-500),axis=-1)
def noise(points,scale,seed):
    q=points/scale; cell=np.floor(q).astype(np.int64); f=q-cell; f=f*f*(3-2*f)
    result=np.zeros(len(q),np.float32)
    for dz in (0,1):
      for dy in (0,1):
       for dx in (0,1):
        j=cell+np.array([dx,dy,dz]); v=j.astype(np.uint32)
        key=(v[:,0]*np.uint32(73856093))^(v[:,1]*np.uint32(19349663))^(v[:,2]*np.uint32(83492791))^np.uint32(seed)
        key^=key>>np.uint32(13); key*=np.uint32(1274126177); key^=key>>np.uint32(16)
        value=(key&np.uint32(0xffffff)).astype(np.float32)/np.float32(0xffffff)*2-1
        result+=value*np.prod(np.where(np.array([dx,dy,dz]),f,1-f),axis=1)
    return result
def edit_weight(points):
    u,d,h=points.T
    return 1-(1-smooth(330,390,abs(u)))*smooth(150,200,h)*(1-smooth(680,740,h))*(1-smooth(65,120,d))
def sweep_slab(points,nodes,seed):
    field=np.zeros(len(points),np.float32)
    for a,b in zip(nodes[:-1],nodes[1:]):
        guard(); direction=b[:3]-a[:3]
        t=np.clip(((points-a[:3])*direction).sum(axis=1)/float(direction@direction),0,1)
        centre=a[:3]+t[:,None]*direction; radii=a[3:]+t[:,None]*(b[3:]-a[3:])
        q=(points-centre)/radii; radius=np.linalg.norm(q,axis=1)
        active=radius<1.181
        if not active.any(): continue
        # Noise is evaluated on the section surface, independent of radial
        # distance. Every section keeps a solid core; no noisy detached puffs.
        rr=radius[active]; qq=q[active]
        direction_q=qq/np.maximum(rr[:,None],1e-6)
        surface=centre[active]+direction_q*radii[active]
        scale=1+.10*noise(surface,97,seed)+.055*noise(surface,43,seed+19)+.025*noise(surface,23,seed+71)
        shell=.88*(1-smooth(.22,1,rr/scale))
        core=.72*(1-smooth(.30,.60,rr))
        local=np.maximum(shell,core).astype(np.float32)
        field[active]=1-(1-field[active])*(1-local)
    return field

def components(a,threshold):
    unseen=(a>threshold).ravel().copy(); counts=[]
    for start in np.flatnonzero(unseen):
        if not unseen[start]: continue
        unseen[start]=False; stack=[int(start)]; count=0
        while stack:
            i=stack.pop(); count+=1; x=i%128; y=(i//128)%128; z=i//16384
            for yes,j in ((x>0,i-1),(x<127,i+1),(y>0,i-128),(y<127,i+128),(z>0,i-16384),(z<127,i+16384)):
                if yes and unseen[j]: unseen[j]=False; stack.append(j)
            if count%32768==0: guard()
        counts.append(count)
    return sorted(counts,reverse=True)

branch_records=[]
for branch in branches:
    nodes=np.asarray(branch['nodes'],float); field=np.zeros_like(control)
    root_xyz=udh_to_xyz(nodes[:1,:3]); root_before=float(sample(candidate,root_xyz,lower,upper)[0])
    for z0 in range(0,128,4):
        guard(); z,y,x=np.meshgrid(lower[2]+(np.arange(z0,z0+4)+.5)*voxel[2],
            lower[1]+(np.arange(128)+.5)*voxel[1],lower[0]+(np.arange(128)+.5)*voxel[0],indexing='ij')
        pts=np.stack((x*.82428549+y*.56617439,x*.56617439-y*.82428549,z+500),axis=-1).reshape(-1,3)
        field[z0:z0+4]=(sweep_slab(pts,nodes,branch['seed'])*edit_weight(pts)).reshape(4,128,128)
    overlap=int(np.count_nonzero((field>.35)&(candidate>.35)))
    branch_records.append(dict(name=branch['name'],rootDensityBeforeAddition=root_before,
        denseOverlapVoxels=overlap,threshold02Components=components(field,.02),
        changedVoxels=int(np.count_nonzero(field>candidate)),fieldSHA256=array_hash(field)))
    np.maximum(candidate,field,out=candidate)
    del field
guard()

# Camera-matched opacity projection is a geometry/coverage preflight only.
# It has no sunlight/shading and must never be presented as a cloud render.
spec=json.loads(SPEC.read_text(encoding='utf8')); camera=np.array(prior['camera']).reshape(4,4)
origin=camera[3,:3]*np.array([1,1,-1])
width,height=spec['fixedView']['nativeResolution']; focal=width/(2*np.tan(np.radians(spec['fixedView']['horizontalFovDegrees'])/2))
yy,xx=np.meshgrid(np.arange(190,315)+.5,np.arange(100,450)+.5,indexing='ij')
directions=np.stack(((xx.ravel()-width/2)/focal,-(yy.ravel()-height/2)/focal,-np.ones(xx.size)),axis=1)@camera[:3,:3]
directions*=np.array([1,1,-1]); directions/=np.linalg.norm(directions,axis=1)[:,None]
t0=(old_lower-origin)/directions; t1=(old_upper-origin)/directions
near=np.maximum(np.minimum(t0,t1).max(axis=1),0); far=np.maximum(near,np.maximum(t0,t1).min(axis=1))
opacity={name:np.zeros(xx.size,np.float32) for name in ('original','control','candidate')}
k=float(spec['fixedLight']['kPerMetre'])
for start in range(0,xx.size,192):
    guard(); stop=min(start+192,xx.size); length=far[start:stop]-near[start:stop]
    n=np.maximum(np.ceil(length/4).astype(int),1); spacing=length/n; j=np.arange(n.max())[None,:]
    valid=j<n[:,None]; depth=near[start:stop,None]+(j+.5)*spacing[:,None]
    points=origin+directions[start:stop,None,:]*depth[...,None]
    for name,grid,lo,hi in (('original',original,old_lower,old_upper),('control',control,lower,upper),('candidate',candidate,lower,upper)):
        tau=k*(sample(grid,points,lo,hi)*valid*spacing[:,None]).sum(axis=1)
        opacity[name][start:stop]=-np.expm1(-tau)
opacity={name:a.reshape(xx.shape) for name,a in opacity.items()}
def bounds(mask):
    yy,xx=np.nonzero(mask)
    return [int(xx.min())+100,int(yy.min())+190,int(xx.max())+101,int(yy.max())+191] if len(xx) else None
def compare(before,after):
    a=before>.02; b=after>.02
    return dict(alpha02IoU=float(np.count_nonzero(a&b)/max(1,np.count_nonzero(a|b))),
        boundsBefore=bounds(a),boundsAfter=bounds(b),newSupportPixels=int(np.count_nonzero(b&~a)),
        maximumOpacityLoss=float(max(0,(before-after).max())),meanOpacityGain=float((after-before).mean()))
projection=dict(kind='UNSHADED_OPACITY_PREFLIGHT_NOT_RENDER',nativeCrop=[100,190,450,315],
    cameraSHA256=hashlib.sha256(np.asarray(prior['camera']).tobytes()).hexdigest(),
    fixedWorldZReflection=True,physicalIntegrationStepMaximum=4,
    originalVsControl=compare(opacity['original'],opacity['control']),
    controlVsCandidate=compare(opacity['control'],opacity['candidate']))

z,y,x=np.meshgrid(lower[2]+(np.arange(128)+.5)*voxel[2],lower[1]+(np.arange(128)+.5)*voxel[1],lower[0]+(np.arange(128)+.5)*voxel[0],indexing='ij')
u=x*.82428549+y*.56617439; d=x*.56617439-y*.82428549; h=z+500
protected=(abs(u)<=330)&(h>=200)&(h<=680)&(d<=65)
def boundary(a): return float(max(a[:3].max(),a[-3:].max(),a[:,:3].max(),a[:,-3:].max(),a[:,:,:3].max(),a[:,:,-3:].max()))
connectivity={name:{str(t):components(a,t) for t in (1e-4,.02)} for name,a in (('original',original),('control',control),('candidate',candidate))}
mass=100*(candidate.sum(dtype=np.float64)/control.sum(dtype=np.float64)-1)
report=dict(status='OFFLINE_GATES_PENDING',nativeExecuted=False,rendered=False,candidateCount=1,grid=[128]*3,
    sourceSHA256=source_hashes,inputNPZSHA256=input_sha,originalSHA256=array_hash(original),controlSHA256=array_hash(control),candidateSHA256=array_hash(candidate),
    lower=lower.tolist(),upper=upper.tolist(),voxel=voxel.tolist(),branches=branch_records,components=connectivity,
    minimumCandidateMinusControl=float((candidate-control).min()),protectedBMaxDelta=float(abs(candidate[protected]-control[protected]).max()),
    boundaryThreeLayersMax=boundary(candidate),densityIntegralIncreasePercent=mass,
    changedVoxelCount=int(np.count_nonzero(candidate>control)),projection=projection,
    sourceFilesUnchanged={n:digest(SOURCE/n)==v for n,v in source_hashes.items()},
    camera=prior['camera'],sunlight=prior['sunlight'],cameraLightMaterialPolicy='Native stage must inherit original HIP unchanged; this stage has no shading/material',
    topologyCleanup=False,globalStretch=False,replicatedCloudAsset=False)
gates=dict(finiteRange=bool(np.isfinite(candidate).all() and candidate.min()>=0 and candidate.max()<=1),
    candidateNeverBelowControl=bool(np.all(candidate>=control)),BExact=report['protectedBMaxDelta']==0,
    zeroThreeLayerBoundary=report['boundaryThreeLayersMax']==0,
    allOriginalControlCandidateConnected=all(len(v)==1 for route in connectivity.values() for v in route.values()),
    everyBranchRooted=all(b['rootDensityBeforeAddition']>.2 and b['denseOverlapVoxels']>=32 for b in branch_records),
    everyBranchSingleConnectedAt02=all(len(b['threshold02Components'])==1 for b in branch_records),
    densityIncreaseLimited=0<mass<8,actualAddition=report['changedVoxelCount']>0,
    projectionShapePreserved=projection['controlVsCandidate']['alpha02IoU']>=.95,
    projectionNoOpacityLoss=projection['controlVsCandidate']['maximumOpacityLoss']<=1e-6,
    sourcesUnchanged=all(report['sourceFilesUnchanged'].values()))
report['gates']=gates
report['gatesPassed']=all(gates.values())
# Evidence is preserved even if a gate rejects the specimen. No cleanup rerun.
np.savez_compressed(ROOT/'density-comparison.npz',original=original,control=control,candidate=candidate,lower=lower,upper=upper)
np.savez_compressed(ROOT/'opacity-preflight.npz',**opacity)
report['densityNPZSHA256']=digest(ROOT/'density-comparison.npz')
report['status']='OFFLINE_GATES_PASSED_NATIVE_PENDING' if all(gates.values()) else 'OFFLINE_REJECTED_NO_NATIVE'
report['seconds']=time.monotonic()-START; save('offline-result.json',report)
print(json.dumps(report,indent=2))
if not all(gates.values()): raise SystemExit(2)
