import unreal as u
import json
from pathlib import Path

cloud = u.load_asset('/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst')
lib = u.MaterialEditingLibrary
report = {'cloud': {
    'scalar': {str(n): lib.get_material_instance_scalar_parameter_value(cloud, n) for n in lib.get_scalar_parameter_names(cloud)},
    'vector': [str(n) for n in lib.get_vector_parameter_names(cloud)],
    'texture': [str(n) for n in lib.get_texture_parameter_names(cloud)]}}
Path(u.Paths.project_dir()).parent.joinpath('Migration/render-asset-probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
u.log('OOW_RENDER_PROBE ' + json.dumps(report))
