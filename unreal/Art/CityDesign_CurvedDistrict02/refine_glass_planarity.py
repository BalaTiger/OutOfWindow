"""Flatten the actual chord panes: finite, closed glass slabs, not twisted quads."""
import bpy
import bmesh
import json
from pathlib import Path
from mathutils import Vector

records=[]
for name in ('Curved_A','Curved_B'):
    for obj in bpy.data.collections[name].objects:
        if obj.type!='MESH' or not any(word in obj.name for word in ('Glass_ChordPanels','Atrium_Glass')):
            continue
        data=obj.data
        neighbors={v.index:set() for v in data.vertices}
        for edge in data.edges:
            a,b=edge.vertices;neighbors[a].add(b);neighbors[b].add(a)
        pending=set(neighbors);groups=[]
        while pending:
            seed=pending.pop();found={seed};stack=[seed]
            while stack:
                for other in neighbors[stack.pop()]:
                    if other in pending:pending.remove(other);found.add(other);stack.append(other)
            groups.append(sorted(found))
        maximum=0.0
        for ids in groups:
            if len(ids)!=8:raise RuntimeError(f'{obj.name}: pane component has {len(ids)} vertices')
            front=[data.vertices[i].co.copy() for i in ids[:4]]
            centre=sum(front,Vector())/4
            normal=(front[1]-front[0]).cross((front[2]+front[3])/2-(front[0]+front[1])/2).normalized()
            projected=[p-normal*(p-centre).dot(normal) for p in front]
            maximum=max(maximum,max((p-q).length for p,q in zip(front,projected)))
            for i,p in zip(ids[:4],projected):data.vertices[i].co=p
            for i,p in zip(ids[4:],projected):data.vertices[i].co=p-normal*.045
        bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free();data.update()
        obj['Pane_Construction']='Planar four-corner chord pane, 45mm physical slab, flat normals.'
        records.append({'name':obj.name,'panes':len(groups),'maximum_front_projection_m':maximum})
bpy.context.scene['Glass_Plane_Correction']='Planar chord panels replace twisted front quads; 45mm slab thickness.'
Path(bpy.data.filepath).with_name('glass_planarity_correction.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
print('GLASS_PLANARITY_REFINED',sum(r['panes'] for r in records),flush=True)
