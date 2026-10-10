from pathlib import Path
import json,ast,math,hashlib,datetime,shutil,py_compile
root=Path(r'C:\Users\zhuzi\Documents\Codex\2026-10-07\task-3')
project=Path(r'C:\Users\zhuzi\Documents\OutOfWindow')
out=project/'unreal/Art/CityDesign_WindowCamera05'
script=root/'build_camera05.py'
py_compile.compile(str(script),doraise=True)
configs=None
for n in ast.parse(script.read_text(encoding='utf-8')).body:
 if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIGS' for t in n.targets):configs=ast.literal_eval(n.value)
records=[]
for c in configs:
 dx,dy,dz=[c['target'][k]-c['eye'][k] for k in range(3)]
 pitch=math.degrees(math.atan2(-dz,math.hypot(dx,dy)))
 eye=c['eye'];floor=c['floor']
 records.append({**c,'state':'PROPOSED_NOT_BUILT_OR_RENDERED','eye_UE_cm':[eye[0]*100,-eye[1]*100,eye[2]*100],'target_UE_cm':[c['target'][0]*100,-c['target'][1]*100,c['target'][2]*100],'standing_eye_height_m':eye[2]-floor,'height_above_nominal_ground_m':eye[2]-6.9,'downward_pitch_deg':pitch,'horizontal_fov_deg':math.degrees(2*math.atan(math.tan(math.radians(c['vfov']/2))*16/9)),'lens_mm':12/math.tan(math.radians(c['vfov']/2)),'nominal_unoccluded_horizon_from_top_fraction':.5-math.tan(math.radians(pitch))/(2*math.tan(math.radians(c['vfov']/2))),'no_render_crop':True,'aspect':'16:9'})
(out/'camera-design-plan.json').write_text(json.dumps({'status':'DESIGN_ONLY_CPU_PREVIEW_PAUSED_FOR_SYSTEM_DIAGNOSIS','candidates':records,'reference':{'official_photo_url':'https://media-prod.zha.com/zhweb-prod-media/media/dxrb5gjv/01499_cp_hc_nov12_n79504.jpg?w=1920','identity':'Previously supplied first overall Galaxy SOHO reference, Hufton + Crow; cannot prove a separate user exact-photo selection from retained messages','actual_pixels_inspected':True,'reference_aspect_approx':2.38,'reference_sky_estimated_fraction':[.16,.18],'reference_ground_estimated_fraction':[.20,.25],'note':'Manual image estimates, not photogrammetry. FOV/pitch/physical original camera height cannot be reconstructed from this photo.'}},indent=2),encoding='utf-8')
inspect=root/'camera05-source-scene.json'
paused={'checked_utc':'2026-10-07T12:49:28Z','state':'NO_BLENDER_UE_PROCESS_NO_RENDER_STARTED_THIS_ROUND','process_read_only_observation':'Get-Process returned no exact Blender/python/OutOfWindow/UnrealEditor/UnrealEditor-Cmd matches at check','system_physical_memory_kib':{'total':33316708,'free':10013944},'latest_scene_inspection_completed_utc':datetime.datetime.fromtimestamp(inspect.stat().st_mtime,datetime.timezone.utc).isoformat(),'only_blender_use_this_round':'Read v04 scene bounds and camera only; process exited; no render or save to source','ongoing_processes_owned_by_this_task':0,'no_gpu_ue_or_focus_operations':True,'next_dependency':'Wait for main/cloud diagnostic confirmation of system stability before Blender build/CPU preview launch'}
(out/'coordination-status.json').write_text(json.dumps(paused,indent=2),encoding='utf-8')
before=json.loads((out/'protected-before.json').read_text(encoding='utf-8'));rows=[]
for old in before['files']:
 p=project/old['relative_path'];now=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
 rows.append({**old,'current_sha256':now,'unchanged':now==old['sha256']})
changes=[x['relative_path'] for x in rows if not x['unchanged']]
(out/'protected-checkpoint.json').write_text(json.dumps({'status':'PASS' if not changes else 'CHANGED_DURING_SHARED_WORK','checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':rows,'changed_files':changes,'scope':'115 original protected/v03 and every v04 deliverable file captured at start of camera-only round'},indent=2),encoding='utf-8')
sources=out/'SourceScripts';sources.mkdir(exist_ok=True)
for name in ['prepare_camera05.py','build_camera05.py','inspect_camera05_scene.py','checkpoint_camera05_pause.py']:shutil.copy2(root/name,sources/name)
shutil.copy2(inspect,out/inspect.name)
(out/'RESUME.md').write_text('''# Camera05 暂停点：机位设计已保存，尚未建模/渲染

用户认可CommercialScale04比例，要求室内临街高楼窗景，更高机位和Galaxy整体官方照的天地面积关系。先查看PLAN.md、camera-design-plan.json、coordination-status.json。

用户报告OutOfWindow进程崩溃，主会话要求避免增加负载。12:49:28 UTC检查无Blender/UE相关进程，可用物理内存约9.55GiB。本轮唯一Blender进程只读场景边界，已退出；本轮还没有CPU渲染、GPU或UE。不要把本目录当作已有blend/预览成果。

两个候选已精确设计，尚未在Blender执行：A B08塔楼第13段内西窗，FF51.6077、眼点(27.5,49,53.2077)，target(-52,21,26.5)；B B09塔楼顶部第16段内西南转角窗，FF61.6、眼点(25.05,86.5,63.2)，target(-50,28,34)。同VFOV52°、16:9，站立眼高1.6m，世界水平地板，不裁切。室内FF和房间为候选新增，不假称原外壳已有内部楼板。B09西玻璃23.605已由原GLB字节核验，不能用裙房bounds X19.55/21.55推断顶层玻璃。

等待主会话/云诊断确认系统稳定后再用单后台Blender CPU一线程执行SourceScripts/build_camera05.py；脚本会从只读v04分别创建两个独立blend，局部宿主实心核真实窗洞，补物理房间/窗台/玻璃，保证除了各自宿主局部窗洞，其余原网格、UV、矩阵和原相机参数指纹不变。先1280×720小样实际像素审阅，仅两个既定机位；再保存正式16:9固定图并按Library支持上传流程传给主会话发送原生附件。

prepare_camera05.py只做一次，已有protected-before.json禁止重跑；不要覆写保护基线。商业/办公尺度、原v04、City、部署及云A/B诊断相机保持不动。无提交推送部署。
''',encoding='utf-8')
index=[{'relative_path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='file-index.json']
(out/'file-index.json').write_text(json.dumps({'state':'DESIGN_CHECKPOINT_NO_NEW_BLEND_OR_PREVIEW','files':index},indent=2),encoding='utf-8')
print('CAMERA05_PAUSE_CHECKPOINT_WRITTEN protected_files='+str(len(rows))+' changes='+str(changes),flush=True)
for c in records:print(c['id'],'eye',c['eye'],'pitch',round(c['downward_pitch_deg'],3),'VFOV',c['vfov'],'H',c['height_above_nominal_ground_m'])
