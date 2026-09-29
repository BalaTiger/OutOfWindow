"""Add three local dry runoff deposits; never overwrite the wet roughness/normal.

Run after build_alley_weathering.py in an Unreal Python commandlet. Positions are
ray-tested against the exported Alley triangles, not estimated from actor pivots.
"""
import hashlib
import json
from pathlib import Path
import sys

DEST = '/Game/Materials/OOW/AlleyWeathering'
WALL = 'OOW_00759_paris_building_09_7'
NORMAL = (.736333, .676619, 0.)
# Centre in UE centimetres, full projected width and height in centimetres.
SITES = [
    ('OOWWeatheringDecal_BalconyA', (-2613.13429, -22203.58122, 2185.37778), (90., 44.)),
    ('OOWWeatheringDecal_BalconyB', (-2244.07259, -22665.06164, 2172.23968), (90., 42.)),
    ('OOWWeatheringDecal_UpperWall', (-2603.33545, -22195.09661, 2701.62429), (75., 28.)),
]


def main():
    import unreal as u
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_surface_materials as surfaces
    surfaces.u, surfaces.mel = u, u.MaterialEditingLibrary
    mel = u.MaterialEditingLibrary
    root = Path(u.Paths.project_dir()).parent
    report_path = root / 'Migration/alley-weathering-decals.json'
    report = {'passed': False, 'kind': 'dry color-only DBuffer deposits', 'actors': [], 'failures': []}
    try:
        levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
        if not levels.load_level('/Game/Maps/Alley'):
            raise RuntimeError('Cannot load Alley')
        actor_editor = u.get_editor_subsystem(u.EditorActorSubsystem)
        actors = {a.get_actor_label(): a for a in actor_editor.get_all_level_actors()}
        wall = actors[WALL]
        assert all(c.get_editor_property('receives_decals') for c in wall.get_components_by_class(u.StaticMeshComponent))
        source = root / 'Art/AlleyWeathering/runoff-mask.png'
        assert source.is_file(), 'Missing generated runoff opacity mask'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        texture_folder = DEST + '/Textures/R_' + digest[:10]
        texture_path = texture_folder + '/runoff-mask'
        texture = u.load_asset(texture_path) if u.EditorAssetLibrary.does_asset_exist(texture_path) else None
        if texture is None:
            manager = u.InterchangeManager.get_interchange_manager_scripted()
            params = u.ImportAssetParameters()
            params.is_automated, params.replace_existing = True, False
            imported = manager.import_asset(texture_folder, manager.create_source_data(str(source)), params)
            texture = next((a for a in (imported or []) if isinstance(a, u.Texture2D)), None)
        assert isinstance(texture, u.Texture2D), 'Runoff mask import failed'
        texture.set_editor_property('srgb', False)
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_MASKS)
        texture.set_editor_property('address_x', u.TextureAddress.TA_CLAMP)
        texture.set_editor_property('address_y', u.TextureAddress.TA_CLAMP)
        texture.set_editor_property('power_of_two_mode', u.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO)
        texture.set_editor_property('max_texture_size', 1024)
        texture.set_editor_property('virtual_texture_streaming', False)
        u.EditorAssetLibrary.save_loaded_asset(texture)

        material_name = 'M_DryRunoff_v2_' + digest[:10]
        path = DEST + '/' + material_name
        material = u.load_asset(path)
        if material is None:
            material = u.AssetToolsHelpers.get_asset_tools().create_asset(material_name, DEST, u.Material, u.MaterialFactoryNew())
            assert material
            material.set_editor_property('material_domain', u.MaterialDomain.MD_DEFERRED_DECAL)
            material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
            graph = surfaces.Graph(material)
            coord = graph.node(u.MaterialExpressionTextureCoordinate)
            # UE decal UV=(local Z, local Y); remap image V to world down.
            uv = graph.custom('return float3(U.y,1.-U.x,0.);', {'U': coord}, True)
            uv_mask = graph.node(u.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
            graph.connect(uv, uv_mask, '')
            sample = graph.node(u.MaterialExpressionTextureSampleParameter2D,
                                parameter_name='RunoffMask', texture=texture,
                                sampler_type=u.MaterialSamplerType.SAMPLERTYPE_MASKS)
            graph.connect(uv_mask, sample, '')
            opacity = graph.custom('return saturate(pow(saturate(M),.7)*Strength);',
                                   {'M': (sample[0], 'R'), 'Strength': graph.scalar('DepositStrength', .32)})
            graph.output(opacity, u.MaterialProperty.MP_OPACITY)
            graph.output(graph.vector((.15, .145, .125)), u.MaterialProperty.MP_BASE_COLOR)
            # Only connected attributes are written to the DBuffer. Leaving normal,
            # roughness, metallic and specular disconnected preserves dynamic rain.
            mel.recompile_material(material)
            surfaces.finish(material, recipe='dry-runoff-v2')
        for prop in (u.MaterialProperty.MP_NORMAL, u.MaterialProperty.MP_ROUGHNESS,
                     u.MaterialProperty.MP_SPECULAR, u.MaterialProperty.MP_METALLIC):
            assert mel.get_material_property_input_node(material, prop) is None
        direction = u.Vector(*(-v for v in NORMAL))
        rotation = u.MathLibrary.make_rot_from_x(direction)
        for name, centre, size in SITES:
            centre = tuple(value + .25 * NORMAL[i] for i, value in enumerate(centre))
            actor = actors.get(name)
            if actor is None:
                actor = actor_editor.spawn_actor_from_class(u.DecalActor, u.Vector(*centre), rotation)
                actor.set_actor_label(name)
            assert isinstance(actor, u.DecalActor)
            actor.set_actor_location(u.Vector(*centre), False, False)
            actor.set_actor_rotation(rotation, False)
            actor.tags = ['OOWWeatheringDecal', 'OOWDryDeposit']
            component = actor.get_component_by_class(u.DecalComponent)
            component.set_decal_material(material)
            # Two-centimetre half-depth clips away balcony fronts and other walls.
            component.set_editor_property('decal_size', u.Vector(2., size[0] * .5, size[1] * .5))
            component.set_fade_screen_size(.001)
            component.set_sort_order(20)
            report['actors'].append({'actor': name, 'wall': WALL, 'centreCm': centre,
                                     'normal': NORMAL, 'sizeCm': size, 'halfDepthCm': 2.})
        assert levels.save_current_level(), 'Could not save Alley decals'
        report.update(passed=True, sourceHash=digest, texture=texture.get_path_name(), material=material.get_path_name())
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        u.log('OOW_ALLEY_DECALS ' + json.dumps(report))


if __name__ == '__main__':
    main()
