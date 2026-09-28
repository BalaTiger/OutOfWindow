"""Rebuild only City: modern boulevard, roadside camera, real trees and traffic.

Run after the legacy import/material steps. Source geometry is in Art/City.
The desktop frame belongs to AWindowFrame, never to this map.
"""
import json
import hashlib
import math
from pathlib import Path
import struct
import sys
import unreal as u

ROOT = Path(u.Paths.project_dir()).parent
ART = ROOT / 'Art' / 'City'
DEST = '/Game/Scenes/City/Modern'
sys.path.insert(0, str(ROOT / 'Scripts'))
import build_surface_materials as surface
surface.u, surface.mel = u, u.MaterialEditingLibrary
surface.masters, surface.instances, surface.probes = {}, {}, {}
surface.interior_textures = None
tree_textures = {}
facade_textures = {}
FACADE_VERSION = 'city-facade-v1'
NIGHT_LIGHTING_VERSION = 'city-office-light-v1'
OFFICE_LIGHT_GAIN = .065
OFFICE_GLASS = {'CityModern_Hero_Glass', 'CityModern_Glass_Day_Blue',
                'CityModern_Glass_Day_Silver', 'Glass_Lit_CityModern_Warm'}
from batch_city_geometry import batch_city_geometry
from import_city_sidewalk import import_sidewalk, import_entrances, REPLACED_ROADS
from build_city_roads import build_roads, REMOVED_ROADS
from city_distant_lighting import (DISTANT_GLASS, DISTANT_LIGHTING_VERSION,
                                  DISTANT_LIGHT_GAIN, apply_distant_lighting)


def document(path):
    with path.open('rb') as stream:
        stream.seek(12)
        size, kind = struct.unpack('<II', stream.read(8))
        assert kind == 0x4E4F534A
        return json.loads(stream.read(size))


def import_facade_textures():
    """Keep source PBR maps untouched; import only the three channels in use."""
    for channel in ('Color', 'Roughness', 'NormalDX'):
        source = ART / 'Facade' / ('Travertine001_2K-JPG_' + channel + '.jpg')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        name = source.stem
        texture = u.load_asset(DEST + '/FacadeTextures/' + name)
        if not texture or str(u.EditorAssetLibrary.get_metadata_tag(texture, 'OOWSourceHash')) != digest:
            manager = u.InterchangeManager.get_interchange_manager_scripted()
            params = u.ImportAssetParameters()
            params.is_automated, params.replace_existing = True, True
            imported = manager.import_asset(DEST + '/FacadeTextures', manager.create_source_data(str(source)), params)
            texture = next((a for a in imported if isinstance(a, u.Texture2D)), None)
        assert texture, source
        texture.set_editor_property('srgb', channel == 'Color')
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_NORMALMAP if channel == 'NormalDX'
                                    else u.TextureCompressionSettings.TC_DEFAULT if channel == 'Color' else u.TextureCompressionSettings.TC_MASKS)
        texture.set_editor_property('virtual_texture_streaming', False)
        texture.set_editor_property('address_x', u.TextureAddress.TA_WRAP)
        texture.set_editor_property('address_y', u.TextureAddress.TA_WRAP)
        u.EditorAssetLibrary.set_metadata_tag(texture, 'OOWSourceHash', digest)
        u.EditorAssetLibrary.save_loaded_asset(texture)
        facade_textures[channel] = texture


def stone_surface(g, wet, pale):
    """Metre-scaled planar PBR on the dominant face, including narrow trim."""
    p = u.MaterialProperty
    position, normal = g.position(), g.node(u.MaterialExpressionVertexNormalWS)
    plane = g.custom('float3 a=abs(N); return a.z>.7?float3(P.xy*.01,0):'
                     'a.x>a.y?float3(P.yz*.01,0):float3(P.xz*.01,0);',
                     {'P': position, 'N': normal}, True, 'City stone coordinates in metres')
    uv = g.custom('return Q/1.2;', {'Q': plane}, True)
    uv_xy = g.node(u.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
    g.connect(uv, uv_xy, '')
    samples = {}
    for channel, parameter, sampler in (
            ('Color', 'CityStoneColor', u.MaterialSamplerType.SAMPLERTYPE_COLOR),
            ('Roughness', 'CityStoneRoughness', u.MaterialSamplerType.SAMPLERTYPE_MASKS),
            ('NormalDX', 'CityStoneNormal', u.MaterialSamplerType.SAMPLERTYPE_NORMAL)):
        sample = g.node(u.MaterialExpressionTextureSampleParameter2D, parameter_name=parameter,
                        texture=facade_textures[channel], sampler_type=sampler)
        g.connect(uv_xy, sample, 'UVs')
        samples[channel] = (sample[0], 'RGB')
    # Antialias the 1.2 x .6 m panel joints so thin distant trim does not shimmer.
    joint = g.custom('float2 q=Q.xy/float2(1.2,.6); float2 d=min(frac(q),1.-frac(q)); '
                     'float2 aa=max(fwidth(q),.0001); '
                     'float2 edge=1.-smoothstep(float2(.0016,.0032),float2(.0016,.0032)+aa,d); '
                     'return saturate(max(edge.x,edge.y));', {'Q': plane})
    g.output(g.custom('float grey=dot(C,float3(.2126,.7152,.0722)); '
                      'return lerp(C,grey.xxx,.58)*Tint*lerp(1.,.72,J)*lerp(1.,.82,saturate(W));',
                      {'C': samples['Color'], 'Tint': g.vector((1.04, 1.07, 1.09) if pale else (1.04, 1., .94)),
                       'J': joint, 'W': wet}, True), p.MP_BASE_COLOR)
    g.output(g.custom('return lerp(clamp(.48+R.r*.35,.5,.85),.36,saturate(W));',
                      {'R': samples['Roughness'], 'W': wet}), p.MP_ROUGHNESS)
    g.material.set_editor_property('tangent_space_normal', False)
    g.output(g.custom('float3 n=normalize(N); float3 a=abs(n); '
                      'float3 t=a.z>.7?float3(1,0,0):a.x>a.y?float3(0,1,0):float3(1,0,0); '
                      'float3 b=a.z>.7?float3(0,1,0):float3(0,0,1); '
                      'return normalize(n+(t*Map.x+b*Map.y)*.26);',
                      {'N': normal, 'Map': samples['NormalDX']}, True), p.MP_NORMAL)


def hero_glass_surface(g, wet, night):
    """Opaque coated-glass approximation: external reflection, no room image."""
    p = u.MaterialProperty
    uv = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=0)
    seed = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=1)
    # Each pane's UV1 seed is constant: colour/roughness never speckle per pixel.
    g.output(g.custom('float k=frac(S.x*73.137+.11); '
                      'return float3(.027,.049,.062)*lerp(.88,1.12,k)*lerp(1.,.9,saturate(W));',
                      {'S': seed, 'W': wet}, True), p.MP_BASE_COLOR)
    g.output(g.constant(0), p.MP_METALLIC)
    g.output(g.constant(.75), p.MP_SPECULAR)
    g.output(g.custom('return clamp(R+(frac(S.x*37.71)-.5)*.035-.015*saturate(W),.075,.2);',
                      {'R': g.scalar('CityGlassRoughness', .12), 'S': seed, 'W': wet}), p.MP_ROUGHNESS)
    g.output(g.custom('float a=.0025; float phase=S.x*6.283185; '
                      'return normalize(float3(a*sin(U.x*6.283185+phase)*sin(U.y*3.14159),'
                      'a*.6*sin(U.y*6.283185+phase),1));',
                      {'U': uv, 'S': seed}, True, 'Subtle pane-scale reflected-image waviness'), p.MP_NORMAL)


def office_lighting(g, night):
    """Continuous office zones are authored per floor, independent of glass bays."""
    uv = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=0)
    color = g.node(u.MaterialExpressionVertexColor)
    g.output(g.custom('float ceiling=smoothstep(.48,.92,U.y); '
                      'float spill=lerp(.15,1.,smoothstep(.035,.18,C.r)); '
                      'return C.rgb*G*spill*lerp(.12,1.,ceiling)*smoothstep(.58,.86,N);',
                      {'C': color, 'G': g.constant(OFFICE_LIGHT_GAIN), 'U': uv, 'N': night}, True,
                      'Authored continuous floor/office-zone lighting; softer lower glass'), u.MaterialProperty.MP_EMISSIVE_COLOR)


def material(spec):
    """Shared native PBR; the first facade pass prioritizes exterior surfaces."""
    name = spec['name']
    path = DEST + '/Materials/M_' + name
    result = u.load_asset(path)
    is_stone = name in ('CityModern_Limestone', 'CityModern_PaleStone')
    is_hero = name == 'CityModern_Hero_Glass'
    is_office = name in OFFICE_GLASS
    version = FACADE_VERSION + hashlib.sha256(Path(__file__).read_bytes()).hexdigest() if is_stone or is_hero else 'city-pbr-v1'
    if is_office:
        version += NIGHT_LIGHTING_VERSION + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if name in DISTANT_GLASS:
        version += DISTANT_LIGHTING_VERSION + hashlib.sha256(
            Path(__file__).with_name('city_distant_lighting.py').read_bytes()).hexdigest()
    recipe = hashlib.sha256((version + json.dumps(spec, sort_keys=True)).encode()).hexdigest()
    if result and str(u.EditorAssetLibrary.get_metadata_tag(result, 'OOWCityRecipe')) == recipe:
        surface.ensure_mesh_usage(result)
        u.EditorAssetLibrary.save_loaded_asset(result)
        return result
    if result:
        u.MaterialEditingLibrary.delete_all_material_expressions(result)
    else:
        result = u.AssetToolsHelpers.get_asset_tools().create_asset('M_' + name, DEST + '/Materials', u.Material, u.MaterialFactoryNew())
    result.set_editor_property('tangent_space_normal', True)
    g, p = surface.Graph(result), u.MaterialProperty
    pbr = spec.get('pbrMetallicRoughness', {})
    color = tuple(pbr.get('baseColorFactor', [1, 1, 1])[:3])
    wet, night = g.scalar('Wetness'), g.scalar('Night')
    g.output(g.custom('return C*lerp(1.,.86,saturate(W));', {'C': g.vector(color), 'W': wet}, True), p.MP_BASE_COLOR)
    rough = pbr.get('roughnessFactor', .5)
    g.output(g.custom('return lerp(R,max(.08,R*.64),saturate(W));', {'R': g.constant(rough), 'W': wet}), p.MP_ROUGHNESS)
    g.output(g.constant(pbr.get('metallicFactor', 0)), p.MP_METALLIC)
    if is_stone:
        stone_surface(g, wet, name.endswith('PaleStone'))
    elif is_hero:
        hero_glass_surface(g, wet, night)
    if is_office:
        office_lighting(g, night)
    elif name in DISTANT_GLASS:
        apply_distant_lighting(g, night)
    elif 'LED' in name or 'lamps' in name.lower():
        emissive = tuple(spec.get('emissiveFactor', [.3, .25, .18]))
        gain = spec.get('extensions', {}).get('KHR_materials_emissive_strength', {}).get('emissiveStrength', 1)
        g.output(g.custom('return E*G*lerp(.08,1.,smoothstep(.58,.86,N));', {'E': g.vector(emissive), 'G': g.constant(gain), 'N': night}, True), p.MP_EMISSIVE_COLOR)
    surface.ensure_mesh_usage(result)
    u.EditorAssetLibrary.set_metadata_tag(result, 'OOWCityRecipe', recipe)
    if is_stone or is_hero:
        u.EditorAssetLibrary.set_metadata_tag(result, 'OOWFacadeVersion', FACADE_VERSION)
    if is_office:
        u.EditorAssetLibrary.set_metadata_tag(result, 'OOWNightLightingVersion', NIGHT_LIGHTING_VERSION)
    u.MaterialEditingLibrary.recompile_material(result)
    u.EditorAssetLibrary.save_loaded_asset(result)
    return result


def build_street_lighting(modern_meta):
    """One downward luminaire for each authored pole, covering the carriageway."""
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    for actor in actors.get_all_level_actors():
        if actor.actor_has_tag('OOWCityLamp') or actor.actor_has_tag('OOWCityLampExtension'):
            actors.destroy_actor(actor)
    settings = {'count': len(modern_meta['streetlights']), 'lumens': 650.,
                'radiusCm': 4000., 'innerConeDegrees': 55., 'outerConeDegrees': 75.,
                'pitchDegrees': -82., 'temperatureK': 3800.}
    originals = {entry['name']: entry for entry in modern_meta['streetlights']}
    templates = {actor.get_actor_label(): actor for actor in actors.get_all_level_actors()}
    extensions = []
    for side in ('W', 'E'):
        template_name = 'CityModern_LED_' + side + '6'
        template = templates[template_name]
        original = template.get_component_by_class(u.StaticMeshComponent)
        if not original or not original.static_mesh:
            raise RuntimeError('Missing City pole template mesh: ' + template_name)
        origin = original.get_world_location()
        for step, lumens in enumerate((550., 450., 350.), 1):
            # Spawn a clean actor: duplicating Interchange actor user data crashes
            # the NullRHI commandlet. Preserve only the effective mesh and state.
            pole = actors.spawn_actor_from_class(u.StaticMeshActor,
                        u.Vector(origin.x, origin.y - 4000. * step, origin.z), original.get_world_rotation())
            if not pole:
                raise RuntimeError('Could not extend City street lighting: ' + template_name)
            pole.set_actor_scale3d(original.get_world_scale())
            component = pole.static_mesh_component
            component.set_static_mesh(original.static_mesh)
            component.set_mobility(u.ComponentMobility.STATIC)
            for slot in range(original.get_num_materials()):
                component.set_material(slot, original.get_material(slot))
            for key in ('cast_shadow', 'evaluate_world_position_offset', 'visible_in_ray_tracing',
                        'visible_in_reflection_captures', 'visible_in_real_time_sky_captures'):
                component.set_editor_property(key, original.get_editor_property(key))
            pole.set_actor_enable_collision(template.get_actor_enable_collision())
            name = 'CityModern_LED_' + side + str(6 + step)
            pole.set_actor_label(name)
            pole.tags = ['OOWGeometry', 'OOWCityLampExtension']
            source_position = originals[template_name]['position']
            extensions.append({'name': name, 'template': template_name,
                               'position': [source_position[0], source_position[1], source_position[2] - 40. * step],
                               'offsetCm': [0., -4000. * step, 0.], 'lumens': lumens})
    settings['extensions'] = extensions
    settings['count'] += len(extensions)
    for source in modern_meta['streetlights'] + extensions:
        side = -1 if source['position'][0] < 0 else 1
        position = u.Vector(side * 1480., source['position'][2] * 100., 1450.)
        lamp = actors.spawn_actor_from_class(u.SpotLight, position,
                    u.Rotator(pitch=settings['pitchDegrees'], yaw=0. if side < 0 else 180., roll=0.))
        lamp.set_actor_label('OOWCityLight_' + source['name'])
        lamp.tags = ['OOWNightLight', 'OOWCityLamp']
        comp = lamp.get_component_by_class(u.SpotLightComponent)
        comp.set_mobility(u.ComponentMobility.MOVABLE)
        for key, value in {'intensity_units': u.LightUnits.LUMENS,
                           'intensity': source.get('lumens', settings['lumens']), 'attenuation_radius': settings['radiusCm'],
                           'inner_cone_angle': settings['innerConeDegrees'],
                           'outer_cone_angle': settings['outerConeDegrees'],
                           'use_temperature': True, 'temperature': settings['temperatureK'],
                           'cast_shadows': False, 'indirect_lighting_intensity': 0.,
                           'volumetric_scattering_intensity': 0.,
                           'affect_translucent_lighting': True}.items():
            comp.set_editor_property(key, value)
    return settings


def import_assets(filename):
    manager = u.InterchangeManager.get_interchange_manager_scripted()
    params = u.ImportAssetParameters()
    params.is_automated, params.replace_existing = True, True
    return manager.import_asset(DEST, manager.create_source_data(str(ART / filename)), params)


def tree_material(leaves):
    """Explicit texture bindings avoid depending on Interchange's generated MI chain."""
    name = 'M_CityLeaves_v2' if leaves else 'M_CityBark_v2'
    path = DEST + '/Materials/' + name
    if u.EditorAssetLibrary.does_asset_exist(path):
        return u.load_asset(path)
    result = u.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST + '/Materials', u.Material, u.MaterialFactoryNew())
    g, p = surface.Graph(result), u.MaterialProperty
    stem = 'Foliage_Linde_Tree_Large_' + ('Green_Leaves' if leaves else 'Trunk')
    texture_name = stem + '_BaseColor'
    texture = tree_textures[texture_name]
    assert texture, stem
    sample = g.node(u.MaterialExpressionTextureSample, texture=texture)
    base = (sample[0], 'RGB')
    color = g.custom('return C*Tint*lerp(1.,.86,saturate(W));',
                     {'C': base, 'Tint': g.vector((.7, .92, .57) if leaves else (1., 1., 1.)), 'W': g.scalar('Wetness')}, True)
    g.output(color, p.MP_BASE_COLOR)
    g.output(g.constant(.78 if leaves else .88), p.MP_ROUGHNESS)
    if leaves:
        result.set_editor_property('blend_mode', u.BlendMode.BLEND_MASKED)
        result.set_editor_property('opacity_mask_clip_value', .35)
        result.set_editor_property('two_sided', True)
        result.set_editor_property('shading_model', u.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
        g.output((sample[0], 'A'), p.MP_OPACITY_MASK)
        g.output(g.custom('return C*.35;', {'C': color}, True), p.MP_SUBSURFACE_COLOR)
    else:
        normal_name = stem + '_Normal'
        normal = tree_textures[normal_name]
        assert normal
        g.output(g.node(u.MaterialExpressionTextureSample, texture=normal, sampler_type=u.MaterialSamplerType.SAMPLERTYPE_NORMAL), p.MP_NORMAL)
    surface.ensure_mesh_usage(result)
    u.MaterialEditingLibrary.recompile_material(result)
    u.EditorAssetLibrary.save_loaded_asset(result)
    return result


def import_tree_textures():
    # Separate source textures from Interchange's reimport-owned objects. Its
    # previous texture objects can remain pending deletion until the editor exits.
    for stem in ('Foliage_Linde_Tree_Large_Trunk_BaseColor', 'Foliage_Linde_Tree_Large_Trunk_Normal',
                 'Foliage_Linde_Tree_Large_Green_Leaves_BaseColor'):
        path = DEST + '/TreeTextures/' + stem
        texture = u.EditorAssetLibrary.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else None
        if not texture:
            manager = u.InterchangeManager.get_interchange_manager_scripted()
            params = u.ImportAssetParameters()
            params.is_automated, params.replace_existing = True, True
            result = manager.import_asset(DEST + '/TreeTextures', manager.create_source_data(str(ART / 'textures' / (stem + '.png'))), params)
            texture = next((asset for asset in result if isinstance(asset, u.Texture2D)), None)
        assert texture, path
        tree_textures[stem] = texture
        if stem.endswith('_Normal'):
            texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_NORMALMAP)
            texture.set_editor_property('srgb', False)
        u.EditorAssetLibrary.save_loaded_asset(texture)


def main():
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    if not levels.load_level('/Game/Maps/City'):
        raise RuntimeError('Missing City map')
    meta = json.loads((ROOT / 'Migration/Exported/city.json').read_text(encoding='utf-8'))
    modern_meta = json.loads((ART / 'modern-city.json').read_text(encoding='utf-8'))
    road_names = {n['name'] for n in meta['nodes'] if 'city-road-functional-zones' in n.get('ancestors', [])} - REPLACED_ROADS - REMOVED_ROADS
    prior = list(actors.get_all_level_actors())
    removed = 0
    for actor in prior:
        # All geometry outside the original road is replaced, including old cars.
        # Environment/camera actors and the independently managed frame are retained.
        if ((isinstance(actor, u.StaticMeshActor) and actor.get_actor_label() not in road_names)
                or actor.actor_has_tag('OOWCityStaticBatch') or actor.actor_has_tag('OOWCityLamp')):
            if not actors.destroy_actor(actor):
                raise RuntimeError('Could not remove old City geometry')
            removed += 1
    # Interchange emits two empty grouping actors; remove only orphaned import groups.
    for _ in range(3):
        for actor in list(actors.get_all_level_actors()):
            if (actor.get_class() == u.Actor.static_class()
                    and actor.get_actor_label() in ('AuxScene', 'OriginalModernCity')
                    and not actor.get_attached_actors() and not actor.tags):
                actors.destroy_actor(actor)
    kept = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
    for index in range(33, 39):
        road = kept.get('OOW_%05d_Mesh' % index)
        if road:
            road.set_actor_scale3d(u.Vector(1, 4.1, 1))
            road.set_actor_location(u.Vector(0, -11160, 0), False, False)
    kept['OOW_00032_city_grounding_underlay'].set_actor_scale3d(u.Vector(2, 2, 2))

    camera = kept['OOWCamera']
    camera.set_actor_location(u.Vector(2600, 4200, 3700), False, False)
    target = u.Vector(-2200, -11500, 1900)
    camera.set_actor_rotation(u.MathLibrary.find_look_at_rotation(camera.get_actor_location(), target), False)
    camera.tags = ['OOWCamera', 'VerticalFov_54', 'OOWRoadsideView']
    camera.camera_component.set_editor_property('field_of_view', math.degrees(2 * math.atan(math.tan(math.radians(27)) * 1280 / 820)))
    camera.camera_component.set_editor_property('aspect_ratio', 1280 / 820)
    camera.camera_component.set_editor_property('constrain_aspect_ratio', False)
    kept['OOWSun'].tags = ['OOWSun', 'OOWSunAzimuth_2.65']
    fog = kept['OOWFog'].get_component_by_class(u.ExponentialHeightFogComponent)
    fog.set_editor_property('fog_density', .006)
    settings = kept['OOWPostProcess'].get_editor_property('settings')
    settings.set_editor_property('override_auto_exposure_bias', True)
    settings.set_editor_property('auto_exposure_bias', -.15)
    kept['OOWPostProcess'].set_editor_property('settings', settings)

    pbr_specs = {m['name']: m for file in ('modern-city.glb', 'traffic-sedan.glb') for m in document(ART / file)['materials']}
    paint_names = []
    for suffix, color in [('Silver', [.46, .48, .5]), ('Blue', [.02, .045, .075]),
                           ('Red', [.19, .027, .018]), ('Charcoal', [.025, .027, .032])]:
        spec = json.loads(json.dumps(pbr_specs['Sedan_Paint']))
        spec['name'] += '_' + suffix
        spec['pbrMetallicRoughness']['baseColorFactor'] = color + [1]
        pbr_specs[spec['name']] = spec
        paint_names.append(spec['name'])
    import_facade_textures()
    native_materials = {name: material(spec) for name, spec in pbr_specs.items()}

    def configure_mesh(mesh, native=True):
        if native and '/modern-city/' in mesh.get_path_name():
            build = mesh_editor.get_lod_build_settings(mesh, 0)
            build.set_editor_property('generate_lightmap_u_vs', False)
            build.set_editor_property('use_full_precision_u_vs', True)
            mesh_editor.set_lod_build_settings(mesh, 0, build)
            assert mesh_editor.get_num_uv_channels(mesh, 0) >= 2, mesh.get_name()
        if native:
            for slot, entry in enumerate(mesh.static_materials):
                original = entry.material_interface
                name = original.get_name() if original else ''
                if name.startswith('M_'):
                    name = name[2:]
                if name not in native_materials:
                    raise RuntimeError('Unmapped City material: ' + name)
                mesh.set_material(slot, native_materials[name])
        else:
            for slot, entry in enumerate(mesh.static_materials):
                mesh.set_material(slot, tree_material(slot == 1))
        nanite = mesh.get_editor_property('nanite_settings')
        nanite.enabled = True
        if not native:
            nanite.set_editor_property('shape_preservation', u.NaniteShapePreservation.PRESERVE_AREA)
        mesh_editor.set_nanite_settings(mesh, nanite, True)
        u.EditorAssetLibrary.save_loaded_asset(mesh)

    before_import = set(a.get_path_name() for a in actors.get_all_level_actors())
    manager = u.InterchangeManager.get_interchange_manager_scripted()
    params = u.ImportAssetParameters()
    params.is_automated, params.replace_existing = True, True
    if not manager.import_scene(DEST, manager.create_source_data(str(ART / 'modern-city.glb')), params):
        raise RuntimeError('Modern city scene import failed')
    architecture = [a for a in actors.get_all_level_actors() if a.get_path_name() not in before_import and isinstance(a, u.StaticMeshActor)]
    assert len(architecture) == modern_meta['meshCount'], len(architecture)
    context_actors = [a for a in architecture if 'CityModern_Context_' in a.get_actor_label()]
    assert len(context_actors) == modern_meta['contextMeshCount'], len(context_actors)
    done = set()
    for actor in architecture:
        comp = actor.static_mesh_component
        if 'CityModern_Skyline' in actor.get_actor_label():
            # Slender, taller outer towers remain visible over the nearer podiums.
            actor.set_actor_scale3d(u.Vector(.65, .60, 1.5))
            actor.set_actor_location(u.Vector(0, -12000, -345), False, False)
        actor.tags = ['OOWGeometry']
        comp.set_mobility(u.ComponentMobility.STATIC)
        comp.set_editor_property('cast_shadow', True)
        if comp.static_mesh not in done:
            configure_mesh(comp.static_mesh)
            done.add(comp.static_mesh)
        for i in range(comp.get_num_materials()):
            comp.set_material(i, comp.static_mesh.get_material(i))
        comp.set_editor_property('evaluate_world_position_offset', False)

    sedan = [a for a in import_assets('traffic-sedan.glb') if isinstance(a, u.StaticMesh)]
    trees = [a for a in import_assets('OOW_City_Linden.glb') if isinstance(a, u.StaticMesh)]
    assert len(sedan) == len(trees) == 1
    import_tree_textures()
    configure_mesh(sedan[0])
    configure_mesh(trees[0], False)

    def spawn_mesh(name, mesh, location, scale=1., yaw=0., tags=None):
        actor = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector(*location), u.Rotator(yaw=yaw))
        actor.set_actor_label(name)
        actor.tags = tags or ['OOWGeometry']
        comp = actor.static_mesh_component
        comp.set_static_mesh(mesh)
        comp.set_mobility(u.ComponentMobility.STATIC)
        actor.set_actor_scale3d(u.Vector(scale, scale, scale))
        return actor

    for i in range(16):
        x = (220 if i % 4 < 2 else 520) * (1 if i % 2 == 0 else -1)
        y = 1100 - ((i * 1337) % 20400)
        car = spawn_mesh('OOWCitySedan_%02d' % i, sedan[0], (x, y, 695), yaw=180 if i % 2 == 0 else 0,
                         tags=['OOWGeometry', 'OOWCar_' + str(i)])
        car.static_mesh_component.set_mobility(u.ComponentMobility.MOVABLE)
        car.static_mesh_component.set_material(0, native_materials[paint_names[i % len(paint_names)]])
    for side in (-1, 1):
        for i in range(14):
            tree = spawn_mesh('OOWCityLinden_%d_%02d' % (side, i), trees[0], (side * 1820, 1400 - i * 2300, 695),
                             scale=.72 + (i * 7 % 5) * .045, yaw=(i * 137 + side * 41) % 360)
            tree.set_actor_enable_collision(False)
            tree.static_mesh_component.set_editor_property('evaluate_world_position_offset', False)

    street_lighting = build_street_lighting(modern_meta)

    sidewalk = import_sidewalk()
    entrances = import_entrances()
    roads = build_roads()
    batch = batch_city_geometry()
    u.EditorAssetLibrary.save_directory(DEST)
    if not levels.save_current_level():
        raise RuntimeError('Cannot save modern City')
    report = {'recipe': 'modern-city-v3-facade', 'removedLegacyActors': removed, 'architectureActors': len(architecture),
              'facade': {'version': FACADE_VERSION, 'heroBuildings': modern_meta['heroBuildingNames'],
                         'heroWindowCount': modern_meta['heroWindowCount'], 'interiorAtlasUsed': False},
              'nightLighting': {'version': NIGHT_LIGHTING_VERSION, 'gain': OFFICE_LIGHT_GAIN,
                                'materials': sorted(OFFICE_GLASS),
                                'source': {key: modern_meta['nightLighting'][key] for key in
                                           ('sourceGeometry', 'allNearPaneCount', 'heroPaneCount', 'checks', 'exportedChecks')}},
              'nearBuildings': modern_meta['nearBuildingCount'], 'skylineBuildings': modern_meta['skylineBuildingCount'],
              'context': {'buildings': modern_meta['contextBuildingCount'], 'actors': len(context_actors),
                          'groups': modern_meta['contextGroups'],
                          'solidGroundProbes': len(modern_meta['visibility']['solidGroundProbes'])},
              'sourceGeometry': {'sha256': hashlib.sha256((ART / 'modern-city.glb').read_bytes()).hexdigest(),
                                 'triangles': modern_meta['triangles'], 'primitives': modern_meta['primitives']},
              'distantLighting': {'version': DISTANT_LIGHTING_VERSION, 'gain': DISTANT_LIGHT_GAIN,
                                  'materials': sorted(DISTANT_GLASS)},
              'streetLighting': street_lighting,
              'movingCars': 16, 'streetTrees': 28, 'nightLights': street_lighting['count'], 'batch': batch, 'sidewalk': sidewalk, 'entrances': entrances, 'roads': roads,
              'camera': [2600, 4200, 3700], 'target': [-2200, -11500, 1900], 'verticalFov': 54,
              'frameOwnership': 'AWindowFrame runtime cosmetic; no frame or sill baked into City map',
              'materialCount': len(native_materials), 'actorsSaved': len(actors.get_all_level_actors())}
    (ROOT / 'Migration/city-modern-build.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    # Scene reimport can retain stale actor bindings; validate the saved result,
    # including earlier imports that a later kit may have changed.
    from audit_city_lookdev import main as audit_saved_city
    audit_saved_city()
    u.log('OOW_CITY_MODERN_COMPLETE ' + json.dumps(report))


if __name__ == '__main__':
    main()
