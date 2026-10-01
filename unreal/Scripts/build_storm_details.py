"""Add unsaturated interior density to the owned v2 storm-cloud graph.

v3 retains the native graph, macro cell envelope, colours, AO and scattering.
DetailStrength=0 reproduces the v2 density exactly. At strength 1, the same two
volume-texture reads resolve kilometre lobes and a 350 m breakup, with porous
interiors instead of the v2 saturated constant-density core. No maps change.
"""
import hashlib
import json
from pathlib import Path
import sys

import unreal as u
sys.path.insert(0, str(Path(u.Paths.project_dir()).parent / 'Scripts'))
import build_storm_clouds as base

RECIPE = 'storm-details-v3'
MASTER = '/Game/Weather/M_OOW_StormCells_v3'
INSTANCE = '/Game/Weather/MI_OOW_StormCells_v3'
LIB = u.MaterialEditingLibrary
DEFAULTS = {'OOW_DetailStrength': 1.0, 'OOW_DetailScaleKm': 0.35,
            'OOW_DetailDensityScale': 0.9}


def replace_once(code, before, after):
    if code.count(before) != 1:
        raise RuntimeError('v2 generator no longer has the expected shape expression')
    return code.replace(before, after)


SHAPE_CODE = replace_once(base.SHAPE_CODE, 'float h = saturate(Height);',
    'float h = saturate(Height);\nfloat detail = saturate(DetailStrength);')
SHAPE_CODE = replace_once(SHAPE_CODE,
    'float4 coarse = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,\n    frac(noisePosition * 0.42 + float3(0.17, 0.31, 0.09)), 0);\nfloat4 fine = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,\n    frac(noisePosition * 1.65 + float3(0.63, 0.12, 0.47)), 0);',
    '''float fineFrequency = 1.0 / max(DetailScaleKm, 0.08);
float4 coarse = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(noisePosition * lerp(0.42, fineFrequency * 0.32, detail)
        + float3(0.17, 0.31, 0.09)), 0);
float4 fine = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(noisePosition * lerp(1.65, fineFrequency, detail)
        + float3(0.63, 0.12, 0.47)), 0);''')
SHAPE_CODE = replace_once(SHAPE_CODE,
    'float cells = saturate((envelope - erosion) * 1.65) * step(0.001, envelope);',
    '''float legacyCells = saturate((envelope - erosion) * 1.65) * step(0.001, envelope);
// v2 envelope=1 always saturated: its maximum erosion is only 0.316.
// Keep noise in the interior, rather than restricting it to the outer edge.
float lobe = smoothstep(0.32, 0.78, coarse.r * 0.75 + coarse.g * 0.25);
float breakup = smoothstep(0.25, 0.80, fine.r);
float detailedErosion = (0.60 - coarse.r) * max(Erosion, 0.40)
    + (0.60 - fine.g) * 0.18;
float bodyDensity = saturate((envelope - detailedErosion) * 1.05)
    * step(0.001, envelope);
// Density valleys remain optically thin over hundreds of metres, exposing
// successive lobes inside the same cell to real ray-marched illumination.
float detailedCells = bodyDensity * (0.10 + 0.90 * lobe * lobe)
    * (0.60 + 0.40 * breakup);
float cells = lerp(legacyCells, detailedCells, detail);''')
SHAPE_CODE = replace_once(SHAPE_CODE,
    '(0.15 * cells + max(DeckStrength, 0.0) * deck);',
    '(0.15 * lerp(1.0, max(DetailDensityScale, 0.05), detail) * cells + max(DeckStrength, 0.0) * deck);')


def finish(asset, code_hash):
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWRecipe', RECIPE)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWCodeHash', code_hash)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWBuildComplete', 'true')
    if not u.EditorAssetLibrary.save_loaded_asset(asset):
        raise RuntimeError('Cannot save ' + asset.get_path_name())


def main():
    scripts = Path(u.Paths.project_dir()).parent / 'Scripts'
    code_hash = hashlib.sha256(('\n'.join((scripts / n).read_text(encoding='utf-8')
        for n in ('build_storm_clouds.py', 'build_storm_details.py'))).encode('utf-8')).hexdigest()
    material, instance = u.load_asset(MASTER), u.load_asset(INSTANCE)
    if material or instance:
        for asset, cls in ((material, u.Material), (instance, u.MaterialInstanceConstant)):
            if not isinstance(asset, cls) or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWRecipe')) != RECIPE:
                raise RuntimeError('Refusing an unrelated or incomplete v3 asset')
            if str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWCodeHash')) != code_hash:
                raise RuntimeError('Generated v3 source hash changed; preserve the asset and version the recipe')
            if str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWBuildComplete')) != 'true':
                raise RuntimeError('Refusing an incomplete v3 asset')
        if instance.get_editor_property('parent') != material:
            raise RuntimeError('Unexpected v3 instance parent')
        u.log('OOW_STORM_DETAILS_REUSED ' + instance.get_path_name())
        return
    old_master = u.load_asset(base.FOLDER + '/' + base.MASTER_NAME)
    old_instance = u.load_asset(base.FOLDER + '/' + base.INSTANCE_NAME)
    for asset, cls in ((old_master, u.Material), (old_instance, u.MaterialInstanceConstant)):
        if not isinstance(asset, cls) or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWRecipe')) != base.RECIPE:
            raise RuntimeError('Missing owned v2 input asset')
        if str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWBuildComplete')) != 'true':
            raise RuntimeError('Incomplete v2 input asset')
    material = u.EditorAssetLibrary.duplicate_asset(old_master.get_path_name(), MASTER)
    if not material:
        raise RuntimeError('Cannot duplicate v2 storm master')
    prefix = material.get_path_name() + ':'
    shape = [e for e in u.ObjectIterator(u.MaterialExpressionCustom)
        if e.get_path_name().startswith(prefix) and str(e.get_editor_property('code')) == base.SHAPE_CODE]
    if len(shape) != 1:
        raise RuntimeError('Expected one v2 density expression')
    graph = base.Graph(material)
    pins = list(shape[0].get_editor_property('inputs'))
    for pin_name in ('DetailStrength', 'DetailScaleKm', 'DetailDensityScale'):
        pin = u.CustomInput()
        pin.set_editor_property('input_name', pin_name)
        pins.append(pin)
    shape[0].set_editor_property('inputs', pins)
    for pin_name, parameter in zip(('DetailStrength', 'DetailScaleKm', 'DetailDensityScale'), DEFAULTS):
        graph.connect(graph.scalar(parameter, DEFAULTS[parameter]), (shape[0], ''), pin_name)
    shape[0].set_editor_property('code', SHAPE_CODE)
    shape[0].set_editor_property('description', 'Storm v3 unsaturated interior density')
    LIB.layout_material_expressions(material)
    LIB.recompile_material(material)
    finish(material, code_hash)
    instance = u.EditorAssetLibrary.duplicate_asset(old_instance.get_path_name(), INSTANCE)
    if not instance:
        raise RuntimeError('Cannot duplicate v2 storm instance')
    LIB.set_material_instance_parent(instance, material)
    finish(instance, code_hash)
    report = dict(recipe=RECIPE, master=material.get_path_name(), instance=instance.get_path_name(),
        sourceMaster=old_master.get_path_name(), sourceInstance=old_instance.get_path_name(),
        codeSha256=code_hash, shapeCodeSha256=hashlib.sha256(SHAPE_CODE.encode()).hexdigest(),
        defaults=DEFAULTS, volumeTextureSamples=2, maxNeighbourCells=9,
        changes='Interior density modulation and noise scale only; native graph, macro envelope, colours, AO, phase and multiple scattering preserved.',
        zeroStrength='Exactly the v2 density expression and original sampling frequencies.',
        compilationVerified=False, mapsModified=False)
    target = Path(u.Paths.project_dir()).parent / 'Migration/storm-cloud-details-material.json'
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    u.log('OOW_STORM_DETAILS ' + json.dumps(report))


if __name__ == '__main__':
    main()
