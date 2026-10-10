"""Prepare a separate commercial-specific revision from explicit authored parts."""
from pathlib import Path
import hashlib
import json
import re
import shutil

root=Path(__file__).parent
project=Path(r'C:\Users\zhuzi\Documents\OutOfWindow')
previous=project/'unreal/Art/CityDesign_WindowScale03'
out=project/'unreal/Art/CityDesign_CommercialScale04'
out.mkdir(exist_ok=True)
paths=[record['relative_path'] for record in json.loads((previous/'protected-before-v3.json').read_text(encoding='utf-8'))]
paths.extend(path.relative_to(project).as_posix() for path in previous.rglob('*') if path.is_file())
paths=sorted(set(paths))
baseline=out/'protected-before-v4.json'
if baseline.exists():
    raise RuntimeError('Do not overwrite the v4 protection baseline; use the already prepared scripts.')
baseline.write_text(json.dumps([{'relative_path':name,'sha256':hashlib.sha256((project/name).read_bytes()).hexdigest()} for name in paths],indent=2),encoding='utf-8')
shutil.copy2(previous/'CityDesign_WindowScale03_CHECKPOINT_BASE_ONLY.blend',out/'CityDesign_CommercialScale04_CHECKPOINT_BASE_ONLY.blend')

source=(root/'build_window_scale03.py').read_text(encoding='utf-8').replace('WindowScale03','CommercialScale04')
source=source.replace('window_scale03_details.py','commercial_scale04_details.py')
def change(old,new):
    global source
    assert old in source,old
    source=source.replace(old,new)
change("a_outline=bezier([(-54,12),(-54,23),(-46,28),(-40,27),(-35,27),(-33.5,24.5),(-34,21),(-34,17),(-26,13),(-25,6),(-24.5,-1),(-34,-3),(-43,-1),(-50,0),(-54,5),(-54,12)],48)",
       "a_outline=bezier([(-60,12),(-60,23),(-49,28),(-40,27),(-35,27),(-33.5,24.5),(-34,21),(-34,17),(-26,13),(-25,6),(-24.5,-3),(-36,-7),(-47,-5),(-56,-3),(-60,5),(-60,12)],48)")
change("b_outline=bezier([(-67,52),(-67,64),(-58,69),(-48,68),(-39,67),(-29,61),(-29,51),(-29,43),(-35,35),(-43,34),(-49,33),(-67,36),(-67,52)],48)",
       "b_outline=bezier([(-74,52),(-74,64),(-62,69),(-48,68),(-39,67),(-29,61),(-29,51),(-29,43),(-35,35),(-43,34),(-52,33),(-74,36),(-74,52)],48)")
source=re.sub(r'profiles_A=\[[^\n]+',"profiles_A=[(.14,1,1,0,0),(6.14,1,.995,-.10,.20),(11.64,.97,.985,-.35,.35),(17.14,.92,.96,-.70,.55),(22.64,.84,.89,-1.10,.80),(28.14,.73,.80,-1.70,1.25)]",source,count=1)
source=re.sub(r'profiles_B=\[[^\n]+',"profiles_B=[(.14,1,1,0,0),(6.14,1,1,-.10,0),(11.64,.99,.99,-.20,-.15),(17.14,.97,.96,-.40,-.30),(22.64,.93,.93,-.55,-.45),(28.14,.86,.87,-.65,-.65),(33.64,.76,.79,-.50,-1)]",source,count=1)
change('bridge_z=G+8.8','bridge_z=G+11.64')
change('bridge_z+.12,white)','bridge_z,white)')
change("if k==0:transom(f'{letter}_L{k}_Retail_Transom',lo,za+3.05)",
       "if k==0:transom(f'{letter}_L{k}_Retail_Transom',lo,za+3.05)\n            else:transom(f'{letter}_L{k}_Vision_Clerestory_Rail',lerp_loop(lo,hi,.62),za+3.05)")
for old,new in [('G+17.10','G+22.64'),('G+21.31','G+28.20'),('G+22.20','G+29.09'),('G+21.47','G+28.36'),('G+22.05','G+28.94'),('G+26.26','G+33.70'),('G+27.60','G+35.04'),('G+26.51','G+33.95'),('G+27.35','G+34.79'),('G+21.85','G+28.14')]:
    change(old,new)
change("transom('A_Terrace_Metal_Coping',offset(aloops[-2],.30),terrace_z+.74,frame)",
       "transom('A_Terrace_Metal_Coping',offset(aloops[-2],.30),terrace_z+1.10,frame)\npane_components('A_Terrace_Clear_Parapet_1100mm',offset(aloops[-2],.28),offset(aloops[-2],.28),terrace_z+.70,terrace_z+1.10,glass,3,0)")
change("transom('B_Terrace_Metal_Coping',offset(bloops[-2],.30),G+28.14+.74,frame)",
       "transom('B_Terrace_Metal_Coping',offset(bloops[-2],.30),G+28.14+1.10,frame)\npane_components('B_Terrace_Clear_Parapet_1100mm',offset(bloops[-2],.28),offset(bloops[-2],.28),G+28.14+.70,G+28.14+1.10,glass,2,0)")
change("'Window-only scale/detail candidate; A+B and bridge redesigned; actual B07/B08/B13 facade details; C stored but hidden. Awaiting visual review.'", "'Commercial-specific scale candidate: first floor 6.0m, standard retail 5.5m; broader A/B; bridge at corresponding commercial L2; actual offices unchanged in mass.'")
change("'New bounded geometry and actual-office details saved; fixed-window CPU preview pending.'", "'Commercial heights selected from primary engineering/architectural evidence; fixed-window preview pending.'")
(root/'build_commercial_scale04.py').write_text(source,encoding='utf-8')
mapping={'window_scale03_details.py':'commercial_scale04_details.py','refine_window_scale03.py':'refine_commercial_scale04.py','export_window_scale03.py':'export_commercial_scale04.py','verify_window_scale03_fbx.py':'verify_commercial_scale04_fbx.py','render_window_scale03.py':'render_commercial_scale04.py'}
for old,new in mapping.items():
    text=(root/old).read_text(encoding='utf-8').replace('WindowScale03','CommercialScale04').replace('WINDOW_SCALE03','COMMERCIAL_SCALE04')
    if old=='render_window_scale03.py':
        text=text[:text.index("if phase=='draft':")]
    (root/new).write_text(text,encoding='utf-8')

evidence={'choice':'First commercial floor 6.0m; standard floors 5.5m, measured floor-to-floor. Not an office-derived common grid.',
 'sources':[
  {'title':'RBS designers: Zhuhai large-chassis twin-tower commercial podium','url':'https://pdf.hanspub.org/hjce20170600000_33611064.pdf','location':'PDF p2, engineering overview','commercial_floor_to_floor_m':[6.0,5.5,5.75,5.5,5.5],'commercial_roof_m':28.25,'same_project_office_floor_to_floor_m':4.2,'same_project_apartment_floor_to_floor_m':3.3,'use':'Primary engineering evidence for selected 6.0/5.5m sample. Not a compulsory design rule.'},
  {'title':'Marrickville Metro architectural report, NSW planning archive','url':'https://dpeeplanningsitbackdata.blob.core.windows.net/pdfmapsdata/assets/55243/Architectural%2520Report%2520Part%25203.pdf','retail_floor_to_floor_m':5.4,'use':'Independent commercial scale cross-check; parameters belong to that project.'},
  {'title':'SOHO official Galaxy C B01 shop delivery listing','url':'https://www.sohochinaoffice.com/room/70915?lang=zch','published_standard_height_m':5.4,'use':'Official commercial-unit example, basement only; cannot imply all Galaxy floors share this value.'},
  {'title':'ZHA Galaxy SOHO project','url':'https://www.zha.com/projects/architecture/galaxy-soho','fact':'Lower three levels retail/entertainment; offices above; top restaurants and cafes. No dimensional floor-height schedule on this page.'},
  {'title':'Published section credited to ZHA','url':'https://www.metalocus.es/sites/default/files/styles/mopis_news_carousel_item_desktop/public/metalocus_zahahadid_beijing_37.jpg?itok=mIKr4ibk','actual_pixels_viewed':[1530,1100],'use':'Lower commercial intervals exceed office intervals; bridge matches floor slabs. No readable dimension scale; never used to derive exact metres.'}
 ],
 'old_v3_actual_above_PAVE_m':{'A':{'first':4.51,'standard':[4.15],'main_roof':21.11,'service_top':22.06},'B':{'first':4.51,'standard':[4.15,4.35],'main_roof':26.06,'service_top':27.46},'office_standard':[3.30,3.7167,3.2923,3.2667]},
 'new_design_above_PAVE_m':{'A':{'first':6.0,'standard':5.5,'occupied_floors':5,'main_roof':28.0},'B':{'first':6.0,'standard':5.5,'occupied_floors':6,'main_roof':33.5}},
 'physical_small_details':'Door panels2.78m, handles, frame sections, band0.89m, guardrails and furniture retain physical dimensions; no uniform XYZ scaling.',
 'scope':'Broaden two finite mall footprints west/near/rear only; retain road-side interfaces and fixed camera. No whole-city growth, UE or deployment.'}
(out/'commercial_height_evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print('COMMERCIAL_SCALE04_PREPARED',len(source),'protected_files',len(paths))
