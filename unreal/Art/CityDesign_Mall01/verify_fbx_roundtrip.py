"""Read FBX in a temporary background scene and audit its normalized metre geometry."""
import bpy
import sys
import runpy
from pathlib import Path

out=Path(sys.argv[sys.argv.index('--')+1])
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.unit_settings.scale_length=1
scene.unit_settings.length_unit='METERS'
bpy.ops.import_scene.fbx(filepath=str(out/'CityDesign_Mall01_Architecture.fbx'),use_image_search=False)
for name,label in (('Mall_Architecture','OOW_Mall01_Architecture'),
                   ('Neighbor_Architecture','OOW_Neighbor01_Architecture')):
    collection=bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    objects=[obj for obj in scene.objects if obj.type=='MESH' and obj.name.startswith(label)]
    assert len(objects)==1,(label,len(objects))
    obj=objects[0]
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)
sys.argv=['validate_city_sample.py','--',str(out/'validation-fbx.json')]
runpy.run_path(str(out/'validate_city_sample.py'),run_name='__main__')
print('FBX_TEMP_SCENE_AUDITED_NO_BLEND_SAVE',flush=True)
