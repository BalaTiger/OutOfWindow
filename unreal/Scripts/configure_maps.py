"""Apply scene-authored lighting metadata without repeating geometry import."""
import gc
import json
from pathlib import Path
import unreal as u

def main():
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    for scene, azimuth in [('alley', None), ('city', -.58), ('village', -.32), ('forest', .42), ('coast', -.82)]:
        if not levels.load_level('/Game/Maps/' + scene.capitalize()):
            raise RuntimeError('Missing map ' + scene)
        for actor in actors.get_all_level_actors():
            if actor.get_actor_label() == 'OOWSun':
                actor.tags = ['OOWSun', 'OOWSunSweep' if azimuth is None else 'OOWSunAzimuth_' + str(azimuth)]
            elif actor.get_actor_label() == 'OOWFog':
                actor.get_component_by_class(u.ExponentialHeightFogComponent).set_editor_property(
                    'fog_density', {'forest': .035, 'village': .020}.get(scene, .008))
            elif actor.get_actor_label() == 'OOWPostProcess':
                settings = actor.get_editor_property('settings')
                settings.set_editor_property('override_auto_exposure_bias', True)
                settings.set_editor_property('auto_exposure_bias', -.5)
                actor.set_editor_property('settings', settings)
        source = Path(u.Paths.project_dir()).parent / 'Migration' / 'Exported' / (scene + '.json')
        if source.exists():
            meta = json.loads(source.read_text(encoding='utf-8'))
            existing = {actor.get_actor_label(): actor for actor in actors.get_all_level_actors()}
            for index, light in enumerate(meta.get('lights', [])):
                name = 'OOWNightLight_' + str(index)
                x, y, z = light['position']
                lamp = existing.get(name) or actors.spawn_actor_from_class(u.PointLight, u.Vector(x*100, z*100, y*100))
                lamp.set_actor_label(name)
                lamp.tags = ['OOWNightLight']
                component = lamp.get_component_by_class(u.PointLightComponent)
                component.set_mobility(u.ComponentMobility.MOVABLE)
                component.set_editor_property('intensity_units', u.LightUnits.LUMENS)
                component.set_editor_property('intensity', 2500.0)
                component.set_editor_property('attenuation_radius', 1600.0)
                component.set_editor_property('source_radius', 8.0)
                component.set_light_color(u.LinearColor(*light['color'], 1.0))
        if not levels.save_current_level():
            raise RuntimeError('Could not save ' + scene)
        u.log('OOW_MAP_CONFIGURED ' + scene)

if __name__ == '__main__':
    main()
    gc.collect()
