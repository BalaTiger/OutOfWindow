"""CPU preview in a fresh Blender process, kept separate from texture baking/export."""
import bpy
import sys
from pathlib import Path

out=Path(sys.argv[sys.argv.index('--')+1])
scene=bpy.context.scene
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=24
scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED'
scene.render.threads=1
for camera,width,height,file in (
    ('Review_Window_UE_VFOV54',960,540,'preview-window.png'),
    ('Review_Mall_Close',1100,760,'preview-close.png'),
    ('Review_Neighbor_Close',1000,760,'preview-neighbor.png')):
    scene.camera=bpy.data.objects[camera]
    scene.render.resolution_x=width
    scene.render.resolution_y=height
    scene.render.resolution_percentage=100
    scene.render.filepath=str(out/file)
    print('CPU_PREVIEW_START',camera,flush=True)
    bpy.ops.render.render(write_still=True)
    print('CPU_PREVIEW_SAVED',file,flush=True)
print('CPU_PREVIEWS_COMPLETE',flush=True)
