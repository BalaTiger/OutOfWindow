"""Native thin-canvas transmission and a bounded set of occupied-window lights.

Called by build_surface_materials.py; no engine import is needed for --self-test
or --plan-only. Sources stay unchanged. RectLights are ordinary shadowed UE
lights: WindowDirector drives their OOWInteriorLight night envelope at runtime.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import sys

import build_window_interiors as windows
import build_room_boxes

LIGHT_PREFIX = 'OOWInteriorLight_'
MAX_LIGHTS = 12
OPTICAL_DEPTH = .65
TRANSMISSION_GAIN = .2
THIN_SHUTTER_ACTOR = 'OOW_00770_paris_building_09_19'


def add_awning_transmission(g, albedo, emission, night):
    """Keep existing surface inputs; incoming light, never emissive, lights cloth."""
    import unreal as u
    g.material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    g.material.set_editor_property('two_sided', True)
    # The native thin two-sided BxDF supplies incident-light direction and shadow
    # visibility. Beer-Lambert supplies the longer optical path at grazing view.
    # Do not gate scattering with Night: actual sun also passes through cloth.
    transmission = g.custom(
        'float NoV=saturate(abs(dot(normalize(N),normalize(V)))); '
        'float path=1./max(NoV,.12); '
        'return saturate(C)*saturate(Gain)*exp(-max(.05,Depth)*path);',
        {'C': albedo, 'N': g.node(u.MaterialExpressionPixelNormalWS),
         'V': g.node(u.MaterialExpressionCameraVectorWS),
         'Gain': g.scalar('OOWAwningTransmission', TRANSMISSION_GAIN),
         'Depth': g.scalar('OOWAwningOpticalDepth', OPTICAL_DEPTH)},
        True, 'OOW thin canvas: shadowed native backlighting, bounded view path length')
    g.output(transmission, u.MaterialProperty.MP_SUBSURFACE_COLOR)


def awning_parts(root, metadata):
    """Split source fabric into connected pieces before associating nearby rooms."""
    doc, blob = windows.read_glb(root / 'Migration' / 'Exported' / 'alley.glb')
    names = {n['name'] for n in metadata['nodes'] if n.get('motion') == 'awning'}
    parts = []
    for node in doc['nodes']:
        if node.get('name') not in names or 'mesh' not in node:
            continue
        matrix = node['matrix']
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            _, positions = windows.read_accessor(doc, blob, primitive['attributes']['POSITION'])
            _, raw_indices = windows.read_accessor(doc, blob, primitive['indices'])
            world = [tuple(sum(matrix[c*4+r]*p[c] for c in range(3)) + matrix[12+r]
                           for r in range(3)) for p in positions]
            indices = [index[0] for index in raw_indices]
            triangles = list(zip(indices[::3], indices[1::3], indices[2::3]))
            groups, welded = windows.Union(len(world)), {}
            for index, point in enumerate(world):
                key = tuple(round(v, 5) for v in point)
                groups.join(index, welded.setdefault(key, index))
            for a, b, c in triangles:
                groups.join(a, b)
                groups.join(a, c)
            pieces = collections.defaultdict(list)
            for triangle in triangles:
                pieces[groups.root(triangle[0])].append(triangle)
            for piece in pieces.values():
                area = sum(windows.length(windows.cross(windows.sub(world[b], world[a]),
                           windows.sub(world[c], world[a]))) * .5 for a, b, c in piece)
                if area < .1:
                    continue
                points = [world[index] for index in {i for tri in piece for i in tri}]
                lo, hi = ([min(p[i] for p in points) for i in range(3)],
                          [max(p[i] for p in points) for i in range(3)])
                parts.append({'actor': node['name'], 'center': [(a+b)*.5 for a, b in zip(lo, hi)],
                              'min': lo, 'max': hi, 'area': area})
    return parts


def in_view(point, camera):
    delta = windows.sub(point, camera['position'])
    forward = windows.unit(windows.sub(camera['target'], camera['position']))
    right = windows.unit(windows.cross(forward, (0, 1, 0)))
    up = windows.cross(right, forward)
    depth = windows.dot(delta, forward)
    half_height = depth * math.tan(math.radians(camera['verticalFov'] * .5))
    return (depth > 0 and windows.length(delta) < 55
            and abs(windows.dot(delta, up)) < half_height * 1.12
            and abs(windows.dot(delta, right)) < half_height * 1280/820 * 1.12)


def plan_window_lighting(root):
    root = Path(root)
    hero_lights = [room['light'] for room in build_room_boxes.plan(root)['rooms'] if room['light']]
    rect_budget = MAX_LIGHTS-len(hero_lights)
    if rect_budget < 0:
        raise RuntimeError('Physical interior lights exceed the shared window-light budget')
    metadata = json.loads((root / 'Migration' / 'Exported' / 'alley.json').read_text(encoding='utf-8'))
    geometry = json.loads((root / 'Migration' / 'window-interiors-geometry.json').read_text(encoding='utf-8'))
    rooms, camera = geometry['rooms'], metadata['camera']
    if any('normalThreeXYZ' not in room for room in rooms):
        raise RuntimeError('Run current build_window_interiors.py first: room outward normals are required')
    associations = []
    for part in awning_parts(root, metadata):
        # ponytail: nearest same-height aperture for this fixed source scene;
        # author an explicit association if future awnings span several shops.
        candidates = [room for room in rooms
                      if part['min'][1]-4 <= room['centerMeters'][1] <= part['max'][1]+.25
                      and all(part['min'][i]-1.2 <= room['centerMeters'][i] <= part['max'][i]+1.2
                              for i in (0, 2))]
        if not candidates:
            continue
        room = min(candidates, key=lambda r: windows.length(windows.sub(r['centerMeters'], part['center'])))
        distance = windows.length(windows.sub(room['centerMeters'], part['center']))
        if distance <= 4:
            associations.append({'awning': part['actor'], 'partCenterMeters': part['center'],
                                 'room': room['id'], 'distanceMeters': distance,
                                 'occupied': windows.shader_choice(room['seed'])[1]})
    associated = {a['room'] for a in associations}
    selected = [room for room in rooms if room['id'] not in windows.HERO_APERTURE_ROOM_IDS
                and windows.shader_choice(room['seed'])[1]
                and in_view(room['centerMeters'], camera)
                and windows.dot(room['normalThreeXYZ'], windows.sub(camera['position'], room['centerMeters'])) > 0]
    selected.sort(key=lambda room: (room['id'] not in associated,
                                   windows.length(windows.sub(room['centerMeters'], camera['position']))))
    lights, selected_rooms = [], []
    for room in selected:
        if len(lights) >= rect_budget:
            break
        # Source glass occasionally contains near-coincident separate apertures;
        # do not double the emitted energy by placing two rects in one opening.
        if any(windows.length(windows.sub(room['centerMeters'], other['centerMeters'])) < .75
               and windows.dot(room['normalThreeXYZ'], other['normalThreeXYZ']) > .95
               for other in selected_rooms):
            continue
        selected_rooms.append(room)
        normal, center = room['normalThreeXYZ'], room['centerMeters']
        position = [center[i] + normal[i] * .035 for i in range(3)]
        # Match the room's stable tint and brightness, not a second occupancy hash.
        seed = room['seed']
        tint_hash = (seed*41.137+.43) % 1
        tint = [a+(b-a)*tint_hash for a, b in zip((1, .88, .75), (.9, .94, 1))]
        gain = .8 + .4 * ((seed*31.718+.07) % 1)
        lights.append({'name': LIGHT_PREFIX + room['id'], 'room': room['id'], 'seed': seed,
                       'occupied': True, 'associatedAwning': room['id'] in associated,
                       'positionCm': [position[0]*100, position[2]*100, position[1]*100],
                       'outwardUE': [normal[0], normal[2], normal[1]],
                       'colorLinear': [a*b for a, b in zip(tint, (1, .79, .57))],
                       'lumens': 2 * gain, 'radiusCm': 400,
                       'widthCm': min(160, room['widthMeters']*65),
                       'heightCm': min(190, room['heightMeters']*65)})
    return {'recipe': 'awning-native-v7', 'appliedToUnreal': False,
            'sourceRoomCount': len(rooms), 'maxLights': MAX_LIGHTS,
            'heroLights': hero_lights, 'maxRectLights': rect_budget,
            'shaderOccupancy': 'step(.62,frac(seed*73.137+.11))',
            'nightEnvelope': 'smoothstep(.58,.86,Night), driven by WindowDirector',
            'transmission': {'shadingModel': 'TwoSidedFoliage', 'gain': TRANSMISSION_GAIN,
                             'opticalDepth': OPTICAL_DEPTH, 'emissiveAdded': False},
            'associations': associations, 'lights': lights}


def configure_window_lighting(root, world=None):
    """Apply while Alley is loaded. Caller saves the level; repeat is idempotent."""
    import unreal as u
    plan = plan_window_lighting(root)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    existing = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
    # The source louver panels are single-sided quads. A local MIC override is
    # required for Nanite's shadow raster path as well as the component flag.
    from build_surface_materials import resolve_source_path
    shutter = existing.get(THIN_SHUTTER_ACTOR)
    if shutter is None:
        raise RuntimeError('Missing confirmed thin shutter actor: ' + THIN_SHUTTER_ACTOR)
    comp = shutter.get_component_by_class(u.StaticMeshComponent)
    comp.set_editor_property('cast_shadow_as_two_sided', True)
    shutter.tags = sorted({str(tag) for tag in shutter.tags} | {'OOWThinShadowCaster'})
    plan['thinShutters'] = {'actor': THIN_SHUTTER_ACTOR, 'castShadowAsTwoSided': True, 'materials': []}
    for slot in range(comp.get_num_materials()):
        current = comp.get_material(slot)
        if not isinstance(current, u.MaterialInstanceConstant):
            raise RuntimeError('Thin shutter needs its existing imported/weather MIC')
        original = resolve_source_path(current.get_path_name(), lambda path:
            str(u.EditorAssetLibrary.get_metadata_tag(u.load_asset(path), 'OOWSource')))
        suffix = '_' + hashlib.sha1(original.encode()).hexdigest()[:8] if comp.get_num_materials() > 1 else ''
        path = '/Game/Materials/OOW/Instances/MI_AlleyThinShutters_v6' + suffix
        instance = u.load_asset(path)
        if instance is None:
            instance = u.EditorAssetLibrary.duplicate_asset(current.get_path_name(), path)
        if not isinstance(instance, u.MaterialInstanceConstant):
            raise RuntimeError('Could not create local shutter MIC: ' + path)
        overrides = instance.get_editor_property('base_property_overrides')
        overrides.set_editor_property('override_two_sided', True)
        overrides.set_editor_property('two_sided', True)
        instance.set_editor_property('base_property_overrides', overrides)
        u.MaterialEditingLibrary.update_material_instance(instance)
        # Point directly to the imported source; builder reruns unwrap this local
        # leaf before weather adaptation and then reapply this idempotent override.
        u.EditorAssetLibrary.set_metadata_tag(instance, 'OOWSource', original)
        u.EditorAssetLibrary.set_metadata_tag(instance, 'OOWRecipe', 'thin-shutters-v6')
        u.EditorAssetLibrary.save_loaded_asset(instance)
        comp.set_material(slot, instance)
        plan['thinShutters']['materials'].append({'slot': slot, 'path': instance.get_path_name(),
                                                  'parent': instance.get_editor_property('parent').get_path_name(),
                                                  'source': original})
    for actor in existing.values():
        if isinstance(actor, u.PostProcessVolume):
            actor.tags = sorted({str(tag) for tag in actor.tags} | {'OOWWindowLookdev'})
    wanted = {light['name'] for light in plan['lights']}
    for name, actor in existing.items():
        if name.startswith(LIGHT_PREFIX) and name not in wanted:
            actors.destroy_actor(actor)
    for light in plan['lights']:
        location = u.Vector(*light['positionCm'])
        actor = existing.get(light['name']) or actors.spawn_actor_from_class(u.RectLight, location)
        if not isinstance(actor, u.RectLight):
            raise RuntimeError('Unexpected actor using reserved window light label: ' + light['name'])
        actor.set_actor_label(light['name'])
        actor.set_actor_location(location, False, False)
        target = u.Vector(*(a+b for a, b in zip(light['positionCm'], light['outwardUE'])))
        actor.set_actor_rotation(u.MathLibrary.find_look_at_rotation(location, target), False)
        actor.tags = ['OOWNightLight', 'OOWInteriorLight', 'OOWRoom_' + light['room']]
        component = actor.get_component_by_class(u.RectLightComponent)
        component.set_mobility(u.ComponentMobility.MOVABLE)
        component.set_editor_property('intensity_units', u.LightUnits.LUMENS)
        component.set_intensity(light['lumens'])
        component.set_attenuation_radius(light['radiusCm'])
        component.set_source_width(light['widthCm'])
        component.set_source_height(light['heightCm'])
        component.set_barn_door_angle(75)
        component.set_barn_door_length(10)
        component.set_light_color(u.LinearColor(*light['colorLinear'], 1), False)
        component.set_cast_shadows(True)
        component.set_transmission(True)
        component.set_volumetric_scattering_intensity(0)
        light['actual'] = {'intensity': float(component.get_editor_property('intensity')),
                           'castShadows': bool(component.get_editor_property('cast_shadows')),
                           'transmission': bool(component.get_editor_property('transmission')),
                           'volumetricScattering': float(component.get_editor_property('volumetric_scattering_intensity'))}
    plan['appliedToUnreal'] = True
    (Path(root) / 'Migration' / 'awning-transmission.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    u.log('OOW_WINDOW_LIGHTS ' + str(len(plan['lights'])))
    return {'lights': len(plan['lights']),
            'awningLights': sum(light['associatedAwning'] for light in plan['lights']),
            'report': 'Migration/awning-transmission.json'}


def source_backlight_relations(root, plan):
    """Triangle-side evidence, not a claim of unobstructed GPU transmission."""
    root = Path(root)
    meta = json.loads((root / 'Migration/Exported/alley.json').read_text(encoding='utf-8'))
    names = {node['name'] for node in meta['nodes'] if node.get('motion') == 'awning'}
    camera = meta['camera']['position']
    doc, blob = windows.read_glb(root / 'Migration/Exported/alley.glb')
    lights = [(light, (light['positionCm'][0]/100, light['positionCm'][2]/100, light['positionCm'][1]/100),
               (light['outwardUE'][0], light['outwardUE'][2], light['outwardUE'][1])) for light in plan['lights']]
    evidence = []
    for node in doc['nodes']:
        if node.get('name') not in names:
            continue
        matrix, stats, area = node['matrix'], collections.defaultdict(lambda: collections.defaultdict(float)), 0
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            _, vertices = windows.read_accessor(doc, blob, primitive['attributes']['POSITION'])
            _, indices = windows.read_accessor(doc, blob, primitive['indices'])
            vertices = [tuple(sum(matrix[c*4+r]*v[c] for c in range(3)) + matrix[12+r]
                              for r in range(3)) for v in vertices]
            for index in range(0, len(indices), 3):
                a, b, c = [vertices[indices[index+j][0]] for j in range(3)]
                cross = windows.cross(windows.sub(b, a), windows.sub(c, a))
                triangle_area = windows.length(cross)*.5
                if triangle_area < 1e-7:
                    continue
                normal, center = windows.unit(cross), tuple((a[j]+b[j]+c[j])/3 for j in range(3))
                view = windows.unit(windows.sub(camera, center))
                area += triangle_area
                for light, position, direction in lights:
                    delta = windows.sub(position, center)
                    distance = windows.length(delta)
                    if distance >= light['radiusCm']/100:
                        continue
                    stat = stats[light['room']]
                    stat['insideRadiusAreaM2'] += triangle_area
                    if windows.dot(direction, windows.sub(center, position)) <= 0:
                        continue
                    stat['lightForwardHemisphereAreaM2'] += triangle_area
                    light_direction = windows.unit(delta)
                    if windows.dot(normal, view)*windows.dot(normal, light_direction) < 0:
                        stat['oppositeSidesAreaM2'] += triangle_area
                        stat['weightedNoV'] += triangle_area*abs(windows.dot(normal, view))
                        stat['weightedNoL'] += triangle_area*abs(windows.dot(normal, light_direction))
                        stat['weightedDistanceMeters'] += triangle_area*distance
        for room, stat in stats.items():
            back_area = stat['oppositeSidesAreaM2']
            evidence.append({'awning': node['name'], 'room': room, 'sourceTriangleAreaM2': area,
                             **{key: stat[key] for key in ('insideRadiusAreaM2', 'lightForwardHemisphereAreaM2', 'oppositeSidesAreaM2')},
                             'meanAbsNoV': stat['weightedNoV']/back_area if back_area else None,
                             'meanAbsNoL': stat['weightedNoL']/back_area if back_area else None,
                             'meanDistanceMeters': stat['weightedDistanceMeters']/back_area if back_area else None})
    return {'method': 'Source triangle centers; same native RectLight radius and forward hemisphere. '
                      'Opposite sides means light and camera straddle the cloth plane. '
                      'Area counts both authored shells; this is not visible pixel area or an occlusion test.',
            'pairs': evidence}


def audit_window_lighting(root, world=None):
    """Read assigned UE assets and light transforms; never alter or save assets."""
    import unreal as u
    mel = u.MaterialEditingLibrary
    root = Path(root)
    plan = json.loads((root / 'Migration/awning-transmission.json').read_text(encoding='utf-8'))
    expected_scalars = {'OOWAwningTransmission': TRANSMISSION_GAIN,
                        'OOWAwningOpticalDepth': OPTICAL_DEPTH}
    report = {'readOnly': True, 'awningActors': [], 'materials': {}, 'leafMaterials': {},
              'expectedAwningScalars': expected_scalars, 'lights': [], 'failures': []}
    actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    by_name = {actor.get_actor_label(): actor for actor in actors}
    meta = json.loads((root / 'Migration/Exported/alley.json').read_text(encoding='utf-8'))

    def check(condition, scope, message):
        if not condition:
            report['failures'].append({'scope': scope, 'error': message})

    shutter = by_name.get(THIN_SHUTTER_ACTOR)
    check(shutter is not None, THIN_SHUTTER_ACTOR, 'Missing confirmed thin shutter actor')
    report['thinShutters'] = {'actor': THIN_SHUTTER_ACTOR, 'materials': []}
    if shutter:
        comp = shutter.get_component_by_class(u.StaticMeshComponent)
        two_sided_shadow = bool(comp.get_editor_property('cast_shadow_as_two_sided'))
        report['thinShutters']['castShadowAsTwoSided'] = two_sided_shadow
        check(two_sided_shadow and 'OOWThinShadowCaster' in {str(tag) for tag in shutter.tags},
              THIN_SHUTTER_ACTOR, 'Thin shadow component flag/tag missing')
        from build_surface_materials import resolve_source_path
        for slot in range(comp.get_num_materials()):
            material = comp.get_material(slot)
            check(isinstance(material, u.MaterialInstanceConstant), THIN_SHUTTER_ACTOR, 'Thin shutter has no local MIC')
            if not isinstance(material, u.MaterialInstanceConstant):
                continue
            overrides = material.get_editor_property('base_property_overrides')
            enabled, two_sided = bool(overrides.get_editor_property('override_two_sided')), bool(overrides.get_editor_property('two_sided'))
            source = resolve_source_path(material.get_path_name(), lambda path:
                str(u.EditorAssetLibrary.get_metadata_tag(u.load_asset(path), 'OOWSource')))
            parent = material.get_editor_property('parent')
            report['thinShutters']['materials'].append({'slot': slot, 'path': material.get_path_name(),
                'overrideTwoSided': enabled, 'twoSided': two_sided, 'effectiveTwoSided': enabled and two_sided,
                'parent': parent.get_path_name(), 'resolvedImportedSource': source})
            check(enabled and two_sided, material.get_path_name(), 'Local thin shutter two-sided override is missing')
            check(str(u.EditorAssetLibrary.get_metadata_tag(parent, 'OOWRecipe')) == 'v2',
                  material.get_path_name(), 'Thin shutter lost its existing v2 parent')
            check(not source.startswith('/Game/Materials/OOW/'), material.get_path_name(), 'Shutter provenance did not unwrap to source')

    for semantic in meta['nodes']:
        if semantic.get('motion') != 'awning':
            continue
        actor = by_name.get(semantic['name'])
        check(actor is not None, semantic['name'], 'Missing awning actor')
        if actor is None:
            continue
        report['awningActors'].append(actor.get_actor_label())
        component = actor.get_component_by_class(u.StaticMeshComponent)
        for slot in range(component.get_num_materials()):
            master = component.get_material(slot)
            if isinstance(master, u.MaterialInstanceConstant):
                leaf_path = master.get_path_name()
                if leaf_path not in report['leafMaterials']:
                    values = {name: float(mel.get_material_instance_scalar_parameter_value(master, name))
                              for name in expected_scalars}
                    report['leafMaterials'][leaf_path] = values
                    for name, expected in expected_scalars.items():
                        check(abs(values[name]-expected) < 1e-6, leaf_path,
                              '%s resolved value %s differs from current %s' % (name, values[name], expected))
            else:
                check(False, actor.get_actor_label(), 'Awning slot has no leaf material instance')
            while isinstance(master, u.MaterialInstanceConstant):
                master = master.get_editor_property('parent')
            if not isinstance(master, u.Material):
                check(False, actor.get_actor_label(), 'Awning has no material master')
                continue
            path = master.get_path_name()
            if path in report['materials']:
                continue
            model = master.get_editor_property('shading_model')
            subsurface = mel.get_material_property_input_node(master, u.MaterialProperty.MP_SUBSURFACE_COLOR)
            code = str(subsurface.get_editor_property('code')) if isinstance(subsurface, u.MaterialExpressionCustom) else ''
            inputs = {key: mel.get_material_property_input_node(master, getattr(u.MaterialProperty, 'MP_'+key))
                      for key in ('NORMAL', 'ROUGHNESS', 'WORLD_POSITION_OFFSET', 'EMISSIVE_COLOR')}
            source_path = str(u.EditorAssetLibrary.get_metadata_tag(master, 'OOWSource'))
            source = u.load_asset(source_path)
            original_normal = mel.get_material_property_input_node(source, u.MaterialProperty.MP_NORMAL) if source else None
            report['materials'][path] = {'shadingModel': str(model), 'twoSided': bool(master.get_editor_property('two_sided')),
                                         'subsurfaceCode': code, 'source': source_path,
                                         'inputs': {key: value.get_class().get_name() if value else None for key, value in inputs.items()}}
            check(model == u.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE, path, 'Awning is not native TwoSidedFoliage')
            check(master.get_editor_property('two_sided'), path, 'Awning two-sided flag missing')
            check('NoV' in code and 'exp(' in code and 'saturate(C)' in code, path, 'View-path transmission input missing')
            check(inputs['NORMAL'] is not None or original_normal is None, path, 'Original fabric normal input lost')
            check(inputs['ROUGHNESS'] is not None and inputs['WORLD_POSITION_OFFSET'] is not None, path, 'Fabric roughness/wind input missing')
            from build_surface_materials import recipe_for
            check(str(u.EditorAssetLibrary.get_metadata_tag(master, 'OOWRecipe')) == recipe_for(('fabric', 'awning', '')),
                  path, 'Awning recipe differs from the surface builder')
    expected_names = {light['name'] for light in plan['lights']}
    actual_names = {actor.get_actor_label() for actor in actors if 'OOWInteriorLight' in {str(tag) for tag in actor.tags}
                    and not actor.actor_has_tag('OOWHeroLight')}
    check(actual_names == expected_names, 'lights', 'Saved window light set differs from plan')
    check(len(actual_names) <= plan['maxRectLights'], 'lights', 'Window light budget/count invalid')
    actual_hero = {actor.get_actor_label() for actor in actors if actor.actor_has_tag('OOWHeroLight')}
    check(actual_hero == {light['name'] for light in plan['heroLights']}, 'lights', 'Physical-room light set differs from plan')
    check(len(actual_names)+len(actual_hero) <= MAX_LIGHTS, 'lights', 'Combined window light budget exceeded')
    for light in plan['lights']:
        actor = by_name.get(light['name'])
        if not isinstance(actor, u.RectLight):
            check(False, light['name'], 'Missing native RectLight')
            continue
        component = actor.get_component_by_class(u.RectLightComponent)
        location, forward = actor.get_actor_location(), actor.get_actor_forward_vector()
        values = {key: component.get_editor_property(key) for key in
                  ('intensity', 'attenuation_radius', 'source_width', 'source_height', 'transmission',
                   'cast_shadows', 'volumetric_scattering_intensity', 'mobility', 'intensity_units',
                   'shadow_bias', 'shadow_slope_bias', 'contact_shadow_length', 'cast_raytraced_shadow')}
        position, direction = [location.x, location.y, location.z], [forward.x, forward.y, forward.z]
        report['lights'].append({'name': light['name'], 'positionCm': position, 'forward': direction,
                                 **{key: str(value) if key in ('mobility', 'intensity_units', 'cast_raytraced_shadow')
                                    else value for key, value in values.items()}})
        check(windows.length(windows.sub(position, light['positionCm'])) < .1, light['name'], 'Light position differs')
        check(windows.dot(direction, light['outwardUE']) > .9999, light['name'], 'Light points away from aperture exterior')
        check(values['mobility'] == u.ComponentMobility.MOVABLE and values['intensity_units'] == u.LightUnits.LUMENS,
              light['name'], 'Incorrect mobility/photometric units')
        check(values['transmission'] and values['cast_shadows'] and values['volumetric_scattering_intensity'] == 0,
              light['name'], 'Transmission/shadow/nonvolumetric settings differ')
        for prop, key in (('intensity', 'lumens'), ('attenuation_radius', 'radiusCm'), ('source_width', 'widthCm'), ('source_height', 'heightCm')):
            check(abs(values[prop]-light[key]) < .1, light['name'], prop+' differs from plan')
        check(windows.shader_choice(light['seed'])[1], light['name'], 'Window light belongs to an unoccupied room')
        check({'OOWNightLight', 'OOWInteriorLight'}.issubset({str(tag) for tag in actor.tags}), light['name'], 'Night envelope tags missing')
    check(any(isinstance(actor, u.PostProcessVolume) and 'OOWWindowLookdev' in {str(tag) for tag in actor.tags}
              for actor in actors), 'postprocess', 'Window lookdev tag missing')
    report['lightCount'] = len(actual_names)
    report['sourceGeometry'] = source_backlight_relations(root, plan)
    report['passed'] = not report['failures']
    return report


def self_test():
    transmission = lambda cosine: TRANSMISSION_GAIN * math.exp(-OPTICAL_DEPTH/max(abs(cosine), .12))
    assert 0 < transmission(.1) < transmission(.5) < transmission(1) < 1
    assert transmission(-.5) == transmission(.5)
    camera = {'position': [0, 0, 0], 'target': [0, 0, -1], 'verticalFov': 55}
    assert in_view((0, 0, -10), camera) and not in_view((0, 0, 10), camera)
    assert not in_view((40, 0, -10), camera)
    root = Path(__file__).resolve().parents[1]
    plan = plan_window_lighting(root)
    assert len(plan['lights']) == plan['maxRectLights'] == 4
    assert len(plan['heroLights']) == 8
    assert len(plan['lights'])+len(plan['heroLights']) <= MAX_LIGHTS
    assert not ({light['room'] for light in plan['lights']} & set(windows.HERO_APERTURE_ROOM_IDS))
    assert all(windows.shader_choice(light['seed'])[1] for light in plan['lights'])
    assert any(light['associatedAwning'] for light in plan['lights'])
    assert len({light['room'] for light in plan['lights']}) == len(plan['lights'])
    print(json.dumps({'selfTest': 'passed', 'lights': len(plan['lights']),
                      'awningLights': sum(light['associatedAwning'] for light in plan['lights']),
                      'normalTransmission': transmission(1), 'grazingTransmission': transmission(.1)}))


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        self_test()
    elif '--plan-only' in sys.argv:
        print(json.dumps(plan_window_lighting(Path(__file__).resolve().parents[1]), indent=2))
    else:
        raise SystemExit('Run through build_surface_materials.py or use --self-test / --plan-only')
