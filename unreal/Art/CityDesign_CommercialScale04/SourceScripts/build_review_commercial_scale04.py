"""One CPU-limited background process: explicit parts, audit, draft and FBX check."""
import bpy
import json
import runpy
import sys
from pathlib import Path

out=Path(sys.argv[sys.argv.index('--')+1]);root=Path(__file__).parent
def run(name,args):
    sys.argv=[name,'--',*map(str,args)]
    try:runpy.run_path(str(root/name),run_name='__main__')
    except SystemExit as error:
        if error.code not in (None,0):raise

for name in ('build_commercial_scale04.py','refine_commercial_scale04.py','commercial_scale04_storefronts.py','export_commercial_scale04.py'):
    run(name,[out])
run('new_curved_validation.py',[out/'mesh_audit.json','--collections','Curved_A','Curved_B','Curved_Bridge','Curved_C','Curved_Site','Office_Window_Visible','--placeholder','Curved_C'])
if json.loads((out/'mesh_audit.json').read_text(encoding='utf-8'))['status']!='PASS':
    raise RuntimeError('Source audit failed; no draft render started.')
run('verify_commercial_scale04_geometry.py',[out])
run('render_commercial_scale04.py',[out,'draft'])
run('verify_commercial_scale04_fbx.py',[out])
print('COMMERCIAL_SCALE04_DRAFT_SEQUENCE_COMPLETE',flush=True)
