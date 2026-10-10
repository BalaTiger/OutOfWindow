"""One background Blender process: export, fixed CPU draft, mesh audit, FBX readback."""
import runpy
import shutil
import sys
from pathlib import Path

out = Path(sys.argv[sys.argv.index('--') + 1])
root = Path(__file__).parent
if (out/'window-draft.png').exists() and not (out/'window-draft-initial.png').exists():
    shutil.copy2(out/'window-draft.png', out/'window-draft-initial.png')
for script in ('export_window_scale03.py', 'render_window_scale03.py', 'verify_window_scale03_fbx.py'):
    sys.argv = [script, '--', str(out), 'draft']
    try:
        runpy.run_path(str(root/script), run_name='__main__')
    except SystemExit as error:
        if error.code not in (None, 0):
            raise
print('WINDOW_SCALE03_EXPORT_REVIEW_SEQUENCE_COMPLETE', flush=True)
