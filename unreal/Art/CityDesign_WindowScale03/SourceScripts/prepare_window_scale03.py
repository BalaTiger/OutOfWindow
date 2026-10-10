"""Derive one explicitly authored candidate from the preserved editing script."""
from pathlib import Path
import json
import hashlib

root=Path(__file__).parent
text=(root/'build_curved_sample.py').read_text(encoding='utf-8')
def change(old,new):
    global text
    assert old in text,old
    text=text.replace(old,new)
change("CityDesign_Mall01\\CityDesign_Mall01.blend","CityDesign_WindowScale03\\CityDesign_WindowScale03_CHECKPOINT_BASE_ONLY.blend")
change("('Mall_Architecture','Neighbor_Architecture','Export_Architecture_Batched')","('Curved_A','Curved_B','Curved_Bridge','Curved_C','Curved_Site','Office_Corner','Export_Curved_Batched')")
change("collection('Office_Corner')","collection('Office_Window_Visible')")
change("bs=m.node_tree.nodes.get('Principled BSDF')", "bs=next((node for node in m.node_tree.nodes if node.type=='BSDF_PRINCIPLED'),None)\n    if bs is None:bs=m.node_tree.nodes.new('ShaderNodeBsdfPrincipled')\n    bs.name='Principled BSDF'\n    output=next((node for node in m.node_tree.nodes if node.type=='OUTPUT_MATERIAL'),None)\n    if output is None:output=m.node_tree.nodes.new('ShaderNodeOutputMaterial')\n    m.node_tree.links.new(bs.outputs['BSDF'],output.inputs['Surface'])")
change("(.69,.72,.71),.43,.20","(.61,.635,.62),.51,.06")
change("(.51,.55,.54),.53,.12","(.32,.35,.34),.66,.04")
change("(.055,.065,.065),.28,.65","(.15,.175,.18),.32,.55")
change("(.17,.22,.23),.12,0,.72","(.18,.225,.235),.17,0,.60")
change("(-54,5),(-54,12)],20)","(-54,5),(-54,12)],48)")
change("(-67,36),(-67,52)],24)","(-67,36),(-67,52)],48)")
start=text.index('profiles_A=');end=text.index('\ndef outline_at',start)
text=text[:start]+"""profiles_A=[(.14,1,1,0,0),(4.65,1,.995,-.10,.20),(8.80,.97,.985,-.35,.35),(12.95,.92,.96,-.70,.55),(17.10,.84,.89,-1.10,.80),(21.25,.73,.80,-1.70,1.25)]
profiles_B=[(.14,1,1,0,0),(4.65,1,1,-.10,0),(8.80,.99,.99,-.20,-.15),(13.15,.97,.96,-.40,-.30),(17.50,.93,.93,-.55,-.45),(21.85,.86,.87,-.65,-.65),(26.20,.76,.79,-.50,-1)]
"""+text[end:]
change("cross=[(-.65,-.35),(.64,-.35),(.92,-.24),(.96,1.13),(.76,1.25),(-.65,1.25)]","cross=[(-.25,-.19),(.25,-.19),(.39,-.14),(.39,.62),(.30,.70),(-.25,.70)]")
change("obj=mesh(name,v,f,material,True)\n    for edge in obj.data.edges:\n        if edge.vertices[0]//n", "obj=mesh(name,v,f,material,True)\n    obj.data.materials.append(soffit)\n    for polygon in obj.data.polygons:\n        if polygon.index//n in (0,5):polygon.material_index=1\n    for edge in obj.data.edges:\n        if edge.vertices[0]//n")
change("za=z+.58;zb=G+p2[0]-.37","za=z+.30;zb=G+p2[0]-.28")
change("lo,hi,za,zb,glass,2)","lo,hi,za,zb,glass,3 if letter=='A' else 2)")
change("lo,hi,za,zb,2)","lo,hi,za,zb,3 if letter=='A' else 2)")
change("width=5.4+3.0*(abs(2*t-1)**3)","width=4.4+1.8*(abs(2*t-1)**3)")
change("bridge_z=18.5","bridge_z=G+8.8")
change("bridge_z-.65-.65*math.sin(math.pi*t)**2,bridge_z+.15","bridge_z-.42-.12*math.sin(math.pi*t)**2,bridge_z+.12")
for old,new in [('4.60','3.65'),('4.94','3.95'),('1.25','0.65'),('4.15','3.52'),('4.90','3.95'),('4.14','3.51'),('4.16','3.53')]:
    # Restrict bridge height edits to the bridge section.
    start=text.index('left,right=bridge_sides');end=text.index('# C is intentionally',start)
    bridge=text[start:end].replace('bridge_z+'+old,'bridge_z+'+new)
    text=text[:start]+bridge+text[end:]
start=text.index('# Three typical floors');end=text.index('# Construction details',start)
text=text[:start]+"# Old isolated office trial is removed; detail the actual visible source buildings instead.\n"+text[end:]
change("G+p[0]-.19,G+p[0]+1.10,8,.012,.012,joint,-.967","G+p[0]-.10,G+p[0]+.57,8,.022,.035,joint,-.407")
for old,new in sorted([('PAVE+5.35','PAVE+4.12'),('PAVE+5.15','PAVE+3.90'),('PAVE+4.75','PAVE+2.75'),('PAVE+4.82','PAVE+2.82'),('PAVE+4.5','PAVE+3.9'),('PAVE+5.45','PAVE+4.12'),('PAVE+5.2','PAVE+3.90'),('PAVE+4.7','PAVE+2.80'),('PAVE+4.76','PAVE+2.86'),('PAVE+5.1','PAVE+3.90'),('PAVE+5.16','PAVE+3.96')],key=lambda pair:len(pair[0]),reverse=True):change(old,new)
change('terrace_z=G+16.6','terrace_z=G+17.10')
change('offset(aloops[3],.78),terrace_z+1.29','offset(aloops[-2],.30),terrace_z+.74')
change('offset(bloops[4],.78),G+21.6+1.29','offset(bloops[-2],.30),G+21.85+.74')
for old,new in [('G+20.81','G+21.31'),('G+21.75','G+22.20'),('G+20.97','G+21.47'),('G+21.60','G+22.05'),('G+26.66','G+26.26'),('G+28.0','G+27.60'),('G+26.91','G+26.51'),('G+27.75','G+27.35'),('PAVE+5.40','PAVE+3.92'),('PAVE+6.05','PAVE+4.55'),('PAVE+5.75','PAVE+4.05'),('PAVE+5.90','PAVE+4.20'),('PAVE+5.50','PAVE+4.02')]:change(old,new)
change("),.39,(math.pi/2,0,0))","),.78,(math.pi/2,0,0))")
start=text.index('def camera(');end=text.index('# Physical metre UV0',start)
text=text[:start]+"exec(Path(__file__).with_name('window_scale03_details.py').read_text(encoding='utf-8'),globals())\nscene.camera=bpy.data.objects['Review_Window_UE_VFOV54']\n\n"+text[end:]
change('# Physical metre UV0 and a separate packed UV1 for every editable part.',"bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'CityDesign_WindowScale03_geometry_checkpoint.blend'))\n# Physical metre UV0 and a separate packed UV1 for every editable part.")
change("        if obj.get('audit_role')=='lettering':", "        # New layers/edit-mode can invalidate RNA layer references; reacquire by name.\n        uv=obj.data.uv_layers['UVMap'];uv1=obj.data.uv_layers['LightmapUV']\n        if obj.get('audit_role')=='lettering':")
change("bridge_z-1.3-PAVE","bridge_z-.54-PAVE")
change("'A+B complete external design sample; one bridge/court; C skyline placeholder; B07 three-floor facade trial. Not finished city art.'","'Window-only scale/detail candidate; A+B and bridge redesigned; actual B07/B08/B13 facade details; C stored but hidden. Awaiting visual review.'")
change("'Original standard PBR colours; original City licensed context and linden preserved read-only.'","'Candidate PBR and source-office preview adaptation; original source materials/assets remain unchanged.'")
change("'Bridge curvature corrected after actual relationship images; entry, panel joints, columns and terrace details added; awaiting CPU pixel review.'","'New bounded geometry and actual-office details saved; fixed-window CPU preview pending.'")
change("OUT/'CityDesign_CurvedDistrict02.blend'","OUT/'CityDesign_WindowScale03.blend'")
(root/'build_window_scale03.py').write_text(text,encoding='utf-8')
project=Path(r'C:\Users\zhuzi\Documents\OutOfWindow');out=project/'unreal/Art/CityDesign_WindowScale03'
paths=[x['relative_path'] for x in json.loads((project/'unreal/Art/CityDesign_CurvedDistrict02/protected-baseline.json').read_text(encoding='utf-8-sig'))]
paths+=['unreal/Art/CityDesign_CurvedDistrict02/CityDesign_CurvedDistrict02.blend','unreal/Art/CityDesign_CurvedDistrict02/preview-window.png','unreal/Art/CityDesign_WindowScale03/CityDesign_WindowScale03_CHECKPOINT_BASE_ONLY.blend','unreal/OutOfWindow/Source/OutOfWindow/WindowDirector.cpp','unreal/OutOfWindow/Source/OutOfWindow/WindowDirector.h']
records=[{'relative_path':p,'sha256':hashlib.sha256((project/p).read_bytes()).hexdigest()} for p in paths]
(out/'protected-before-v3.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print('WINDOW_SCALE03_AUTHORED_SCRIPT_READY',len(text))
