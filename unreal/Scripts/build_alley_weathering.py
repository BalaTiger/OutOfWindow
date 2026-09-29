"""Alley facade dry plaster/aggregate layer, upstream of existing v9 weather.

Run with UnrealEditor-Cmd -run=pythonscript -script=<this file>. Input:
Art/AlleyWeathering/plaster-relief-height.png (linear authored height, not albedo).
Only TARGETS are rebound; imported assets, shared v9 masters and roofs are intact.
Outputs: /Game/Materials/OOW/AlleyWeathering and Migration/alley-weathering.json.
Plain Python --self-test validates the exported target/material contract.
"""
import hashlib
import json
from pathlib import Path
import sys

VERSION = 'alley-weathering-v2'
DEST = '/Game/Materials/OOW/AlleyWeathering'
# Ray inspection identifies 08_7/09_7 as walls; their Smooth slots are trim.
TARGETS = {'OOW_00726_Paris_Building_08_paris_building_08_7': 'MASTER_Concrete',
           'OOW_00759_paris_building_09_7': 'MASTER_Concrete'}
PARAMETERS = {
    'OOWExposureCoverage': .49,  # Linear height threshold; transition is +/- .05.
    'OOWReliefStrength': .70,    # Full macro height in centimetres, not displacement.
    'OOWWeatheringContrast': .70,
    'OOWWeatheringTileCm': 240.,
    'OOWWeatheringPatchCm': 900.,
    'OOWWeatheringWarpCm': 180.,  # Low-frequency UV warp; breaks tiling without gating relief.
}
BASE_CODE = 'return C * lerp(1.0, 0.80000, saturate(W));'
ROUGH_CODE = ('float r = saturate(R); return lerp(r, min(r, max(0.27000, r*0.52000)), saturate(W));')


def input_link(material, expression, pin):
    inputs = dict(zip(map(str, mel.get_material_expression_input_names(expression)),
                      mel.get_inputs_for_material_expression(material, expression)))
    node = inputs.get(pin)
    assert node, 'Missing input: ' + pin
    output = mel.get_input_node_output_name_for_material_expression(expression, node)
    assert output is not None, 'Cannot resolve source output: ' + pin
    return node, output


def check_code(node, code):
    assert isinstance(node, u.MaterialExpressionCustom), 'Expected the existing v9 custom node'
    assert str(node.get_editor_property('code')) == code, 'Unexpected or already layered weather graph'


def weather_inputs(material):
    """Fail closed if another adapter changed the v9 graph or already added dry layers."""
    assert not material.get_editor_property('use_material_attributes')
    base = mel.get_material_property_input_node(material, u.MaterialProperty.MP_BASE_COLOR)
    rough = mel.get_material_property_input_node(material, u.MaterialProperty.MP_ROUGHNESS)
    check_code(base, 'return C*(1.-.28*M);')
    check_code(rough, 'return lerp(R,min(R,.24),saturate(M*2.));')
    base_wet, _ = input_link(material, base, 'C')
    rough_wet, _ = input_link(material, rough, 'R')
    check_code(base_wet, BASE_CODE)
    check_code(rough_wet, ROUGH_CODE)
    color, roughness = input_link(material, base_wet, 'C'), input_link(material, rough_wet, 'R')
    assert isinstance(color[0], u.MaterialExpressionMaterialFunctionCall)
    assert isinstance(roughness[0], u.MaterialExpressionMaterialFunctionCall)
    mask = input_link(material, base, 'M')
    assert mask[0] == input_link(material, rough, 'M')[0]
    return base_wet, rough_wet, color, roughness, mask


def import_height(root):
    source = root / 'Art/AlleyWeathering/plaster-relief-height.png'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = DEST + '/Textures/H_' + digest[:10]
    # A hash-specific folder never overwrites an earlier generated asset.
    textures = [u.load_asset(p) for p in u.EditorAssetLibrary.list_assets(folder, recursive=False)]
    texture = next((a for a in textures if isinstance(a, u.Texture2D)), None)
    if not texture:
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        params = u.ImportAssetParameters()
        params.is_automated, params.replace_existing = True, False
        assets = manager.import_asset(folder, manager.create_source_data(str(source)), params)
        texture = next((a for a in assets if isinstance(a, u.Texture2D)), None)
        assert texture, 'Height texture import failed'
        for name, value in {
            'srgb': False, 'compression_settings': u.TextureCompressionSettings.TC_MASKS,
            'virtual_texture_streaming': False,
            'power_of_two_mode': u.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO,
            'address_x': u.TextureAddress.TA_WRAP, 'address_y': u.TextureAddress.TA_WRAP,
        }.items():
            texture.set_editor_property(name, value)
        u.EditorAssetLibrary.set_metadata_tag(texture, 'OOWSourceHash', digest)
        assert u.EditorAssetLibrary.save_loaded_asset(texture)
    assert not texture.get_editor_property('srgb')
    assert str(u.EditorAssetLibrary.get_metadata_tag(texture, 'OOWSourceHash')) == digest
    return texture, digest


def add_dry_layer(material, texture):
    base_wet, rough_wet, color, roughness, wet_mask = weather_inputs(material)
    g, p = surface.Graph(material), u.MaterialProperty
    position, vertex_normal = g.position(), g.node(u.MaterialExpressionVertexNormalWS)
    vertical = g.custom('return 1.-smoothstep(.55,.9,abs(N.z));', {'N': vertex_normal})
    # Reuse the height at a facade-sized scale for both the sparse colour macro
    # and a low-frequency UV warp. Warping shifts the height field instead of
    # zeroing it, so it breaks tile repetition without touching relief coverage.
    patch_uv3 = g.custom(
        'return float3(float2(dot(P.xy,float2(.61,.79)),P.z)/max(Scale,100.)+'
        'float2(.173,.619),0);',
        {'P': position, 'Scale': g.scalar('OOWWeatheringPatchCm', PARAMETERS['OOWWeatheringPatchCm'])}, True,
        'OOW alley large sparse weathering regions')
    patch_uv = g.node(u.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
    g.connect(patch_uv3, patch_uv, '')
    warp_uv3 = g.custom(
        'return float3(float2(dot(P.xy,float2(.61,.79)),P.z)/max(Scale,100.)+'
        'float2(.723,.188),0);',
        {'P': position, 'Scale': g.scalar('OOWWeatheringPatchCm', PARAMETERS['OOWWeatheringPatchCm'])}, True,
        'OOW alley warp phase, offset so X/Y warp decorrelate')
    warp_uv = g.node(u.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
    g.connect(warp_uv3, warp_uv, '')
    patch_samples = []
    for node_uv in (patch_uv, warp_uv):
        sample = g.node(u.MaterialExpressionTextureSampleParameter2D,
                        parameter_name='OOWPlasterHeight', texture=texture,
                        sampler_type=u.MaterialSamplerType.SAMPLERTYPE_MASKS,
                        mip_value_mode=u.TextureMipValueMode.TMVM_MIP_BIAS)
        g.connect(node_uv, sample, 'UVs')
        g.connect(g.constant(3.), sample, 'Bias')
        patch_samples.append(sample)
    patch_sample, warp_sample = patch_samples
    uv3 = g.custom('return float3((float2(abs(N.y)>.55?P.x:P.y,P.z)'
                   '+(float2(WX,WY)-.5)*Warp)/max(Scale,20.),0);',
                   {'P': position, 'N': vertex_normal,
                    'Scale': g.scalar('OOWWeatheringTileCm', PARAMETERS['OOWWeatheringTileCm']),
                    'WX': (patch_sample[0], 'R'), 'WY': (warp_sample[0], 'R'),
                    'Warp': g.scalar('OOWWeatheringWarpCm', PARAMETERS['OOWWeatheringWarpCm'])}, True,
                   'OOW alley world-aligned plaster warped by facade-scale noise, centimetres')
    uv = g.node(u.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
    g.connect(uv3, uv, '')
    samples = []
    for bias in (0., 2.):
        sample = g.node(u.MaterialExpressionTextureSampleParameter2D,
                        parameter_name='OOWPlasterHeight', texture=texture,
                        sampler_type=u.MaterialSamplerType.SAMPLERTYPE_MASKS,
                        mip_value_mode=u.TextureMipValueMode.TMVM_MIP_BIAS)
        g.connect(uv, sample, 'UVs')
        g.connect(g.constant(bias), sample, 'Bias')
        samples.append((sample[0], 'R'))
    detail, height = samples
    exposure = g.custom('return (1.-smoothstep(T-.05,T+.05,H))*smoothstep(.60,.72,Patch)*V;',
                         {'H': height, 'Patch': (patch_sample[0], 'R'), 'V': vertical,
                          'T': g.scalar('OOWExposureCoverage', PARAMETERS['OOWExposureCoverage'])},
                         description='OOW alley shared sparse exposure for color and roughness')
    # Relief keeps the dense threshold-only mask: the sparse macro gate would
    # erase the height gradient on ~95% of the wall, which is exactly where
    # the eye reads plaster relief. Tighter +/-.025 edge steepens the boundary.
    relief_exposure = g.custom('return (1.-smoothstep(T-.025,T+.025,H))*V;',
                               {'H': height, 'V': vertical,
                                'T': g.scalar('OOWExposureCoverage', PARAMETERS['OOWExposureCoverage'])},
                               description='OOW alley dense relief exposure, independent of sparse regions')
    grain = g.custom('return clamp((D-H)*4.,-.5,.5);', {'D': detail, 'H': height},
                     description='OOW alley fine aggregate separated from macro relief')
    dry_color = g.custom(
        'float l=max(dot(C,float3(.2126,.7152,.0722)),.01); '
        'float3 plaster=C*(lerp(.34,l,saturate(Contrast))/l); '
        'float3 mortar=float3(.255,.238,.213)*(1.+.10*G); '
        'return lerp(C,lerp(plaster,mortar,E),V);',
        {'C': color, 'E': exposure, 'G': grain, 'V': vertical,
         'Contrast': g.scalar('OOWWeatheringContrast', PARAMETERS['OOWWeatheringContrast'])}, True,
        'OOW alley dry plaster pigmentation and warm exposed mortar')
    dry_roughness = g.custom(
        'float plaster=clamp(.82+(R-.7)*.12+.025*G,.74,.9); '
        'float mortar=clamp(.91+.045*G,.86,.96); '
        'return lerp(R,lerp(plaster,mortar,E),V);',
        {'R': roughness, 'E': exposure, 'G': grain, 'V': vertical},
        description='OOW alley independent dry plaster and aggregate roughness')
    g.connect(dry_color, (base_wet, ''), 'C')
    g.connect(dry_roughness, (rough_wet, ''), 'R')
    original_normal = g.read(p.MP_NORMAL, (0, 0, 1))
    tangent = bool(material.get_editor_property('tangent_space_normal'))
    if tangent:
        transformed = g.node(u.MaterialExpressionTransform,
                             transform_source_type=u.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT,
                             transform_type=u.MaterialVectorCoordTransform.TRANSFORM_WORLD)
        g.connect(original_normal, transformed, '')
        original_normal = transformed
    physical_height = g.custom(
        'return -RE*max(Relief,0.)+'
        'G*.05*lerp(1.,.35,saturate(WetMask*2.))*V;',
        {'RE': relief_exposure, 'G': grain, 'V': vertical, 'WetMask': wet_mask,
         'Relief': g.scalar('OOWReliefStrength', PARAMETERS['OOWReliefStrength'])},
        description='OOW alley mortar recess matches exposure; wet streaks soften only fine grain')
    normal = g.custom(
        'float3 n=normalize(N), dx=ddx(P), dy=ddy(P); '
        'float3 rx=cross(dy,n), ry=cross(n,dx); float det=dot(dx,rx); '
        'float3 gradient=ddx(H)*rx+ddy(H)*ry; '
        'return abs(det)<1.e-7?n:normalize(abs(det)*n-sign(det)*gradient);',
        {'N': original_normal, 'P': position, 'H': physical_height}, True,
        'OOW alley physical height surface gradient over original normal')
    if tangent:
        transformed = g.node(u.MaterialExpressionTransform,
                             transform_source_type=u.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                             transform_type=u.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
        g.connect(normal, transformed, '')
        normal = transformed
    g.output(normal, p.MP_NORMAL)
    surface.ensure_mesh_usage(material)
    mel.recompile_material(material)


def v9_source(material):
    if material.get_path_name().startswith(DEST + '/'):
        path = str(u.EditorAssetLibrary.get_metadata_tag(material, 'OOWWeatheringSource'))
        material = u.load_asset(path)
        assert material, 'Missing pre-weathering source: ' + path
    assert str(u.EditorAssetLibrary.get_metadata_tag(material, 'OOWRecipe')) == 'v9'
    return material


def read_parameters(instance):
    names = set(map(str, mel.get_scalar_parameter_names(instance)))
    assert PARAMETERS.keys() <= names, 'Missing plaster parameters: ' + str(PARAMETERS.keys() - names)
    actual = {name: float(mel.get_material_instance_scalar_parameter_value(instance, name))
              for name in PARAMETERS}
    for name, expected in PARAMETERS.items():
        assert abs(actual[name] - expected) < 1.e-5, '%s: requested %s, read back %s' % (name, expected, actual[name])
    return actual


def adapt(current, texture, build_id, cache):
    current = v9_source(current)
    if current.get_path_name() in cache:
        return cache[current.get_path_name()]
    base, chain = current, []
    while isinstance(base, u.MaterialInstanceConstant):
        chain.append(base)
        base = base.get_editor_property('parent')
    assert isinstance(base, u.Material)
    assert str(u.EditorAssetLibrary.get_metadata_tag(base, 'OOWRecipe')) == 'v9'
    weather_inputs(base)
    name = surface.asset_name('M_Plaster', base.get_path_name() + '/' + build_id)
    parent, created = surface.duplicate(base, DEST, name, build_id)
    if created:
        add_dry_layer(parent, texture)
        surface.finish(parent, surface.original_material(base), build_id)
    for item in reversed(chain):
        name = surface.asset_name('MI_Plaster', item.get_path_name() + '/' + build_id)
        copied, created = surface.duplicate(item, DEST, name, build_id)
        if created:
            mel.set_material_instance_parent(copied, parent)
            u.EditorAssetLibrary.set_metadata_tag(copied, 'OOWWeatheringSource', item.get_path_name())
        if item == current:
            for parameter, value in PARAMETERS.items():
                # UE 5.7's setter updates the instance but always returns false.
                # Verify the resolved parameter names/values instead of its bool.
                mel.set_material_instance_scalar_parameter_value(copied, parameter, value)
            read_parameters(copied)
        if created or item == current:
            mel.update_material_instance(copied)
            surface.finish(copied, surface.original_material(item), build_id)
        parent = copied
    assert chain, 'Expected the imported instance chain'
    cache[current.get_path_name()] = parent
    return parent


def main():
    global u, mel, surface
    import unreal as u
    root = Path(u.Paths.project_dir()).parent
    sys.path.insert(0, str(root / 'Scripts'))
    import build_surface_materials as surface  # Its __main__ guard prevents scene rebuilds.
    mel = u.MaterialEditingLibrary
    surface.u, surface.mel = u, mel
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    assert levels.load_level('/Game/Maps/Alley')
    metadata = json.loads((root / 'Migration/Exported/alley.json').read_text(encoding='utf-8'))
    semantics = {n['name']: n for n in metadata['nodes']}
    actors = {a.get_actor_label(): a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    pending = []
    for label, source_name in TARGETS.items():
        assert label in actors and semantics[label]['materials'] == [source_name], label
        comp = actors[label].get_component_by_class(u.StaticMeshComponent)
        assert comp and comp.get_num_materials() == 1, label
        current = comp.get_material(0)
        assert current, label
        v9_source(current)
        pending.append((label, comp, current))
    texture, digest = import_height(root)
    build_id = VERSION + '_' + hashlib.sha256((digest + Path(__file__).read_text(encoding='utf-8')).encode()).hexdigest()[:10]
    cache, changes = {}, []
    replacements = [(label, comp, current, adapt(current, texture, build_id, cache))
                    for label, comp, current in pending]
    for label, comp, old, new in replacements:
        comp.set_material(0, new)
        assert comp.get_material(0) == new
        changes.append({'actor': label, 'slot': 0, 'sourceName': TARGETS[label],
                        'before': old.get_path_name(), 'after': new.get_path_name(),
                        'resolvedParameters': read_parameters(new)})
    assert levels.save_current_level(), 'Alley save failed'
    report = {'passed': True, 'version': VERSION, 'buildId': build_id, 'texture': texture.get_path_name(),
              'sourceHash': digest, 'parameters': PARAMETERS, 'changedSlots': changes, 'failures': []}
    (root / 'Migration/alley-weathering.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_ALLEY_WEATHERING_COMPLETE ' + json.dumps(report))


def self_test():
    root = Path(__file__).resolve().parents[1]
    nodes = {n['name']: n for n in json.loads((root / 'Migration/Exported/alley.json').read_text(encoding='utf-8'))['nodes']}
    assert TARGETS and all(nodes[label]['materials'] == [name] for label, name in TARGETS.items())
    assert 'OOW_00759_paris_building_09_7' in TARGETS
    assert 'OOW_00754_paris_building_09_2' not in TARGETS  # Visible trim is not the main wall.
    assert 0 < PARAMETERS['OOWExposureCoverage'] < 1
    assert 0 < PARAMETERS['OOWReliefStrength'] < 1
    assert 0 < PARAMETERS['OOWWeatheringWarpCm'] <= PARAMETERS['OOWWeatheringTileCm']
    print('Alley facade target contract passed:', len(TARGETS), 'slots; no Unreal import or asset writes')


if __name__ == '__main__':
    self_test() if '--self-test' in sys.argv else main()
