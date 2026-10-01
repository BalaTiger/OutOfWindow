"""Repair only the generated storm-cells-v2 conservative density and position.

The first v2 commandlet build saved an Add(float4,float3) graph which SM6 rejects.
Replace that generated Add with an explicit float4 Custom node, preserving the
native cached G/B/A values. Engine materials, maps, cloud appearance parameters,
and the instance's overrides are not changed. The candidate's Position node is
also changed to WPT_DEFAULT: cloud shaders initialize this absolute ray-sample
position, but leave the no-material-offset position uninitialized. Both repairs
are idempotent; no cloud morphology code is changed.
"""
import hashlib
import json
from pathlib import Path
import sys

import unreal as u


def input_link(material, expression, pin):
    lib = u.MaterialEditingLibrary
    inputs = dict(zip(map(str, lib.get_material_expression_input_names(expression)),
        lib.get_inputs_for_material_expression(material, expression)))
    source = inputs.get(pin)
    if not source:
        raise RuntimeError('Missing expected generated input ' + pin)
    output = lib.get_input_node_output_name_for_material_expression(expression, source)
    if output is None:
        raise RuntimeError('Cannot resolve expected generated input ' + pin)
    return source, output


def main():
    scripts = Path(u.Paths.project_dir()).parent / 'Scripts'
    sys.path.insert(0, str(scripts))
    import build_storm_clouds as build
    lib = u.MaterialEditingLibrary
    material = u.load_asset(build.FOLDER + '/' + build.MASTER_NAME)
    instance = u.load_asset(build.FOLDER + '/' + build.INSTANCE_NAME)
    for asset, cls in ((material, u.Material), (instance, u.MaterialInstanceConstant)):
        if not isinstance(asset, cls) or str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWRecipe')) != build.RECIPE:
            raise RuntimeError('Repair is restricted to complete generated storm-cells-v2 assets')
        if str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWBuildComplete')) != 'true':
            raise RuntimeError('Refusing to repair an incomplete generated asset')
    if instance.get_editor_property('parent') != material:
        raise RuntimeError('Generated instance has a different material parent')
    prefix = material.get_path_name() + ':'
    advanced = [node for node in u.ObjectIterator(u.MaterialExpressionVolumetricAdvancedMaterialOutput)
        if node.get_path_name().startswith(prefix)]
    if len(advanced) != 1:
        raise RuntimeError('Expected the one preserved native advanced output')
    names = list(map(str, lib.get_material_expression_input_names(advanced[0])))
    pin = next((name for name in names if name.replace(' ', '').lower() == 'conservativedensity'), None)
    if pin is None:
        raise RuntimeError('Missing native ConservativeDensity input')
    current = input_link(material, advanced[0], pin)[0]
    repaired = False
    if isinstance(current, u.MaterialExpressionCustom):
        if str(current.get_editor_property('code')) != build.CONSERVATIVE_CODE:
            raise RuntimeError('Unexpected custom conservative-density graph')
    else:
        if not isinstance(current, u.MaterialExpressionAdd):
            raise RuntimeError('Expected the generated v2 Add to repair')
        native = input_link(material, current, 'A')
        addition = input_link(material, current, 'B')[0]
        if not isinstance(addition, u.MaterialExpressionMultiply):
            raise RuntimeError('Expected the generated conservative-density Multiply')
        weight = input_link(material, addition, 'B')
        if not isinstance(weight[0], u.MaterialExpressionCustom) or str(weight[0].get_editor_property('code')) != 'return smoothstep(0.15, 0.75, saturate(Storm));':
            raise RuntimeError('Unexpected storm transition input')
        build.preserve_native_conservative_density(build.Graph(material), weight, native_override=native)
        # Both nodes belong only to this adapter. Native layout/profile nodes,
        # all other generated properties, and the advanced output are retained.
        lib.delete_material_expression(material, current)
        lib.delete_material_expression(material, addition)
        repaired = True
    # Locate only the candidate shape's Position input; preserve every native
    # WorldPosition node and the two native texture-layout paths.
    shapes = [node for node in u.ObjectIterator(u.MaterialExpressionCustom)
        if node.get_path_name().startswith(prefix)
        and str(node.get_editor_property('code')) == build.SHAPE_CODE]
    if len(shapes) != 1:
        raise RuntimeError('Expected one generated storm-cell shape expression')
    position = input_link(material, shapes[0], 'Position')[0]
    if not isinstance(position, u.MaterialExpressionWorldPosition):
        raise RuntimeError('Candidate Position is not its expected WorldPosition node')
    current_offset_mode = position.get_editor_property('world_position_shader_offset')
    if current_offset_mode not in (u.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS,
            u.WorldPositionIncludedOffsets.WPT_DEFAULT):
        raise RuntimeError('Unexpected candidate world-position mode')
    position_repaired = current_offset_mode != u.WorldPositionIncludedOffsets.WPT_DEFAULT
    if position_repaired:
        position.set_editor_property('world_position_shader_offset', u.WorldPositionIncludedOffsets.WPT_DEFAULT)
    lib.layout_material_expressions(material)
    lib.recompile_material(material)
    code_hash = hashlib.sha256((scripts / 'build_storm_clouds.py').read_text(encoding='utf-8').encode('utf-8')).hexdigest()
    build.finish(material, code_hash)
    # Match generator reuse metadata; no instance parameters are changed.
    build.finish(instance, code_hash)
    report_path = Path(u.Paths.project_dir()).parent / 'Migration' / 'storm-cloud-material.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    report.update(codeSha256=code_hash, conservativeDensityFloat4Repair=True,
        stormWorldPosition='WPT_DEFAULT (absolute cloud ray-sample position)',
        compilationVerified=False)
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_STORM_CLOUD_REPAIRED ' + json.dumps({
        'master': material.get_path_name(), 'repaired': repaired,
        'worldPositionRepaired': position_repaired,
        'codeSha256': code_hash, 'compilationVerified': False,
    }))


if __name__ == '__main__':
    main()
