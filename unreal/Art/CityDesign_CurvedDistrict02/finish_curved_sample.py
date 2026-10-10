"""Fix only the small lettering UV warning, then export and audit the saved sample."""
import bpy
import sys
import runpy
from pathlib import Path

out=Path(sys.argv[sys.argv.index('--')+1])
script=Path(__file__).parent
obj=bpy.data.objects['B_Entry_ORBIT_GALLERIA']
for layer_name in [layer.name for layer in obj.data.uv_layers]:
    if layer_name not in ('UVMap','LightmapUV'):obj.data.uv_layers.remove(obj.data.uv_layers[layer_name])
for dest,source in zip(obj.data.uv_layers['UVMap'].data,obj.data.uv_layers['LightmapUV'].data):
    dest.uv=source.uv
obj['UV0_Intent']='Packed glyph atlas; solid colour material. Tiny extrusion is not a facade texture.'
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
sys.argv=['export_curved_sample.py','--',str(out)]
runpy.run_path(str(script/'export_curved_sample.py'),run_name='__main__')
sys.argv=['new_curved_validation.py','--',str(out/'mesh_audit.json'),'--collections','Curved_A','Curved_B','Curved_Bridge','Curved_C','Curved_Site','Office_Corner','--placeholder','Curved_C']
runpy.run_path(str(script/'new_curved_validation.py'),run_name='__main__')
