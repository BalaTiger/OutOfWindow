"""Fresh-process CPU previews; relationship pass first, detail pass after pixel review."""
import bpy
import sys
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:]
out=Path(args[0]);stage=args[1] if len(args)>1 else 'relationship'
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.device='CPU'
scene.render.threads_mode='FIXED';scene.render.threads=1
scene.cycles.use_denoising=True
scene.render.image_settings.file_format='PNG'
scene.render.resolution_percentage=100
if stage=='relationship':
    scene.cycles.samples=12
    shots=[('Review_Window_UE_VFOV54',960,540,'relationship-window.png'),('Review_Courtyard_Low',1000,660,'relationship-courtyard.png')]
else:
    scene.cycles.samples=32
    shots=[('Review_Window_UE_VFOV54',1280,720,'preview-window.png'),('Review_Curved_Overall',1200,800,'preview-overall.png'),('Review_Courtyard_Low',1200,800,'preview-courtyard.png'),('Review_Office_Corner',1200,850,'preview-office.png')]
for cam,w,h,file in shots:
    scene.camera=bpy.data.objects[cam];scene.render.resolution_x=w;scene.render.resolution_y=h;scene.render.filepath=str(out/file)
    hidden=[]
    bpy.data.collections['Office_Corner'].hide_render=(cam!='Review_Office_Corner')
    if cam=='Review_Office_Corner':
        for obj in bpy.data.objects:
            if obj.name.startswith('CityModern_B07_') and not obj.hide_render:obj.hide_render=True;hidden.append(obj)
    print('CPU_PREVIEW_START',stage,cam,flush=True)
    bpy.ops.render.render(write_still=True)
    for obj in hidden:obj.hide_render=False
    print('CPU_PREVIEW_SAVED',file,flush=True)
print('CPU_PREVIEWS_COMPLETE',stage,flush=True)
