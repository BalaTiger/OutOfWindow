"""Bake six furnished room templates to static, calibrated HDR TextureCubes.

--self-test is CPU-only. --generate-only writes template GLB and the manifest.
In UE, run with a real RHI in a dedicated editor process; never use NullRHI.
The bake uses an isolated level and does not load or save the Alley level.
CaptureScene pushes deferred scene updates; TextureCube conversion synchronously
reads all six faces and flushes rendering. No runtime capture or POM is involved.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

RECIPE = 'interior-cubes-v3'
DEST = '/Game/Materials/OOW/InteriorMapping'
BAKE_DEST = '/Game/Scenes/Alley/InteriorAtlasBake'
BAKE_MAP = '/Game/Maps/OOWInteriorAtlasBake'
FACE_SIZE = 256
BOX_MIN = (-1.8, -.45, 0.)
BOX_MAX = (1.8, 3.05, 3.4)
WINDOW_MIN = (-1., 0.)
WINDOW_MAX = (1., 2.75)
# Keep the probe near the window: a room-centre probe greatly magnifies nearby
# furniture when its radiance is projected onto the room's outer box surfaces.
CAPTURE_CENTER = (0., 1.375, .20)
LAMP_LUMENS = 135.
CEILING_FILL_LUMENS = 120.
WINDOW_FILL_LUMENS = 60.
CUBE_PATHS = tuple(DEST + '/T_RoomCube_%02d' % index for index in range(1, 7))
TEXTURE_PATHS = CUBE_PATHS


def hdr_statistics(path):
    """Read UE's exported RGBE scanlines; reject a black/unrendered capture."""
    with path.open('rb') as stream:
        line = stream.readline()
        while line and not line.startswith(b'-Y '):
            line = stream.readline()
        tokens = line.split()
        if len(tokens) != 4 or tokens[2] != b'+X':
            raise RuntimeError('Unsupported HDR dimensions: ' + str(path))
        height, width = int(tokens[1]), int(tokens[3])
        luminance = []
        for _ in range(height):
            header = stream.read(4)
            if header == bytes((2, 2, width >> 8, width & 255)):
                channels = []
                for _ in range(4):
                    channel = bytearray()
                    while len(channel) < width:
                        count = stream.read(1)[0]
                        if count > 128:
                            channel.extend(stream.read(1)*(count-128))
                        elif count:
                            channel.extend(stream.read(count))
                        else:
                            raise RuntimeError('Invalid HDR RLE run')
                    if len(channel) != width:
                        raise RuntimeError('HDR RLE exceeds scanline')
                    channels.append(channel)
                pixels = zip(*channels)
            else:
                raw = header + stream.read(width*4-4)
                if len(raw) != width*4:
                    raise RuntimeError('Truncated HDR scanline')
                pixels = zip(*[iter(raw)]*4)
            for red, green, blue, exponent in pixels:
                luminance.append(((red+.5)*.2126+(green+.5)*.7152+(blue+.5)*.0722)
                                 *math.ldexp(1., exponent-136) if exponent else 0.)
    luminance.sort()
    result = {'width': width, 'height': height, 'min': luminance[0], 'max': luminance[-1],
              'mean': sum(luminance)/len(luminance),
              'p95': luminance[int((len(luminance)-1)*.95)],
              'p99': luminance[int((len(luminance)-1)*.99)],
              'nonBlackFraction': sum(value > .0001 for value in luminance)/len(luminance)}
    if result['max'] < .001 or result['nonBlackFraction'] < .2:
        raise RuntimeError('Interior capture is mostly black: ' + json.dumps(result))
    return result


def cube_direction(uv, ray, window_size):
    """CPU reference: ray=(right,up,inward) in world metres, already inward.

    Match real window width/height to the canonical window; depth follows height.
    Return the UE TextureCube direction (right,inward,up), hit and hit axis.
    """
    if min(window_size) <= 0 or ray[2] <= 0:
        raise ValueError('Window dimensions and inward ray component must be positive')
    scales = (2. / window_size[0], 2.75 / window_size[1], 2.75 / window_size[1])
    direction = tuple(a*b for a, b in zip(ray, scales))
    origin = (-1. + 2.*uv[0], 2.75*uv[1], 0.)
    distances = [((BOX_MAX[axis] if component > 0 else BOX_MIN[axis])-origin[axis])/component
                 if abs(component) > 1e-9 else math.inf for axis, component in enumerate(direction)]
    axis = min(range(3), key=distances.__getitem__)
    hit = tuple(origin[i] + direction[i]*distances[axis] for i in range(3))
    delta = tuple(hit[i]-CAPTURE_CENTER[i] for i in range(3))
    return (delta[0], delta[2], delta[1]), hit, axis


def generate(root):
    """Reuse actual furnished meshes; never derive room faces from photographs."""
    import build_room_boxes as rooms
    root = Path(root)
    descriptors = [rooms.template_room(index) for index in range(6)]
    for room in descriptors:
        for key, expected in (('imBoxMin', BOX_MIN), ('imBoxMax', BOX_MAX),
                              ('imWindowMin', WINDOW_MIN), ('imWindowMax', WINDOW_MAX)):
            if tuple(room[key]) != expected:
                raise RuntimeError('Template calibration differs: ' + room['name'] + '/' + key)
        if tuple(room['originMeters']) != (0., 0., 0.):
            raise RuntimeError('Bake templates must use the canonical origin')
    output = root / 'Migration/Generated/interior-atlas-rooms.glb'
    geometry = rooms.write_geometry(descriptors, output)
    geometry_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = {
        'recipe': RECIPE, 'bakedInUnreal': False, 'faceSize': FACE_SIZE,
        'sourceGeometry': str(output.relative_to(root)), 'sourceGeometrySha256': geometry_hash,
        'boxMin': BOX_MIN, 'boxMax': BOX_MAX, 'windowMin': WINDOW_MIN, 'windowMax': WINDOW_MAX,
        'captureCenter': CAPTURE_CENTER, 'canonicalAxes': ['right', 'up', 'inward'],
        'capturePlacement': 'Window centre height, 0.20 m behind the window plane',
        'cubeAxes': ['right', 'inward', 'up'],
        'windowRayScale': ['2/widthMeters', '2.75/heightMeters', '2.75/heightMeters'],
        'sampling': 'ray-box hit minus captureCenter, then swizzle xzy for TextureCube',
        'captureSource': 'SceneColor HDR; no tone mapping; fixed direct lighting; Night=1',
        'limits': 'Furniture radiance is projected onto one room box. It has no independent depth or disocclusion. '
                  'Near windows requiring accurate furniture occlusion retain real geometry.',
        'rooms': [{**part, 'cubeAsset': CUBE_PATHS[index], 'layout': descriptors[index]['layout'],
                   'lampLocalMeters': descriptors[index]['lampLocalMeters']}
                  for index, part in enumerate(geometry['rooms'])],
    }
    if len(manifest['rooms']) != 6:
        raise RuntimeError('Expected six furnished room templates')
    path = root / 'Migration/interior-atlas.json'
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return output, manifest, descriptors


def bake(root):
    import unreal as u
    import build_room_boxes as rooms
    if '-nullrhi' in u.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Interior cubemap baking needs a real RHI, not NullRHI')
    source, manifest, descriptors = generate(root)
    assets = u.AssetToolsHelpers.get_asset_tools()
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    # This dedicated level is a bake workspace. Never open or save production maps.
    open_level = levels.load_level if u.EditorAssetLibrary.does_asset_exist(BAKE_MAP) else levels.new_level
    if not open_level(BAKE_MAP):
        raise RuntimeError('Cannot open the isolated interior bake level')
    for actor in actors.get_all_level_actors():
        if str(actor.get_class().get_name()) not in ('WorldSettings', 'Brush'):
            actors.destroy_actor(actor)
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    for command in ('r.UsePreExposure 0', 'r.EyeAdaptationQuality 0', 'r.Lumen.DiffuseIndirect.Allow 0',
                    'r.Lumen.Reflections.Allow 0'):
        u.SystemLibrary.execute_console_command(world, command)

    manager = u.InterchangeManager.get_interchange_manager_scripted()
    params = u.ImportAssetParameters()
    params.is_automated, params.replace_existing = True, True
    imported = manager.import_asset(BAKE_DEST, manager.create_source_data(str(source)), params)
    meshes = {asset.get_name(): asset for asset in (imported or []) if isinstance(asset, u.StaticMesh)}
    for room in manifest['rooms']:
        if room['name'] not in meshes:
            mesh = u.load_asset(BAKE_DEST + '/' + source.stem + '/StaticMeshes/' + room['name'])
            if not isinstance(mesh, u.StaticMesh) or mesh.get_num_triangles(0) != room['renderTriangles']:
                raise RuntimeError('Missing or stale reused bake mesh: ' + room['name'])
            meshes[room['name']] = mesh

    slots = sorted({slot for room in manifest['rooms'] for slot in room['materialSlots']})
    materials = {}
    for slot in slots:
        parent = u.load_asset(rooms.MATERIAL_DEST + '/M_HeroRoom_' + slot)
        if not isinstance(parent, u.Material):
            raise RuntimeError('Build room materials before baking: M_HeroRoom_' + slot)
        name = 'MI_Bake_' + slot
        material = u.load_asset(BAKE_DEST + '/Materials/' + name)
        if material is None:
            material = assets.create_asset(name, BAKE_DEST + '/Materials', u.MaterialInstanceConstant,
                                           u.MaterialInstanceConstantFactoryNew())
        u.MaterialEditingLibrary.set_material_instance_parent(material, parent)
        u.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(material, 'Night', 1.)
        u.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(material, 'Occupied', 1.)
        u.MaterialEditingLibrary.update_material_instance(material)
        materials[slot] = material

    room_actor = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector())
    room_actor.set_actor_label('OOWInteriorBakeRoom')
    component = room_actor.static_mesh_component
    component.set_mobility(u.ComponentMobility.MOVABLE)
    component.set_cast_shadow(True)
    capture_actor = actors.spawn_actor_from_class(u.SceneCaptureCube,
        u.Vector(CAPTURE_CENTER[0]*100, CAPTURE_CENTER[2]*100, CAPTURE_CENTER[1]*100))
    capture = capture_actor.get_editor_property('capture_component_cube')
    capture.set_editor_property('capture_every_frame', False)
    capture.set_editor_property('capture_on_movement', False)
    capture.set_editor_property('capture_rotation', False)
    capture.set_editor_property('capture_source', u.SceneCaptureSource.SCS_SCENE_COLOR_HDR)
    capture.set_editor_property('post_process_blend_weight', 0.)
    target_name = 'RT_InteriorBake'
    target = u.load_asset(BAKE_DEST + '/' + target_name)
    if target is None:
        target = assets.create_asset(target_name, BAKE_DEST, u.TextureRenderTargetCube,
                                     u.TextureRenderTargetCubeFactoryNew())
    target.set_editor_property('hdr', True)
    target.set_editor_property('size_x', FACE_SIZE)
    capture.set_editor_property('texture_target', target)

    def point_light(name, point, lumens, temperature, shadows):
        actor = actors.spawn_actor_from_class(u.PointLight, u.Vector(point[0]*100, point[2]*100, point[1]*100))
        actor.set_actor_label(name)
        light = actor.get_component_by_class(u.PointLightComponent)
        light.set_mobility(u.ComponentMobility.MOVABLE)
        light.set_editor_property('intensity_units', u.LightUnits.LUMENS)
        light.set_intensity(lumens)
        light.set_editor_property('use_temperature', True)
        light.set_temperature(temperature)
        light.set_attenuation_radius(650.)
        light.set_cast_shadows(shadows)
        return actor

    lamp = point_light('OOWInteriorBakeLamp', descriptors[0]['lampLocalMeters'], LAMP_LUMENS, 3000., True)
    # ponytail: cheap fixed fill approximates diffuse bounce for background cubes;
    # use a calibrated GI/path-traced bake if close-up lighting fidelity is needed.
    point_light('OOWInteriorBakeCeilingFill', (0., 2.7, 1.6), CEILING_FILL_LUMENS, 3300., False)
    point_light('OOWInteriorBakeWindowFill', (0., 1.8, .15), WINDOW_FILL_LUMENS, 4200., False)

    for index, room in enumerate(manifest['rooms']):
        mesh = meshes.get(room['name'])
        if mesh is None:
            raise RuntimeError('Missing imported template: ' + room['name'])
        component.set_static_mesh(mesh)
        for slot, name in enumerate(room['materialSlots']):
            component.set_material(slot, materials[name])
        position = descriptors[index]['lampLocalMeters']
        lamp.set_actor_location(u.Vector(position[0]*100, position[2]*100, position[1]*100), False, False)
        u.AutomationLibrary.finish_loading_before_screenshot()
        capture.capture_scene()
        texture = u.load_asset(room['cubeAsset'])
        if texture is None:
            texture = u.RenderingLibrary.render_target_create_static_texture_cube_editor_only(
                target, room['cubeAsset'], u.TextureCompressionSettings.TC_HDR_COMPRESSED,
                u.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
        else:
            if not isinstance(texture, u.TextureCube):
                raise RuntimeError('Cube destination contains a different asset type: ' + room['cubeAsset'])
            u.RenderingLibrary.convert_render_target_to_texture_cube_editor_only(world, target, texture)
        if not isinstance(texture, u.TextureCube):
            raise RuntimeError('GPU capture did not produce a static TextureCube')
        texture.set_editor_property('srgb', False)
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_HDR_COMPRESSED)
        texture.set_editor_property('mip_gen_settings', u.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
        for key, value in (('OOWRecipe', RECIPE), ('OOWInteriorGeometry', manifest['sourceGeometrySha256']),
                           ('OOWInteriorCalibration', json.dumps([BOX_MIN, BOX_MAX, CAPTURE_CENTER])),
                           ('OOWInteriorVariant', str(index))):
            u.EditorAssetLibrary.set_metadata_tag(texture, key, value)
        u.EditorAssetLibrary.save_loaded_asset(texture)
        export_path = root / 'Art/InteriorMapping' / ('room-cube-%02d.hdr' % (index+1))
        export_path.parent.mkdir(parents=True, exist_ok=True)
        task = u.AssetExportTask()
        task.object, task.filename = texture, str(export_path)
        task.exporter = u.TextureCubeExporterHDR()
        task.automated, task.prompt, task.replace_identical = True, False, True
        u.AutomationLibrary.finish_loading_before_screenshot()
        if not u.Exporter.run_asset_export_task(task) or not export_path.is_file():
            raise RuntimeError('Cannot export cube evidence: ' + str(export_path))
        room['hdrExport'] = str(export_path.relative_to(root))
        room['hdrExportSha256'] = hashlib.sha256(export_path.read_bytes()).hexdigest()
        room['luminance'] = hdr_statistics(export_path)
        room['textureClass'] = texture.get_class().get_name()
        room['captured'] = True
        u.log('OOW_INTERIOR_CUBE ' + room['cubeAsset'])

    manifest['bakedInUnreal'] = True
    manifest['captureSynchronization'] = 'FinishLoadingBeforeScreenshot; CaptureScene end-of-frame updates; '
    manifest['captureSynchronization'] += 'TextureCube ReadFloat16Pixels/FlushRenderingCommands'
    manifest['lighting'] = {'lampLumens': LAMP_LUMENS, 'ceilingFillLumens': CEILING_FILL_LUMENS,
                            'windowFillLumens': WINDOW_FILL_LUMENS,
                            'lampShadows': True, 'ceilingFillShadows': False, 'windowFillShadows': False,
                            'night': 1., 'lumen': False, 'runtimeCapture': False}
    (root / 'Migration/interior-atlas.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    u.log('OOW_INTERIOR_ATLAS_COMPLETE ' + json.dumps({'recipe': RECIPE, 'cubes': 6, 'faceSize': FACE_SIZE}))
    return manifest


def self_test():
    assert all(lo < value < hi for lo, value, hi in zip(BOX_MIN, CAPTURE_CENTER, BOX_MAX))
    assert len(CUBE_PATHS) == len(set(CUBE_PATHS)) == 6
    for uv, ray, expected_axis, expected_sign in (
            ((.5, .5), (0., 0., 1.), 2, 1),
            ((.5, .5), (0., 1., .1), 1, 1),
            ((.5, .5), (0., -1., .1), 1, -1),
            ((.5, .5), (1., 0., .1), 0, 1)):
        direction, hit, axis = cube_direction(uv, ray, (2., 2.75))
        assert axis == expected_axis
        assert abs(hit[axis] - (BOX_MAX[axis] if expected_sign > 0 else BOX_MIN[axis])) < 1e-8
        assert all(lo-1e-8 <= value <= hi+1e-8 for lo, value, hi in zip(BOX_MIN, hit, BOX_MAX))
        if axis == 1:
            assert direction[2]*expected_sign > 0, 'Ceiling/floor must sample the correct cube Z face'
    # The visible A-window lower ray must no longer select a photographed floor
    # from an arbitrary rear card: its geometric box hit defines the cube lookup.
    direction, hit, axis = cube_direction((.5, .1), (.374728738, .289961893, .880625047),
                                          (1.88654336, 2.74836391))
    assert axis in (0, 2) and hit[1] > WINDOW_MIN[1]
    print(json.dumps({'recipe': RECIPE, 'cubes': 6, 'boxMin': BOX_MIN, 'boxMax': BOX_MAX,
                      'captureCenter': CAPTURE_CENTER, 'orientationChecks': 'passed',
                      'visibleWindowHit': hit, 'visibleWindowCubeDirection': direction}))


if __name__ == '__main__':
    project_root = Path(__file__).resolve().parent.parent
    if '--self-test' in sys.argv:
        self_test()
    elif '--generate-only' in sys.argv:
        _, result, _ = generate(project_root)
        print(json.dumps(result, indent=2))
    else:
        bake(project_root)
