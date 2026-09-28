"""Read the saved City map in a fresh UE commandlet and verify its scene data."""
import json
import hashlib
import math
import struct
from pathlib import Path
import unreal as u


ROOT = Path(u.Paths.project_dir()).parent
MODERN = '/Game/Scenes/City/Modern/'


def xyz(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def two_sided(material):
    while isinstance(material, u.MaterialInstanceConstant):
        overrides = material.get_editor_property('base_property_overrides')
        if overrides.get_editor_property('override_two_sided'):
            return overrides.get_editor_property('two_sided')
        material = material.get_editor_property('parent')
    return bool(material and material.get_editor_property('two_sided'))


def connected_nodes(material, output):
    """Read saved expression links without requiring compiled RHI resources."""
    pending = [u.MaterialEditingLibrary.get_material_property_input_node(material, output)]
    visited = set()
    while pending:
        node = pending.pop()
        if not node or node.get_path_name() in visited:
            continue
        visited.add(node.get_path_name())
        yield node
        pending.extend(u.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))


def connected_textures(material, output):
    textures = set()
    for node in connected_nodes(material, output):
        if isinstance(node, u.MaterialExpressionTextureSample):
            texture = node.get_editor_property('texture')
            if texture:
                textures.add(texture.get_path_name())
    return textures


def audit_sidewalk(actors, expected, tree_instances, mesh_editor, check):
    authored = json.loads((ROOT / 'Art/City/city-sidewalk.json').read_text(encoding='utf-8'))
    source = (ROOT / 'Art/City/city-sidewalk.glb').read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    check(authored.get('sourceGeometry', {}).get('sha256') == digest,
          'Sidewalk geometry checks are stale relative to the authored GLB')
    check(expected.get('sha256') == digest, 'Saved sidewalk build has a stale source hash')
    meshes = {entry['meshName']: entry for entry in authored['meshes']}
    check(len(meshes) == authored['meshCount'] == expected.get('meshCount'),
          'Sidewalk mesh count differs between source and saved build report')
    check(len(authored['ramps']) == 4, 'Expected four modeled crossing ramps')
    check(len(authored['treePits']) == 28, 'Expected 28 modeled tree pits')
    pit_centres = sorted((pit['center'][0]*100, pit['center'][2]*100) for pit in authored['treePits'])
    tree_centres = sorted(tuple(tree['position'][:2]) for tree in tree_instances)
    check(len(pit_centres) == len(tree_centres) and
          all(abs(a-b) < .5 for pit, tree in zip(pit_centres, tree_centres) for a, b in zip(pit, tree)),
          'Modeled sidewalk tree pits do not align with saved tree instances')
    check(abs(authored['sidewalkTop'] - 7.04) < .0001, 'Authored sidewalk top changed')
    geometry_checks = authored.get('geometryChecks', {})
    check(geometry_checks.get('passed') is True and bool(geometry_checks.get('tests')),
          'Sidewalk exported geometry has no passing raycast checks')
    for test in geometry_checks.get('tests', []):
        check(test.get('passed') is True, 'Sidewalk geometry check failed: ' + str(test))
    color_design = authored.get('pavingColorDesign', {})
    check(color_design.get('attribute') == 'COLOR_0 RGB / Unreal VertexColor RGB',
          'Sidewalk paving color interface is missing')
    paving_checks = [entry for entry in color_design.get('exportedChecks', [])
                     if entry.get('material') == 'CitySidewalk_Paving']
    check(len(paving_checks) == 1 and paving_checks[0].get('uniqueTints', 0) > 1
          and paving_checks[0].get('constantPerTriangle') is True,
          'Paving export lost stable slab color variation')
    document = json.loads(source[20:20+int.from_bytes(source[12:16], 'little')])
    paving_nodes = [node for node in document['nodes'] if node.get('name') == 'CitySidewalk_Paving']
    check(len(paving_nodes) == 1, 'Paving source mesh is missing or duplicated')
    for node in paving_nodes:
        for primitive in document['meshes'][node['mesh']]['primitives']:
            color_index = primitive['attributes'].get('COLOR_0')
            color = document['accessors'][color_index] if color_index is not None else {}
            positions = document['accessors'][primitive['attributes']['POSITION']]
            check(color.get('type') == 'VEC3' and color.get('componentType') == 5126
                  and color.get('count') == positions['count'], 'Paving GLB lost float COLOR_0 per vertex')
    saved, sidewalk_materials = {}, {}
    for actor in actors:
        label = actor.get_actor_label()
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = component.static_mesh
            if not mesh:
                continue
            path = mesh.get_path_name()
            if not (actor.actor_has_tag('OOWCitySidewalk') or label.startswith('CitySidewalk_')
                    or path.startswith(MODERN + 'city-sidewalk/')):
                continue
            check(actor.actor_has_tag('OOWCitySidewalk'), 'Sidewalk actor lost its semantic tag: ' + label)
            check(path.startswith(MODERN + 'city-sidewalk/'), 'Sidewalk mesh is outside its project folder: ' + label)
            check(label in meshes and label not in saved, 'Unexpected or duplicate sidewalk mesh actor: ' + label)
            if label not in meshes:
                continue
            check(component.get_editor_property('mobility') == u.ComponentMobility.STATIC,
                  'Sidewalk component is not static: ' + label)
            check(str(u.EditorAssetLibrary.get_metadata_tag(mesh, 'OOWSidewalkSourceHash')) == digest,
                  'Saved sidewalk mesh has a stale source hash: ' + label)
            entry = meshes[label]
            origin, extent, _ = u.SystemLibrary.get_component_bounds(component)
            centre, half_size = xyz(origin), xyz(extent)
            low = [a-b for a, b in zip(centre, half_size)]
            high = [a+b for a, b in zip(centre, half_size)]
            source_low = [entry['bounds']['min'][i]*100 for i in (0, 2, 1)]
            source_high = [entry['bounds']['max'][i]*100 for i in (0, 2, 1)]
            check(all(abs(a-b) < .5 for a, b in zip(low + high, source_low + source_high)),
                  'Saved sidewalk placement or dimensions differ from authored geometry: ' + label)
            check(high[2]-low[2] > .1, 'Sidewalk batch has no modeled thickness: ' + label)
            triangles = mesh.get_num_triangles(0)
            check(0 < triangles <= entry['triangles'], 'Sidewalk fallback geometry is empty or stale: ' + label)
            materials = [component.get_material(i) for i in range(component.get_num_materials())]
            names = [material.get_name() for material in materials if material]
            check(sorted(names) == sorted('M_' + name for name in entry['materialSlots']),
                  'Sidewalk native material slots differ from authored geometry: ' + label)
            check(all(material and material.get_path_name().startswith(MODERN + 'Materials/M_CitySidewalk_')
                      for material in materials), 'Sidewalk native material is missing: ' + label)
            sidewalk_materials.update((material.get_path_name(), material) for material in materials if material)
            if label == 'CitySidewalk_Paving':
                check(abs(high[2] - authored['sidewalkTop']*100) < .5, 'Saved paving top height changed')
                has_vertex_colors = bool(mesh_editor.has_vertex_colors(mesh))
                check(has_vertex_colors, 'Saved paving mesh lost its authored vertex colors')
            saved[label] = {'mesh': path, 'worldBoundsCm': {'min': low, 'max': high},
                            'fallbackTriangles': triangles, 'materials': names}
            if label == 'CitySidewalk_Paving':
                saved[label]['hasVertexColors'] = has_vertex_colors
    check(set(saved) == set(meshes), 'Saved sidewalk batches do not match authored geometry')
    texture_bindings = {}
    for path, material in sidewalk_materials.items():
        if any(kind in material.get_name() for kind in ('Planting', 'Soil')):
            continue
        master = material.get_base_material()
        if material.get_name() == 'M_CitySidewalk_Paving':
            check(any(isinstance(node, u.MaterialExpressionVertexColor)
                      for node in connected_nodes(master, u.MaterialProperty.MP_BASE_COLOR)),
                  'Paving vertex colors are disconnected from BaseColor')
        bindings = {}
        for parameter, stem, output in (
                ('SidewalkConcreteColor', 'Concrete3_BaseColor', u.MaterialProperty.MP_BASE_COLOR),
                ('SidewalkConcreteNormal', 'Concrete3_Normal', u.MaterialProperty.MP_NORMAL)):
            texture = u.MaterialEditingLibrary.get_material_default_texture_parameter_value(master, parameter)
            texture_path = texture.get_path_name() if texture else ''
            check(texture_path == MODERN + 'SidewalkTextures/' + stem + '.' + stem,
                  'Sidewalk concrete texture binding is missing or stale: ' + path + ':' + parameter)
            check(bool(texture) and texture_path in connected_textures(master, output),
                  'Sidewalk concrete texture is disconnected from its output: ' + path + ':' + parameter)
            if texture and parameter == 'SidewalkConcreteNormal':
                check(texture.get_editor_property('flip_green_channel') and not texture.get_editor_property('srgb'),
                      'Sidewalk concrete normal has incorrect green-channel or color-space settings: ' + texture_path)
            bindings[parameter] = texture_path
        texture_bindings[path] = bindings
    return {'sha256': digest, 'meshes': saved, 'sidewalkTop': authored['sidewalkTop'],
            'ramps': len(authored['ramps']), 'treePits': len(authored['treePits']),
            'geometryChecks': geometry_checks, 'concreteTextureBindings': texture_bindings,
            'pavingColorDesign': color_design}


def audit_roads(actors, expected, check):
    authored = json.loads((ROOT / 'Art/City/city-road-markings.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256((ROOT / 'Art/City/city-road-markings.glb').read_bytes()).hexdigest()
    check(expected.get('sha256') == authored.get('sourceGeometry', {}).get('sha256') == digest,
          'Road marking source or saved build hash is stale')
    sources = {entry['meshName']: entry for entry in authored['meshes']}
    check(set(sources) == {'CityRoadMarkings_White', 'CityRoadMarkings_Yellow'}
          and authored['meshCount'] == expected.get('meshCount') == 2, 'Expected two merged road marking meshes')
    removed = {'OOW_%05d_Mesh' % i for i in (*range(39, 42), *range(44, 84))}
    check(set(authored['removedLegacyActors']) == set(expected.get('removedLegacyActors', [])) == removed,
          'Road marking replacement list is stale')
    geometry_checks = authored.get('geometryChecks', {})
    check(geometry_checks.get('passed') is True and bool(geometry_checks.get('tests'))
          and all(test.get('passed') is True for test in geometry_checks.get('tests', [])),
          'Road marking actual geometry checks are missing or failed')
    target_bindings = expected.get('roadBindings', {})
    road_names = {'OOW_00032_city_grounding_underlay'} | {'OOW_%05d_Mesh' % i for i in range(33, 37)}
    check(set(target_bindings) == road_names, 'Expected five native road surface bindings')
    saved, bindings, materials = {}, {}, {}
    for actor in actors:
        label = actor.get_actor_label()
        if label in road_names:
            component = actor.get_component_by_class(u.StaticMeshComponent)
            material = component.get_material(0) if component else None
            path = material.get_path_name() if material else ''
            check(path == target_bindings.get(label) and path.startswith(MODERN + 'Materials/M_CityRoad_'),
                  'Legacy road surface lost its native City road material: ' + label)
            bindings[label] = path
            if material:
                materials[path] = material
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = component.static_mesh
            if not mesh:
                continue
            path = mesh.get_path_name()
            if not (actor.actor_has_tag('OOWCityRoadMarkings') or label.startswith('CityRoadMarkings_')
                    or path.startswith(MODERN + 'city-road-markings/')):
                continue
            check(actor.actor_has_tag('OOWCityRoadMarkings'), 'Road markings lost their semantic tag: ' + label)
            check(path.startswith(MODERN + 'city-road-markings/'), 'Road marking mesh is outside its project folder')
            check(label in sources and label not in saved, 'Unexpected or duplicate road marking actor: ' + label)
            if label not in sources:
                continue
            check(str(u.EditorAssetLibrary.get_metadata_tag(mesh, 'OOWRoadMarkingsSourceHash')) == digest,
                  'Saved road marking source hash is stale: ' + label)
            check(mesh.get_editor_property('nanite_settings').enabled, 'Road marking Nanite is disabled: ' + label)
            cast_shadow = bool(component.get_editor_property('cast_shadow'))
            check(not cast_shadow, 'Road markings cast floating shadows: ' + label)
            origin, extent, _ = u.SystemLibrary.get_component_bounds(component)
            low = [a-b for a, b in zip(xyz(origin), xyz(extent))]
            high = [a+b for a, b in zip(xyz(origin), xyz(extent))]
            entry = sources[label]
            target = [entry['bounds'][key][axis]*100 for key in ('min', 'max') for axis in (0, 2, 1)]
            check(all(abs(a-b) < .1 for a, b in zip(low + high, target)),
                  'Saved road marking placement or height differs from the source: ' + label)
            triangles = mesh.get_num_triangles(0)
            check(0 < triangles <= entry['triangles'], 'Road marking fallback geometry is empty or stale: ' + label)
            material = component.get_material(0)
            material_path = material.get_path_name() if material else ''
            name = 'M_CityRoad_' + label.rsplit('_', 1)[1]
            check(component.get_num_materials() == 1 and material_path == MODERN + 'Materials/' + name + '.' + name,
                  'Road marking native paint material is wrong: ' + label)
            if material:
                materials[material_path] = material
            saved[label] = {'mesh': path, 'worldBoundsCm': {'min': low, 'max': high},
                            'fallbackTriangles': triangles, 'material': material_path, 'castShadow': cast_shadow}
    check(set(saved) == set(sources), 'Saved road markings do not match the two authored meshes')
    check(set(bindings) == road_names, 'A native road surface actor is missing')
    for path, material in materials.items():
        check(str(u.EditorAssetLibrary.get_metadata_tag(material, 'OOWRoadVersion')) == 'city-road-v1',
              'Stale native road material version: ' + path)
        check(material.get_blend_mode() == u.BlendMode.BLEND_OPAQUE, 'Road material must be opaque: ' + path)
        parameters = {str(node.get_editor_property('parameter_name'))
                      for node in connected_nodes(material.get_base_material(), u.MaterialProperty.MP_ROUGHNESS)
                      if isinstance(node, u.MaterialExpressionScalarParameter)}
        check({'Wetness', 'Water'} <= parameters, 'Road roughness lost Wetness or Water input: ' + path)
    texture_bindings = {}
    asphalt = next((material for material in materials.values() if material.get_name() == 'M_CityRoad_Asphalt'), None)
    check(asphalt is not None, 'Native asphalt material is missing')
    if asphalt:
        master = asphalt.get_base_material()
        for channel, output in (('diffuse', u.MaterialProperty.MP_BASE_COLOR),
                                ('roughness', u.MaterialProperty.MP_ROUGHNESS), ('normal', u.MaterialProperty.MP_NORMAL)):
            texture = u.MaterialEditingLibrary.get_material_default_texture_parameter_value(master, 'CityRoad_' + channel)
            path = texture.get_path_name() if texture else ''
            stem = 'Asphalt02_' + channel
            check(path == MODERN + 'RoadTextures/' + stem + '.' + stem and path in connected_textures(master, output),
                  'Native asphalt texture binding or output connection is missing: ' + channel)
            if texture:
                check(bool(texture.get_editor_property('srgb')) == (channel == 'diffuse'),
                      'Asphalt texture has incorrect color space: ' + channel)
                if channel == 'normal':
                    check(texture.get_editor_property('flip_green_channel'), 'Asphalt OpenGL normal was not converted')
            texture_bindings[channel] = path
    return {'sha256': digest, 'meshes': saved, 'roadBindings': bindings, 'asphaltTextureBindings': texture_bindings,
            'geometryChecks': {'passed': geometry_checks.get('passed'), 'tests': len(geometry_checks.get('tests', []))}}


def audit_entrances(actors, expected, mesh_editor, check):
    authored = json.loads((ROOT / 'Art/City/city-entrances.json').read_text(encoding='utf-8'))
    source = (ROOT / 'Art/City/city-entrances.glb').read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    check(expected.get('sha256') == digest == authored.get('sha256'),
          'Entrance source or saved build hash is stale')
    check(authored.get('sourceGeometry', {}).get('sha256') ==
          hashlib.sha256((ROOT / 'Art/City/modern-city.glb').read_bytes()).hexdigest(),
          'Entrance geometry no longer matches the authored building shell')
    check(authored.get('geometryChecks', {}).get('allPassed') is True,
          'Entrance or balcony geometry checks failed')
    json_size = int.from_bytes(source[12:16], 'little')
    document = json.loads(source[20:20+json_size])
    binary_start = 28 + json_size
    for primitive in (p for mesh in document['meshes'] for p in mesh['primitives']):
        color_index = primitive['attributes'].get('COLOR_0')
        color = document['accessors'][color_index] if color_index is not None else {}
        positions = document['accessors'][primitive['attributes']['POSITION']]
        valid = color.get('type') == 'VEC3' and color.get('componentType') == 5126 and color.get('count') == positions['count']
        check(valid, 'Entrance source lost its explicit black COLOR_0 night-light mask')
        if valid:
            view = document['bufferViews'][color['bufferView']]
            offset = binary_start + view.get('byteOffset', 0) + color.get('byteOffset', 0)
            stride = view.get('byteStride', 12)
            check(all(struct.unpack_from('<fff', source, offset+i*stride) == (0., 0., 0.)
                      for i in range(color['count'])), 'Entrance source contains unintended office-light emission')
    sources = {entry['meshName']: entry for entry in authored['meshes']}
    saved = {}
    for actor in actors:
        if not actor.actor_has_tag('OOWCityEntrance'):
            continue
        label = actor.get_actor_label()
        check(label in sources and label not in saved, 'Unexpected entrance mesh: ' + label)
        if label not in sources:
            continue
        components = actor.get_components_by_class(u.StaticMeshComponent)
        check(len(components) == 1, 'Unexpected entrance component count: ' + label)
        if len(components) != 1:
            continue
        component = components[0]
        mesh = component.static_mesh
        check(mesh is not None, 'Saved entrance has no static mesh: ' + label)
        if mesh is None:
            continue
        check(str(u.EditorAssetLibrary.get_metadata_tag(mesh, 'OOWEntranceSourceHash')) == digest,
              'Saved entrance source hash changed: ' + label)
        origin, extent, _ = u.SystemLibrary.get_component_bounds(component)
        low = [a-b for a, b in zip(xyz(origin), xyz(extent))]
        high = [a+b for a, b in zip(xyz(origin), xyz(extent))]
        bounds = sources[label]['bounds']
        target = [bounds[key][axis]*100 for key in ('min', 'max') for axis in (0, 2, 1)]
        check(all(abs(a-b) < .5 for a, b in zip(low + high, target)),
              'Saved entrance or balcony door bounds changed: ' + label)
        check(0 < mesh.get_num_triangles(0) <= sources[label]['triangles'], 'Entrance mesh is empty: ' + label)
        has_vertex_colors = bool(mesh_editor.has_vertex_colors(mesh))
        check(has_vertex_colors, 'Saved entrance mesh lost its explicit black vertex colors: ' + label)
        saved[label] = {'mesh': mesh.get_path_name(), 'worldBoundsCm': {'min': low, 'max': high},
                        'hasVertexColors': has_vertex_colors}
    check(set(saved) == set(sources), 'Missing entrance or balcony geometry')
    check(len(authored['entrances']) == 6, 'Expected six modeled street entrances')
    check(len(authored.get('balconyAccess', [])) >= 4, 'Expected access doors on the four terrace buildings')
    return {'sha256': digest, 'meshes': saved, 'streetEntrances': len(authored['entrances']),
            'balconyDoors': len(authored.get('balconyAccess', []))}


def audit_office_lights(actors, authored, expected, digest, mesh_editor, check):
    lighting = authored.get('nightLighting', {})
    version = 'city-office-light-v1'
    check(lighting.get('version') == version, 'Authored office-light version is stale')
    expected_gain = expected.get('gain')
    valid_gain = isinstance(expected_gain, (int, float)) and math.isfinite(expected_gain) and 0 < expected_gain <= 1.
    check(expected.get('version') == version and valid_gain, 'Saved office-light build version or gain is stale')
    check(lighting.get('sourceGeometry', {}).get('sha256') == digest,
          'Office-light checks do not match the authored City GLB')
    names = set(lighting.get('buildingNames', []))
    check(len(names) == 16 and names == {entry['name'] for entry in authored['buildings']
                                        if entry['name'].startswith('CityModern_B')},
          'Office-light masks must cover all 16 near buildings')
    source_checks = lighting.get('checks', {})
    check(all(source_checks.get(key) is True for key in
              ('passed', 'allPanesHaveColor', 'paneColorsConstant', 'nonGlassBlack', 'continuousOfficeGroups')),
          'Office-light masks failed their authored continuity or pane checks')
    exported = lighting.get('exportedChecks', {})
    check(all(exported.get(key) is True for key in ('passed', 'allPrimitivesHaveColor0')),
          'Office-light GLB color checks failed')
    if exported.get('baselineCompared') is not False:
        check(all(exported.get(key) is True for key in ('geometryUnchanged', 'materialsUnchanged')),
              'Office-light GLB checks changed daytime geometry/materials')
        check(bool(exported.get('beforeGeometrySha256')) and
              exported.get('beforeGeometrySha256') == exported.get('afterGeometrySha256') and
              bool(exported.get('beforeMaterialSha256')) and
              exported.get('beforeMaterialSha256') == exported.get('afterMaterialSha256'),
              'Night masks changed the authored geometry or daytime material data')
    check(exported.get('actualNearPaneCount', 0) == lighting.get('allNearPaneCount', -1) > 0 and
          exported.get('actualHeroPaneCount', 0) == lighting.get('heroPaneCount', -1) == authored['heroWindowCount'],
          'Exported office-light pane counts do not match the source')
    glass_names = {'M_CityModern_Hero_Glass', 'M_CityModern_Glass_Day_Blue',
                   'M_CityModern_Glass_Day_Silver', 'M_Glass_Lit_CityModern_Warm'}
    buildings, materials = {}, {}
    for actor in actors:
        label = actor.get_actor_label()
        if label not in names:
            continue
        components = actor.get_components_by_class(u.StaticMeshComponent)
        check(len(components) == 1 and label not in buildings, 'Unexpected near-building component count: ' + label)
        for component in components:
            mesh = component.static_mesh
            has_colors = bool(mesh and mesh_editor.has_vertex_colors(mesh))
            check(has_colors, 'Saved near building lost its office-light vertex colors: ' + label)
            buildings[label] = {'mesh': mesh.get_path_name() if mesh else '', 'hasVertexColors': has_colors}
            for index in range(component.get_num_materials()):
                material = component.get_material(index)
                if material and material.get_name() in glass_names:
                    materials[material.get_name()] = material
    check(set(buildings) == names, 'Saved office-light building coverage is incomplete')
    check(set(materials) == glass_names, 'A near-glass office-light material is missing')
    material_report = {}
    for name, material in materials.items():
        master = material.get_base_material()
        check(str(u.EditorAssetLibrary.get_metadata_tag(material, 'OOWNightLightingVersion')) == version,
              'Native glass retained its old night-light recipe: ' + name)
        nodes = list(connected_nodes(master, u.MaterialProperty.MP_EMISSIVE_COLOR))
        check(any(isinstance(node, u.MaterialExpressionVertexColor) for node in nodes),
              'Office-light vertex color is disconnected from Emissive: ' + name)
        check(not any(isinstance(node, u.MaterialExpressionVertexColor)
                      for node in connected_nodes(master, u.MaterialProperty.MP_BASE_COLOR)),
              'Office-light vertex mask changes the daytime glass color: ' + name)
        parameters = {str(node.get_editor_property('parameter_name')) for node in nodes
                      if isinstance(node, u.MaterialExpressionScalarParameter)}
        check('Night' in parameters, 'Office-light Night input is disconnected: ' + name)
        customs = [(node, str(node.get_editor_property('code'))) for node in nodes
                   if isinstance(node, u.MaterialExpressionCustom)]
        codes = [code for _, code in customs]
        check(not any('frac(' in ''.join(code.split()) for code in codes),
              'Office-light emission still contains a per-pane random hash: ' + name)
        office_nodes = [node for node, code in customs if 'float ceiling' in code and 'spill' in code]
        check(len(office_nodes) == 1, 'Office-light shading node is missing or duplicated: ' + name)
        gain = None
        if len(office_nodes) == 1:
            office = office_nodes[0]
            inputs = dict(zip(u.MaterialEditingLibrary.get_material_expression_input_names(office),
                              u.MaterialEditingLibrary.get_inputs_for_material_expression(master, office)))
            gain_node = inputs.get('G')
            check(isinstance(gain_node, u.MaterialExpressionConstant), 'Office-light G input is not an authored constant: ' + name)
            if isinstance(gain_node, u.MaterialExpressionConstant):
                gain = float(gain_node.get_editor_property('r'))
        check(gain is not None and math.isfinite(gain) and valid_gain and abs(gain-expected_gain) < .0001,
              'Office-light gain differs from the saved build report: ' + name)
        material_report[name] = {'version': version, 'gain': gain, 'connectedParameters': sorted(parameters)}
    gains = [record['gain'] for record in material_report.values() if record['gain'] is not None]
    check(not gains or max(gains)-min(gains) < .0001, 'Near-glass materials do not share one office-light gain')
    return {'version': version, 'buildings': buildings, 'materials': material_report,
            'sourceGeometrySha256': digest, 'exportedChecks': exported}


def audit_distant_lights(actors, authored, expected, near_gain, check):
    version = 'city-distant-office-v1'
    names = {'CityModern_Skyline_Glass_Blue', 'CityModern_Skyline_Glass_Grey'}
    gain = expected.get('gain')
    valid_gain = isinstance(gain, (int, float)) and math.isfinite(gain) and 0 < gain < near_gain
    check(expected.get('version') == version and valid_gain and set(expected.get('materials', [])) == names,
          'Distant-light build version, material list or relative gain is stale')
    required = {entry['name'] for entry in authored['buildings'] if entry['name'].startswith('CityModern_Skyline')}
    required.update(entry['meshName'] for entry in authored['contextBuildings'])
    buildings, materials = set(), {}
    for actor in actors:
        label = actor.get_actor_label()
        if label not in required:
            continue
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            for slot in range(component.get_num_materials()):
                material = component.get_material(slot)
                if material and material.get_name() in {'M_' + name for name in names}:
                    materials[material.get_name()] = material
                    buildings.add(label)
    check(buildings == required, 'A distant building lacks the native office-light material')
    check(set(materials) == {'M_' + name for name in names}, 'A distant-glass night-light material is missing')
    records = {}
    for name, material in materials.items():
        master = material.get_base_material()
        check(str(u.EditorAssetLibrary.get_metadata_tag(material, 'OOWDistantLightingVersion')) == version,
              'Saved distant glass has an old lighting recipe: ' + name)
        nodes = list(connected_nodes(master, u.MaterialProperty.MP_EMISSIVE_COLOR))
        parameters = {str(node.get_editor_property('parameter_name')) for node in nodes
                      if isinstance(node, u.MaterialExpressionScalarParameter)}
        check('Night' in parameters, 'Distant office-light Night input is disconnected: ' + name)
        check(any(isinstance(node, u.MaterialExpressionWorldPosition) for node in nodes)
              and any(isinstance(node, u.MaterialExpressionVertexNormalWS) for node in nodes)
              and any(isinstance(node, u.MaterialExpressionTextureCoordinate)
                      and node.get_editor_property('coordinate_index') == 0 for node in nodes),
              'Distant office lighting lost its face coordinates or roof exclusion normal: ' + name)
        transforms = [node for node in nodes if isinstance(node, u.MaterialExpressionTransformPosition)]
        check(len(transforms) == 1
              and transforms[0].get_editor_property('transform_source_type') == u.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD
              and transforms[0].get_editor_property('transform_type') == u.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL,
              'Distant floor spacing no longer follows source geometry under actor scaling: ' + name)
        office_nodes = [node for node in nodes if isinstance(node, u.MaterialExpressionCustom)
                        and 'float zoneWidth' in str(node.get_editor_property('code'))]
        check(len(office_nodes) == 1, 'Distant office-zone emission node is missing or duplicated: ' + name)
        actual_gain = None
        if len(office_nodes) == 1:
            office = office_nodes[0]
            code = ''.join(str(office.get_editor_property('code')).split())
            check('*smoothstep(.58,.86,Night)' in code and '*vertical*' in code,
                  'Distant office light lost its strict day gate or vertical-face mask: ' + name)
            inputs = dict(zip(u.MaterialEditingLibrary.get_material_expression_input_names(office),
                              u.MaterialEditingLibrary.get_inputs_for_material_expression(master, office)))
            gain_node = inputs.get('G')
            check(isinstance(gain_node, u.MaterialExpressionConstant), 'Distant office-light G input must be a constant: ' + name)
            if isinstance(gain_node, u.MaterialExpressionConstant):
                actual_gain = float(gain_node.get_editor_property('r'))
        check(actual_gain is not None and valid_gain and abs(actual_gain-gain) < .0001,
              'Saved distant-light gain differs from the build report: ' + name)
        check(not any(isinstance(node, u.MaterialExpressionScalarParameter)
                      and str(node.get_editor_property('parameter_name')) == 'Night'
                      for node in connected_nodes(master, u.MaterialProperty.MP_BASE_COLOR)),
              'Distant night-light shading changes the daytime facade color: ' + name)
        records[name] = {'version': version, 'gain': actual_gain, 'connectedParameters': sorted(parameters)}
    return {'version': version, 'meshActors': sorted(buildings), 'materials': records}


def audit_street_lights(lights, actors, authored, expected, check):
    originals = {entry['name']: entry for entry in authored['streetlights']}
    extensions = expected.get('extensions', [])
    extension_names = {'CityModern_LED_' + side + str(index) for side in ('W', 'E') for index in range(7, 10)}
    check(len(originals) == 12, 'Expected the original twelve authored street poles')
    check(len(extensions) == 6 and {entry['name'] for entry in extensions} == extension_names,
          'Expected six modeled street-light extensions beyond the original poles')
    sources = {'OOWCityLight_' + entry['name']: entry for entry in authored['streetlights'] + extensions}
    check(len(lights) == len(sources) == expected.get('count') == 18,
          'Expected one downward City night spotlight at each of the 18 modeled poles')
    poles = {actor.get_actor_label(): actor for actor in actors
             if actor.get_actor_label().startswith('CityModern_LED_')}
    check(set(poles) == set(originals) | extension_names, 'Street-light pole geometry is missing or duplicated')
    check({actor.get_actor_label() for actor in actors if actor.actor_has_tag('OOWCityLampExtension')} == extension_names,
          'Extended street poles lost their semantic tag or tagged an original pole')
    pole_records = {}
    for entry in extensions:
        name = entry['name']
        if name not in extension_names:
            continue
        template_name = name[:-1] + '6'
        step = int(name[-1]) - 6
        check(entry.get('template') == template_name, 'Street extension references the wrong pole template: ' + name)
        source = originals.get(template_name)
        check(source is not None, 'Street extension has no authored pole template: ' + name)
        if not source:
            continue
        offset = [0., -4000. * step, 0.]
        position = list(source['position'])
        position[2] -= 40. * step
        check(entry.get('offsetCm') == offset and entry.get('position') == position,
              'Street extension spacing differs from the authored 40 metre rhythm: ' + name)
        check(0 < entry.get('lumens', 0) < expected.get('lumens', 0),
              'Far street-light extensions must be dimmer than the original lights: ' + name)
        pole, template = poles.get(name), poles.get(template_name)
        if not pole or not template:
            continue
        component = pole.get_component_by_class(u.StaticMeshComponent)
        original = template.get_component_by_class(u.StaticMeshComponent)
        check(bool(component and original), 'Street-light extension or template has no modeled pole: ' + name)
        if not component or not original:
            continue
        check(pole.actor_has_tag('OOWGeometry') and component.static_mesh == original.static_mesh,
              'Street-light extension does not reuse its original mesh: ' + name)
        check(pole.get_class() == u.StaticMeshActor.static_class()
              and component.get_editor_property('mobility') == u.ComponentMobility.STATIC,
              'Street-light extension must be a clean static mesh actor: ' + name)
        materials = [component.get_material(slot) for slot in range(component.get_num_materials())]
        original_materials = [original.get_material(slot) for slot in range(original.get_num_materials())]
        check(materials == original_materials, 'Street-light extension changed its template materials: ' + name)
        # Compare effective component transforms, not imported actor origins;
        # a clean spawned actor can have a different parent/relative transform.
        actual, target = component.get_world_transform(), original.get_world_transform()
        for point in (u.Vector(), u.Vector(1, 0, 0), u.Vector(0, 1, 0), u.Vector(0, 0, 1)):
            actual_point = xyz(u.MathLibrary.transform_location(actual, point))
            target_point = [a+b for a, b in zip(xyz(u.MathLibrary.transform_location(target, point)), offset)]
            check(all(abs(a-b) < .01 for a, b in zip(actual_point, target_point)),
                  'Street-light extension failed to preserve its template transform: ' + name)
        pole_records[name] = {'template': template_name, 'mesh': component.static_mesh.get_path_name(),
                              'offsetCm': offset, 'lumens': entry['lumens']}
    check(set(pole_records) == extension_names, 'Saved extended street-pole coverage is incomplete')
    for side in ('W', 'E'):
        levels = [next((entry.get('lumens', 0) for entry in extensions
                        if entry['name'] == 'CityModern_LED_' + side + str(index)), 0) for index in range(7, 10)]
        check(levels[0] > levels[1] > levels[2] > 0, 'Far street lights do not taper toward the horizon: ' + side)
    properties = {'intensity': 'lumens', 'attenuation_radius': 'radiusCm',
                  'inner_cone_angle': 'innerConeDegrees', 'outer_cone_angle': 'outerConeDegrees',
                  'temperature': 'temperatureK'}
    check(all(isinstance(expected.get(key), (int, float)) and math.isfinite(expected[key]) and expected[key] > 0
              for key in properties.values()), 'Street-light build parameters are missing or invalid')
    pitch = expected.get('pitchDegrees', float('nan'))
    check(math.isfinite(pitch) and -90 <= pitch < 0 and pitch + expected.get('outerConeDegrees', 90) < 0,
          'Street-light outer cone must remain below the horizon')
    records = {}
    for lamp in lights:
        label = lamp.get_actor_label()
        check(label in sources and label not in records, 'Unexpected or duplicate City night lamp: ' + label)
        component = lamp.get_component_by_class(u.SpotLightComponent)
        check(component is not None, 'City street lamp is not a spotlight: ' + label)
        check(lamp.actor_has_tag('OOWNightLight'), 'City street lamp lost its runtime night control tag: ' + label)
        if not component or label not in sources:
            continue
        source = sources[label]
        side = -1 if source['position'][0] < 0 else 1
        position = xyz(lamp.get_actor_location())
        target = [side * 1480., source['position'][2] * 100., 1450.]
        check(all(abs(a-b) < .5 for a, b in zip(position, target)), 'Street lamp does not align with its modeled luminaire: ' + label)
        forward = xyz(component.get_forward_vector())
        expected_forward = [-side * math.cos(math.radians(pitch)), 0., math.sin(math.radians(pitch))]
        check(all(abs(a-b) < .001 for a, b in zip(forward, expected_forward)),
              'Street lamp does not point down and inward toward the road: ' + label)
        values = {key: float(component.get_editor_property(key)) for key in properties}
        for key, report_key in properties.items():
            target_value = source.get('lumens', expected.get('lumens', float('nan'))) if key == 'intensity' else expected.get(report_key, float('nan'))
            check(abs(values[key] - target_value) < .01,
                  'Street lamp differs from its saved lighting setting: ' + label + ':' + key)
        check(component.get_editor_property('intensity_units') == u.LightUnits.LUMENS
              and component.get_editor_property('use_temperature')
              and component.get_editor_property('mobility') == u.ComponentMobility.MOVABLE,
              'Street lamp lost physical units, temperature or runtime mobility: ' + label)
        values['cast_shadows'] = bool(component.get_editor_property('cast_shadows'))
        check(not values['cast_shadows'], 'Street lamp enables unwanted shadows: ' + label)
        values['affect_translucent_lighting'] = bool(component.get_editor_property('affect_translucent_lighting'))
        check(values['affect_translucent_lighting'], 'Street lamp cannot illuminate the lit world rain: ' + label)
        for key in ('indirect_lighting_intensity', 'volumetric_scattering_intensity'):
            values[key] = float(component.get_editor_property(key))
            check(abs(values[key]) < .0001, 'Street lamp enables an unwanted lighting pass: ' + label + ':' + key)
        records[label] = {'positionCm': position, 'direction': forward, **values}
    check(set(records) == set(sources), 'Saved street lighting does not cover all authored poles')
    return {'settings': expected, 'lights': records, 'extendedPoles': pole_records}


def main():
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    expected = json.loads((ROOT / 'Migration/city-modern-build.json').read_text(encoding='utf-8'))
    authored = json.loads((ROOT / 'Art/City/modern-city.json').read_text(encoding='utf-8'))
    hero_names = authored.get('heroBuildingNames', [])
    check(len(hero_names) == len(set(hero_names)) == 2, 'Expected two authored hero building names')
    check(authored.get('heroWindowCount', 0) > 0, 'Authored hero window count is missing')
    facade_parameters = {
        'M_CityModern_Hero_Glass': (),
        'M_CityModern_Limestone': ('CityStoneColor', 'CityStoneRoughness', 'CityStoneNormal'),
        'M_CityModern_PaleStone': ('CityStoneColor', 'CityStoneRoughness', 'CityStoneNormal'),
    }
    facade_outputs = {'CityStoneColor': u.MaterialProperty.MP_BASE_COLOR,
                      'CityStoneRoughness': u.MaterialProperty.MP_ROUGHNESS,
                      'CityStoneNormal': u.MaterialProperty.MP_NORMAL}
    facade_materials, hero_buildings = {}, {}
    source_digest = hashlib.sha256((ROOT / 'Art/City/modern-city.glb').read_bytes()).hexdigest()
    check(expected.get('sourceGeometry', {}).get('sha256') == source_digest,
          'Saved City build is stale relative to the authored modern-city.glb')
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    if not levels.load_level('/Game/Maps/City'):
        raise RuntimeError('Cannot reload saved City map')
    mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    actors = list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    camera = [a for a in actors if a.actor_has_tag('OOWCamera')]
    check(len(camera) == 1, 'Expected one saved OOWCamera')
    camera_record = {}
    if camera:
        actor = camera[0]
        position = xyz(actor.get_actor_location())
        check(all(abs(a-b) < .01 for a, b in zip(position, expected['camera'])), 'Camera location changed')
        check(actor.actor_has_tag('OOWRoadsideView'), 'Roadside camera tag missing')
        check(actor.actor_has_tag('VerticalFov_' + str(expected['verticalFov'])), 'Vertical FOV tag changed')
        direction = [b-a for a, b in zip(position, expected['target'])]
        length = math.sqrt(sum(value*value for value in direction))
        forward = xyz(actor.get_actor_forward_vector())
        check(length > 0 and all(abs(a-b/length) < .0001 for a, b in zip(forward, direction)),
              'Camera no longer faces the authored target')
        fov = actor.camera_component.get_editor_property('field_of_view')
        target_fov = math.degrees(2*math.atan(math.tan(math.radians(expected['verticalFov']/2))*1280/820))
        check(abs(fov-target_fov) < .001, 'Saved camera horizontal FOV changed')
        camera_record = {'position': position, 'forward': forward, 'horizontalFov': fov}

    cars, buildings, skyline, context, leds, tree_instances, batches = [], [], [], [], [], [], []
    unique_car_ids, unique_meshes, unique_materials = [], {}, {}
    preserved_roads = {n['name'] for n in json.loads((ROOT / 'Migration/Exported/city.json').read_text(encoding='utf-8'))['nodes']
                       if 'city-road-functional-zones' in n.get('ancestors', [])}
    replaced_roads = {'OOW_%05d_Mesh' % i for i in range(37, 84)}
    preserved_roads -= replaced_roads
    found_roads = set()
    for actor in actors:
        label = actor.get_actor_label()
        tags = [str(tag) for tag in actor.tags]
        check(label not in replaced_roads, 'Replaced legacy road geometry remains: ' + label)
        check(actor.get_class().get_name() != 'WindowFrame', 'Runtime window frame was saved in the City map')
        car_ids = [tag for tag in tags if tag.startswith('OOWCar_')]
        if car_ids:
            unique_car_ids.extend(car_ids)
            check(len(car_ids) == 1, 'Ambiguous car tags: ' + label)
        if label in preserved_roads:
            found_roads.add(label)
        components = actor.get_components_by_class(u.StaticMeshComponent)
        for component in components:
            mesh = component.static_mesh
            if not mesh:
                continue
            mesh_path = mesh.get_path_name()
            # AWindowFrame is attached by runtime code, never serialized in City.
            check('DesktopFrame' not in mesh_path and not any('DesktopFrame' in tag for tag in tags),
                  'Desktop frame geometry was baked into the City map: ' + label)
            if mesh_path.startswith('/Game/Scenes/City/') and not mesh_path.startswith(MODERN):
                check(label in preserved_roads, 'Legacy City geometry remains: ' + label)
            is_modern = mesh_path.startswith(MODERN)
            if not is_modern:
                continue
            settings = mesh.get_editor_property('nanite_settings')
            check(settings.enabled, 'Nanite disabled: ' + mesh_path)
            unique_meshes[mesh_path] = bool(settings.enabled)
            materials = [component.get_material(i) for i in range(component.get_num_materials())]
            check(bool(materials) and all(materials), 'Missing material slot: ' + label)
            hero_slots = sum(bool(material and material.get_name() == 'M_CityModern_Hero_Glass')
                             for material in materials)
            if label in hero_names:
                check(label not in hero_buildings, 'Hero building has multiple mesh components: ' + label)
                uv_channels = mesh_editor.get_num_uv_channels(mesh, 0)
                build_settings = mesh_editor.get_lod_build_settings(mesh, 0)
                generated_uvs = bool(build_settings.get_editor_property('generate_lightmap_u_vs'))
                check(uv_channels >= 2, 'Hero building lost pane UV0 or seed UV1: ' + label)
                check(not generated_uvs, 'Hero building can overwrite authored UVs with lightmap UVs: ' + label)
                check(hero_slots == 1, 'Hero building must have one merged native glass slot: ' + label)
                hero_buildings[label] = {'mesh': mesh_path, 'uvChannels': uv_channels,
                                        'generateLightmapUVs': generated_uvs, 'heroGlassSlots': hero_slots}
            else:
                check(hero_slots == 0, 'Hero glass leaked onto a non-hero mesh: ' + label)
            is_tree = 'OOW_City_Linden' in mesh_path
            for material in materials:
                if not material:
                    continue
                path = material.get_path_name()
                master = material.get_base_material()
                check('defaultmaterial' not in (path + master.get_path_name()).lower(),
                      'DefaultMaterial fallback is bound: ' + label)
                material_name = material.get_name()
                if material_name in facade_parameters and material_name not in facade_materials:
                    version = str(u.EditorAssetLibrary.get_metadata_tag(material, 'OOWFacadeVersion'))
                    check(version == 'city-facade-v1', 'Stale facade material version: ' + path)
                    output_textures = {parameter: connected_textures(master, facade_outputs[parameter])
                                       for parameter in facade_parameters[material_name]}
                    texture_names = {str(name) for name in
                                     u.MaterialEditingLibrary.get_texture_parameter_names(material)}
                    bindings = {}
                    for parameter in facade_parameters[material_name]:
                        check(parameter in texture_names, 'Facade texture parameter missing: ' + path + ':' + parameter)
                        if isinstance(material, u.MaterialInstanceConstant):
                            texture = u.MaterialEditingLibrary.get_material_instance_texture_parameter_value(material, parameter)
                        else:
                            texture = u.MaterialEditingLibrary.get_material_default_texture_parameter_value(master, parameter)
                        texture_path = texture.get_path_name() if texture else ''
                        check(texture_path.startswith(MODERN + 'FacadeTextures/'),
                              'Facade texture binding is missing or outside the project folder: ' + path + ':' + parameter)
                        check(texture_path in output_textures[parameter],
                              'Facade texture is not connected to its native output: ' + path + ':' + parameter)
                        bindings[parameter] = texture_path
                    facade_materials[material_name] = {'path': path, 'version': version,
                                                       'bindings': bindings,
                                                       'texturesByOutput': {parameter: sorted(textures)
                                                                            for parameter, textures in output_textures.items()}}
                    if material_name == 'M_CityModern_Hero_Glass':
                        parameter = 'CityGlassRoughness'
                        scalar_names = {str(name) for name in
                                        u.MaterialEditingLibrary.get_scalar_parameter_names(material)}
                        check(parameter in scalar_names, 'Hero glass roughness parameter missing: ' + path)
                        if isinstance(material, u.MaterialInstanceConstant):
                            roughness = u.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, parameter)
                        else:
                            roughness = u.MaterialEditingLibrary.get_material_default_scalar_parameter_value(master, parameter)
                        check(abs(roughness - .12) < .0001, 'Hero glass default roughness changed: ' + path)
                        facade_materials[material_name]['roughness'] = roughness
                blend = material.get_blend_mode()
                check(blend in (u.BlendMode.BLEND_OPAQUE, u.BlendMode.BLEND_MASKED),
                      'Unexpected translucent modern material: ' + path)
                if not is_tree:
                    check(path.startswith(MODERN + 'Materials/M_'), 'Native City material not bound: ' + path)
                    check(blend == u.BlendMode.BLEND_OPAQUE, 'Native City material must be opaque: ' + path)
                nanite_usage = u.MaterialEditingLibrary.has_material_usage(master, u.MaterialUsage.MATUSAGE_NANITE)
                ism_usage = u.MaterialEditingLibrary.has_material_usage(master, u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
                check(nanite_usage, 'Material lacks Nanite usage: ' + path)
                if isinstance(component, u.InstancedStaticMeshComponent):
                    check(ism_usage, 'Saved ISM material lacks instance usage: ' + path)
                if is_tree and 'Leaves' in path:
                    check(blend == u.BlendMode.BLEND_MASKED and two_sided(material),
                          'Tree leaf mask/two-sided shading was lost: ' + path)
                unique_materials[path] = {'blend': str(blend), 'naniteUsage': nanite_usage, 'ismUsage': ism_usage}
            if 'CityModern_B' in label:
                buildings.append(label)
            if 'CityModern_Skyline' in label:
                skyline.append(label)
            if 'CityModern_Context_' in label:
                context.append(label)
                if 'CityModern_Context_Reflection' in label:
                    check(component.get_editor_property('visible_in_ray_tracing'),
                          'Reflection context is hidden from ray tracing: ' + label)
                    check(mesh.get_num_triangles(0) > 0,
                          'Reflection context has no fallback triangles: ' + label)
                check(all(abs(value-1) < .0001 for value in xyz(actor.get_actor_scale3d())),
                      'Context geometry lost its authored scale: ' + label)
                group = next((g for g in authored['contextGroups'] if g['meshName'] in label), None)
                check(group is not None, 'Unknown context mesh: ' + label)
                if group:
                    bounds = mesh.get_bounds()
                    actual_centre = xyz(u.MathLibrary.transform_location(component.get_world_transform(), bounds.origin))
                    low, high = group['bounds']['min'], group['bounds']['max']
                    centre = [(a+b)*50 for a, b in zip(low, high)]
                    size = [(b-a)*100 for a, b in zip(low, high)]
                    check(all(abs(a-b) < 2 for a, b in zip(actual_centre, [centre[0], centre[2], centre[1]])),
                          'Context placement no longer covers its authored ground region: ' + label)
                    actual_size = [value*2 for value in xyz(bounds.box_extent)]
                    check(all(abs(a-b) < 2 for a, b in zip(actual_size, [size[0], size[2], size[1]])),
                          'Context mesh dimensions changed: ' + label)
            if 'CityModern_LED_' in label:
                leds.append(label)
            if car_ids:
                check(component.get_editor_property('mobility') == u.ComponentMobility.MOVABLE,
                      'Traffic component is not movable: ' + label)
                dimensions = [value*2 for value in xyz(mesh.get_bounds().box_extent)]
                check(all(abs(a-b) < 2 for a, b in zip(dimensions, [180.3, 430., 145.])),
                      'Sedan dimensions are not full-size: ' + label)
                check(component.get_num_materials() == 6, 'Sedan lost modeled parts/materials: ' + label)
                check(all(abs(value-1) < .0001 for value in xyz(actor.get_actor_scale3d())),
                      'Unexpected sedan actor scale: ' + label)
                check(actor.get_actor_up_vector().z > .999, 'Sedan is tilted or upside down: ' + label)
                cars.append({'label': label, 'tag': car_ids[0], 'dimensionsCm': dimensions,
                             'position': xyz(actor.get_actor_location())})
            if isinstance(component, u.InstancedStaticMeshComponent):
                transforms = [component.get_instance_transform(i, True) for i in range(component.get_instance_count())]
                check(actor.actor_has_tag('OOWCityStaticBatch'), 'Saved modern ISM lacks batch tag: ' + label)
                check(all(transforms), 'Unreadable saved instance transform: ' + label)
                batches.append({'label': label, 'mesh': mesh_path, 'instances': len(transforms)})
                if is_tree:
                    check(settings.get_editor_property('shape_preservation') == u.NaniteShapePreservation.PRESERVE_AREA,
                          'Tree Nanite area preservation missing')
                    for transform in transforms:
                        if transform:
                            tree_instances.append({'position': xyz(transform.translation), 'scale': xyz(transform.scale3d)})
                            up = u.MathLibrary.transform_direction(transform, u.Vector(0, 0, 1))
                            check(up.z > .99, 'Tree is tilted or buried: ' + label)
            elif is_tree:
                failures.append('Tree was not preserved as a saved ISM: ' + label)

    check(set(unique_car_ids) == {'OOWCar_' + str(i) for i in range(16)} and len(unique_car_ids) == 16,
          'Expected exactly one movable actor for each of the 16 traffic IDs')
    check(len(cars) == 16, 'Expected 16 full-size sedan meshes')
    check(len(buildings) == 16, 'Expected 16 modern building actors')
    check(set(hero_buildings) == set(hero_names), 'Saved hero buildings do not match the authored names')
    check(set(facade_materials) == set(facade_parameters), 'Hero glass or stone facade materials are missing')
    check(len(skyline) == 18, 'Expected 18 distant skyline buildings')
    check(len(context) == authored['contextMeshCount'], 'Merged context mesh count does not match authored metadata')
    check(expected.get('context', {}).get('buildings') == authored['contextBuildingCount'],
          'Context building count is absent or stale in the build report')
    check(authored['triangles'] <= 100000 and authored['primitives'] <= 200,
          'Authored architecture exceeds its triangle/material-section budget')
    check(len(leds) == len(set(leds)) == 18, 'Expected 12 original and six extended modern LED pole actors')
    check(len(tree_instances) == 28, 'Expected 28 trees restored from saved ISM instances')
    expected_trees = sorted((side*1820, 1400-i*2300, 695) for side in (-1, 1) for i in range(14))
    actual_trees = sorted(tuple(round(value, 2) for value in tree['position']) for tree in tree_instances)
    check(actual_trees == expected_trees, 'Saved tree instance world positions changed')
    check(found_roads == preserved_roads, 'Original road geometry missing')
    check(len(found_roads) == 5, 'Expected five preserved native road surface actors')
    check(len(actors) < 300, 'Modern City exceeds the 300 actor budget')
    lights = [a for a in actors if a.actor_has_tag('OOWCityLamp')]
    check(len(lights) == expected.get('nightLights') == 18, 'Expected eighteen budgeted City night lights')
    check(sum(batch['instances'] for batch in batches) == expected['batch']['instancesCreated'],
          'Saved instance count does not match the build report')
    report = {'savedMap': '/Game/Maps/City', 'passed': not failures, 'failures': failures,
              'actors': len(actors), 'camera': camera_record, 'cars': cars,
              'buildings': buildings, 'skyline': skyline, 'context': context,
              'contextBuildings': authored['contextBuildingCount'], 'ledPoles': leds, 'treeInstances': tree_instances,
              'savedBatches': batches, 'preservedRoadActors': len(found_roads), 'nightLights': len(lights),
              'modernMeshes': unique_meshes, 'modernMaterials': unique_materials}
    report['heroBuildings'] = hero_buildings
    report['authoredHeroWindowCount'] = authored.get('heroWindowCount', 0)
    report['facadeMaterials'] = facade_materials
    report['sidewalk'] = audit_sidewalk(actors, expected.get('sidewalk', {}), tree_instances, mesh_editor, check)
    report['entrances'] = audit_entrances(actors, expected.get('entrances', {}), mesh_editor, check)
    report['roads'] = audit_roads(actors, expected.get('roads', {}), check)
    report['nightLighting'] = audit_office_lights(actors, authored, expected.get('nightLighting', {}), source_digest, mesh_editor, check)
    report['distantLighting'] = audit_distant_lights(actors, authored, expected.get('distantLighting', {}),
                                                    expected.get('nightLighting', {}).get('gain', 0), check)
    report['streetLighting'] = audit_street_lights(lights, actors, authored, expected.get('streetLighting', {}), check)
    report['passed'] = not failures
    path = ROOT / 'Migration/city-modern-audit.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_CITY_AUDIT ' + json.dumps({'passed': not failures, 'actors': len(actors), 'failures': failures}))
    assert not failures, '; '.join(failures)
    return report


if __name__ == '__main__':
    main()
