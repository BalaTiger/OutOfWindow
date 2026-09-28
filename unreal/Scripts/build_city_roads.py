"""City-only road surfacing and lane paint; retain the traffic/camera contracts."""
import hashlib
import json
from pathlib import Path
import sys
import unreal as u

ROOT = Path(u.Paths.project_dir()).parent
ART = ROOT / 'Art/City'
DEST = '/Game/Scenes/City/Modern'
sys.path.insert(0, str(ROOT / 'Scripts'))
import build_surface_materials as surface
from import_city_sidewalk import import_geometry, import_textures as concrete_textures

REMOVED_ROADS = {'OOW_%05d_Mesh' % i for i in (*range(39, 42), *range(44, 84))}
ROAD_BINDINGS = {'OOW_00032_city_grounding_underlay': 'Concrete', 'OOW_00033_Mesh': 'Asphalt',
                 'OOW_00034_Mesh': 'Parking', 'OOW_00035_Mesh': 'Parking', 'OOW_00036_Mesh': 'Cycle'}
VERSION = 'city-road-v1'


def asphalt_textures():
    textures = {}
    for channel in ('diffuse', 'normal', 'roughness'):
        source = ART / 'Road' / ('Asphalt02_' + channel + '.jpg')
        texture = u.load_asset(DEST + '/RoadTextures/' + source.stem)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if not texture or str(u.EditorAssetLibrary.get_metadata_tag(texture, 'OOWSourceHash')) != digest:
            manager = u.InterchangeManager.get_interchange_manager_scripted()
            params = u.ImportAssetParameters()
            params.is_automated, params.replace_existing = True, True
            assets = manager.import_asset(DEST + '/RoadTextures', manager.create_source_data(str(source)), params)
            texture = next((a for a in assets if isinstance(a, u.Texture2D)), None)
        assert texture, source
        texture.set_editor_property('srgb', channel == 'diffuse')
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_NORMALMAP if channel == 'normal'
                                    else u.TextureCompressionSettings.TC_MASKS if channel == 'roughness' else u.TextureCompressionSettings.TC_DEFAULT)
        if channel == 'normal':
            texture.set_editor_property('flip_green_channel', True)
        texture.set_editor_property('virtual_texture_streaming', False)
        texture.set_editor_property('address_x', u.TextureAddress.TA_WRAP)
        texture.set_editor_property('address_y', u.TextureAddress.TA_WRAP)
        u.EditorAssetLibrary.set_metadata_tag(texture, 'OOWSourceHash', digest)
        u.EditorAssetLibrary.save_loaded_asset(texture)
        textures[channel] = texture
    return textures


def material(kind, textures):
    name = 'M_CityRoad_' + kind
    asset = u.load_asset(DEST + '/Materials/' + name)
    if asset:
        u.MaterialEditingLibrary.delete_all_material_expressions(asset)
    else:
        asset = u.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST + '/Materials', u.Material, u.MaterialFactoryNew())
    surface.u, surface.mel = u, u.MaterialEditingLibrary
    g, p = surface.Graph(asset), u.MaterialProperty
    wet, water, position = g.scalar('Wetness'), g.scalar('Water'), g.position()
    tile_cm = 120. if kind == 'Concrete' else 300.
    coords = g.custom('return float3(P.xy/%.1f,0);' % tile_cm, {'P': position}, True, 'World-aligned grain at source scale')
    uv = g.node(u.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
    g.connect(coords, uv, '')
    samples = {}
    for channel, sampler in (('diffuse', u.MaterialSamplerType.SAMPLERTYPE_COLOR),
                             ('normal', u.MaterialSamplerType.SAMPLERTYPE_NORMAL),
                             ('roughness', u.MaterialSamplerType.SAMPLERTYPE_MASKS)):
        sample = g.node(u.MaterialExpressionTextureSampleParameter2D, parameter_name='CityRoad_' + channel,
                        texture=textures[channel], sampler_type=sampler)
        g.connect(uv, sample, 'UVs')
        samples[channel] = (sample[0], 'RGB')
    palette = {'Asphalt': (.068, .073, .078), 'Parking': (.085, .091, .094),
               'Cycle': (.095, .126, .116), 'Concrete': (.15, .16, .153),
               'White': (.55, .57, .54), 'Yellow': (.60, .40, .06)}
    paint = kind in ('White', 'Yellow')
    # Restrict smooth water to disconnected low spots. Wet aggregate stays rough.
    puddle = g.custom('float2 q=P.xy*.003; float n=0.; float weight=.57; '
                      '[unroll] for(int i=0;i<3;i++){ float2 cell=floor(q), f=frac(q); f=f*f*(3.-2.*f); '
                      'float2 k=float2(127.1,311.7); '
                      'float4 h=frac(sin(float4(dot(cell,k),dot(cell+float2(1,0),k),'
                      'dot(cell+float2(0,1),k),dot(cell+1.,k)))*43758.5453); '
                      'n+=lerp(lerp(h.x,h.y,f.x),lerp(h.z,h.w,f.x),f.y)*weight; '
                      'q=float2(q.x*.8+q.y*.6,-q.x*.6+q.y*.8)*2.1+float2(3.71,1.37); weight*=.5; } '
                      'float edge=lerp(.2,1.,smoothstep(650.,870.,abs(P.x))); '
                      'return smoothstep(.65,.82,n)*edge*saturate(A);', {'P': position, 'A': water},
                      description='Sparse standing water, separate from a rough wet road')
    g.output(g.custom('float grey=dot(C,float3(.2126,.7152,.0722)); '
                      'float grain=lerp(.86,1.12,saturate(grey*3.)); '
                      'return Tint*grain*lerp(1.,WetTint,saturate(W))*lerp(1.,.94,M);',
                      {'C': samples['diffuse'], 'Tint': g.vector(palette[kind]), 'W': wet,
                       'WetTint': g.constant(.8 if paint else .63), 'M': puddle}, True), p.MP_BASE_COLOR)
    g.output(g.custom('float dry=clamp(Dry+R.r*.09,.72,.95); '
                      'float damp=lerp(Wet,Wet+.08,R.r); '
                      'return lerp(lerp(dry,damp,saturate(W)),.22,M);',
                      {'R': samples['roughness'], 'Dry': g.constant(.73 if paint else .84),
                       'Wet': g.constant(.52 if paint else .54), 'W': wet, 'M': puddle}), p.MP_ROUGHNESS)
    asset.set_editor_property('tangent_space_normal', False)
    g.output(g.custom('float gain=G*lerp(1.,.12,M); return normalize(float3(N.xy*gain,1.));',
                      {'N': samples['normal'], 'G': g.constant(.16 if paint else .5), 'M': puddle}, True), p.MP_NORMAL)
    g.output(g.constant(0), p.MP_METALLIC)
    g.output(g.constant(.35), p.MP_SPECULAR)
    surface.ensure_mesh_usage(asset)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWRoadVersion', VERSION)
    u.MaterialEditingLibrary.recompile_material(asset)
    u.EditorAssetLibrary.save_loaded_asset(asset)
    return asset


def build_roads():
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    for actor in list(actors.get_all_level_actors()):
        if actor.get_actor_label() in REMOVED_ROADS:
            assert actors.destroy_actor(actor), actor.get_actor_label()
    textures = asphalt_textures()
    native = {kind: material(kind, textures) for kind in ('Asphalt', 'Parking', 'Cycle', 'White', 'Yellow')}
    # The broad grounding surface is concrete, using the existing licensed grain.
    concrete = concrete_textures()
    native['Concrete'] = material('Concrete', {'diffuse': concrete['BaseColor'], 'normal': concrete['Normal'],
                                               'roughness': textures['roughness']})
    bound = {}
    for actor in actors.get_all_level_actors():
        label = actor.get_actor_label()
        if label in ROAD_BINDINGS:
            component = actor.get_component_by_class(u.StaticMeshComponent)
            component.set_material(0, native[ROAD_BINDINGS[label]])
            bound[label] = native[ROAD_BINDINGS[label]].get_path_name()
    assert set(bound) == set(ROAD_BINDINGS), bound
    # The far junction uses a native material slot on an original context mesh.
    for actor in actors.get_all_level_actors():
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            for slot in range(component.get_num_materials()):
                original = component.get_material(slot)
                if original and original.get_name() == 'M_CityModern_Context_Asphalt':
                    component.set_material(slot, native['Asphalt'])
    paint = {'CityRoadMarkings_White': native['White'], 'CityRoadMarkings_Yellow': native['Yellow']}
    paint.update({'CityRoad_White': native['White'], 'CityRoad_Yellow': native['Yellow']})
    report = import_geometry('city-road-markings', paint, 'OOWCityRoadMarkings')
    for actor in actors.get_all_level_actors():
        if actor.actor_has_tag('OOWCityRoadMarkings'):
            actor.static_mesh_component.set_editor_property('cast_shadow', False)
    report.update({'version': VERSION, 'roadBindings': bound, 'removedLegacyActors': sorted(REMOVED_ROADS),
                   'worldTextureMeters': 3, 'wetBaseRoughness': [.54, .62], 'puddleRoughness': .22})
    return report


if __name__ == '__main__':
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    assert levels.load_level('/Game/Maps/City')
    path = ROOT / 'Migration/city-modern-build.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    report['roads'] = build_roads()
    report['actorsSaved'] = len(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    u.EditorAssetLibrary.save_directory(DEST)
    assert levels.save_current_level()
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_CITY_ROADS_COMPLETE ' + json.dumps(report['roads']))
