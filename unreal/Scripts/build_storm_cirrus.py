"""Add a high cirrus layer to the owned v3 storm-cloud graph (v4).

The window sees only 2.4% of the sky. The fair-weather okta there came from one
thing: the deck's overall density, whose response saturates (density -> okta was
0.4 at 0, 1.2 at 2e-4, 4.4 at 1e-3, 8.0 at 3e-2). No single smooth curve can
hit 晴 1.5 / 晴间多云 2.5 / 多云 4; the low two would be a razor-thin density
apart. A second independent layer fixes that: cirrus (high, thin, coverage-driven)
owns the fair-weather end.

Why it is a separate node, not part of the v3 shape: the v3 shape output is wired
as lerp(native, stormExtinction, weight), weight = smoothstep(0.15, 0.75, Storm).
Storm is 0 for every fair weather, so that lerp discards the whole owned graph
whenever it is not raining. Cirrus is fair-weather sky, so it is ADDED to the
final SubsurfaceColor after that lerp. CirrusStrength=0 reproduces v3 exactly.
No maps change.
"""
import hashlib
import json
from pathlib import Path
import sys

import unreal as u
sys.path.insert(0, str(Path(u.Paths.project_dir()).parent / 'Scripts'))
import build_storm_clouds as base
import build_storm_details as v3

RECIPE = 'storm-cirrus-v4'
MASTER = '/Game/Weather/M_OOW_StormCells_v4'
INSTANCE = '/Game/Weather/MI_OOW_StormCells_v4'
LIB = u.MaterialEditingLibrary
# pin name -> (scalar-parameter name, default). The shader body uses the short
# pin names; the material exposes the OOW_-prefixed names the runtime sets.
DEFAULTS = {'CirrusStrength': ('OOW_CirrusStrength', 1.0),
            'CirrusCoverage': ('OOW_CirrusCoverage', 0.5),
            'CirrusDensity': ('OOW_CirrusDensity', 0.004),
            'CirrusScaleKm': ('OOW_CirrusScaleKm', 6.0)}

# Thin high band: only the top slice of the cloud layer (h is 0..1 across it).
# Long streaked wisps come from two stretched noise octaves; a coverage offset
# keeps low cover as scattered streaks rather than a flat sheet.
CIRRUS_CODE = r'''float h = saturate(Height);
float band = smoothstep(0.60, 0.72, h) * (1.0 - smoothstep(0.86, 0.99, h));
float cirrusScale = max(CirrusScaleKm, 1.0);
float3 cp = float3(Position.xy * 0.00001, h) / cirrusScale;
float4 cc1 = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(cp * 0.9 + float3(0.21, 0.53, 0.07)), 0);
float4 cc2 = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(cp * 2.3 + float3(0.71, 0.19, 0.44)), 0);
float wisp = smoothstep(0.30, 0.80, cc1.r * 0.7 + cc2.g * 0.3);
float cover = saturate(CirrusCoverage);
float bandMask = band * smoothstep(0.10, 0.90, wisp + (cover - 0.5) * 0.9);
return float3(max(CirrusDensity, 0.0) * bandMask * saturate(CirrusStrength), 0.0, 0.0);'''

ADD_CODE = 'return A + B;'


def finish(asset, code_hash):
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWRecipe', RECIPE)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWCodeHash', code_hash)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWBuildComplete', 'true')
    if not u.EditorAssetLibrary.save_loaded_asset(asset):
        raise RuntimeError('Cannot save ' + asset.get_path_name())


def main():
    scripts = Path(u.Paths.project_dir()).parent / 'Scripts'
    code_hash = hashlib.sha256('\n'.join((scripts / n).read_text(encoding='utf-8')
        for n in ('build_storm_clouds.py', 'build_storm_details.py', 'build_storm_cirrus.py')).encode()).hexdigest()
    material, instance = u.load_asset(MASTER), u.load_asset(INSTANCE)
    if material or instance:
        for asset, cls in ((material, u.Material), (instance, u.MaterialInstanceConstant)):
            if not isinstance(asset, cls) or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWRecipe')) != RECIPE:
                raise RuntimeError('Refusing an unrelated or incomplete v4 asset')
            if str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWCodeHash')) != code_hash:
                raise RuntimeError('Generated v4 source hash changed; preserve the asset and version the recipe')
            if str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWBuildComplete')) != 'true':
                raise RuntimeError('Refusing an incomplete v4 asset')
        u.log('OOW_STORM_CIRRUS_REUSED ' + instance.get_path_name())
        return
    master_v3 = u.load_asset(v3.MASTER)
    instance_v3 = u.load_asset(v3.INSTANCE)
    for asset, cls in ((master_v3, u.Material), (instance_v3, u.MaterialInstanceConstant)):
        if not isinstance(asset, cls) or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWRecipe')) != v3.RECIPE:
            raise RuntimeError('Missing owned v3 input asset')
        if str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWBuildComplete')) != 'true':
            raise RuntimeError('Incomplete v3 input asset')
    material = u.EditorAssetLibrary.duplicate_asset(master_v3.get_path_name(), MASTER)
    if not material:
        raise RuntimeError('Cannot duplicate v3 storm master')
    prefix = material.get_path_name() + ':'
    graph = base.Graph(material)
    attributes = graph.node(u.MaterialExpressionCloudSampleAttribute)
    height = attributes[0], 'NormAltitudeInLayer'
    noise_object = graph.node(u.MaterialExpressionTextureObjectParameter,
        parameter_name='OOW_StormNoise',
        texture=u.load_asset(base.NOISE_PATH),
        sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    world = next((n for n in u.ObjectIterator(u.MaterialExpressionWorldPosition)
        if n.get_path_name().startswith(prefix)), None)
    if world is None:
        raise RuntimeError('v3 master lost its world-position node')
    cirrus_inputs = {'Position': (world, ''), 'Height': height, 'NoiseTex': noise_object}
    for pin_name, (param_name, value) in DEFAULTS.items():
        cirrus_inputs[pin_name] = graph.scalar(param_name, value)
    cirrus = graph.custom(CIRRUS_CODE, cirrus_inputs,
        description='OOW v4 high cirrus band (fair-weather sky)')
    cirrus_ext = graph.channel(cirrus, 'r')
    # Add cirrus on top of whatever the SubsurfaceColor already resolves to, so
    # the storm gate (weight) cannot discard it in fair weather.
    native = graph.read(u.MaterialProperty.MP_SUBSURFACE_COLOR,
        graph.node(u.MaterialExpressionConstant3Vector, constant=u.LinearColor(0, 0, 0, 1)))
    combined = graph.custom(ADD_CODE, {'A': native, 'B': cirrus_ext},
        description='OOW v4 cirrus added after the storm blend')
    graph.output(combined, u.MaterialProperty.MP_SUBSURFACE_COLOR)
    LIB.layout_material_expressions(material)
    LIB.recompile_material(material)
    finish(material, code_hash)
    instance = u.EditorAssetLibrary.duplicate_asset(instance_v3.get_path_name(), INSTANCE)
    if not instance:
        raise RuntimeError('Cannot duplicate v3 storm instance')
    LIB.set_material_instance_parent(instance, material)
    finish(instance, code_hash)
    report = dict(recipe=RECIPE, master=material.get_path_name(), instance=instance.get_path_name(),
        sourceMaster=master_v3.get_path_name(), sourceInstance=instance_v3.get_path_name(),
        codeSha256=code_hash, shapeCodeSha256=hashlib.sha256(CIRRUS_CODE.encode()).hexdigest(),
        defaults={k: v[1] for k, v in DEFAULTS.items()},
        changes='Adds a thin high cirrus band to SubsurfaceColor after the storm blend; deck graph unchanged.',
        zeroStrength='CirrusStrength=0 makes the added term 0 (v3 output).',
        compilationVerified=False, mapsModified=False)
    target = Path(u.Paths.project_dir()).parent / 'Migration/storm-cloud-cirrus-material.json'
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    u.log('OOW_STORM_CIRRUS ' + json.dumps(report))


if __name__ == '__main__':
    main()
