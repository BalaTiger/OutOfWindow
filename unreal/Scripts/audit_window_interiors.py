"""Read-only Alley asset audit. Writes JSON evidence; never saves UE assets.

Run after build_window_interiors.py and build_surface_materials.py, in NullRHI.
Geometry bytes were verified by the generator; this checks their import settings
and actual assigned material graph. GPU appearance still requires visual review.
"""
import collections
import hashlib
import json
from pathlib import Path


def main():
    import unreal as u
    mel = u.MaterialEditingLibrary
    root = Path(u.Paths.project_dir()).parent
    output = root / 'Migration' / 'window-interiors-audit.json'
    report = {'map': '/Game/Maps/Alley', 'readOnly': True, 'actors': [],
              'materials': {}, 'masters': {}, 'textures': {}, 'failures': []}

    def check(condition, scope, message):
        if not condition:
            report['failures'].append({'scope': scope, 'error': message})

    def metadata(asset, key):
        return str(u.EditorAssetLibrary.get_metadata_tag(asset, key))

    def texture_audit(texture):
        path = texture.get_path_name()
        if path in report['textures']:
            return
        properties = ('srgb', 'address_x', 'address_y', 'mip_gen_settings',
                      'power_of_two_mode', 'virtual_texture_streaming', 'compression_settings')
        values = {key: texture.get_editor_property(key) for key in properties}
        report['textures'][path] = {key: value if isinstance(value, bool) else str(value)
                                    for key, value in values.items()}
        expected = {'srgb': True, 'address_x': u.TextureAddress.TA_CLAMP,
                    'address_y': u.TextureAddress.TA_CLAMP,
                    'mip_gen_settings': u.TextureMipGenSettings.TMGS_BLUR2,
                    'power_of_two_mode': u.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO,
                    'virtual_texture_streaming': False,
                    'compression_settings': u.TextureCompressionSettings.TC_DEFAULT}
        for key, value in expected.items():
            check(values[key] == value, path, 'Unexpected texture setting: ' + key)
        report['textures'][path]['mipEvidence'] = 'Native mip generation enabled; resident mip count is not exposed by this audit'

    def master_audit(master):
        path = master.get_path_name()
        if path in report['masters']:
            return
        evidence = {'nodes': [], 'edges': [], 'uvChannels': [], 'roomParameters': []}
        report['masters'][path] = evidence
        root_node = mel.get_material_property_input_node(master, u.MaterialProperty.MP_EMISSIVE_COLOR)
        check(root_node is not None, path, 'Emissive has no input node')
        check(not master.get_editor_property('use_material_attributes'), path, 'Unsupported material attributes graph')
        queue, seen, counts = [root_node] if root_node else [], set(), collections.Counter()
        room_nodes, uv_nodes, object_nodes, custom_codes, mip_bias_nodes = [], [], [], [], []
        while queue:
            node = queue.pop()
            name = node.get_path_name()
            if name in seen:
                continue
            seen.add(name)
            kind = node.get_class().get_name()
            counts[kind] += 1
            entry = {'node': name, 'class': kind}
            check('WorldPosition' not in kind or kind == 'MaterialExpressionObjectPositionWS',
                  path, 'Per-pixel WorldPosition in emissive dependency: ' + name)
            check('MaterialFunctionCall' not in kind, path,
                  'Emissive contains an unexpanded function; cannot prove its dependencies: ' + name)
            if kind == 'MaterialExpressionObjectPositionWS':
                object_nodes.append(name)
            if kind == 'MaterialExpressionTextureCoordinate':
                index = int(node.get_editor_property('coordinate_index'))
                entry.update(channel=index, vTiling=float(node.get_editor_property('v_tiling')))
                uv_nodes.append(entry)
            if kind == 'MaterialExpressionCustom':
                code = str(node.get_editor_property('code'))
                entry['code'] = code
                custom_codes.append(code)
                check('WorldPosition' not in code and 'GetWorldPosition' not in code, path,
                      'Custom code directly reads WorldPosition: ' + name)
            if kind == 'MaterialExpressionTextureSampleParameter2D':
                parameter = str(node.get_editor_property('parameter_name'))
                entry['parameter'] = parameter
                if parameter.startswith('OOWRoom'):
                    room_nodes.append(node)
                    evidence['roomParameters'].append(parameter)
                    mode = node.get_editor_property('mip_value_mode')
                    entry['mipValueMode'] = str(mode)
                    check(mode == u.TextureMipValueMode.TMVM_MIP_BIAS, path,
                          parameter + ' is not using native mip bias')
                    # Both APIs preserve input order, including unconnected pins.
                    pins = dict(zip(mel.get_material_expression_input_names(node),
                                    mel.get_inputs_for_material_expression(master, node)))
                    bias = pins.get('Bias') or pins.get('MipBias')
                    check(bias is not None, path, parameter + ' has no connected mip-bias input')
                    if bias:
                        entry['mipBiasInput'] = bias.get_path_name()
                        is_scalar = bias.get_class().get_name() == 'MaterialExpressionScalarParameter'
                        check(is_scalar, path, parameter + ' mip bias is not a scalar parameter')
                        if is_scalar:
                            check(str(bias.get_editor_property('parameter_name')) == 'OOWInteriorMipBias',
                                  path, parameter + ' uses an unexpected mip-bias parameter')
                            check(abs(float(bias.get_editor_property('default_value')) - 1.25) < 1e-6,
                                  path, parameter + ' mip-bias default must equal 1.25')
                            mip_bias_nodes.append(bias.get_path_name())
                    texture = node.get_editor_property('texture')
                    check(isinstance(texture, u.Texture2D), path, parameter + ' is not a Texture2D')
                    if isinstance(texture, u.Texture2D):
                        entry['defaultTexture'] = texture.get_path_name()
                        texture_audit(texture)
            inputs = [value for value in mel.get_inputs_for_material_expression(master, node) if value]
            for value in inputs:
                evidence['edges'].append({'from': name, 'input': value.get_path_name()})
            queue.extend(inputs)
            evidence['nodes'].append(entry)
        evidence['classCounts'] = dict(counts)
        evidence['uvChannels'] = sorted({node['channel'] for node in uv_nodes})
        evidence['objectPositionFallbackNodes'] = object_nodes
        evidence['mipBiasParameterNodes'] = sorted(set(mip_bias_nodes))
        expected_rooms = ['OOWRoom%02d' % i for i in range(1, 7)]
        check(sorted(evidence['roomParameters']) == expected_rooms, path, 'Emissive must depend on exactly six OOWRoom samples')
        check(len(mip_bias_nodes) == 6 and len(set(mip_bias_nodes)) == 1, path,
              'All six room samples must share OOWInteriorMipBias')
        check(any(node['channel'] == 1 and node['vTiling'] == -1 for node in uv_nodes), path,
              'Missing vertically flipped UV1 for room imagery')
        check(any(node['channel'] == 2 for node in uv_nodes), path, 'Missing UV2 room seed/enable channel')
        check(bool(object_nodes), path, 'Missing ObjectPositionWS fallback')
        check(any('step(.5,S.y)' in code and 'saturate(Enabled)' in code for code in custom_codes),
              path, 'Missing two-part interior enable gate')
        check(abs(mel.get_material_default_scalar_parameter_value(master, 'OOWInteriorEnabled')) < 1e-6,
              path, 'Master interior enable must default to zero')
        for node in room_nodes:
            upstream, visited = [node], set()
            channels = set()
            while upstream:
                current = upstream.pop()
                if current.get_path_name() in visited:
                    continue
                visited.add(current.get_path_name())
                if current.get_class().get_name() == 'MaterialExpressionTextureCoordinate':
                    channels.add(int(current.get_editor_property('coordinate_index')))
                upstream.extend(value for value in mel.get_inputs_for_material_expression(master, current) if value)
            check(channels == {1}, path, str(node.get_editor_property('parameter_name')) + ' must sample only UV1')

    def material_audit(material):
        path = material.get_path_name()
        if path in report['materials']:
            return
        evidence = {'chain': [], 'textures': {}}
        report['materials'][path] = evidence
        check(isinstance(material, u.MaterialInstanceConstant), path, 'Assigned interior material is not a leaf instance')
        if not isinstance(material, u.MaterialInstanceConstant):
            return
        evidence['enabled'] = mel.get_material_instance_scalar_parameter_value(material, 'OOWInteriorEnabled')
        check(abs(evidence['enabled'] - 1.) < 1e-6, path, 'Leaf interior enable must equal one')
        evidence['mipBias'] = mel.get_material_instance_scalar_parameter_value(material, 'OOWInteriorMipBias')
        check(abs(evidence['mipBias'] - 2.) < 1e-6, path, 'Resolved room mip bias must equal 2.0')
        evidence['gain'] = mel.get_material_instance_scalar_parameter_value(material, 'OOWInteriorGain')
        check(abs(evidence['gain'] - 1.8) < 1e-6, path, 'Resolved room gain must equal 1.8')
        current, seen = material, set()
        while current:
            name = current.get_path_name()
            if name in seen:
                check(False, path, 'Cyclic material parent chain')
                return
            seen.add(name)
            recipe, source = metadata(current, 'OOWRecipe'), metadata(current, 'OOWSource')
            evidence['chain'].append({'path': name, 'recipe': recipe, 'source': source})
            check(recipe == 'v5', name, 'Assigned chain is not recipe v5')
            check(bool(source) and source != 'None' and u.EditorAssetLibrary.does_asset_exist(source),
                  name, 'Missing original-source provenance')
            if isinstance(current, u.Material):
                evidence['master'] = name
                master_audit(current)
                break
            current = current.get_editor_property('parent')
        check(bool(current), path, 'Material chain has no master')
        for index in range(1, 7):
            parameter = 'OOWRoom%02d' % index
            texture = mel.get_material_instance_texture_parameter_value(material, parameter)
            check(isinstance(texture, u.Texture2D), path, 'Missing resolved ' + parameter)
            if isinstance(texture, u.Texture2D):
                evidence['textures'][parameter] = texture.get_path_name()
                texture_audit(texture)
        check(len(set(evidence['textures'].values())) == 6, path, 'Room parameters do not resolve to six distinct textures')

    try:
        geometry = json.loads((root / 'Migration' / 'window-interiors-geometry.json').read_text(encoding='utf-8'))
        expected = {entry['actor']: entry for entry in geometry['actors']}
        glb_hash = hashlib.sha256((root / 'Migration' / 'Generated' / 'alley-window-interiors.glb').read_bytes()).hexdigest()
        check(glb_hash == geometry['generatedSha256'], 'geometry', 'Generated GLB differs from imported report')
        levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
        if not levels.load_level(report['map']):
            raise RuntimeError('Cannot load Alley')
        mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
        actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
        tagged = {a.get_actor_label(): a for a in actors if isinstance(a, u.StaticMeshActor)
                  and 'OOWWindowInterior' in {str(tag) for tag in a.tags}}
        report['expectedTaggedActors'], report['actualTaggedActors'] = len(expected), len(tagged)
        check(set(tagged) == set(expected), 'actors', 'Tagged actor set differs from generated manifest: '
              + json.dumps({'missing': sorted(set(expected)-set(tagged)), 'extra': sorted(set(tagged)-set(expected))}))
        for label, actor in sorted(tagged.items()):
            try:
                comp, entry = actor.static_mesh_component, {'actor': label}
                report['actors'].append(entry)
                mesh = comp.static_mesh
                build = mesh_editor.get_lod_build_settings(mesh, 0)
                entry.update(mesh=mesh.get_path_name(), uvChannels=mesh_editor.get_num_uv_channels(mesh, 0),
                             fullPrecisionUV=bool(build.get_editor_property('use_full_precision_u_vs')),
                             generateLightmapUV=bool(build.get_editor_property('generate_lightmap_u_vs')),
                             originalMesh=metadata(mesh, 'OOWWindowOriginalMesh'),
                             geometryHash=metadata(mesh, 'OOWWindowGeometry'), materials=[])
                check(entry['uvChannels'] >= 3, label, 'Imported mesh lacks UV0/UV1/UV2')
                check(entry['fullPrecisionUV'], label, 'Room seed UV is not full precision')
                check(not entry['generateLightmapUV'], label, 'Automatic lightmap generation can overwrite room UVs')
                check(entry['geometryHash'] == glb_hash, label, 'Mesh geometry provenance hash differs')
                check(u.EditorAssetLibrary.does_asset_exist(entry['originalMesh']), label, 'Original mesh was not retained')
                for index in range(comp.get_num_materials()):
                    material = comp.get_material(index)
                    check(material is not None, label, 'Unassigned material slot ' + str(index))
                    if material:
                        entry['materials'].append(material.get_path_name())
                        material_audit(material)
            except Exception as error:
                check(False, label, str(error))
    except Exception as error:
        check(False, 'audit', str(error))
    report['passed'] = not report['failures']
    report['counts'] = {'actors': len(report['actors']), 'leafMaterials': len(report['materials']),
                        'masters': len(report['masters']), 'textures': len(report['textures']),
                        'failures': len(report['failures'])}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_WINDOW_INTERIORS_AUDIT ' + json.dumps({'passed': report['passed'], **report['counts']}))
    if report['failures']:
        raise RuntimeError('Window interior audit failed; see ' + str(output))


if __name__ == '__main__':
    main()
