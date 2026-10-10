"""Bounded correction on the independent sample: keep four sweep corners sharp."""
import bpy
from pathlib import Path

changed=[]
for obj in bpy.data.collections['Curved_Bridge'].objects:
    if obj.type!='MESH' or not any(word in obj.name for word in ('Soffit_and_Deck','Curved_Roof','Continuous_Fascia','Upper_Fascia')):
        continue
    count=len(obj.data.vertices)//4
    for edge in obj.data.edges:
        a,b=edge.vertices
        edge.use_edge_sharp=(a%4==b%4 or (a//4==b//4 and a//4 in (0,count-1)))
    obj.data.update()
    changed.append(obj.name)
bpy.context.scene['Bridge_Shading']='Sharp deck/soffit cross section and end caps; smooth along the authored curve.'
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
print('BRIDGE_SHADING_REFINED',changed,flush=True)
