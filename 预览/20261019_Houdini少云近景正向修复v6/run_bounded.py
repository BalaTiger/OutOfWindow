"""Run one authorized stage; 2 GiB job, 2 CPU, 180 s, no concurrent UE/Houdini."""
import ctypes,ctypes.wintypes as w,subprocess,time,json,os,sys,re
from pathlib import Path
if sys.flags.optimize: raise RuntimeError('Optimized Python disables required validation')
ROOT=Path(__file__).resolve().parent
k=ctypes.WinDLL('kernel32',use_last_error=True); papi=ctypes.WinDLL('psapi',use_last_error=True)
class BASIC(ctypes.Structure):
    _fields_=[('ProcessTime',ctypes.c_int64),('JobTime',ctypes.c_int64),('Flags',w.DWORD),('MinWS',ctypes.c_size_t),('MaxWS',ctypes.c_size_t),('Active',w.DWORD),('Affinity',ctypes.c_size_t),('Priority',w.DWORD),('Scheduling',w.DWORD)]
class IO(ctypes.Structure):
    _fields_=[(n,ctypes.c_uint64) for n in ('r','w','o','rb','wb','ob')]
class EXT(ctypes.Structure):
    _fields_=[('Basic',BASIC),('Io',IO),('ProcessMemory',ctypes.c_size_t),('JobMemory',ctypes.c_size_t),('PeakProcess',ctypes.c_size_t),('PeakJob',ctypes.c_size_t)]
class MEM(ctypes.Structure):
    _fields_=[('length',w.DWORD),('load',w.DWORD)]+[(n,ctypes.c_uint64) for n in ('total','avail','pageTotal','pageAvail','virtualTotal','virtualAvail','extended')]
class PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_=[('cb',w.DWORD)]+[(n,ctypes.c_size_t) for n in ('commitTotal','commitLimit','commitPeak','physicalTotal','physicalAvailable','systemCache','kernelTotal','kernelPaged','kernelNonpaged','pageSize')]+[(n,w.DWORD) for n in ('handles','processes','threads')]
def resources():
    m=MEM(); m.length=ctypes.sizeof(m); p=PERFORMANCE_INFORMATION(); p.cb=ctypes.sizeof(p)
    if not k.GlobalMemoryStatusEx(ctypes.byref(m)): raise ctypes.WinError(ctypes.get_last_error())
    if not papi.GetPerformanceInfo(ctypes.byref(p),p.cb): raise ctypes.WinError(ctypes.get_last_error())
    return dict(availableGiB=m.avail/2**30,commitHeadroomGiB=(p.commitLimit-p.commitTotal)*p.pageSize/2**30)
k.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR]; k.CreateJobObjectW.restype=w.HANDLE
k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
k.TerminateJobObject.argtypes=[w.HANDLE,w.UINT]; k.CloseHandle.argtypes=[w.HANDLE]
k.QueryInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p]
class PROCESSENTRY32W(ctypes.Structure):
    _fields_=[('dwSize',w.DWORD),('cntUsage',w.DWORD),('th32ProcessID',w.DWORD),('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',w.DWORD),('cntThreads',w.DWORD),('th32ParentProcessID',w.DWORD),('pcPriClassBase',w.LONG),('dwFlags',w.DWORD),('szExeFile',w.WCHAR*260)]
class THREADENTRY32(ctypes.Structure):
    _fields_=[('dwSize',w.DWORD),('cntUsage',w.DWORD),('th32ThreadID',w.DWORD),('th32OwnerProcessID',w.DWORD),('tpBasePri',w.LONG),('tpDeltaPri',w.LONG),('dwFlags',w.DWORD)]
k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD]; k.CreateToolhelp32Snapshot.restype=w.HANDLE
k.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(PROCESSENTRY32W)]; k.Process32NextW.argtypes=k.Process32FirstW.argtypes
k.Thread32First.argtypes=[w.HANDLE,ctypes.POINTER(THREADENTRY32)]; k.Thread32Next.argtypes=k.Thread32First.argtypes
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]; k.OpenProcess.restype=w.HANDLE
k.OpenThread.argtypes=[w.DWORD,w.BOOL,w.DWORD]; k.OpenThread.restype=w.HANDLE
k.ResumeThread.argtypes=[w.HANDLE]; k.ResumeThread.restype=w.DWORD
k.IsProcessInJob.argtypes=[w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)]
def snapshot(flag):
    handle=k.CreateToolhelp32Snapshot(flag,0)
    if handle==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    return handle
def work_processes():
    result=[]; snap=snapshot(2)
    try:
        item=PROCESSENTRY32W(); item.dwSize=ctypes.sizeof(item)
        if not k.Process32FirstW(snap,ctypes.byref(item)): raise ctypes.WinError(ctypes.get_last_error())
        while True:
            name=item.szExeFile
            if re.fullmatch(r'(UnrealEditor.*|OutOfWindow.*|hython|hbatch|houdini|houdinifx|houdinicore|mantra|husk|ShaderCompileWorker)\.exe',name,re.I):
                result.append((int(item.th32ProcessID),name))
            if not k.Process32NextW(snap,ctypes.byref(item)): break
    finally: k.CloseHandle(snap)
    return result
def outside_job(job):
    outside=[]
    for pid,name in work_processes():
        handle=k.OpenProcess(0x1000,False,pid)
        if not handle:
            if ctypes.get_last_error()==87: continue # exited since snapshot
            outside.append((pid,name,'cannot inspect job')); continue
        try:
            member=w.BOOL()
            if not k.IsProcessInJob(handle,job,ctypes.byref(member)) or not member.value: outside.append((pid,name))
        finally: k.CloseHandle(handle)
    return outside
def resume_primary(child):
    snap=snapshot(4); tids=[]
    try:
        item=THREADENTRY32(); item.dwSize=ctypes.sizeof(item)
        if not k.Thread32First(snap,ctypes.byref(item)): raise ctypes.WinError(ctypes.get_last_error())
        while True:
            if item.th32OwnerProcessID==child.pid: tids.append(int(item.th32ThreadID))
            if not k.Thread32Next(snap,ctypes.byref(item)): break
    finally: k.CloseHandle(snap)
    if len(tids)!=1: raise RuntimeError('Expected exactly one suspended primary thread: '+str(tids))
    thread=k.OpenThread(0x0002,False,tids[0])
    if not thread: raise ctypes.WinError(ctypes.get_last_error())
    try:
        count=k.ResumeThread(thread)
        if count!=1: raise RuntimeError('Unexpected prior suspend count: '+str(count))
    finally: k.CloseHandle(thread)
def main(stage):
    if stage not in ('build_native','render_triple'): raise ValueError('Expected build_native or render_triple')
    lock=ROOT/'native-stage.lock'
    descriptor=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(descriptor,json.dumps(dict(ownerPid=os.getpid(),stage=stage)).encode('utf8')); os.close(descriptor)
    job=None; child=None; log=None; err=None; code=1; reason=None; peak=0; started=time.monotonic()
    try:
        if (ROOT/(stage+'-start.json')).exists(): raise RuntimeError('An uncertain or completed stage must not be rerun')
        other=work_processes()
        if other: raise RuntimeError('Another UE/Houdini process is active: '+str(other))
        initial=resources()
        if min(initial.values())<6: raise RuntimeError('Insufficient initial memory: '+str(initial))
        job=k.CreateJobObjectW(None,None)
        if not job: raise ctypes.WinError(ctypes.get_last_error())
        limit=EXT(); limit.Basic.Flags=0x2000|0x200|0x10; limit.Basic.Affinity=3; limit.JobMemory=2*1024**3
        if not k.SetInformationJobObject(job,9,ctypes.byref(limit),ctypes.sizeof(limit)): raise ctypes.WinError(ctypes.get_last_error())
        env=os.environ.copy(); env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HOUDINI_MAXTHREADS='2',CUDA_VISIBLE_DEVICES='-1',HOUDINI_USER_PREF_DIR=str(ROOT/'prefs__HVER__'))
        log=(ROOT/(stage+'-stdout.log')).open('xb'); err=(ROOT/(stage+'-stderr.log')).open('xb')
        # CREATE_SUSPENDED closes the native bootstrap gap before Job assignment.
        child=subprocess.Popen(['D:/Houdini/bin/hython.exe','-j','2',str(ROOT/(stage+'.py'))],cwd=str(ROOT),stdin=subprocess.PIPE,stdout=log,stderr=err,env=env,creationflags=0x08000000|0x4000|0x4)
        if not k.AssignProcessToJobObject(job,w.HANDLE(child._handle)): raise ctypes.WinError(ctypes.get_last_error())
        with (ROOT/(stage+'-start.json')).open('x',encoding='utf8') as out:
            json.dump(dict(pid=child.pid,initial=initial,deadlineSeconds=180,jobMemoryCapGiB=2,CPU=2,systemReserveGiB=4,createdSuspended=True,assignedToJobBeforeResume=True),out)
        other=outside_job(job)
        if other: raise RuntimeError('External UE/Houdini appeared before resume: '+str(other))
        resume_primary(child)
        child.stdin.write(b'go\n'); child.stdin.flush(); child.stdin.close()
        while child.poll() is None:
            m=EXT()
            if not k.QueryInformationJobObject(job,9,ctypes.byref(m),ctypes.sizeof(m),None): raise ctypes.WinError(ctypes.get_last_error())
            peak=max(peak,m.PeakJob); r=resources(); other=outside_job(job)
            if time.monotonic()-started>180: reason='180 second deadline'
            if min(r.values())<4: reason='system reserve below 4 GiB'
            if other: reason='External UE/Houdini appeared: '+str(other)
            if (ROOT/(stage+'-cancel')).exists(): reason='local cancellation requested'
            if reason: k.TerminateJobObject(job,124); break
            time.sleep(.5)
        code=child.wait(timeout=10)
        m=EXT()
        if k.QueryInformationJobObject(job,9,ctypes.byref(m),ctypes.sizeof(m),None): peak=max(peak,m.PeakJob)
    except Exception as exc:
        reason=type(exc).__name__+': '+str(exc)
    finally:
        if child is not None and child.poll() is None:
            if job: k.TerminateJobObject(job,124)
            child.terminate(); child.wait(timeout=10)
        if job: k.CloseHandle(job)
        if log: log.close()
        if err: err.close()
        # Only this invocation created this lock with O_EXCL.
        lock.unlink()
    report=dict(status='COMPLETED' if code==0 and reason is None else 'STOPPED',exitCode=code,reason=reason,seconds=time.monotonic()-started,peakJobBytes=peak,resourcesEnd=resources(),CPUslotReleased=True,nativeChildCreated=child is not None)
    # A rejected preflight must not occupy the result name of a future allowed
    # stage. Native attempts remain non-repeatable and preserve their logs.
    report_name=stage+'-budget.json' if child is not None else stage+'-preflight-'+str(time.time_ns())+'.json'
    with (ROOT/report_name).open('x',encoding='utf8') as out: json.dump(report,out,indent=2)
    print(json.dumps(report)); return code
if __name__=='__main__': sys.exit(main(sys.argv[1] if len(sys.argv)>1 else ''))
