"""Update City lighting and precipitation without reimporting its geometry."""
import json
from pathlib import Path
import runpy
import sys
import unreal as u

ROOT = Path(u.Paths.project_dir()).parent
sys.path.insert(0, str(ROOT / 'Scripts'))
import build_city_lookdev as city


def main():
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    if not levels.load_level('/Game/Maps/City'):
        raise RuntimeError('Cannot load City')
    metadata = json.loads((city.ART / 'modern-city.json').read_text(encoding='utf-8'))
    for spec in city.document(city.ART / 'modern-city.glb')['materials']:
        if spec['name'] in city.DISTANT_GLASS:
            city.material(spec)
    lighting = city.build_street_lighting(metadata)
    if not levels.save_current_level():
        raise RuntimeError('Cannot save City lighting')
    path = ROOT / 'Migration/city-modern-build.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    report['streetLighting'] = lighting
    report['nightLights'] = lighting['count']
    report['distantLighting'] = {'version': city.DISTANT_LIGHTING_VERSION,
                                 'gain': city.DISTANT_LIGHT_GAIN,
                                 'materials': sorted(city.DISTANT_GLASS)}
    report['actorsSaved'] = len(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    runpy.run_path(str(ROOT / 'Scripts/build_precipitation.py'), run_name='__main__')
    from audit_city_lookdev import main as audit_saved_city
    audit_saved_city()
    u.log('OOW_CITY_NIGHT_WEATHER_COMPLETE')


if __name__ == '__main__':
    main()
