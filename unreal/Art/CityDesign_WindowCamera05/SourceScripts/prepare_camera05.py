from pathlib import Path
import json,hashlib,subprocess,datetime
project=Path(r'C:\Users\zhuzi\Documents\OutOfWindow')
old=project/'unreal/Art/CityDesign_CommercialScale04'
out=project/'unreal/Art/CityDesign_WindowCamera05'
out.mkdir(exist_ok=True)
baseline=out/'protected-before.json'
if baseline.exists():raise SystemExit('Existing baseline must be preserved; preparation is one-shot.')
paths={project/x['relative_path'] for x in json.loads((old/'protected-before-v4.json').read_text(encoding='utf-8'))}
paths.update(p for p in old.rglob('*') if p.is_file())
records=[{'relative_path':p.relative_to(project).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]
baseline.write_text(json.dumps({'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':records},indent=2),encoding='utf-8')
(out/'worktree-before.txt').write_text(subprocess.check_output(['git','status','--short'],cwd=project,text=True),encoding='utf-8')
(out/'PLAN.md').write_text('''# 固定高楼窗景机位候选

锁定 CommercialScale04 商业尺度，不修改原 v04、City、部署或云 A/B 相机。已实际查看此前首张 Galaxy SOHO 整体官方照 n79504 和 v04 固定窗景；参考高位浅至中度斜俯、立面主导，天空约16–18%、地面约20–25%的人工像素估读。原参考是2.38:1，不能把照片反推成测量机位。

只做两个有区别的16:9固定候选：A在B08顶层西向窗，眼高约53.2m，强调跨街立面；B在B09顶层西南转角窗，眼高63.2m，展示更多屋顶、连桥和庭院。原宿主只有外壳与实心核；在各自独立blend中局部打开宿主窗洞、补水平房间楼板/墙面/窗台与玻璃。不是把框贴到原浮空机位，亦不裁切原图冒充抬高。

单个后台Blender进程、CPU一线程，先1280×720小样实际看像素，再为这两套既定机位保存正式固定图。建筑保留指纹、机位记录、保护记录和本地文件清单。预览按Library支持流程上传作为image。无UE、GPU、运镜、提交推送或部署。

拟交付：Camera05_A_B08.blend、Camera05_B_B09.blend，preview-A/B.png，camera-records.json、geometry-lock-audit.json、protected-before/after.json、README.md、RESUME.md、file-index.json及SourceScripts。
''',encoding='utf-8')
print('CAMERA05_PREPARED protected_files='+str(len(records)),flush=True)
