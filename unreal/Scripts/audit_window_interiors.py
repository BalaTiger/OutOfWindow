"""Read-only Alley asset audit. Writes JSON evidence; never saves UE assets.

Run after build_window_interiors.py and build_surface_materials.py, in NullRHI.
Reads generated UV flags, imported mesh settings and actual assigned material
graphs. --self-test checks generated GLB flags without UE. GPU appearance still
requires visual review.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys


def generated_geometry_audit(root, geometry, check):
    """Read actual generated accessor bytes; imported meshes are linked by hash below."""
    import build_window_interiors as windows
    path = root / 'Migration' / 'Generated' / 'alley-window-interiors.glb'
    doc, blob = windows.read_glb(path)
    meshes = {mesh['name']: mesh for mesh in doc['meshes']}
    result = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'meshes': {},
              'flagEvidence': 'Generated GLB accessor bytes, matched to imported mesh provenance; not GPU pixel readback'}
    rejected = {entry['actor']: set() for entry in geometry['actors']}
    for rim in geometry['rejectedRims']:
        rejected[rim['actor']].update(rim['triangles'])
    for front, entries in ((False, geometry['actors']), (True, geometry['frontActors'])):
        for entry in entries:
            name = entry['actor']
            primitive = meshes[entry['assetName']]['primitives'][0]
            _, uv = windows.read_accessor(doc, blob, primitive['attributes']['TEXCOORD_2'])
            _, indices = windows.read_accessor(doc, blob, primitive['indices'])
            flags = []
            for index in range(0, len(indices), 3):
                values = [uv[indices[index + corner][0]] for corner in range(3)]
                check(len(set(values)) == 1, name, 'Room seed/flag varies across a triangle')
                flag = values[0][1]
                check(flag in (-1., 1.), name, 'Generated adapted mesh contains unsupported room flag')
                flags.append(flag)
            counts = collections.Counter(flags)
            if front:
                check(counts[-1.] == 0 and counts[1.] == entry['triangles'], name, 'Front glass contains non-room triangles')
            else:
                check(counts[1.] == entry['enabledTriangles'], name, 'Enabled room triangle count differs')
                check(counts[-1.] == entry['nonEmissiveRimTriangles'] + entry['nonEmissiveOtherTriangles'],
                      name, 'Non-emissive triangle count differs')
                check(all(flags[index] == -1. for index in rejected[name]), name, 'Rejected rim still has an emissive room flag')
            result['meshes'][name] = {'roomTriangles': counts[1.], 'nonEmissiveTriangles': counts[-1.],
                                      'frontGlass': front}
    check(result['sha256'] == geometry['generatedSha256'], 'geometry', 'Generated GLB differs from imported report')
    return result


def main():
    import unreal as u
    mel = u.MaterialEditingLibrary
    root = Path(u.Paths.project_dir()).parent
    sys.path.insert(0, str(root / 'Scripts'))
    import build_surface_materials as surfaces
    import build_window_interiors as windows
    expected_recipe = surfaces.recipe_for(('glass', '', 'window'), interior=True)
    expected_scalars = surfaces.INTERIOR_OVERRIDES
    output = root / 'Migration' / 'window-interiors-audit.json'
    report = {'map': '/Game/Maps/Alley', 'readOnly': True, 'actors': [],
              'recipe': expected_recipe, 'materials': {}, 'masters': {}, 'textures': {},
              'frontActors': [], 'frontMaterials': {}, 'failures': []}

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
                    'mip_gen_settings': u.TextureMipGenSettings.TMGS_SHARPEN0,
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
        scalar_names = {str(name) for name in mel.get_scalar_parameter_names(master)}
        scalar_defaults = {name: mel.get_material_default_scalar_parameter_value(master, name)
                           for name in sorted(scalar_names) if name.startswith('OOWInterior')}
        evidence = {'nodes': [], 'edges': [], 'uvChannels': [], 'roomParameters': [],
                    'scalarDefaults': scalar_defaults}
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
                            entry['mipBiasDefault'] = float(bias.get_editor_property('default_value'))
                            check(abs(entry['mipBiasDefault'] - scalar_defaults.get('OOWInteriorMipBias', -999)) < 1e-6,
                                  path, parameter + ' mip-bias node differs from resolved master default')
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
        check(any('S.y<-.5' in code and 'GlassLayer>.5 && S.y<.5' in code and
                  'return float3(0,0,0)' in code for code in custom_codes),
              path, 'Missing explicit non-emissive rim/unsupported-face guard')
        check(any('Highlights' in code and 'highlight*highlight' in code and 'room*max(0.,Intensity)' in code
                  for code in custom_codes), path, 'Missing separate room base and HDR highlight contributions')
        check(any('fresnel' in code and 'saturate(GlassLayer)' in code for code in custom_codes),
              path, 'Native glass backing cannot disable duplicate Fresnel attenuation')
        check(set(expected_scalars) | {'OOWInteriorGlassLayer'} <= scalar_names,
              path, 'Missing v6 interior scalar parameters')
        check(abs(mel.get_material_default_scalar_parameter_value(master, 'OOWInteriorEnabled')) < 1e-6,
              path, 'Master interior enable must default to zero')
        check(abs(mel.get_material_default_scalar_parameter_value(master, 'OOWInteriorGlassLayer')) < 1e-6,
              path, 'Master must not assume that every room has a native glass front')
        specular = mel.get_material_property_input_node(master, u.MaterialProperty.MP_SPECULAR)
        check(specular is not None and specular.get_class().get_name() == 'MaterialExpressionCustom'
              and 'saturate(G)*step(.5,S.y)' in str(specular.get_editor_property('code')),
              path, 'Backing room panes do not disable their duplicate opaque specular layer')
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

    def material_audit(material, glass_backing):
        path = material.get_path_name()
        check(isinstance(material, u.MaterialInstanceConstant), path, 'Assigned interior material is not a leaf instance')
        if not isinstance(material, u.MaterialInstanceConstant):
            return
        glass_layer = mel.get_material_instance_scalar_parameter_value(material, 'OOWInteriorGlassLayer')
        check(abs(glass_layer - float(glass_backing)) < 1e-6, path,
              'Resolved glass-layer parameter does not match backing actor tag')
        if path in report['materials']:
            return
        evidence = {'chain': [], 'textures': {}, 'scalarValues': {}}
        report['materials'][path] = evidence
        for parameter, expected_value in expected_scalars.items():
            value = mel.get_material_instance_scalar_parameter_value(material, parameter)
            evidence['scalarValues'][parameter] = value
            check(abs(value - expected_value) < 1e-6, path, 'Resolved value differs from current recipe: ' + parameter)
        evidence['scalarValues']['OOWInteriorGlassLayer'] = glass_layer
        evidence['enabled'] = evidence['scalarValues']['OOWInteriorEnabled']
        evidence['mipBias'] = evidence['scalarValues']['OOWInteriorMipBias']
        evidence['gain'] = evidence['scalarValues']['OOWInteriorGain']
        current, seen = material, set()
        while current:
            name = current.get_path_name()
            if name in seen:
                check(False, path, 'Cyclic material parent chain')
                return
            seen.add(name)
            recipe, source = metadata(current, 'OOWRecipe'), metadata(current, 'OOWSource')
            evidence['chain'].append({'path': name, 'recipe': recipe, 'source': source})
            check(recipe == expected_recipe, name, 'Assigned chain is not current recipe ' + expected_recipe)
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

    def front_material_audit(material):
        path = material.get_path_name()
        if path in report['frontMaterials']:
            return
        check(isinstance(material, u.Material), path, 'Front glass is not the native material master')
        if not isinstance(material, u.Material):
            return
        properties = ('blend_mode', 'shading_model', 'translucency_lighting_mode', 'two_sided')
        values = {key: material.get_editor_property(key) for key in properties}
        evidence = {key: value if isinstance(value, bool) else str(value) for key, value in values.items()}
        report['frontMaterials'][path] = evidence
        expected = {'blend_mode': u.BlendMode.BLEND_TRANSLUCENT,
                    'shading_model': u.MaterialShadingModel.MSM_THIN_TRANSLUCENT,
                    'translucency_lighting_mode': u.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING,
                    'two_sided': True}
        for key, value in expected.items():
            check(values[key] == value, path, 'Unexpected front glass property: ' + key)
        check(metadata(material, 'OOWRecipe') == expected_recipe, path, 'Front glass recipe differs')
        evidence['scalarDefaults'] = {str(name): mel.get_material_default_scalar_parameter_value(material, name)
                                      for name in mel.get_scalar_parameter_names(material)}
        for name in ('Wetness', 'OOWGlassRoughness', 'OOWGlassDistortion'):
            check(name in evidence['scalarDefaults'], path, 'Missing front glass parameter ' + name)
        check(not list(mel.get_texture_parameter_names(material)), path, 'Front glass unexpectedly adds texture samples')
        opacity = mel.get_material_property_input_node(material, u.MaterialProperty.MP_OPACITY)
        is_zero = (opacity is not None and opacity.get_class().get_name() == 'MaterialExpressionConstant'
                   and abs(float(opacity.get_editor_property('r'))) < 1e-6)
        check(is_zero, path, 'Thin glass must have zero opaque-coating coverage')
        evidence['opacityCoatingCoverage'] = 0. if is_zero else None
        emission = mel.get_material_property_input_node(material, u.MaterialProperty.MP_EMISSIVE_COLOR)
        if emission and emission.get_class().get_name() == 'MaterialExpressionConstant3Vector':
            color = emission.get_editor_property('constant')
            evidence['emission'] = [color.r, color.g, color.b]
            check(max(abs(value) for value in evidence['emission']) < 1e-6, path, 'Front glass must not emit light')
        else:
            check(False, path, 'Cannot prove front glass has zero emission')
        outputs = []
        for node in u.ObjectIterator(u.MaterialExpressionThinTranslucentMaterialOutput):
            outer = node.get_outer()
            while outer and not isinstance(outer, u.Material):
                outer = outer.get_outer()
            if outer == material:
                outputs.append(node)
        check(len(outputs) == 1, path, 'Missing unique native thin-translucent output')
        for node in outputs:
            inputs = mel.get_inputs_for_material_expression(material, node)
            color_node = inputs[0] if inputs else None
            check(color_node is not None, path, 'Thin glass has no transmission input')
            if color_node and color_node.get_class().get_name() == 'MaterialExpressionConstant3Vector':
                color = color_node.get_editor_property('constant')
                evidence['transmissionColor'] = [color.r, color.g, color.b]
                check(all(0 < value <= 1 for value in evidence['transmissionColor']), path, 'Invalid glass transmission')
            else:
                check(False, path, 'Cannot verify native glass transmission color')

    try:
        geometry = json.loads((root / 'Migration' / 'window-interiors-geometry.json').read_text(encoding='utf-8'))
        check(geometry['recipe'] == windows.RECIPE, 'geometry', 'Geometry recipe is stale')
        check(geometry.get('appliedToUnreal') is True, 'geometry', 'Geometry report is not from a completed UE import')
        report['geometryFlags'] = generated_geometry_audit(root, geometry, check)
        expected = {entry['actor']: entry for entry in geometry['actors']}
        expected_fronts = {entry['actor']: entry for entry in geometry['frontActors']}
        backing_labels = {entry['backingActor'] for entry in geometry['frontActors']}
        glb_hash = report['geometryFlags']['sha256']
        levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
        if not levels.load_level(report['map']):
            raise RuntimeError('Cannot load Alley')
        mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
        actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
        tagged = {a.get_actor_label(): a for a in actors if isinstance(a, u.StaticMeshActor)
                  and 'OOWWindowInterior' in {str(tag) for tag in a.tags}}
        tagged_fronts = {a.get_actor_label(): a for a in actors if isinstance(a, u.StaticMeshActor)
                         and 'OOWWindowGlassFront' in {str(tag) for tag in a.tags}}
        actual_backings = {a.get_actor_label() for a in actors if isinstance(a, u.StaticMeshActor)
                           and 'OOWWindowGlassBacking' in {str(tag) for tag in a.tags}}
        report['expectedTaggedActors'], report['actualTaggedActors'] = len(expected), len(tagged)
        report['expectedFrontActors'], report['actualFrontActors'] = len(expected_fronts), len(tagged_fronts)
        check(set(tagged) == set(expected), 'actors', 'Tagged actor set differs from generated manifest: '
              + json.dumps({'missing': sorted(set(expected)-set(tagged)), 'extra': sorted(set(tagged)-set(expected))}))
        check(set(tagged_fronts) == set(expected_fronts), 'frontActors', 'Front actor set differs from generated manifest')
        check(actual_backings == backing_labels, 'backingActors', 'Backing tag set differs from actual generated front sheets')
        for label, actor in sorted(tagged.items()):
            try:
                comp, entry = actor.static_mesh_component, {'actor': label, 'glassBacking': label in actual_backings}
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
                        material_audit(material, entry['glassBacking'])
            except Exception as error:
                check(False, label, str(error))
        for label, actor in sorted(tagged_fronts.items()):
            try:
                comp = actor.static_mesh_component
                mesh = comp.static_mesh
                build = mesh_editor.get_lod_build_settings(mesh, 0)
                entry = {'actor': label, 'mesh': mesh.get_path_name(), 'materials': [],
                         'geometryHash': metadata(mesh, 'OOWWindowGeometry'),
                         'backingActor': metadata(mesh, 'OOWWindowSourceNode'),
                         'nanite': bool(mesh.get_editor_property('nanite_settings').enabled),
                         'lodCount': mesh_editor.get_lod_count(mesh),
                         'uvChannels': mesh_editor.get_num_uv_channels(mesh, 0),
                         'fullPrecisionUV': bool(build.get_editor_property('use_full_precision_u_vs')),
                         'generateLightmapUV': bool(build.get_editor_property('generate_lightmap_u_vs')),
                         'castShadow': bool(comp.get_editor_property('cast_shadow')),
                         'visibleInRayTracing': bool(comp.get_editor_property('visible_in_ray_tracing'))}
                report['frontActors'].append(entry)
                check(entry['geometryHash'] == glb_hash, label, 'Front mesh geometry provenance differs')
                check(entry['backingActor'] == expected_fronts[label]['backingActor'], label, 'Front/back mesh pairing differs')
                backing = tagged.get(entry['backingActor'])
                check(backing is not None, label, 'Front glass backing actor is absent')
                if backing:
                    transforms = []
                    for candidate in (actor, backing):
                        location, rotation, scale = (candidate.get_actor_location(), candidate.get_actor_rotation(),
                                                     candidate.get_actor_scale3d())
                        transforms.append([location.x, location.y, location.z, rotation.pitch, rotation.yaw,
                                           rotation.roll, scale.x, scale.y, scale.z])
                    entry['transform'], entry['backingTransform'] = transforms
                    check(max(abs(a-b) for a, b in zip(*transforms)) < .001, label,
                          'Front actor transform no longer matches its backing; offset belongs in generated mesh')
                check(not entry['nanite'], label, 'Transparent front sheet must not use Nanite')
                check(entry['lodCount'] >= 3, label, 'Front sheet lacks native LODs')
                entry['lods'] = []
                for lod in range(entry['lodCount']):
                    reduction = mesh_editor.get_lod_reduction_settings(mesh, lod)
                    entry['lods'].append({'index': lod, 'vertices': mesh_editor.get_number_verts(mesh, lod),
                                         'percentTriangles': float(reduction.get_editor_property('percent_triangles'))})
                check(len(entry['lods']) >= 3 and entry['lods'][1]['percentTriangles'] < 1
                      and entry['lods'][2]['percentTriangles'] < entry['lods'][1]['percentTriangles'],
                      label, 'Native LOD reductions are not configured')
                check(entry['uvChannels'] >= 3 and entry['fullPrecisionUV'] and not entry['generateLightmapUV'],
                      label, 'Front mesh UV settings differ from geometry contract')
                check(not entry['castShadow'], label, 'Transparent front sheet must not cast an opaque shadow')
                check(entry['visibleInRayTracing'], label, 'Front sheet is absent from ray tracing')
                for index in range(comp.get_num_materials()):
                    material = comp.get_material(index)
                    check(material is not None, label, 'Front glass material slot is unassigned')
                    if material:
                        entry['materials'].append(material.get_path_name())
                        front_material_audit(material)
            except Exception as error:
                check(False, label, str(error))
        from window_lookdev import audit_window_lighting
        report['lighting'] = audit_window_lighting(root, u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world())
        for failure in report['lighting'].get('failures', []):
            check(False, 'lighting', failure if isinstance(failure, str) else json.dumps(failure))
    except Exception as error:
        check(False, 'audit', str(error))
    report['passed'] = not report['failures']
    report['counts'] = {'actors': len(report['actors']), 'leafMaterials': len(report['materials']),
                        'masters': len(report['masters']), 'textures': len(report['textures']),
                        'frontActors': len(report['frontActors']), 'frontMaterials': len(report['frontMaterials']),
                        'failures': len(report['failures'])}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_WINDOW_INTERIORS_AUDIT ' + json.dumps({'passed': report['passed'], **report['counts']}))
    if report['failures']:
        raise RuntimeError('Window interior audit failed; see ' + str(output))


def self_test():
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / 'Scripts'))
    geometry = json.loads((root / 'Migration' / 'window-interiors-geometry.json').read_text(encoding='utf-8'))
    failures = []
    def check(condition, scope, message):
        if not condition:
            failures.append({'scope': scope, 'error': message})
    evidence = generated_geometry_audit(root, geometry, check)
    assert not failures, json.dumps(failures, indent=2)
    print(json.dumps({'generatedMeshCount': len(evidence['meshes']),
                      'nonEmissiveTriangles': sum(mesh['nonEmissiveTriangles'] for mesh in evidence['meshes'].values()),
                      'geometrySha256': evidence['sha256'], 'passed': True}))


if __name__ == '__main__':
    self_test() if '--self-test' in sys.argv else main()
