"""Save only the CPU fixed-window review preset, with no rendering or mesh edits."""
import bpy
import sys
from pathlib import Path
out = Path(sys.argv[sys.argv.index('--') + 1])
scene = bpy.context.scene
scene.camera = bpy.data.objects['Review_Window_UE_VFOV54']
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.threads_mode = 'FIXED'
scene.render.threads = 1
scene.render.resolution_x = 2560
scene.render.resolution_y = 1440
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(out/'preview-window.png')
scene['Final_Window_Review_Preset'] = '2560x1440, Cycles CPU, 1 thread, 24 samples, denoised; camera unchanged.'
bpy.ops.wm.save_as_mainfile(filepath=str(out/'CityDesign_WindowScale03.blend'))
print('WINDOW_SCALE03_CPU_PRESET_SAVED',flush=True)
