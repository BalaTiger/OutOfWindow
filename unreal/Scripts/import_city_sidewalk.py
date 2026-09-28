"""Import the modeled pavement kit without rebuilding buildings or runtime cosmetics."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unreal as u

ROOT = Path(u.Paths.project_dir()).parent
ART = ROOT / 'Art/City'
DEST = '/Game/Scenes/City/Modern'
REPLACED_ROADS = {'OOW_%05d_Mesh' % i for i in (37, 38, 42, 43)}
VERSION = 'city-sidewalk-v1'
sys.path.insert(0, str(ROOT / 'Scripts'))
import build_surface_materials as surface


def document(path):
    with path.open('rb') as stream:
        stream.seek(12)
        size, kind = struct.unpack('<II', stream.read(8))
        assert kind == 0x4E4F534A
        return json.loads(stream.read(size))


def import_textures():
    textures = {}
    for channel in ('BaseColor', 'Normal'):
        source = ART / 'Sidewalk' / ('Concrete3_' + channel + '.png')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        texture = u.load_asset(DEST + '/SidewalkTextures/' + source.stem)
        if not texture or str(u.EditorAssetLibrary.get_metadata_tag(texture, 'OOWSourceHash')) != digest:
            manager = u.InterchangeManager.get_interchange_manager_scripted()
            params = u.ImportAssetParameters()
            params.is_automated, params.replace_existing = True, True
            imported = manager.import_asset(DEST + '/SidewalkTextures', manager.create_source_data(str(source)), params)
            texture = next((a for a in imported if isinstance(a, u.Texture2D)), None)
        assert texture, source
        texture.set_editor_property('srgb', channel == 'BaseColor')
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_NORMALMAP if channel == 'Normal'
                                    else u.TextureCompressionSettings.TC_DEFAULT)
        if channel == 'Normal':
            texture.set_editor_property('flip_green_channel', True)
        texture.set_editor_property('virtual_texture_streaming', False)
        texture.set_editor_property('address_x', u.TextureAddress.TA_WRAP)
        texture.set_editor_property('address_y', u.TextureAddress.TA_WRAP)
        u.EditorAssetLibrary.set_metadata_tag(texture, 'OOWSourceHash', digest)
        u.EditorAssetLibrary.save_loaded_asset(texture)
        textures[channel] = texture
    return textures


def material(spec, textures):
    name = 'M_' + spec['name']
    result = u.load_asset(DEST + '/Materials/' + name)
    if result:
        u.MaterialEditingLibrary.delete_all_material_expressions(result)
    else:
        result = u.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST + '/Materials', u.Material, u.MaterialFactoryNew())
    surface.u, surface.mel = u, u.MaterialEditingLibrary
    g, p = surface.Graph(result), u.MaterialProperty
    wet = g.scalar('Wetness')
    color = tuple(spec.get('pbrMetallicRoughness', {}).get('baseColorFactor', [.35, .36, .35])[:3])
    planting = 'Planting' in name
    if 'Soil' in name or planting:
        g.output(g.custom('return C*lerp(1.,.65,saturate(W));', {'C': g.vector(color), 'W': wet}, True), p.MP_BASE_COLOR)
        g.output(g.constant(.94), p.MP_ROUGHNESS)
    else:
        position, normal = g.position(), g.node(u.MaterialExpressionVertexNormalWS)
        plane = g.custom('float3 a=abs(N); return a.z>.7?float3(P.xy/120.,0):'
                         'a.x>a.y?float3(P.yz/120.,0):float3(P.xz/120.,0);',
                         {'P': position, 'N': normal}, True, 'Concrete grain: authored 1.2 metre coverage')
        uv = g.node(u.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
        g.connect(plane, uv, '')
        color_sample = g.node(u.MaterialExpressionTextureSampleParameter2D, parameter_name='SidewalkConcreteColor',
                              texture=textures['BaseColor'], sampler_type=u.MaterialSamplerType.SAMPLERTYPE_COLOR)
        normal_sample = g.node(u.MaterialExpressionTextureSampleParameter2D, parameter_name='SidewalkConcreteNormal',
                               texture=textures['Normal'], sampler_type=u.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        g.connect(uv, color_sample, 'UVs')
        g.connect(uv, normal_sample, 'UVs')
        tint = g.vector(color)
        if 'Paving' in name:
            tint = g.custom('return C*V;', {'C': tint, 'V': g.node(u.MaterialExpressionVertexColor)}, True,
                            'Stable whole-slab and functional-band colors authored in COLOR_0')
        g.output(g.custom('float grey=dot(C,float3(.2126,.7152,.0722)); '
                          'return Tint*clamp(grey/.42,.65,1.25)*lerp(1.,.52,saturate(W));',
                          {'C': (color_sample[0], 'RGB'), 'Tint': tint, 'W': wet}, True), p.MP_BASE_COLOR)
        # The source contains no measured roughness map: use a narrow concrete range.
        g.output(g.custom('return lerp(.86,.62,saturate(W));', {'W': wet}), p.MP_ROUGHNESS)
        result.set_editor_property('tangent_space_normal', False)
        g.output(g.custom('float3 n=normalize(N); float3 a=abs(n); '
                          'float3 t=a.z>.7?float3(1,0,0):a.x>a.y?float3(0,1,0):float3(1,0,0); '
                          'float3 b=a.z>.7?float3(0,1,0):float3(0,0,1); '
                          'return normalize(n+(t*Map.x+b*Map.y)*.24);',
                          {'N': normal, 'Map': (normal_sample[0], 'RGB')}, True), p.MP_NORMAL)
    g.output(g.constant(0), p.MP_METALLIC)
    surface.ensure_mesh_usage(result)
    u.EditorAssetLibrary.set_metadata_tag(result, 'OOWSidewalkVersion', VERSION)
    u.MaterialEditingLibrary.recompile_material(result)
    u.EditorAssetLibrary.save_loaded_asset(result)
    return result


def import_geometry(stem, materials, tag):
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    source = ART / (stem + '.glb')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    meta = json.loads((ART / (stem + '.json')).read_text(encoding='utf-8'))
    for actor in list(actors.get_all_level_actors()):
        if actor.actor_has_tag(tag):
            assert actors.destroy_actor(actor), actor.get_actor_label()
    doc = document(source)
    group_names = {node.get('name', '') for node in doc['nodes'] if 'mesh' not in node} | {'AuxScene'}
    for _ in range(3):
        for actor in list(actors.get_all_level_actors()):
            if (actor.get_class() == u.Actor.static_class() and actor.get_actor_label() in group_names
                    and not actor.tags and not actor.get_attached_actors()):
                actors.destroy_actor(actor)
    before = {a.get_path_name() for a in actors.get_all_level_actors()}
    manager = u.InterchangeManager.get_interchange_manager_scripted()
    params = u.ImportAssetParameters()
    params.is_automated, params.replace_existing = True, True
    assert manager.import_scene(DEST, manager.create_source_data(str(source)), params), stem + ' import failed'
    imported = [a for a in actors.get_all_level_actors() if a.get_path_name() not in before and isinstance(a, u.StaticMeshActor)]
    assert len(imported) == meta['meshCount'], len(imported)
    saved = []
    for actor in imported:
        actor.tags = ['OOWGeometry', tag]
        component = actor.static_mesh_component
        component.set_mobility(u.ComponentMobility.STATIC)
        component.set_editor_property('cast_shadow', True)
        component.set_editor_property('evaluate_world_position_offset', False)
        mesh = component.static_mesh
        for slot, entry in enumerate(mesh.static_materials):
            name = entry.material_interface.get_name().removeprefix('M_')
            assert name in materials, name
            mesh.set_material(slot, materials[name])
            component.set_material(slot, materials[name])
        build = editor.get_lod_build_settings(mesh, 0)
        build.set_editor_property('generate_lightmap_u_vs', False)
        build.set_editor_property('use_full_precision_u_vs', True)
        editor.set_lod_build_settings(mesh, 0, build)
        nanite = mesh.get_editor_property('nanite_settings')
        nanite.enabled = True
        editor.set_nanite_settings(mesh, nanite, True)
        u.EditorAssetLibrary.set_metadata_tag(mesh, tag.replace('City', '') + 'SourceHash', digest)
        u.EditorAssetLibrary.save_loaded_asset(mesh)
        saved.append({'label': actor.get_actor_label(), 'mesh': mesh.get_path_name(),
                      'fallbackTriangles': mesh.get_num_triangles(0)})
    return {'version': VERSION, 'sha256': digest, 'triangles': meta['triangles'],
            'meshCount': len(imported), 'actors': saved}


def import_sidewalk():
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    for actor in list(actors.get_all_level_actors()):
        if actor.get_actor_label() in REPLACED_ROADS:
            assert actors.destroy_actor(actor), actor.get_actor_label()
    textures = import_textures()
    materials = {spec['name']: material(spec, textures) for spec in document(ART / 'city-sidewalk.glb')['materials']}
    report = import_geometry('city-sidewalk', materials, 'OOWCitySidewalk')
    report['replacedRoads'] = sorted(REPLACED_ROADS)
    return report


def import_entrances():
    materials = {spec['name']: u.load_asset(DEST + '/Materials/M_' + spec['name'])
                 for spec in document(ART / 'city-entrances.glb')['materials']}
    assert all(materials.values()), 'Missing native entrance materials'
    return import_geometry('city-entrances', materials, 'OOWCityEntrance')


if __name__ == '__main__':
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    assert levels.load_level('/Game/Maps/City'), 'Missing City map'
    report_path = ROOT / 'Migration/city-modern-build.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['sidewalk'] = import_sidewalk()
    report['entrances'] = import_entrances()
    report['actorsSaved'] = len(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    u.EditorAssetLibrary.save_directory(DEST)
    assert levels.save_current_level(), 'Cannot save City'
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_CITY_SIDEWALK_COMPLETE ' + json.dumps(report['sidewalk']))
