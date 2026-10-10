"""Render one already verified fixed interior candidate; caller owns resource window."""
import bpy,json,sys
from pathlib import Path
out=Path(r'C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\CityDesign_WindowCamera05')
candidate=sys.argv[sys.argv.index('--')+1] if '--' in sys.argv else 'A'
if candidate!='A':raise SystemExit('This existing repaired-preview path is for A only; B is a separate single candidate build.')
audit=json.loads((out/'aperture-ray-audit-A.json').read_text(encoding='utf-8'))
assert audit['status']=='PASS' and len(audit['rays'])==15
scene=bpy.context.scene;assert scene.camera.name=='Window05_A_Fixed_Camera'
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.denoising_use_gpu=False;scene.cycles.preview_denoising_use_gpu=False
scene.render.threads_mode='FIXED';scene.render.threads=2;scene.cycles.samples=8;scene.cycles.use_denoising=True
scene.render.resolution_x=640;scene.render.resolution_y=360;scene.render.resolution_percentage=100
scene.render.use_border=False;scene.render.use_crop_to_border=False;scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'preview-A-repaired-low.png')
print('CAMERA05_FIXED_CPU_START A_REPAIRED_EXISTING',flush=True)
bpy.ops.render.render(write_still=True)
print('CAMERA05_ONE_LOW_FIXED_CANDIDATE_COMPLETE A_REPAIRED_EXISTING',flush=True)
