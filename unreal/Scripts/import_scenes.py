"""Reproducible UE import. Run via UnrealEditor-Cmd -run=pythonscript.

The exported GLB already includes every world transform. UE's glTF translator
maps (x,y,z) metres to (x,z,y) centimetres; never apply the source wrapper twice.
"""
import json
import math
import os
from pathlib import Path
import unreal as u

def main():
    ROOT = Path(u.Paths.project_dir()).parent
    EXPORT = ROOT / 'Migration' / 'Exported'
    IDS = os.environ.get('OOW_IMPORT_SCENES', 'alley,city,village,forest,coast').split(',')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    meshes = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    report = []

    def vector(v):
        return u.Vector(v[0]*100, v[2]*100, v[1]*100)

    def spawn(cls, name, location=None):
        existing = next((a for a in actors.get_all_level_actors() if a.get_actor_label() == name), None)
        if existing:
            return existing
        actor = actors.spawn_actor_from_class(cls, location or u.Vector())
        actor.set_actor_label(name)
        actor.tags = [name]
        return actor

    for scene_id in IDS:
        title = scene_id.capitalize()
        source = EXPORT / (scene_id + '.glb')
        meta = json.loads((EXPORT / (scene_id + '.json')).read_text(encoding='utf-8'))
        map_path = '/Game/Maps/' + title
        create_or_load = levels.load_level if u.EditorAssetLibrary.does_asset_exist(map_path) else levels.new_level
        if not create_or_load(map_path):
            raise RuntimeError('Cannot create level ' + map_path)
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        params = u.ImportAssetParameters()
        params.is_automated = True
        params.replace_existing = True
        if not any(isinstance(a, u.StaticMeshActor) for a in actors.get_all_level_actors()):
            if not manager.import_scene('/Game/Scenes/' + title, manager.create_source_data(str(source)), params):
                raise RuntimeError('Interchange failed: ' + scene_id)
            u.EditorAssetLibrary.save_directory('/Game/Scenes/' + title)
            levels.save_current_level()
        u.log('OOW_IMPORTED ' + scene_id)
        metadata = {n['name']: n for n in meta['nodes']}
        static_meshes = set()
        imported_actors = 0
        for actor in actors.get_all_level_actors():
            if not isinstance(actor, u.StaticMeshActor):
                continue
            imported_actors += 1
            comp = actor.static_mesh_component
            comp.set_editor_property('mobility', u.ComponentMobility.STATIC)
            comp.set_editor_property('cast_shadow', True)
            comp.set_editor_property('visible_in_ray_tracing', True)
            mesh = comp.static_mesh
            if mesh:
                static_meshes.add(mesh)
            label = actor.get_actor_label()
            semantic = metadata.get(label)
            if not semantic:
                semantic = next((v for k,v in metadata.items() if label.startswith(k)), None)
            tags = ['OOWGeometry']
            if semantic:
                if semantic['car'] >= 0:
                    tags.append('OOWCar_' + str(semantic['car']))
                    comp.set_mobility(u.ComponentMobility.MOVABLE)
                if semantic['water']:
                    tags.append('OOWWater')
                if semantic['motion']:
                    tags.append('OOWWind')
            actor.tags = tags
        # Import without Nanite first; enable only compatible opaque/masked meshes.
        nanite_count = 0
        lod_count = 0
        for mesh in static_meshes:
            opaque = all(not slot.material_interface or slot.material_interface.get_blend_mode() in
                         (u.BlendMode.BLEND_OPAQUE, u.BlendMode.BLEND_MASKED)
                         for slot in mesh.static_materials)
            if opaque:
                settings = mesh.get_editor_property('nanite_settings')
                if not settings.enabled:
                    settings.enabled = True
                    meshes.set_nanite_settings(mesh, settings, True)
                nanite_count += 1
            else:
                settings = mesh.get_editor_property('nanite_settings')
                if settings.enabled:
                    settings.enabled = False
                    meshes.set_nanite_settings(mesh, settings, True)
                options = u.StaticMeshReductionOptions()
                options.auto_compute_lod_screen_size = False
                options.reduction_settings = [u.StaticMeshReductionSettings(percent_triangles=1.0, screen_size=1.0),
                    u.StaticMeshReductionSettings(percent_triangles=0.5, screen_size=0.35),
                    u.StaticMeshReductionSettings(percent_triangles=0.2, screen_size=0.1)]
                meshes.set_lods(mesh, options)
                lod_count += 1
        u.EditorAssetLibrary.save_directory('/Game/Scenes/' + title)
        levels.save_current_level()
        camera = spawn(u.CameraActor, 'OOWCamera', vector(meta['camera']['position']))
        target = vector(meta['camera']['target'])
        camera.set_actor_rotation(u.MathLibrary.find_look_at_rotation(camera.get_actor_location(), target), False)
        camera.camera_component.set_editor_property('constrain_aspect_ratio', False)
        camera.camera_component.set_editor_property('field_of_view', math.degrees(2*math.atan(math.tan(math.radians(meta['camera']['verticalFov']/2))*1280/820)))
        camera.tags = ['OOWCamera', 'VerticalFov_' + str(meta['camera']['verticalFov'])]
        for index, light in enumerate(meta.get('lights', [])):
            lamp = spawn(u.PointLight, 'OOWNightLight_' + str(index), vector(light['position']))
            lamp.tags = ['OOWNightLight']
            component = lamp.get_component_by_class(u.PointLightComponent)
            component.set_mobility(u.ComponentMobility.MOVABLE)
            component.set_editor_property('intensity_units', u.LightUnits.LUMENS)
            component.set_editor_property('intensity', 2500.0)
            component.set_editor_property('attenuation_radius', 1600.0)
            component.set_editor_property('source_radius', 8.0)
            component.set_light_color(u.LinearColor(*light['color'], 1.0))
        sun = spawn(u.DirectionalLight, 'OOWSun', u.Vector(0,0,5000))
        sun.set_actor_rotation(u.Rotator(-50, -40, 0), False)
        sun.light_component.set_mobility(u.ComponentMobility.MOVABLE)
        sun.get_component_by_class(u.DirectionalLightComponent).set_editor_property('atmosphere_sun_light', True)
        sun.light_component.set_editor_property('intensity', 65000.0)
        sun.tags = ['OOWSun', 'OOWSunSweep' if scene_id == 'alley' else
                    'OOWSunAzimuth_' + str({'city': -.58, 'village': -.32, 'forest': .42, 'coast': -.82}[scene_id])]
        sky = spawn(u.SkyLight, 'OOWSky')
        sky.light_component.set_mobility(u.ComponentMobility.MOVABLE)
        sky.light_component.set_editor_property('real_time_capture', True)
        spawn(u.SkyAtmosphere, 'OOWAtmosphere')
        fog = spawn(u.ExponentialHeightFog, 'OOWFog')
        fog.get_component_by_class(u.ExponentialHeightFogComponent).set_editor_property('fog_density',
            {'forest': .035, 'village': .020}.get(scene_id, .008))
        fog.get_component_by_class(u.ExponentialHeightFogComponent).set_editor_property('volumetric_fog_distance', 35000.0)
        fog.get_component_by_class(u.ExponentialHeightFogComponent).set_editor_property('enable_volumetric_fog', True)
        cloud = spawn(u.VolumetricCloud, 'OOWCloud')
        cloud.get_component_by_class(u.VolumetricCloudComponent).set_editor_property('material', u.load_asset('/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst'))
        post = spawn(u.PostProcessVolume, 'OOWPostProcess')
        post.set_editor_property('unbound', True)
        settings = post.get_editor_property('settings')
        settings.set_editor_property('override_auto_exposure_min_brightness', True)
        settings.set_editor_property('override_auto_exposure_max_brightness', True)
        settings.set_editor_property('auto_exposure_min_brightness', -4.0)
        settings.set_editor_property('auto_exposure_max_brightness', 16.0)
        settings.set_editor_property('override_auto_exposure_bias', True)
        settings.set_editor_property('auto_exposure_bias', -.5)
        post.set_editor_property('settings', settings)
        u.EditorAssetLibrary.save_directory('/Game/Scenes/' + title)
        levels.save_current_level()
        report.append({'scene':scene_id, 'map':map_path, 'actors':imported_actors,
                       'uniqueMeshes':len(static_meshes), 'naniteMeshes':nanite_count, 'traditionalLodMeshes':lod_count})
        (ROOT / 'Migration' / ('import-' + scene_id + '.json')).write_text(json.dumps(report[-1],indent=2), encoding='utf-8')
        u.log('OOW_SCENE_COMPLETE ' + json.dumps(report[-1]))

    u.log('OOW_IMPORT_COMPLETE ' + json.dumps(report))


if __name__ == '__main__':
    main()
    import gc
    gc.collect()
