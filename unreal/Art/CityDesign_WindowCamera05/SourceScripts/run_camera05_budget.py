"""Launch exactly one CPU preview; monitor only this child, never other applications."""
import ctypes,ctypes.wintypes as W,subprocess,json,time,datetime,sys,argparse,py_compile
from pathlib import Path
GiB=1024**3
ROOT=Path(r'C:\Users\zhuzi\Documents\Codex\2026-10-07\task-3')
OUT=Path(r'C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\CityDesign_WindowCamera05')
SOURCE=Path(r'C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\CityDesign_CommercialScale04\CityDesign_CommercialScale04.blend')
class PERF(ctypes.Structure):
 _fields_=[('cb',W.DWORD)]+[(n,ctypes.c_size_t) for n in ['CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable','SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize']]+[(n,W.DWORD) for n in ['HandleCount','ProcessCount','ThreadCount']]
class MEM(ctypes.Structure):
 _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD)]+[(n,ctypes.c_size_t) for n in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage']]
psapi=ctypes.WinDLL('psapi',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
psapi.GetPerformanceInfo.argtypes=[ctypes.POINTER(PERF),W.DWORD];psapi.GetPerformanceInfo.restype=W.BOOL
psapi.GetProcessMemoryInfo.argtypes=[W.HANDLE,ctypes.POINTER(MEM),W.DWORD];psapi.GetProcessMemoryInfo.restype=W.BOOL
kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
def system():
 p=PERF();p.cb=ctypes.sizeof(p)
 if not psapi.GetPerformanceInfo(ctypes.byref(p),p.cb):raise ctypes.WinError(ctypes.get_last_error())
 return {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'physical_available_gib':p.PhysicalAvailable*p.PageSize/GiB,'commit_headroom_gib':(p.CommitLimit-p.CommitTotal)*p.PageSize/GiB,'system_committed_gib':p.CommitTotal*p.PageSize/GiB,'commit_limit_gib':p.CommitLimit*p.PageSize/GiB,'process_count':p.ProcessCount}
def process(handle):
 m=MEM();m.cb=ctypes.sizeof(m)
 if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(m),m.cb):raise ctypes.WinError(ctypes.get_last_error())
 return {'private_gib':m.PrivateUsage/GiB,'working_set_gib':m.WorkingSetSize/GiB,'working_set_peak_gib':m.PeakWorkingSetSize/GiB,'pagefile_peak_gib':m.PeakPagefileUsage/GiB}
parser=argparse.ArgumentParser();parser.add_argument('--sample-only',action='store_true');parser.add_argument('--candidate',choices=['A','B'],default='A');parser.add_argument('--resume-before-first-render',action='store_true');parser.add_argument('--geometry-only',action='store_true');parser.add_argument('--render-existing-fixed',action='store_true');args=parser.parse_args()
if args.render_existing_fixed and (args.geometry_only or args.candidate!='A'):raise SystemExit('Repaired-existing mode is a single A preview, separate from geometry-only.')
baseline=system();print('CAMERA05_MEMORY_NOW',json.dumps(baseline),flush=True)
if args.sample_only:raise SystemExit(0)
report=OUT/(('memory-geometry-'+args.candidate+'-B08-fix.json') if args.geometry_only else ('memory-monitor-A-repaired.json' if args.render_existing_fixed else 'memory-monitor-'+args.candidate+'.json'))
if report.exists():
 previous=json.loads(report.read_text(encoding='utf-8'));previous_log=OUT/(('camera-'+args.candidate+'-geometry-fix.log') if args.geometry_only else ('camera-'+args.candidate+'-low.log'))
 never_rendered=previous.get('status')=='BLENDER_FAILED' and 'CAMERA05_FIXED_CPU_START' not in previous_log.read_text(encoding='utf-8',errors='replace') and (args.geometry_only or not (OUT/('preview-'+args.candidate+'-low.png')).exists())
 if not args.resume_before_first_render or not never_rendered:raise SystemExit('Refusing another preview render for this candidate without new coordination.')
 archive_id=1;archive_prefix=('memory-geometry-' if args.geometry_only else 'memory-monitor-')+args.candidate+'-setup-error-';log_prefix='camera-'+args.candidate+('-geometry-error-' if args.geometry_only else '-setup-error-')
 while (OUT/(archive_prefix+str(archive_id)+'.json')).exists():archive_id+=1
 report.rename(OUT/(archive_prefix+str(archive_id)+'.json'));previous_log.rename(OUT/(log_prefix+str(archive_id)+'.log'))
py_compile.compile(str(ROOT/'build_camera05.py'),doraise=True)
if args.render_existing_fixed:py_compile.compile(str(ROOT/'render_camera05_low.py'),doraise=True)
baseline=system()
private_limit=1.0 if args.geometry_only else 4.0
state={'candidate':args.candidate,'geometry_only_no_render':args.geometry_only,'limits':{'own_process_private_budget_gib':private_limit,'minimum_physical_available_gib':4.0,'minimum_commit_headroom_gib':6.0,'required_start_physical_gib':4.0+private_limit,'required_start_commit_headroom_gib':6.0+private_limit},'baseline':baseline,'samples':[],'status':'NOT_STARTED','no_gpu_ue_parallel_process_started':True}
def save():report.write_text(json.dumps(state,indent=2),encoding='utf-8')
if baseline['physical_available_gib']<state['limits']['required_start_physical_gib'] or baseline['commit_headroom_gib']<state['limits']['required_start_commit_headroom_gib']:
 state['status']='BUDGET_BLOCKED_BEFORE_LAUNCH';save();raise SystemExit(3)
log=OUT/(('camera-'+args.candidate+'-geometry-fix.log') if args.geometry_only else ('camera-A-repaired-low.log' if args.render_existing_fixed else 'camera-'+args.candidate+'-low.log'))
cmd=[r'D:\Blender\blender.exe','-b','-t','1' if args.geometry_only else '2','--python-exit-code','1','--python',str(ROOT/'build_camera05.py'),'--','--candidate',args.candidate]+(['--geometry-only'] if args.geometry_only else [])
if args.render_existing_fixed:cmd=[r'D:\Blender\blender.exe','-b',str(OUT/'Camera05_A_B08.blend'),'-t','2','--python-exit-code','1','--python',str(ROOT/'render_camera05_low.py'),'--','A']
start=time.monotonic();child=None;handle=None;stopped=False
try:
 with log.open('w',encoding='utf-8') as stream:
  child=subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
  state['pid']=child.pid;state['status']='RUNNING_OWN_SINGLE_CPU_PREVIEW';save()
  handle=kernel.OpenProcess(0x0400|0x0010,False,child.pid)
  if not handle:raise ctypes.WinError(ctypes.get_last_error())
  while child.poll() is None:
   current=system();current.update(process(handle));current['elapsed_seconds']=time.monotonic()-start;state['samples'].append(current)
   limits=[]
   if current['physical_available_gib']<4:limits.append('physical_available_below_4GiB')
   if current['commit_headroom_gib']<6:limits.append('commit_headroom_below_6GiB')
   if max(current['private_gib'],current['pagefile_peak_gib'])>private_limit:limits.append('own_private_budget_above_'+str(private_limit)+'GiB')
   if limits:
    state['stop_reasons']=limits;state['status']='STOPPED_OWN_PREVIEW_AT_MEMORY_LIMIT';stopped=True;child.terminate();child.wait(timeout=20);break
   save();time.sleep(2)
  state['exit_code']=child.wait(timeout=20)
  if not stopped:state['status']='COMPLETED' if state['exit_code']==0 else 'BLENDER_FAILED'
except Exception as exc:
 state['status']='MONITOR_ERROR_STOPPED_OWN_PREVIEW';state['monitor_error']=type(exc).__name__+': '+str(exc)
 raise
finally:
 if child is not None and child.poll() is None:
  child.terminate();child.wait(timeout=20);state['status']='STOPPED_OWN_CHILD_ON_MONITOR_ERROR'
 if handle:kernel.CloseHandle(handle)
 state['elapsed_seconds']=time.monotonic()-start;state['after']=system()
 rows=state['samples'];state['peak_private_gib']=max((max(r.get('private_gib',0),r.get('pagefile_peak_gib',0)) for r in rows),default=0);state['peak_private_commit_gib']=max((r.get('pagefile_peak_gib',0) for r in rows),default=0);state['peak_working_set_gib']=max((r.get('working_set_peak_gib',0) for r in rows),default=0);state['minimum_physical_available_gib']=min((r['physical_available_gib'] for r in rows),default=baseline['physical_available_gib']);state['minimum_commit_headroom_gib']=min((r['commit_headroom_gib'] for r in rows),default=baseline['commit_headroom_gib']);state['monitor_period_seconds']=2;save()
 print('CAMERA05_MONITOR_END',json.dumps({k:state[k] for k in ['status','elapsed_seconds','peak_private_gib','peak_working_set_gib','minimum_physical_available_gib','minimum_commit_headroom_gib','after']}),flush=True)
if state['status']!='COMPLETED':raise SystemExit(2)
expected='CAMERA05_ONE_GEOMETRY_CANDIDATE_COMPLETE' if args.geometry_only else 'CAMERA05_ONE_LOW_FIXED_CANDIDATE_COMPLETE'
preview_name='preview-A-repaired-low.png' if args.render_existing_fixed else 'preview-'+args.candidate+'-low.png'
if expected not in log.read_text(encoding='utf-8',errors='replace') or (not args.geometry_only and not (OUT/preview_name).is_file()):
 state['status']='EXPECTED_PREVIEW_OUTPUT_MISSING';save();raise SystemExit(4)
