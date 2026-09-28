"""Create lit, depth-tested world-space precipitation materials (UE 5.7).

Run after import_scenes.py. The runtime owns fixed ISM instances; WPO moves
their centres on the GPU. No frame captures, particle textures or plugins.
"""
import unreal as u

LIB = u.MaterialEditingLibrary
TOOLS = u.AssetToolsHelpers.get_asset_tools()
FOLDER = '/Game/Weather'
u.EditorAssetLibrary.make_directory(FOLDER)


def expression(material, cls, **properties):
    node = LIB.create_material_expression(material, cls)
    for key, value in properties.items():
        node.set_editor_property(key, value)
    return node


def connect(source, target, input_name):
    if not LIB.connect_material_expressions(source, '', target, input_name):
        raise RuntimeError('Cannot connect material input ' + input_name)


def custom(material, code, output_type, inputs):
    node = expression(material, u.MaterialExpressionCustom, code=code, output_type=output_type)
    names = []
    for name in inputs:
        entry = u.CustomInput()
        entry.set_editor_property('input_name', name)
        names.append(entry)
    node.set_editor_property('inputs', names)
    for name, source in inputs.items():
        connect(source, node, name)
    return node


for snow in (False, True):
    name = 'M_Snow' if snow else 'M_Rain'
    material = u.load_asset(FOLDER + '/' + name)
    if not material:
        material = TOOLS.create_asset(name, FOLDER, u.Material, u.MaterialFactoryNew())
    LIB.delete_all_material_expressions(material)
    material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
    material.set_editor_property('translucency_lighting_mode',
                                 u.TranslucencyLightingMode.TLM_VOLUMETRIC_PER_VERTEX_NON_DIRECTIONAL)
    material.set_editor_property('two_sided', True)
    material.set_editor_property('disable_depth_test', False)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    # ISM culling must include the wrapped GPU position, not just each tiny
    # plane's original bounds (component BoundsScale alone is insufficient).
    material.set_editor_property('max_world_position_offset_displacement', 12500.0)
    material.set_editor_property('always_evaluate_world_position_offset', True)

    centre = expression(material, u.MaterialExpressionPerInstanceCustomData3Vector, data_index=0)
    rank_vertex = expression(material, u.MaterialExpressionPerInstanceCustomData, data_index=3)
    rank = expression(material, u.MaterialExpressionVertexInterpolator)
    connect(rank_vertex, rank, 'VS')
    uv = expression(material, u.MaterialExpressionTextureCoordinate)
    fall_speed = 220.0 if snow else 4600.0
    # Keep long-running desktop sessions numerically stable. A wrap moves the
    # field by exactly one volume height, so no visible global reset occurs.
    period = 5600.0 / fall_speed
    time = expression(material, u.MaterialExpressionTime, override_period=True, period=period)
    depth = expression(material, u.MaterialExpressionPixelDepth)
    amount = expression(material, u.MaterialExpressionScalarParameter,
                        parameter_name='Amount', default_value=0.0)
    minimum = expression(material, u.MaterialExpressionVectorParameter,
                         parameter_name='VolumeMin', default_value=u.LinearColor(-3000, -3000, -3000, 0))
    size = expression(material, u.MaterialExpressionVectorParameter,
                      parameter_name='VolumeSize', default_value=u.LinearColor(6000, 6000, 5600, 0))
    wind = expression(material, u.MaterialExpressionVectorParameter,
                      parameter_name='WindOffset', default_value=u.LinearColor(0, 0, 0, 0))
    velocity = expression(material, u.MaterialExpressionVectorParameter,
                          parameter_name='WindVelocity', default_value=u.LinearColor(0, 0, 0, 0))

    motion = '''
float3 p = Centre;
p.xy += WindOffset.xy;
p.z -= Time * FALL_SPEED;
p = Minimum.xyz + frac((p - Minimum.xyz) / max(Size.xyz, 1.0)) * Size.xyz;
MOTION_DETAIL
return p - Centre;
'''.replace('FALL_SPEED', str(fall_speed)).replace('MOTION_DETAIL',
        'p.xy += float2(sin(Time * ' + str(6.28318530718 * 5 / period) + ' + Centre.x), '
        'cos(Time * ' + str(6.28318530718 * 4 / period) + ' + Centre.y)) * 18.0;'
        if snow else 'p.xy -= WindVelocity.xy / 4600.0 * (Position.z - Centre.z);')
    motion_inputs = {'Centre': centre, 'Time': time, 'Minimum': minimum, 'Size': size,
                     'WindOffset': wind, 'WindVelocity': velocity, 'UV': uv}
    if not snow:
        # Shear each endpoint by its actual height, including the instance scale.
        motion_inputs['Position'] = expression(material, u.MaterialExpressionWorldPosition,
            world_position_shader_offset=u.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    wpo = custom(material, motion, u.CustomMaterialOutputType.CMOT_FLOAT3, motion_inputs)
    LIB.connect_material_property(wpo, '', u.MaterialProperty.MP_WORLD_POSITION_OFFSET)

    shape = ('1.0 - smoothstep(0.6, 1.0, length(UV * 2.0 - 1.0))' if snow else
             'pow(saturate(1.0 - abs(UV.x * 2.0 - 1.0)), 1.5) * saturate(1.0 - abs(UV.y * 2.0 - 1.0))')
    near_fade = '100.0, 350.0' if snow else '800.0, 1800.0'
    opacity = custom(material,
        'float population = saturate((Amount - Rank) * 20.0);\n'
        'float distanceFade = smoothstep(' + near_fade + ', Depth) * (1.0 - smoothstep(9000.0, 12000.0, Depth));\n'
        'return (' + shape + ') * population * distanceFade * ' + ('0.9;' if snow else '0.33;'),
        u.CustomMaterialOutputType.CMOT_FLOAT1,
        {'UV': uv, 'Rank': rank, 'Amount': amount, 'Depth': depth})
    fade = expression(material, u.MaterialExpressionDepthFade, fade_distance_default=20.0)
    connect(opacity, fade, 'Opacity')
    LIB.connect_material_property(fade, '', u.MaterialProperty.MP_OPACITY)
    colour = expression(material, u.MaterialExpressionConstant3Vector,
                        constant=u.LinearColor(0.85, 0.9, 0.98, 1) if snow else u.LinearColor(0.42, 0.48, 0.56, 1))
    roughness = expression(material, u.MaterialExpressionConstant, r=0.7 if snow else 0.15)
    LIB.connect_material_property(colour, '', u.MaterialProperty.MP_BASE_COLOR)
    LIB.connect_material_property(roughness, '', u.MaterialProperty.MP_ROUGHNESS)
    LIB.layout_material_expressions(material)
    LIB.recompile_material(material)
    u.EditorAssetLibrary.save_loaded_asset(material)
    u.log('OOW_PRECIPITATION_MATERIAL ' + material.get_path_name())

# Small airborne droplets following a ballistic arc after rain hits a real
# upward-facing surface. Ground/puddle ring ripples belong to surface shaders.
name = 'M_RainSplash'
material = u.load_asset(FOLDER + '/' + name)
if not material:
    material = TOOLS.create_asset(name, FOLDER, u.Material, u.MaterialFactoryNew())
LIB.delete_all_material_expressions(material)
material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
material.set_editor_property('translucency_lighting_mode',
                             u.TranslucencyLightingMode.TLM_VOLUMETRIC_PER_VERTEX_NON_DIRECTIONAL)
material.set_editor_property('two_sided', True)
material.set_editor_property('disable_depth_test', False)
material.set_editor_property('used_with_instanced_static_meshes', True)
material.set_editor_property('max_world_position_offset_displacement', 128.0)
material.set_editor_property('always_evaluate_world_position_offset', True)

normal = expression(material, u.MaterialExpressionPerInstanceCustomData3Vector, data_index=0)
phase = expression(material, u.MaterialExpressionPerInstanceCustomData, data_index=3)
angle = expression(material, u.MaterialExpressionPerInstanceCustomData, data_index=4)
rank_vertex = expression(material, u.MaterialExpressionPerInstanceCustomData, data_index=5)
speed = expression(material, u.MaterialExpressionPerInstanceCustomData, data_index=6)
time = expression(material, u.MaterialExpressionTime, override_period=True, period=1.4)
wind = expression(material, u.MaterialExpressionVectorParameter,
                  parameter_name='WindVelocity', default_value=u.LinearColor(0, 0, 0, 0))
amount = expression(material, u.MaterialExpressionScalarParameter,
                    parameter_name='OOW_RainAmount', default_value=0.0)
age = custom(material, 'return frac(Time / 1.4 + Phase) * 1.4;',
             u.CustomMaterialOutputType.CMOT_FLOAT1, {'Time': time, 'Phase': phase})
motion = custom(material, '''
float3 n = normalize(Normal);
float3 tangent = normalize(cross(n, abs(n.z) > 0.95 ? float3(0,1,0) : float3(0,0,1)));
float3 direction = cos(Angle) * tangent + sin(Angle) * cross(n, tangent);
float flight = 2.0 * Speed / 980.0;
float t = min(Age, flight);
float height = max(0.0, Speed * t - 490.0 * t * t);
return n * height + direction * t * 65.0 + WindVelocity.xyz * t * 0.025;
''', u.CustomMaterialOutputType.CMOT_FLOAT3,
    {'Normal': normal, 'Angle': angle, 'Speed': speed, 'Age': age, 'WindVelocity': wind})
LIB.connect_material_property(motion, '', u.MaterialProperty.MP_WORLD_POSITION_OFFSET)

pixel_inputs = {}
for key, node in {'Age': age, 'Speed': speed, 'Rank': rank_vertex}.items():
    interpolator = expression(material, u.MaterialExpressionVertexInterpolator)
    connect(node, interpolator, 'VS')
    pixel_inputs[key] = interpolator
pixel_inputs['UV'] = expression(material, u.MaterialExpressionTextureCoordinate)
pixel_inputs['Amount'] = amount
pixel_inputs['Depth'] = expression(material, u.MaterialExpressionPixelDepth)
opacity = custom(material, '''
float flight = 2.0 * Speed / 980.0;
float life = smoothstep(0.0, 0.012, Age) * (1.0 - smoothstep(flight * 0.65, flight, Age));
float shape = 1.0 - smoothstep(0.35, 1.0, length(UV * 2.0 - 1.0));
float population = saturate((Amount - Rank) * 20.0);
float distanceFade = smoothstep(100.0, 300.0, Depth) * (1.0 - smoothstep(8500.0, 11000.0, Depth));
return shape * life * population * distanceFade * 0.8;
''', u.CustomMaterialOutputType.CMOT_FLOAT1, pixel_inputs)
fade = expression(material, u.MaterialExpressionDepthFade, fade_distance_default=0.8)
connect(opacity, fade, 'Opacity')
LIB.connect_material_property(fade, '', u.MaterialProperty.MP_OPACITY)
colour = expression(material, u.MaterialExpressionConstant3Vector, constant=u.LinearColor(0.6, 0.67, 0.75, 1))
roughness = expression(material, u.MaterialExpressionConstant, r=0.2)
LIB.connect_material_property(colour, '', u.MaterialProperty.MP_BASE_COLOR)
LIB.connect_material_property(roughness, '', u.MaterialProperty.MP_ROUGHNESS)
LIB.layout_material_expressions(material)
LIB.recompile_material(material)
u.EditorAssetLibrary.save_loaded_asset(material)
u.log('OOW_PRECIPITATION_MATERIAL ' + material.get_path_name())
u.log('OOW_PRECIPITATION_COMPLETE')
