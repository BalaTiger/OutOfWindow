"""Verify actual saved design heights, invariant human fittings and fixed-camera pitch."""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

out=Path(sys.argv[sys.argv.index('--')+1]);scene=bpy.context.scene;camera=scene.camera
PAVE=7.04
expected={'A':[7.04,13.04,18.54,24.04,29.54,35.04],
          'B':[7.04,13.04,18.54,24.04,29.54,35.04,40.54]}
old={'A':[7.04,11.55,15.70,19.85,24.00,28.15],
     'B':[7.04,11.55,15.70,20.05,24.40,28.75,33.10]}
errors=[];floors={};bands={}


def bounds(obj):
    points=[obj.matrix_world@vertex.co for vertex in obj.data.vertices]
    return {'min':[min(point[i] for point in points) for i in range(3)],
            'max':[max(point[i] for point in points) for i in range(3)]}


for letter,levels in expected.items():
    actual=[];band_heights=[]
    for index,z in enumerate(levels):
        b=bounds(bpy.data.objects[f'{letter}_L{index}_FloorPlate_OpenAtrium'])
        actual.append(b['max'][2])
        if abs(actual[-1]-z)>1e-4:errors.append(f'{letter} floor{index} FF mismatch')
        b=bounds(bpy.data.objects[f'{letter}_L{index}_Continuous_Curved_Band'])
        height=b['max'][2]-b['min'][2];band_heights.append(height)
        if abs(height-.89)>1e-4:errors.append(f'{letter} band{index} physical thickness changed')
    floors[letter]={'absolute_FF_m':actual,'floor_to_floor_m':[actual[i+1]-actual[i] for i in range(len(actual)-1)],
        'main_roof_above_entry_PAVE_m':actual[-1]-PAVE,
        'previous_main_roof_above_entry_PAVE_m':old[letter][-1]-PAVE,
        'roof_height_growth_ratio':(actual[-1]-PAVE)/(old[letter][-1]-PAVE),
        'service_top_above_entry_PAVE_m':bounds(bpy.data.objects[letter+'_Roof_Service_Screen'])['max'][2]-PAVE}
    bands[letter]=band_heights

office_previous=Path(r'C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\CityDesign_WindowScale03\export_manifest.json')
previous={record['name']:record for record in json.loads(office_previous.read_text(encoding='utf-8'))['proxy_meshes']}
offices=[]
for code in ('B07','B08','B13'):
    name='OOW_View_Office_'+code;b=bounds(bpy.data.objects[name]);p=previous[name]
    delta=max(abs(b[key][i]-p['world_bounds_blender_m'][key][i]) for key in ('min','max') for i in range(3))
    bpy.data.objects[name].data.calc_loop_triangles()
    triangles=len(bpy.data.objects[name].data.loop_triangles)
    if delta>1e-4 or triangles!=p['triangles']:errors.append(name+' mass/count changed against v3')
    offices.append({'name':name,'world_bounds_m':b,'maximum_bounds_delta_from_v3_m':delta,'triangles':triangles})

doors=[]
for index in range(4):
    name=f'A_MainEntry_Door{index}';b=bounds(bpy.data.objects[name]);head=b['max'][2]-PAVE
    panel=b['max'][2]-b['min'][2]
    if abs(head-2.78)>1e-4 or abs(panel-2.76)>1e-4:errors.append(name+' human scale changed')
    doors.append({'name':name,'head_above_FF_m':head,'panel_height_m':panel})
if max(abs(camera.location[i]-[26,-42,37][i]) for i in range(3))>1e-5:errors.append('Camera position changed')
vfov=math.degrees(2*math.atan(camera.data.sensor_height/(2*camera.data.lens)))
if abs(vfov-54)>1e-3 or camera.data.sensor_fit!='VERTICAL':errors.append('Camera FOV/sensor fit changed')

pitch={}
for letter,x,y in [('A',-26,5),('B',-30,44)]:
    values={}
    for label,levels in [('v3',old[letter]),('v4',expected[letter])]:
        ys=[(1-world_to_camera_view(scene,camera,Vector((x,y,z))).y)*1440 for z in levels]
        values[label]={'screen_FF_y_px':ys,'floor_pitch_px':[ys[i]-ys[i+1] for i in range(len(ys)-1)]}
    pitch[letter]={'same_world_xy_probe':[x,y],'resolution':[2560,1440],**values,
        'meaning':'Analytical fixed-camera projection at same XY, not an occlusion-aware facade pixel mask; actual image reviewed separately.'}
bridge=scene['Bridge_Deck_Absolute_Z_m']
clearance=scene['Bridge_Min_Clearance_Above_Pavement_m']
if abs(bridge-18.54)>1e-4 or abs(clearance-10.96)>1e-4:errors.append('Bridge level/clearance mismatch')
bridge_bounds=bounds(bpy.data.objects['Bridge_Upper_Curved_Roof'])
deck_bounds=bounds(bpy.data.objects['Bridge_Closed_Arched_Soffit_and_Deck'])
if abs(deck_bounds['max'][2]-18.54)>1e-4:errors.append('Actual bridge walking surface differs from commercial floor')
if abs(bridge_bounds['max'][2]-bridge-3.95)>1e-4:errors.append('Bridge cabin stretched')

report={'status':'FAIL' if errors else 'PASS','scope':'Commercial-specific physical dimensions, unchanged office bounds and human details; fixed-camera mathematical pitch.',
    'floors':floors,'ordinary_band_heights_m':bands,'main_entry_doors':doors,'offices_vs_v3':offices,
    'bridge':{'deck_reference_absolute_m':bridge,'actual_walking_surface_absolute_m':deck_bounds['max'][2],'underdeck_clearance_above_pavement_m':clearance,'upper_roof_top_over_deck_m':3.95,'same_level':'A_L2 and B_L2'},
    'camera':{'name':camera.name,'position':list(camera.location),'VFOV_deg':vfov,'fixed':True},
    'fixed_camera_pitch_comparison':pitch,'errors':errors,
    'limitations':['Layer height is floor-to-floor, not a promised finished ceiling clear height.',
        'Matching office bounds/count does not prove byte-identical mesh ordering.',
        'This does not validate construction, load paths, accessibility or UE placement.',
        'Projected floor pitch is not image segmentation or visual approval.']}
(out/'commercial_scale_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('COMMERCIAL_SCALE04_PHYSICAL_AUDIT',report['status'],flush=True)
if errors:raise RuntimeError('; '.join(errors))
