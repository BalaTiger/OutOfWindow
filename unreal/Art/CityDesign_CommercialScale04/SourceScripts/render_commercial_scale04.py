"""Only the fixed window camera; background CPU rendering, one fixed thread."""
import bpy
import sys
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:]
out=Path(args[0]);phase=args[1] if len(args)>1 else 'draft'
scene=bpy.context.scene
scene.camera=bpy.data.objects['Review_Window_UE_VFOV54']
scene.render.engine='CYCLES';scene.cycles.device='CPU'
scene.render.threads_mode='FIXED';scene.render.threads=1
scene.cycles.use_denoising=True
scene.cycles.samples=12 if phase=='draft' else 24
scene.render.resolution_x=1280 if phase=='draft' else 2560
scene.render.resolution_y=720 if phase=='draft' else 1440
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.filepath=str(out/('window-draft.png' if phase=='draft' else 'preview-window.png'))
print('FIXED_WINDOW_CPU_START',phase,scene.render.resolution_x,scene.render.resolution_y,flush=True)
bpy.ops.render.render(write_still=True)
print('FIXED_WINDOW_CPU_SAVED',scene.render.filepath,flush=True)
