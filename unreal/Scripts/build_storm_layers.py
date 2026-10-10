"""Version the existing v4 graph with low clouds and an independently placed 8-10 km cirrus band.

One UE cloud volume contains both layers; no maps or old assets are modified.
All old normalized-height consumers are remapped before extending the containing volume.
"""
from pathlib import Path
import hashlib
import json
import sys
import unreal as u

sys.path.insert(0, str(Path(u.Paths.project_dir()).parent / 'Scripts'))
import build_storm_clouds as base
import build_storm_cirrus as v4

LIB = u.MaterialEditingLibrary
MASTER = '/Game/Weather/M_OOW_StormCells_v6'
INSTANCE = '/Game/Weather/MI_OOW_StormCells_v6'
RECIPE = 'storm-layers-v6'

def output(node, source):
    return source, LIB.get_input_node_output_name_for_material_expression(node, source)

def inputs(material, node):
    return dict(zip(map(str, LIB.get_material_expression_input_names(node)), LIB.get_inputs_for_material_expression(material, node)))

def finish(asset, code_hash):
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWRecipe', RECIPE)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWCodeHash', code_hash)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWBuildComplete', 'true')
    if not u.EditorAssetLibrary.save_loaded_asset(asset): raise RuntimeError('Cannot save ' + asset.get_path_name())

def main():
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    existing = [u.load_asset(MASTER), u.load_asset(INSTANCE)]
    if any(existing):
        for asset, cls in zip(existing, [u.Material, u.MaterialInstanceConstant]):
            if not isinstance(asset, cls) or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWRecipe')) != RECIPE \
                or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWCodeHash')) != code_hash \
                or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWBuildComplete')) != 'true':
                raise RuntimeError('Refusing unrelated or changed v6 asset')
        u.log('OOW_STORM_LAYERS_REUSED ' + INSTANCE)
        return
    old = u.load_asset(v4.MASTER)
    old_instance = u.load_asset(v4.INSTANCE)
    for asset in [old, old_instance]:
        if not asset or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWBuildComplete')) != 'true':
            raise RuntimeError('Missing complete v4 source')
    material = u.EditorAssetLibrary.duplicate_asset(old.get_path_name(), MASTER)
    if not material: raise RuntimeError('Cannot duplicate v4')
    graph = base.Graph(material)
    prefix = material.get_path_name() + ':'
    nodes = [n for n in u.ObjectIterator(u.MaterialExpression) if n.get_path_name().startswith(prefix)]
    custom = [n for n in nodes if isinstance(n, u.MaterialExpressionCustom)]
    cirrus = next(n for n in custom if 'CirrusDensity' in n.get_editor_property('code'))
    combined = next(n for n in custom if n.get_editor_property('code').strip() == 'return A + B;')
    low_extinction = output(combined, inputs(material, combined)['A'])
    attributes = graph.node(u.MaterialExpressionCloudSampleAttribute)
    altitude = attributes[0], 'Altitude' # cm, measured from SkyAtmosphere's ground radius
    bottom = graph.scalar('OOW_LowBottomKm', 2.2)
    height = graph.scalar('OOW_LowHeightKm', 2.5)
    normalized_low = graph.custom('return (Altitude * 0.00001 - Bottom) / max(Height, 0.01);',
        {'Altitude': altitude, 'Bottom': bottom, 'Height': height}, description='Original low-cloud normalized altitude')
    normalized_high = graph.custom('return (Altitude * 0.00001 - 8.0) / 2.0;',
        {'Altitude': altitude}, description='Independent 8-10 km high-cloud altitude')
    low_mask = graph.custom('return step(0.0, H) * step(H, 1.0);', {'H': normalized_low})
    high_mask = graph.custom('return step(0.0, H) * step(H, 1.0);', {'H': normalized_high})
    rewired = []
    for node in nodes:
        for pin, source in inputs(material, node).items():
            if isinstance(source, u.MaterialExpressionCloudSampleAttribute):
                name = output(node, source)[1]
                if name == 'NormAltitudeInLayer':
                    graph.connect(normalized_low, (node, ''), pin)
                    rewired.append(dict(node=node.get_name(), pin=pin))
                elif name == 'AltitudeInLayer':
                    raise RuntimeError('Unreviewed native AltitudeInLayer consumer')
    # Preserve v4's existing noise/wisp shape. Only height placement and motion change.
    graph.connect(normalized_high, (cirrus, ''), 'Height')
    code = cirrus.get_editor_property('code')
    code = code.replace('smoothstep(0.60, 0.72, h) * (1.0 - smoothstep(0.86, 0.99, h))',
                        'smoothstep(0.02, 0.10, h) * (1.0 - smoothstep(0.85, 0.98, h))')
    code = code.replace('Position.xy * 0.00001', '(Position.xy * 0.00001 - Placement.xy * LayoutScale)')
    # Support has a true empty-cloud side; density controls opacity inside the wisps.
    code = code.replace('smoothstep(0.10, 0.90, wisp + (cover - 0.5) * 0.9)',
                        'smoothstep(0.0, 0.025, wisp - (1.0 - cover))')
    existing_inputs = cirrus.get_editor_property('inputs')
    for name in ['Placement', 'LayoutScale']:
        pin = u.CustomInput()
        pin.set_editor_property('input_name', name)
        existing_inputs.append(pin)
    cirrus.set_editor_property('inputs', existing_inputs)
    cirrus.set_editor_property('code', code)
    graph.connect(graph.vector('Layout_GlobalTexturePlacement', (0,0,0,0)), (cirrus,''), 'Placement')
    graph.connect(graph.scalar('Layout_CloudGlobalScale', 32), (cirrus,''), 'LayoutScale')
    sheet = graph.scalar('OOW_OvercastSheetDensity',0)
    masked_low = graph.custom('float band = smoothstep(0.0,0.1,H) * (1.0-smoothstep(0.8,1.0,H)); return (Extinction + Sheet * band) * Mask;',
        {'Extinction': low_extinction, 'Mask': low_mask, 'H': normalized_low, 'Sheet': sheet}, vector=True)
    graph.connect(masked_low, (combined,''), 'A')
    advanced = next(n for n in nodes if isinstance(n, u.MaterialExpressionVolumetricAdvancedMaterialOutput))
    pin = next(n for n in inputs(material, advanced) if n.replace(' ','').lower() == 'conservativedensity')
    native_conservative = output(advanced, inputs(material, advanced)[pin])
    bound = graph.custom('return float4((Native.r * (Density > 0.0 ? 1.0 : 0.0) + Sheet) * Low + HighExtinction.r, Native.gba);',
        {'Native': native_conservative, 'Low': low_mask, 'HighExtinction': (cirrus, ''), 'Density': graph.scalar('Cloud_GlobalDensity',0), 'Sheet': sheet},
        output_type=u.CustomMaterialOutputType.CMOT_FLOAT4, description='Density-aware cloud bound retaining native low cache')
    graph.connect(bound, (advanced,''), pin)
    LIB.layout_material_expressions(material)
    LIB.recompile_material(material)
    finish(material, code_hash)
    instance = u.EditorAssetLibrary.duplicate_asset(old_instance.get_path_name(), INSTANCE)
    if not instance: raise RuntimeError('Cannot duplicate v4 instance')
    LIB.set_material_instance_parent(instance, material)
    finish(instance, code_hash)
    report = dict(recipe=RECIPE, master=MASTER, instance=INSTANCE, sourceMaster=v4.MASTER,
        codeSha256=code_hash, lowHeightConsumers=rewired, highAltitudeKm=[8,10],
        lowLayerPreserved=True, highLayerWindIntegrated=True, highConservativeDensity=True, zeroExtinctionSamplesSkipped=True, closedOvercastSheet=True,
        mapsModified=False, compilationVerified=False)
    (Path(u.Paths.project_dir()).parent / 'Migration/storm-cloud-layers-material.json').write_text(json.dumps(report,indent=2)+'\n')
    u.log('OOW_STORM_LAYERS ' + json.dumps(report))

if __name__ == '__main__': main()
