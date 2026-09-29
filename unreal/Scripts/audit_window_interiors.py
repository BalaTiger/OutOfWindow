"""Read-only Alley asset audit. Writes JSON evidence; never saves UE assets.

Run after window geometry, hero rooms/backing clearance and surface materials,
in NullRHI. Reads generated UV flags/dimensions, imported meshes and assigned
material graphs. --self-test checks the generated GLB without UE and rejects
corrupt room dimensions. GPU appearance still requires visual review.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import sys


def allocation_contract(root, check):
    """Compare production selection with the approved per-window allocation."""
    import build_window_interiors as windows
    allocation = json.loads((root / 'Migration/window-technique-allocation.json').read_text(encoding='utf-8'))
    rows = allocation['windows']
    selected = {row['id'] for row in rows if row['proposedTechnique'] == 'simplified_3d'}
    detailed = {row['id'] for row in rows if row['proposedTechnique'] == 'baked_room_im'}
    split = {row['id'] for row in rows if row['roomConfigurations'] == 2}
    primary = {row['id'] for row in rows if row['roomConfigurations'] > 0}
    check(len(rows) == 45 and len(selected) == 14 and len(detailed) == 17
          and sum(row['roomConfigurations'] for row in rows) == 15,
          'allocation', 'Approved allocation must retain 15 physical rooms and 31 visible IM groups')
    check(set(windows.HERO_ROOM_IDS) == primary and set(windows.HERO_SPLIT_ROOM_IDS) == split,
          'allocation', 'Production hero selection differs from the approved physical openings')
    apertures = selected | {'2e308641366c36c4'}
    check(set(windows.HERO_APERTURE_ROOM_IDS) == apertures,
          'allocation', 'Production opening set omits a selected/duplicate pane or opens an extra window')
    check(set(windows.DETAILED_IM_ROOM_IDS) == detailed,
          'allocation', 'Detailed IM selection differs from the approved 17 visible groups')
    return apertures, detailed, primary, split


def generated_geometry_audit(root, geometry, check):
    """Read actual generated accessor bytes; imported meshes are linked by hash below."""
    import build_window_interiors as windows
    path = root / 'Migration' / 'Generated' / 'alley-window-interiors.glb'
    doc, blob = windows.read_glb(path)
    meshes = {mesh['name']: mesh for mesh in doc['meshes']}
    result = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'meshes': {},
              'flagEvidence': 'Generated GLB accessor bytes, matched to imported mesh provenance; not GPU pixel readback'}
    rejected = {entry['actor']: set() for entry in geometry['actors']}
    room_sizes = {room['seed']: (room['widthMeters'], room['heightMeters']) for room in geometry['rooms']}
    room_ids = {room['seed']: room['id'] for room in geometry['rooms']}
    aperture_ids, detailed_ids, _, _ = allocation_contract(root, check)
    check({room['id'] for room in geometry['rooms'] if room.get('flag') == 2} == aperture_ids,
          'geometry', 'Hero aperture manifest differs from the approved source openings and duplicate panes')
    check({room['id'] for room in geometry['rooms'] if room.get('flag') == 1} == detailed_ids,
          'geometry', 'Detailed IM manifest differs from the approved 17 groups')
    actual_apertures, actual_detailed, actual_basic = set(), set(), set()
    for rim in geometry['rejectedRims']:
        rejected[rim['actor']].update(rim['triangles'])
    for front, entries in ((False, geometry['actors']), (True, geometry['frontActors'])):
        for entry in entries:
            name = entry['actor']
            primitive = meshes[entry['assetName']]['primitives'][0]
            _, uv = windows.read_accessor(doc, blob, primitive['attributes']['TEXCOORD_2'])
            size_accessor = primitive['attributes'].get('TEXCOORD_3')
            check(size_accessor is not None, name, 'Generated mesh lacks UV3 room dimensions')
            sizes = windows.read_accessor(doc, blob, size_accessor)[1] if size_accessor is not None else None
            _, indices = windows.read_accessor(doc, blob, primitive['indices'])
            flags = []
            for index in range(0, len(indices), 3):
                values = [uv[indices[index + corner][0]] for corner in range(3)]
                check(len(set(values)) == 1, name, 'Room seed/flag varies across a triangle')
                flag = values[0][1]
                check(flag in (-1., .5, 1., 2.), name, 'Generated adapted mesh contains unsupported room flag')
                flags.append(flag)
                if flag > 0:
                    room_id = room_ids.get(values[0][0])
                    check(flag == (2. if room_id in aperture_ids else 1. if room_id in detailed_ids else .5), name,
                          'UV2 flag differs from the approved geometry/detailed/basic selection')
                    if flag == 2.:
                        actual_apertures.add(room_id)
                    elif flag == 1.:
                        actual_detailed.add(room_id)
                    elif flag == .5:
                        actual_basic.add(room_id)
                if sizes is not None:
                    dimensions = [sizes[indices[index + corner][0]] for corner in range(3)]
                    check(len(set(dimensions)) == 1, name, 'Room dimensions vary across a triangle')
                    check(all(math.isfinite(value) for pair in dimensions for value in pair),
                          name, 'Room dimensions contain non-finite values')
                    if flag > 0:
                        expected_size = room_sizes.get(values[0][0])
                        check(expected_size is not None, name, 'Room seed has no authored dimensions')
                        check(all(value > 0 for value in dimensions[0]), name, 'Room dimensions must be positive')
                        if expected_size is not None:
                            check(max(abs(a-b) for a, b in zip(dimensions[0], expected_size)) < .00001,
                                  name, 'UV3 dimensions differ from authored room dimensions')
                    else:
                        check(dimensions[0] == (1., 1.), name, 'Non-room face lacks safe placeholder dimensions')
            counts = collections.Counter(flags)
            if front:
                check(counts[-1.] == 0 and counts[.5] + counts[1.] + counts[2.] == entry['triangles'], name, 'Front glass contains non-room triangles')
            else:
                check(counts[.5] + counts[1.] + counts[2.] == entry['enabledTriangles'], name, 'Enabled room triangle count differs')
                check(counts[-1.] == entry['nonEmissiveRimTriangles'] + entry['nonEmissiveOtherTriangles'],
                      name, 'Non-emissive triangle count differs')
                check(all(flags[index] == -1. for index in rejected[name]), name, 'Rejected rim still has an emissive room flag')
            result['meshes'][name] = {'roomTriangles': counts[.5] + counts[1.] + counts[2.], 'heroApertureTriangles': counts[2.],
                                      'basicIMTriangles': counts[.5], 'detailedIMTriangles': counts[1.],
                                      'nonEmissiveTriangles': counts[-1.],
                                      'frontGlass': front, 'roomDimensionsUV': sizes is not None}
    check(actual_apertures == aperture_ids, 'geometry', 'Generated GLB must flag exactly the approved aperture rooms')
    check(actual_detailed == detailed_ids, 'geometry', 'Generated GLB must flag exactly the detailed IM rooms')
    check(actual_basic == set(room_ids.values()) - aperture_ids - detailed_ids,
          'geometry', 'Generated GLB basic IM coverage differs from the remaining source rooms')
    result['heroApertureRoomIds'] = sorted(actual_apertures)
    result['detailedIMRoomIds'] = sorted(actual_detailed)
    result['basicIMRoomCount'] = len(actual_basic)
    check(result['sha256'] == geometry['generatedSha256'], 'geometry', 'Generated GLB differs from imported report')
    return result


def main():
    import unreal as u
    mel = u.MaterialEditingLibrary
    root = Path(u.Paths.project_dir()).parent
    sys.path.insert(0, str(root / 'Scripts'))
    import build_surface_materials as surfaces
    import build_window_interiors as windows
    import build_interior_atlas as atlas_builder
    expected_texture_paths = ['/Game/Materials/OOW/InteriorMapping/T_RoomCube_%02d' % index for index in range(1, 7)]
    expected_recipe = surfaces.recipe_for(('glass', '', 'window'), interior=True)
    expected_scalars = surfaces.INTERIOR_OVERRIDES
    output = root / 'Migration' / 'window-interiors-audit.json'
    report = {'map': '/Game/Maps/Alley', 'readOnly': True, 'actors': [],
              'recipe': expected_recipe, 'materials': {}, 'masters': {}, 'textures': {},
              'frontActors': [], 'curtainActors': [], 'awningControls': [], 'heroActors': [], 'failures': []}
    atlas = None

    def check(condition, scope, message):
        if not condition:
            report['failures'].append({'scope': scope, 'error': message})

    def metadata(asset, key):
        return str(u.EditorAssetLibrary.get_metadata_tag(asset, key))

    def capture_input_audit(pins, path, description):
        capture = pins.get('Capture')
        value = capture.get_editor_property('constant') if isinstance(capture, u.MaterialExpressionConstant3Vector) else None
        check(value is not None and max(abs(a-b) for a, b in
              zip((value.r, value.g, value.b), atlas_builder.CAPTURE_CENTER)) < 1e-6,
              path, description + ' Capture must be a constant vector matching the baked cube probe')

    def texture_audit(texture):
        path = texture.get_path_name()
        if path in report['textures']:
            return
        check(isinstance(texture, u.TextureCube), path, 'Interior mapping texture must be a cube, not a perspective photo')
        properties = ('srgb', 'mip_gen_settings', 'compression_settings')
        values = {key: texture.get_editor_property(key) for key in properties}
        report['textures'][path] = {key: value if isinstance(value, bool) else str(value)
                                    for key, value in values.items()}
        expected = {'srgb': False, 'compression_settings': u.TextureCompressionSettings.TC_HDR_COMPRESSED,
                    'mip_gen_settings': u.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP}
        for key, value in expected.items():
            check(values[key] == value, path, 'Unexpected texture setting: ' + key)
        variant = expected_texture_paths.index(path.split('.')[0]) if path.split('.')[0] in expected_texture_paths else -1
        check(variant >= 0 and metadata(texture, 'OOWInteriorVariant') == str(variant), path, 'Room cube variant provenance differs')
        check(atlas is not None and metadata(texture, 'OOWRecipe') == atlas_builder.RECIPE
              and metadata(texture, 'OOWInteriorGeometry') == atlas['sourceGeometrySha256'],
              path, 'Room cube is stale or detached from its baked geometry')
        expected_calibration = [list(atlas_builder.BOX_MIN), list(atlas_builder.BOX_MAX), list(atlas_builder.CAPTURE_CENTER)]
        check(json.loads(metadata(texture, 'OOWInteriorCalibration')) == expected_calibration,
              path, 'Room cube calibration differs from the projection contract')
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
        custom_nodes = []
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
            check(kind != 'MaterialExpressionTime', path, 'Window interior has animated material input: ' + name)
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
                custom_nodes.append(node)
                check('WorldPosition' not in code and 'GetWorldPosition' not in code, path,
                      'Custom code directly reads WorldPosition: ' + name)
            if kind == 'MaterialExpressionTextureObjectParameter':
                check(str(node.get_editor_property('parameter_name')) == 'LocalWindowReflection',
                      path, 'Unexpected reflection texture parameter')
                check(isinstance(node.get_editor_property('texture'), u.TextureCube),
                      path, 'Local reflection parameter is not a cube')
            if kind == 'MaterialExpressionTextureSampleParameter2D':
                check(not str(node.get_editor_property('parameter_name')).startswith('OOWRoom'),
                      path, 'Legacy perspective-photo room sample remains in the emissive graph')
            if kind == 'MaterialExpressionTextureSampleParameterCube':
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
                    check(node.get_editor_property('sampler_type') == u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
                          path, parameter + ' must sample linear HDR room radiance')
                    check(isinstance(texture, u.TextureCube), path, parameter + ' is not a TextureCube')
                    if isinstance(texture, u.TextureCube):
                        entry['defaultTexture'] = texture.get_path_name()
                        index = int(parameter.removeprefix('OOWRoom')) - 1
                        check(texture.get_path_name().split('.')[0] == expected_texture_paths[index],
                              path, parameter + ' does not use its calibrated room cube')
                        texture_audit(texture)
            inputs = [value for value in mel.get_inputs_for_material_expression(master, node) if value]
            for value in inputs:
                evidence['edges'].append({'from': name, 'input': value.get_path_name()})
            queue.extend(inputs)
            evidence['nodes'].append(entry)
        evidence['classCounts'] = dict(counts)
        check(counts['MaterialExpressionTextureObjectParameter'] == 1
              and counts['MaterialExpressionSkyLightEnvMapSample'] == 0
              and counts['MaterialExpressionReflectionVectorWS'] == 1,
              path, 'Window lacks its shared local environment reflection')
        check(any('Ready<.5' in code and 'GetRayTracingQualitySwitch()' in code and 'distance(Camera,Capture)<1.' in code
                  and 'TextureCubeSampleLevel(LocalWindowReflection,LocalWindowReflectionSampler,R,2)' in code
                  for code in custom_codes), path, 'Local capture lacks its readiness/feedback guard or mip filtering')
        check(abs(mel.get_material_default_scalar_parameter_value(master, 'LocalWindowReflectionReady')) < 1e-6,
              path, 'Local capture must not display the placeholder before runtime binding')
        check(not counts['MaterialExpressionTime'], path, 'Window surface has time-driven animation')
        evidence['uvChannels'] = sorted({node['channel'] for node in uv_nodes})
        evidence['objectPositionFallbackNodes'] = object_nodes
        evidence['mipBiasParameterNodes'] = sorted(set(mip_bias_nodes))
        expected_rooms = ['OOWRoom%02d' % i for i in range(1, 7)]
        check(sorted(evidence['roomParameters']) == expected_rooms, path, 'Emissive must depend on exactly six OOWRoom samples')
        check(counts['MaterialExpressionTextureSampleParameterCube'] == 6, path,
              'Emissive must use exactly six calibrated room cube samples')
        check(len(mip_bias_nodes) == 6 and len(set(mip_bias_nodes)) == 1, path,
              'All six room samples must share OOWInteriorMipBias')
        check(any(node['channel'] == 1 for node in uv_nodes), path, 'Missing whole-room UV1')
        check(any(node['channel'] == 2 for node in uv_nodes), path, 'Missing UV2 room seed/enable channel')
        check(any(node['channel'] == 3 for node in uv_nodes), path, 'Missing UV3 room dimensions')
        check(bool(object_nodes), path, 'Missing ObjectPositionWS fallback')
        check(any('step(.25,S.y)' in code and 'saturate(Enabled)' in code for code in custom_codes),
              path, 'Missing two-part interior enable gate')
        check(any('S.y<-.5' in code and 'GlassLayer>.5 && S.y<.25' in code and
                  'return float3(0,0,0)' in code for code in custom_codes),
              path, 'Missing explicit non-emissive rim/unsupported-face guard')
        check(not ({'OOWInteriorHighlightGain', 'OOWInteriorHighlightThreshold'} & scalar_names)
              and not any('highlight*highlight' in code for code in custom_codes),
              path, 'Legacy photo highlight reconstruction remains in the room shader')
        check(any('room*max(0.,Intensity)' in code and 'step(.75,S.y)' in code for code in custom_codes),
              path, 'Calibrated radiance gain or detailed/basic room gate is absent')
        check(any('fresnel' in code and 'saturate(GlassLayer)' in code for code in custom_codes),
              path, 'Native glass backing cannot disable duplicate Fresnel attenuation')
        check(set(expected_scalars) | {'OOWInteriorGlassLayer'} <= scalar_names,
              path, 'Missing interior scalar parameters')
        check(abs(mel.get_material_default_scalar_parameter_value(master, 'OOWInteriorEnabled')) < 1e-6,
              path, 'Master interior enable must default to zero')
        check(abs(mel.get_material_default_scalar_parameter_value(master, 'OOWInteriorGlassLayer')) < 1e-6,
              path, 'Master must not assume that every room has a native glass front')
        check(master.get_editor_property('blend_mode') == u.BlendMode.BLEND_MASKED,
              path, 'Window panes lack masked openings for the authored hero rooms')
        check(0 < master.get_editor_property('opacity_mask_clip_value') < 1,
              path, 'A zero clip threshold would keep the hero window occluder')
        aperture = mel.get_material_property_input_node(master, u.MaterialProperty.MP_OPACITY_MASK)
        aperture_custom = isinstance(aperture, u.MaterialExpressionCustom)
        check(aperture_custom, path, 'Opacity mask has no explicit hero aperture')
        if aperture_custom:
            aperture_code = str(aperture.get_editor_property('code'))
            aperture_inputs = dict(zip(mel.get_material_expression_input_names(aperture),
                                       mel.get_inputs_for_material_expression(master, aperture)))
            aperture_seed = aperture_inputs.get('S')
            evidence['heroAperture'] = {'node': aperture.get_path_name(), 'code': aperture_code}
            check(str(aperture.get_editor_property('description')) == 'OOW hero aperture',
                  path, 'Opacity mask is not the authored hero aperture')
            check(aperture_code == 'return S.y>1.5 ? 0. : 1.;',
                  path, 'Hero aperture must use the integer semantic flag, without float seed equality')
            check(isinstance(aperture_seed, u.MaterialExpressionTextureCoordinate)
                  and int(aperture_seed.get_editor_property('coordinate_index')) == 2,
                  path, 'Hero aperture does not use the UV2 semantic flag')
            check(aperture.get_path_name() in seen, path, 'Hero aperture does not reach interior emission')
            emission_gate = False
            for node in custom_nodes:
                code = ''.join(str(node.get_editor_property('code')).split())
                if 'Aperture<.5' not in code or 'returnfloat3(0,0,0)' not in code:
                    continue
                pins = dict(zip(mel.get_material_expression_input_names(node),
                                mel.get_inputs_for_material_expression(master, node)))
                gate = pins.get('Aperture')
                emission_gate |= gate is not None and gate.get_path_name() == aperture.get_path_name()
            check(emission_gate, path, 'Hero openings do not disable the old image emission through the shared aperture')
        check(mel.get_material_property_input_node(master, u.MaterialProperty.MP_WORLD_POSITION_OFFSET) is None,
              path, 'Window panes have vertex animation')
        evidence['paneProperties'] = {}
        for property_name, expected_value in (('BASE_COLOR', (0., 0., 0.)), ('SPECULAR', .5),
                                              ('METALLIC', 0.), ('AMBIENT_OCCLUSION', 1.),
                                              ('NORMAL', (0., 0., 1.)), ('ROUGHNESS', None)):
            node = mel.get_material_property_input_node(master, getattr(u.MaterialProperty, 'MP_' + property_name))
            code = str(node.get_editor_property('code')) if isinstance(node, u.MaterialExpressionCustom) else ''
            check('step(.25,S.y)' in code, path, property_name + ' does not preserve non-pane source faces')
            evidence['paneProperties'][property_name] = {'code': code}
            if not isinstance(node, u.MaterialExpressionCustom):
                continue
            inputs = dict(zip(mel.get_material_expression_input_names(node),
                              mel.get_inputs_for_material_expression(master, node)))
            seed = inputs.get('S')
            check(isinstance(seed, u.MaterialExpressionTextureCoordinate)
                  and int(seed.get_editor_property('coordinate_index')) == 2,
                  path, property_name + ' does not use authored pane flags')
            value_node = inputs.get('V')
            if expected_value is None:
                check('lerp(.20,.16,saturate(W))' in code, path, 'Pane roughness lacks the soft dry/wet response')
            elif isinstance(expected_value, tuple):
                value = value_node.get_editor_property('constant') if isinstance(value_node, u.MaterialExpressionConstant3Vector) else None
                check(value is not None and max(abs(a-b) for a, b in zip((value.r, value.g, value.b), expected_value)) < 1e-6,
                      path, property_name + ' has an unexpected pane value')
            else:
                check(isinstance(value_node, u.MaterialExpressionConstant)
                      and abs(float(value_node.get_editor_property('r')) - expected_value) < 1e-6,
                      path, property_name + ' has an unexpected pane value')
        projection_inputs = set()
        evidence['roomProjections'] = []
        for node in room_nodes:
            upstream, visited = [node], set()
            channels, kinds, codes = set(), set(), []
            sample_inputs = mel.get_inputs_for_material_expression(master, node)
            uv_input = sample_inputs[0] if sample_inputs else None
            check(isinstance(uv_input, u.MaterialExpressionCustom)
                  and str(uv_input.get_editor_property('description')) == 'OOW room-box projection',
                  path, str(node.get_editor_property('parameter_name')) + ' must sample projection XYZ directly, without a ComponentMask')
            if uv_input:
                projection_inputs.add(uv_input.get_path_name())
            projections = []
            while upstream:
                current = upstream.pop()
                if current.get_path_name() in visited:
                    continue
                visited.add(current.get_path_name())
                kind = current.get_class().get_name()
                kinds.add(kind)
                if kind == 'MaterialExpressionTextureCoordinate':
                    channels.add(int(current.get_editor_property('coordinate_index')))
                if kind == 'MaterialExpressionCustom':
                    codes.append(str(current.get_editor_property('code')))
                    if str(current.get_editor_property('description')) == 'OOW room-box projection':
                        projections.append(current)
                upstream.extend(value for value in mel.get_inputs_for_material_expression(master, current) if value)
            parameter = str(node.get_editor_property('parameter_name'))
            evidence['roomProjections'].append({'parameter': parameter, 'uvChannels': sorted(channels),
                                                'nodeClasses': sorted(kinds), 'customCodes': codes})
            check({1, 3} <= channels <= {1, 2, 3}, path, parameter + ' must project authored UV1 using UV3 dimensions')
            check('MaterialExpressionCameraVectorWS' in kinds
                  and bool(kinds & {'MaterialExpressionVertexNormalWS', 'MaterialExpressionPixelNormalWS'})
                  and bool(codes), path, parameter + ' lacks view-dependent room projection')
            check(len(projections) == 1, path, parameter + ' does not use one explicit room-box projection')
            for projection in projections:
                check(projection.get_editor_property('output_type') == u.CustomMaterialOutputType.CMOT_FLOAT3,
                      path, parameter + ' cube direction is not float3')
                code = ''.join(str(projection.get_editor_property('code')).split())
                check('direction=hit-Capture;' in code and 'returndirection.xzy;' in code
                      and 'lo=float3(-1.8,-.45,0.)' in code and 'hi=float3(1.8,3.05,3.4)' in code,
                      path, parameter + ' lacks the calibrated room/cube coordinate transform')
                pins = dict(zip(mel.get_material_expression_input_names(projection),
                                mel.get_inputs_for_material_expression(master, projection)))
                capture_input_audit(pins, path, parameter + ' projection')
                for pin, channel in (('UV', 1), ('Size', 3), ('Seed', 2)):
                    value = pins.get(pin)
                    check(isinstance(value, u.MaterialExpressionTextureCoordinate)
                          and int(value.get_editor_property('coordinate_index')) == channel,
                          path, parameter + ' projection has an incorrect ' + pin + ' input')
                check(isinstance(pins.get('Normal'), u.MaterialExpressionVertexNormalWS)
                      and isinstance(pins.get('View'), u.MaterialExpressionCameraVectorWS),
                      path, parameter + ' projection lacks geometric normal or view direction')
        check(len(projection_inputs) == 1, path, 'Room samples do not share one projection')
        interiors = [node for node in custom_nodes if str(node.get_editor_property('description')).startswith('OOW calibrated baked HDR interior')]
        check(len(interiors) == 1, path, 'Room emission must use one calibrated interior node')
        for node in interiors:
            code = ''.join(str(node.get_editor_property('code')).split())
            check('hit=Projection.xzy+Capture;' in code, path, 'Room emission does not recover the calibrated room hit')
            pins = dict(zip(mel.get_material_expression_input_names(node),
                            mel.get_inputs_for_material_expression(master, node)))
            capture_input_audit(pins, path, 'Room emission')
            projection = pins.get('Projection')
            check(projection is not None and projection.get_path_name() in projection_inputs,
                  path, 'Room emission hit must use the same projection as the cube samples')

    def material_audit(material):
        path = material.get_path_name()
        check(isinstance(material, u.MaterialInstanceConstant), path, 'Assigned interior material is not a leaf instance')
        if not isinstance(material, u.MaterialInstanceConstant):
            return
        glass_layer = mel.get_material_instance_scalar_parameter_value(material, 'OOWInteriorGlassLayer')
        check(abs(glass_layer) < 1e-6, path, 'Background panes still assume a separate transparent front')
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
            check(isinstance(texture, u.TextureCube), path, 'Missing resolved ' + parameter)
            if isinstance(texture, u.TextureCube):
                evidence['textures'][parameter] = texture.get_path_name()
                check(texture.get_path_name().split('.')[0] == expected_texture_paths[index - 1],
                      path, parameter + ' resolved to an unexpected cube asset')
                texture_audit(texture)
        check(len(set(evidence['textures'].values())) == 6, path, 'Room parameters do not resolve to six distinct textures')

    def hero_audit(actors, by_name, geometry):
        import build_room_boxes as heroes
        manifest = json.loads((root / 'Migration' / 'hero-rooms.json').read_text(encoding='utf-8'))
        check(manifest['recipe'] == heroes.RECIPE and manifest.get('appliedToUnreal') is True,
              'heroRooms', 'Hero manifest is stale or not from a completed UE import')
        hero_source, planned_manifest = heroes.generate(root, write=False)
        hero_hash = hashlib.sha256(hero_source.read_bytes()).hexdigest()
        check(manifest['generatedSha256'] == hero_hash, 'heroRooms', 'Hero GLB differs from the imported manifest')
        check(planned_manifest['generatedSha256'] == hero_hash, 'heroRooms', 'Hero GLB differs from the current CPU room plan')
        _, _, primary, split = allocation_contract(root, check)
        expected_ids = (primary - split) | {source + suffix for source in split for suffix in ('_L', '_R')}
        check({room['id'] for room in manifest['rooms']} == expected_ids
              and len(manifest['rooms']) == 15, 'heroRooms', 'Hero manifest must contain exactly the 15 approved physical rooms')
        planned = {room['id']: room for room in planned_manifest['rooms']}
        check(set(planned) == expected_ids, 'heroRooms', 'Room builder selection differs from the approved openings')
        expected_actors = {part['name'] for room in manifest['rooms'] for part in (room, room['glass'])}
        tagged = {actor.get_actor_label() for actor in actors if 'OOWHeroRoom' in {str(tag) for tag in actor.tags}}
        check(tagged == expected_actors, 'heroRooms', 'Hero room/glass actors differ from the manifest')
        source_rooms = {room['id']: room for room in geometry['rooms']}
        report['heroGeometryHash'] = hero_hash
        expected_lights = {room['light']['name'] for room in planned.values() if room.get('light')}
        actual_lights = {actor.get_actor_label() for actor in actors if 'OOWHeroLight' in {str(tag) for tag in actor.tags}}
        check(actual_lights == expected_lights, 'heroLights', 'Local lamp actor set differs from the planned light budget')
        for room in manifest['rooms']:
            source_id = room.get('sourceRoomId')
            check(source_id in source_rooms and room['seed'] == source_rooms[source_id]['seed'],
                  room['name'], 'Hero room is detached from its authored window seed')
            check(source_id in primary and source_rooms.get(source_id, {}).get('flag') == 2,
                  room['name'], 'Hero room has no flagged opening in the facade')
            check(room.get('light') == planned.get(room['id'], {}).get('light'),
                  room['name'], 'Room lamp parameters differ from the planned selective lighting')
            check(room.get('occupied') == planned.get(room['id'], {}).get('occupied'),
                  room['name'], 'Room occupancy differs from its stable source seed')
            check(room.get('apertureSourceBounds') == planned.get(room['id'], {}).get('apertureSourceBounds'),
                  room['name'], 'Physical opening bounds differ from the approved merged/split source panes')
            check(room['materialSlots'] == ['surface', 'lamp'], room['name'],
                  'Simplified room must use the two shared surface/lamp sections')
            for glass, part in ((False, room), (True, room['glass'])):
                label = part['name']
                actor = by_name.get(label)
                check(isinstance(actor, u.StaticMeshActor), label, 'Hero mesh actor is absent')
                if not isinstance(actor, u.StaticMeshActor):
                    continue
                comp, tags = actor.static_mesh_component, {str(tag) for tag in actor.tags}
                mesh = comp.static_mesh
                expected_triangles = 2 if glass else planned[room['id']]['renderTriangles']
                entry = {'actor': label, 'room': room['id'], 'glass': glass,
                         'mesh': mesh.get_path_name() if mesh else None,
                         'actualTriangles': mesh.get_num_triangles(0) if mesh else None,
                         'expectedTriangles': expected_triangles,
                         'sourceTriangles': 2 if glass else planned[room['id']]['triangles'],
                         'visible': bool(comp.get_editor_property('visible')),
                         'hidden': bool(actor.get_editor_property('hidden')),
                         'visibleInRayTracing': bool(comp.get_editor_property('visible_in_ray_tracing')),
                         'materials': []}
                report['heroActors'].append(entry)
                check('OOWRoom_' + room['id'] in tags and ('OOWHeroGlass' in tags) == glass,
                      label, 'Hero room/glass tags do not identify the same authored room')
                check(entry['visible'] and not entry['hidden'] and entry['visibleInRayTracing'],
                      label, 'Hero interior or glass is hidden from the camera/reflections')
                check(mesh is not None and metadata(mesh, 'OOWRoomGeometry') == hero_hash,
                      label, 'Hero mesh provenance differs from generated geometry')
                check(entry['actualTriangles'] == expected_triangles,
                      label, 'Imported hero triangle count differs from the current CPU room plan')
                if mesh:
                    check(mesh.get_path_name() == part['unrealMesh'], label, 'Assigned hero mesh differs from manifest')
                material_names = ['glass'] if glass else room['materialSlots']
                check(comp.get_num_materials() == len(material_names), label, 'Hero material-slot count differs')
                for index, name in enumerate(material_names):
                    material = comp.get_material(index)
                    entry['materials'].append(material.get_path_name() if material else None)
                    if name == 'lamp':
                        is_instance = isinstance(material, u.MaterialInstanceConstant)
                        check(is_instance, label, 'Lamp must use a per-room occupancy instance')
                        if is_instance:
                            check(material.get_name() == 'MI_HeroRoom_lamp_' + ('on' if room['occupied'] else 'off')
                                  and metadata(material, 'OOWRecipe') == heroes.RECIPE,
                                  label, 'Lamp does not use the current shared occupancy material')
                            check(abs(mel.get_material_instance_scalar_parameter_value(material, 'Occupied') - float(room['occupied'])) < 1e-6,
                                  label, 'Lamp occupancy differs from its physical room')
                            material = material.get_editor_property('parent')
                    check(isinstance(material, u.Material), label, 'Hero material is missing or replaced by a window material')
                    if not isinstance(material, u.Material):
                        continue
                    check(material.get_name() == 'M_HeroRoom_' + name and metadata(material, 'OOWRecipe') == heroes.RECIPE,
                          label, 'Hero room has an unexpected material recipe')
                    check(material.get_editor_property('blend_mode') == (u.BlendMode.BLEND_TRANSLUCENT if glass else u.BlendMode.BLEND_OPAQUE),
                          label, 'Hero material has an incorrect blend mode')
                    check(material.get_editor_property('shading_model') == (u.MaterialShadingModel.MSM_THIN_TRANSLUCENT if glass else u.MaterialShadingModel.MSM_DEFAULT_LIT),
                          label, 'Hero material has an incorrect shading model')
                    emission = mel.get_material_property_input_node(material, u.MaterialProperty.MP_EMISSIVE_COLOR)
                    if name != 'lamp':
                        check(emission is None, label, 'Hero room surfaces must receive light instead of displaying an emissive image')
                    else:
                        check(emission is not None and {'Night', 'Occupied'} <= {str(value) for value in mel.get_scalar_parameter_names(material)},
                              label, 'Hero lamp lacks its day/night and occupancy emission control')
                    if glass:
                        check(material.get_editor_property('translucency_lighting_mode') == u.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING,
                              label, 'Hero glass does not use Surface Forward Shading')
            if room.get('light'):
                light = by_name.get(room['light']['name'])
                check(isinstance(light, u.PointLight) and set(room['light']['tags']) <= {str(tag) for tag in light.tags},
                      room['name'], 'Selected hero room has no tagged local lamp for shared night control')
        import clear_hero_backings as backings
        backing_manifest = json.loads((root / 'Migration/hero-backings.json').read_text(encoding='utf-8'))
        backing_hash = hashlib.sha256((root / 'Migration/Generated' / backings.SOURCE_GLB_NAME).read_bytes()).hexdigest()
        check(backing_manifest['recipe'] == backings.RECIPE and backing_manifest.get('appliedToUnreal') is True
              and backing_manifest['generatedSha256'] == backing_hash,
              'heroBackings', 'Source backing clearance is stale or not imported')
        check({entry['actor'] for entry in backing_manifest['actors']} == set(backings.TARGETS),
              'heroBackings', 'Backing clearance actor set differs from its source plan')
        actual_backing_actors = {actor.get_actor_label() for actor in actors if isinstance(actor, u.StaticMeshActor)
                                and actor.static_mesh_component.static_mesh
                                and metadata(actor.static_mesh_component.static_mesh, 'OOWHeroBackingSource') not in ('', 'None')}
        check(actual_backing_actors == set(backings.TARGETS), 'heroBackings',
              'A non-approved actor uses a cleared backing mesh, or an approved backing is missing')
        report['heroBackings'] = []
        for entry in backing_manifest['actors']:
            label = entry['actor']
            actor = by_name.get(label)
            check(isinstance(actor, u.StaticMeshActor), label, 'Cleared source backing actor is absent')
            if not isinstance(actor, u.StaticMeshActor):
                continue
            comp, expected = actor.static_mesh_component, backings.TARGETS[label]
            mesh, material = comp.static_mesh, comp.get_material(0)
            check(entry['sourceGeometryHash'] == expected[0] and entry['sourceTriangles'] == expected[1]
                  and set(entry['removedTriangleIds']) == expected[2]
                  and entry['retainedTriangles'] == expected[1] - len(expected[2]),
                  label, 'Backing clearance no longer removes only the approved source triangles')
            check(mesh is not None and mesh.get_path_name() == entry['unrealMesh']
                  and metadata(mesh, 'OOWHeroBackingGeometry') == backing_hash
                  and metadata(mesh, 'OOWHeroBackingOriginalMesh') == entry['originalMesh']
                  and u.EditorAssetLibrary.does_asset_exist(entry['originalMesh']),
                  label, 'Cleared backing mesh is missing or has lost source provenance')
            if mesh:
                check(mesh.get_num_triangles(0) == entry['retainedTriangles'], label,
                      'Imported backing triangle count differs from the exact retained source subset')
            check(comp.get_num_materials() == 1 and material is not None
                  and material.get_path_name() == entry['unrealMaterial'],
                  label, 'Backing clearance replaced the original surface material')
            report['heroBackings'].append({'actor': label, 'retainedTriangles': entry['retainedTriangles'],
                                           'geometryHash': metadata(mesh, 'OOWHeroBackingGeometry') if mesh else None})

    try:
        check(list(atlas_builder.TEXTURE_PATHS) == expected_texture_paths,
              'interiorAtlas', 'Room cube destinations differ from the six approved assets')
        atlas = json.loads((root / 'Migration/interior-atlas.json').read_text(encoding='utf-8'))
        check(atlas['recipe'] == atlas_builder.RECIPE and atlas.get('bakedInUnreal') is True
              and atlas['faceSize'] == atlas_builder.FACE_SIZE,
              'interiorAtlas', 'Room atlas is stale or has not completed all real-RHI captures')
        check(atlas.get('captureCenter') == list(atlas_builder.CAPTURE_CENTER),
              'interiorAtlas', 'Baked atlas probe differs from the shader calibration')
        check(hashlib.sha256((root / atlas['sourceGeometry']).read_bytes()).hexdigest() == atlas['sourceGeometrySha256'],
              'interiorAtlas', 'Baked cube source geometry differs from its manifest')
        check([room['cubeAsset'] for room in atlas['rooms']] == expected_texture_paths,
              'interiorAtlas', 'Baked atlas must contain six ordered distinct room cubes')
        for room in atlas['rooms']:
            check(room.get('captured') is True and room.get('textureClass') == 'TextureCube',
                  room['cubeAsset'], 'Room cube has no completed GPU capture evidence')
            check(hashlib.sha256((root / room['hdrExport']).read_bytes()).hexdigest() == room['hdrExportSha256'],
                  room['cubeAsset'], 'Exported linear HDR evidence differs from its bake')
        report['interiorAtlas'] = {'recipe': atlas['recipe'], 'faceSize': atlas['faceSize'],
                                   'sourceGeometrySha256': atlas['sourceGeometrySha256'], 'cubes': expected_texture_paths}
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
        by_name = {a.get_actor_label(): a for a in actors}
        hero_audit(actors, by_name, geometry)
        source_nodes = json.loads((root / 'Migration/Exported/alley.json').read_text(encoding='utf-8'))['nodes']
        # Keep expected coverage independent of the production classifier.
        cyan_curtains = {
            'OOW_00728_Paris_Building_08_paris_building_08_9',
            'OOW_00739_Paris_Building_08_paris_building_08_9__2_',
            'OOW_00751_Paris_Building_08_paris_building_08_9__3_',
        }
        expected_curtains = {node['name'] for node in source_nodes
                             if node['materials'] == ['MASTER_Curtains']} | cyan_curtains
        classified_curtains = {node['name'] for node in source_nodes if surfaces.source_curtain(node)}
        check(len(expected_curtains) == 74, 'curtainActors', 'Expected 71 original and three Cyan curtain actors')
        check(classified_curtains == expected_curtains, 'curtainActors', 'Curtain classification differs from the 74 source targets')
        curtain_states = ('visible', 'visible_in_ray_tracing', 'evaluate_world_position_offset',
                          'evaluate_world_position_offset_in_ray_tracing')
        for source in source_nodes:
            if source['name'] not in expected_curtains:
                continue
            label = source['name']
            actor = by_name.get(label)
            check(isinstance(actor, u.StaticMeshActor), label, 'Source curtain actor is missing')
            if not isinstance(actor, u.StaticMeshActor):
                continue
            comp = actor.static_mesh_component
            entry = {'actor': label, 'hidden': bool(actor.get_editor_property('hidden')),
                     **{name: bool(comp.get_editor_property(name)) for name in curtain_states}}
            report['curtainActors'].append(entry)
            check(entry['hidden'] and not any(entry[name] for name in curtain_states),
                  label, 'Source curtain remains visible or has motion enabled')
        check({entry['actor'] for entry in report['curtainActors']} == expected_curtains,
              'curtainActors', 'Saved map does not contain all 74 audited curtain targets')
        awning_label = 'OOW_00517_paris_building_04_16'
        awning = by_name.get(awning_label)
        check(isinstance(awning, u.StaticMeshActor), awning_label, 'Outdoor Cyan awning control is missing')
        if isinstance(awning, u.StaticMeshActor):
            comp = awning.static_mesh_component
            entry = {'actor': awning_label, 'hidden': bool(awning.get_editor_property('hidden')),
                     **{name: bool(comp.get_editor_property(name)) for name in curtain_states},
                     'materials': []}
            report['awningControls'].append(entry)
            check(not entry['hidden'] and all(entry[name] for name in curtain_states), awning_label,
                  'Outdoor Cyan awning must remain visible in raster/RT with WPO evaluation enabled')
            check(comp.get_num_materials() > 0, awning_label, 'Outdoor Cyan awning has no material')
            for slot in range(comp.get_num_materials()):
                material, seen = comp.get_material(slot), set()
                while material and not isinstance(material, u.Material):
                    path = material.get_path_name()
                    if path in seen:
                        material = None
                        break
                    seen.add(path)
                    material = material.get_editor_property('parent')
                connected = bool(material and mel.get_material_property_input_node(
                    material, u.MaterialProperty.MP_WORLD_POSITION_OFFSET))
                entry['materials'].append({'slot': slot, 'master': material.get_path_name() if material else None,
                                           'worldPositionOffsetConnected': connected})
                check(connected, awning_label, 'Outdoor Cyan awning material has no connected WPO output')
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
                check(entry['uvChannels'] >= 4, label, 'Imported mesh lacks UV0/UV1/UV2/UV3')
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
                         'hidden': bool(actor.get_editor_property('hidden')),
                         'visible': bool(comp.get_editor_property('visible')),
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
                check(entry['uvChannels'] >= 4 and entry['fullPrecisionUV'] and not entry['generateLightmapUV'],
                      label, 'Front mesh UV settings differ from geometry contract')
                check(not entry['castShadow'], label, 'Transparent front sheet must not cast an opaque shadow')
                check(entry['hidden'] and not entry['visible'] and not entry['visibleInRayTracing'],
                      label, 'Legacy front sheet still adds transparent reflections')
                for index in range(comp.get_num_materials()):
                    material = comp.get_material(index)
                    check(material is not None, label, 'Front glass material slot is unassigned')
                    if material:
                        entry['materials'].append(material.get_path_name())
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
                        'frontActors': len(report['frontActors']), 'curtainActors': len(report['curtainActors']),
                        'awningControls': len(report['awningControls']),
                        'heroRooms': sum(not actor['glass'] for actor in report['heroActors']),
                        'heroGlass': sum(actor['glass'] for actor in report['heroActors']),
                        'failures': len(report['failures'])}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_WINDOW_INTERIORS_AUDIT ' + json.dumps({'passed': report['passed'], **report['counts']}))
    if report['failures']:
        raise RuntimeError('Window interior audit failed; see ' + str(output))


def self_test():
    import os
    import shutil
    import tempfile
    import build_window_interiors as windows
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / 'Scripts'))
    failures = []
    def check(condition, scope, message):
        if not condition:
            failures.append({'scope': scope, 'error': message})
    # Generate isolated test bytes so this check never rewrites production import
    # evidence and does not require a preceding UE import of the current recipe.
    temporary_parent = root.parent / '.runtime/ue-window-rebuild'
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='audit-self-test-', dir=temporary_parent) as directory:
        test_root = Path(directory)
        (test_root / 'Migration/Exported').mkdir(parents=True)
        os.link(root / 'Migration/Exported/alley.glb', test_root / 'Migration/Exported/alley.glb')
        shutil.copyfile(root / 'Migration/window-technique-allocation.json',
                        test_root / 'Migration/window-technique-allocation.json')
        _, geometry = windows.generate(test_root)
        evidence = generated_geometry_audit(test_root, geometry, check)
        assert not failures, json.dumps(failures, indent=2)
        geometry['rooms'][0]['widthMeters'] += .1
        generated_geometry_audit(test_root, geometry, check)
        assert any(failure['error'] == 'UV3 dimensions differ from authored room dimensions' for failure in failures), \
            'Audit must reject room dimensions that do not match the generated mesh'
        geometry['rooms'][0]['widthMeters'] -= .1
        failures.clear()
        selected = next(room for room in geometry['rooms'] if room['flag'] == 1.)
        selected['flag'] = 2.
        generated_geometry_audit(test_root, geometry, check)
        assert any('Hero aperture manifest differs' in failure['error'] for failure in failures), \
            'Audit must reject an extra opening outside the approved selection'
    print(json.dumps({'generatedMeshCount': len(evidence['meshes']),
                      'nonEmissiveTriangles': sum(mesh['nonEmissiveTriangles'] for mesh in evidence['meshes'].values()),
                      'geometrySha256': evidence['sha256'], 'heroApertureGroups': len(evidence['heroApertureRoomIds']),
                      'detailedIMGroups': len(evidence['detailedIMRoomIds']), 'basicIMGroups': evidence['basicIMRoomCount'],
                      'corruptDimensionsRejected': True, 'extraOpeningRejected': True, 'passed': True}))


if __name__ == '__main__':
    self_test() if '--self-test' in sys.argv else main()
