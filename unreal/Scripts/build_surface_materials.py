"""Adapt imported glTF materials without editing any imported/plugin master.

Run in UE after import_scenes.py. OOW_MATERIAL_SCENES defaults to all five maps;
OOW_MATERIAL_KINDS=ground,stone restricts repairs to those surface kinds.
OOW_MATERIAL_PROBE_ONLY=1 only writes Migration/material-probe.json. Runtime MIDs
drive Wetness/Water/RainIntensity/Night [0,1], WindStrength [m/s] and
WindDirection [world unit XY]. Water expands ground puddles; RainIntensity
drives their ripples independently of retained water after rain stops.
Native Time drives water/wind. Plain Python --self-test checks semantic routing.
OOWWindowInterior actors use UV1 for room images and constant UV2=(seed,flag):
2=hero aperture, 1=detailed room, .5=basic room, 0=legacy fallback, -1=frame.
Tagged interiors use v16 calibrated baked cubemaps and geometric room openings.
Awning hems use v17, foliage uses v8, ground/stone uses v9, other windows retain v3 and other surfaces retain v2.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

VERSION = 'v2'
DEST = '/Game/Materials/OOW'
INTERIOR_OVERRIDES = {'OOWInteriorEnabled': 1.0, 'OOWInteriorMipBias': 0.,
                      'OOWInteriorGain': 1.0}
LEGACY_CURTAIN_ACTORS = {
    'OOW_00728_Paris_Building_08_paris_building_08_9',
    'OOW_00739_Paris_Building_08_paris_building_08_9__2_',
    'OOW_00751_Paris_Building_08_paris_building_08_9__3_',
}


def source_curtain(node):
    # These three Bistro variants are vertical indoor hanging cloth, despite
    # their shared Cyan awning material. The actual outdoor Cyan awnings stay.
    return node.get('materials') == ['MASTER_Curtains'] or (
        node.get('name') in LEGACY_CURTAIN_ACTORS
        and node.get('materials') == ['MASTER_Awning_Fabric_Cyan'])
PROFILES = {  # wet albedo multiplier, roughness multiplier, roughness floor
    'stone': (.80, .52, .27), 'ground': (.76, .34, .16),
    'wood': (.82, .55, .24), 'metal': (.94, .58, .13),
    'fabric': (.89, .78, .54), 'foliage': (.92, .70, .28),
    'generic': (.87, .55, .22), 'glass': (.98, .82, .065),
}


def classify(name, motion=None, source=None, semantic=None):
    """Only exported motion metadata permits WPO; material names never move buildings."""
    n = name.lower()
    semantic = semantic or {}
    # This exported group contains only the road, parking, cycle lanes,
    # sidewalks and markings built by buildCityRoadLayout. Its materials are
    # otherwise anonymous Material_32..37 and must not classify every concrete
    # building or every Material_N as a puddle surface.
    ground_node = ('city-road-functional-zones' in semantic.get('ancestors', [])
                   or semantic.get('source') == 'city-grounding-underlay')
    ground_node = ground_node and semantic.get('car', -1) < 0 and not motion
    lamp = bool(re.search(r'light_bulb|streetlight_glass|stringlights|spotlight_(emissive|glass)|headlight', n))
    glass = 'glass' in n and not lamp
    window = glass and bool(re.search(r'^master_(focus_)?glass|^master_frosted_glass|facade_glass', n))
    if glass:
        kind = 'glass'
    elif motion == 'foliage':
        kind = 'foliage'
    elif re.search(r'fabric|awning|canvas', n):
        kind = 'fabric'
    elif ground_node or re.search(r'pavement|road|asphalt|cobble|ground|terrain|curbstone', n):
        kind = 'ground'
    elif re.search(r'foliage|leaves|leaf|needles', n):
        kind = 'foliage'
    elif re.search(r'brick|concrete|plaster|masonry|stone|roof', n):
        kind = 'stone'
    elif re.search(r'wood|timber|bark', n):
        kind = 'wood'
    elif re.search(r'metal|steel|iron|bronze|copper|manhole|railing', n):
        kind = 'metal'
    else:
        kind = 'generic'
    # Unnamed program-generated materials retain their exported physical response.
    if kind == 'generic' and (source or {}).get('pbrMetallicRoughness', {}).get('metallicFactor', 0) > .6:
        kind = 'metal'
    wind = motion if motion in ('foliage', 'awning') else ''
    return kind, wind, 'lamp' if lamp else ('window' if window else '')


def glb_materials(path):
    with open(path, 'rb') as f:
        magic, version, _ = struct.unpack('<III', f.read(12))
        size, chunk = struct.unpack('<II', f.read(8))
        assert magic == 0x46546C67 and version == 2 and chunk == 0x4E4F534A
        document = json.loads(f.read(size))
    return {m.get('name', ''): m for m in document.get('materials', [])}


def asset_name(prefix, identity):
    readable = re.sub(r'[^A-Za-z0-9_]', '_', identity.rsplit('/', 1)[-1])[:45]
    return prefix + '_' + readable + '_' + hashlib.sha1(identity.encode()).hexdigest()[:10]


def recipe_for(profile, interior=False):
    if profile[1] == 'awning':
        return 'v17'
    if profile[1] == 'foliage':
        return 'v8'
    if profile[0] in ('ground', 'stone'):
        return 'v9'
    return ('v16' if interior else 'v3') if profile[2] == 'window' else VERSION


def wind_anchor_data(lower, upper):
    """Current tagged meshes are upright; tilted assets need authored axis weights."""
    height = upper[2] - lower[2]
    if height <= 0 or max(abs(upper[i] - lower[i]) for i in (0, 1)) > .01:
        raise RuntimeError('Wind mesh must be upright with positive height')
    return lower[2], height


def configure_wind_bounds(comp):
    lo, hi = comp.get_local_bounds()
    transform = comp.get_world_transform()
    endpoints = [u.MathLibrary.transform_location(transform, u.Vector(0, 0, z)) for z in (lo.z, hi.z)]
    data = wind_anchor_data(*[tuple(getattr(p, axis) for axis in ('x', 'y', 'z')) for p in endpoints])
    # Saved primitive data keeps shared MIDs and exact mesh anchors independent
    # of render-path local transforms and the bounds expanded by WPO/Nanite.
    for index, value in enumerate(data):
        comp.set_default_custom_primitive_data_float(index, value)


def source_chain(material):
    chain = []
    while isinstance(material, u.MaterialInstanceConstant):
        chain.append(material)
        material = material.get_editor_property('parent')
    if not isinstance(material, u.Material):
        raise RuntimeError('Unsupported material parent: ' + str(material))
    if material.get_path_name().startswith(DEST + '/'):
        raise RuntimeError('Generated master reached without original source; refusing stacked weather: ' + material.get_path_name())
    return material, chain


def resolve_source_path(path, source_for_path):
    """Follow metadata across any recipe versions, never reuse a weather graph."""
    seen = set()
    while path.startswith(DEST + '/'):
        if path in seen:
            raise RuntimeError('Cyclic OOWSource metadata: ' + path)
        seen.add(path)
        source = source_for_path(path)
        if not source or source == 'None':
            raise RuntimeError('Generated surface has no OOWSource metadata: ' + path)
        path = source
    return path


def original_material(material):
    def source_for_path(path):
        asset = u.load_asset(path)
        if not asset:
            raise RuntimeError('Missing OOWSource asset: ' + path)
        return str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWSource'))
    path = resolve_source_path(material.get_path_name(), source_for_path)
    original = u.load_asset(path)
    if not original:
        raise RuntimeError('Missing original material: ' + path)
    return original


class Graph:
    def __init__(self, material):
        self.material, self.index = material, 0

    def node(self, cls, **properties):
        self.index += 1
        node = mel.create_material_expression(self.material, cls, -1400 + self.index * 35, 400 + self.index * 50)
        if not node:
            raise RuntimeError('Cannot create ' + str(cls))
        for key, value in properties.items():
            node.set_editor_property(key, value)
        return node, ''

    def constant(self, value):
        return self.node(u.MaterialExpressionConstant, r=float(value))

    def vector(self, value):
        return self.node(u.MaterialExpressionConstant3Vector, constant=u.LinearColor(*value, 1.0))

    def scalar(self, name, default=0):
        return self.node(u.MaterialExpressionScalarParameter, parameter_name=name, default_value=float(default))

    def custom(self, code, inputs, vector=False, description='OOW weather'):
        pins = []
        for key in inputs:
            pin = u.CustomInput()
            pin.set_editor_property('input_name', key)
            pins.append(pin)
        out = self.node(u.MaterialExpressionCustom, code=code, inputs=pins, description=description,
                        output_type=u.CustomMaterialOutputType.CMOT_FLOAT3 if vector else u.CustomMaterialOutputType.CMOT_FLOAT1)
        for key, value in inputs.items():
            self.connect(value, out, key)
        return out

    def connect(self, source, destination, pin):
        if not mel.connect_material_expressions(source[0], source[1], destination[0], pin):
            raise RuntimeError('Cannot connect ' + str(source[0]) + ' to ' + pin)

    def read(self, prop, fallback):
        node = mel.get_material_property_input_node(self.material, prop)
        if node:
            return node, mel.get_material_property_input_node_output_name(self.material, prop)
        return self.vector(fallback) if isinstance(fallback, tuple) else self.constant(fallback)

    def output(self, source, prop):
        if not mel.connect_material_property(source[0], source[1], prop):
            raise RuntimeError('Cannot connect material property ' + str(prop))

    def position(self):
        return self.node(u.MaterialExpressionWorldPosition,
                         world_position_shader_offset=u.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)


def probe(material):
    base, chain = source_chain(material)
    key = base.get_path_name()
    if key not in probes:
        props = {}
        for name in ('BASE_COLOR', 'ROUGHNESS', 'EMISSIVE_COLOR', 'WORLD_POSITION_OFFSET', 'MATERIAL_ATTRIBUTES'):
            prop = getattr(u.MaterialProperty, 'MP_' + name)
            node = mel.get_material_property_input_node(base, prop)
            props[name] = {'node': node.get_class().get_name(), 'output': mel.get_material_property_input_node_output_name(base, prop)} if node else None
        probes[key] = {'usesMaterialAttributes': bool(base.get_editor_property('use_material_attributes')),
                       'properties': props, 'example': material.get_path_name(),
                       'chain': [item.get_path_name() for item in chain]}
    return base, chain


def duplicate(source, folder, name, recipe=VERSION):
    path = folder + '/' + name
    existing = u.load_asset(path)
    if existing:
        existing_recipe = str(u.EditorAssetLibrary.get_metadata_tag(existing, 'OOWRecipe'))
        if existing_recipe == recipe:
            return existing, False
        # v2's first ground build failed before assignment/saving its recipe.
        # Recover only this exact generated ground master, with no referencers.
        incomplete_ground = (folder == DEST + '/Masters' and isinstance(existing, u.Material)
                             and re.fullmatch(r'M_ground_.*_v2_[0-9a-f]{10}', name)
                             and existing_recipe in ('', 'None'))
        if not incomplete_ground or u.EditorAssetLibrary.find_package_referencers_for_asset(path, True):
            raise RuntimeError('Refusing to overwrite incomplete or referenced asset: ' + path)
        if not u.EditorAssetLibrary.delete_asset(path):
            raise RuntimeError('Cannot remove unreferenced failed ground master: ' + path)
        u.log_warning('OOW_RECOVERED_INCOMPLETE_GROUND ' + path)
    result = u.EditorAssetLibrary.duplicate_asset(source.get_path_name(), path)
    if not result:
        raise RuntimeError('Duplicate failed: ' + path)
    return result, True


def finish(asset, source=None, recipe=VERSION):
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWRecipe', recipe)
    if source:
        u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWSource', source.get_path_name())
    u.EditorAssetLibrary.save_loaded_asset(asset)


def ensure_mesh_usage(material):
    """Persist shader usage before saving, including when reusing an existing asset."""
    # ConnectMaterialProperty does not clear the imported constant-zero WPO flag.
    # Match the editor graph's UE-219232 handling, or a connected graph compiles
    # with UsesWorldPositionOffset=false. Repair existing generated masters too.
    if u.WindowMaterialLibrary.enable_connected_world_position_offset(material):
        mel.recompile_material(material)
        u.log('OOW_WPO_ENABLED ' + material.get_path_name())
    usages = [u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES]
    if material.get_blend_mode() in (u.BlendMode.BLEND_OPAQUE, u.BlendMode.BLEND_MASKED):
        usages.append(u.MaterialUsage.MATUSAGE_NANITE)
    for usage in usages:
        if not mel.has_material_usage(material, usage):
            mel.set_material_usage(material, usage)
        if not mel.has_material_usage(material, usage):
            raise RuntimeError('Material usage was not set: %s / %s' % (material.get_path_name(), usage))


def window_interior_textures():
    global interior_textures
    if interior_textures is not None:
        return interior_textures
    from build_interior_atlas import TEXTURE_PATHS
    textures = [u.load_asset(path) for path in TEXTURE_PATHS]
    if not all(isinstance(texture, u.TextureCube) for texture in textures):
        raise RuntimeError('Bake build_interior_atlas.py with a real RHI before building window materials')
    interior_textures = textures
    return textures


def hero_aperture(g, metadata):
    # Integer semantic flags survive Nanite's UV quantization and interpolation.
    return g.custom('return S.y>1.5 ? 0. : 1.;',
                    {'S': metadata}, description='OOW hero aperture')


def room_box_projection(g, uv, metadata):
    # The baked cube and ray intersection share one calibrated room, in metres.
    # ponytail: furniture is baked onto the proxy walls; large windows use geometry.
    from build_interior_atlas import CAPTURE_CENTER
    code = r'''
float2 size=max(Size.xy,float2(.05,.05));
float3 n=normalize(Normal);
float major=abs(n.x)>=abs(n.y)?n.x:n.y;
float3 cn=n*(major<0.?-1.:1.);
float3 right=normalize(float3(cn.y,-cn.x,0.));
float3 up=normalize(float3(0.,0.,1.)-n*n.z);
float3 view=normalize(View);
float3 ray=float3(-dot(view,right),-dot(view,up),max(.001,abs(dot(view,n))));
ray*=float3(2./size.x,2.75/size.y,2.75/size.y);
float3 p=float3((UV.x-.5)*2.,UV.y*2.75,0.);
float3 lo=float3(-1.8,-.45,0.), hi=float3(1.8,3.05,3.4);
float2 side=(float2(ray.x>0.?hi.x:lo.x,ray.y>0.?hi.y:lo.y)-p.xy)
    /float2(abs(ray.x)<.0001?.0001:ray.x,abs(ray.y)<.0001?.0001:ray.y);
if(abs(ray.x)<.0001) side.x=1.e6;
if(abs(ray.y)<.0001) side.y=1.e6;
float rear=hi.z/ray.z;
float t=min(rear,min(side.x,side.y));
float3 hit=p+ray*t;
// Cube uses UE axes: X=right, Y=inward, Z=up; capture centre is fixed.
float3 direction=hit-Capture;
return direction.xzy;
'''
    return g.custom(code, {'UV': uv, 'Size': g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=3),
                          'Normal': g.node(u.MaterialExpressionVertexNormalWS),
                          'View': g.node(u.MaterialExpressionCameraVectorWS), 'Seed': metadata,
                          'Capture': g.vector(CAPTURE_CENTER)},
                    True, 'OOW room-box projection')


def add_window_interior(g, fallback, night, textures, aperture):
    # UV2 is constant for every pane in one authored window group. Only texture
    # detail varies across UV1; occupancy, room choice and tint never vary per pixel.
    from build_interior_atlas import CAPTURE_CENTER
    uv = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=1)
    metadata = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=2)
    projection = room_box_projection(g, uv, metadata)
    inputs = {'F': fallback, 'N': night, 'S': metadata,
              'Enabled': g.scalar('OOWInteriorEnabled'), 'Intensity': g.scalar('OOWInteriorGain', 1),
              'GlassLayer': g.scalar('OOWInteriorGlassLayer'),
              'Aperture': aperture, 'Projection': projection, 'UV': uv,
              'Capture': g.vector(CAPTURE_CENTER),
              'Normal': g.node(u.MaterialExpressionPixelNormalWS),
              'View': g.node(u.MaterialExpressionCameraVectorWS)}
    mip_bias = g.scalar('OOWInteriorMipBias', 0)
    for index, texture in enumerate(textures):
        sample = g.node(u.MaterialExpressionTextureSampleParameterCube,
                        parameter_name='OOWRoom%02d' % (index + 1), texture=texture,
                        sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
                        mip_value_mode=u.TextureMipValueMode.TMVM_MIP_BIAS,
                        sampler_source=u.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS)
        g.connect(projection, sample, '')
        g.connect(mip_bias, sample, 'Bias')  # MaterialEditingLibrary uses the shortened MipBias pin name.
        inputs['R%d' % index] = (sample[0], 'RGB')
    code = ('if(Aperture<.5 || S.y<-.5 || (GlassLayer>.5 && S.y<.25)) return float3(0,0,0); '
            'float seed=saturate(S.x); float id=floor(frac(seed*17.171+.37)*6.); '
            'float3 room=id<1?R0:id<2?R1:id<3?R2:id<4?R3:id<5?R4:R5; '
            'float occupied=step(.62,frac(seed*73.137+.11)); '
            'float gain=lerp(.8,1.2,frac(seed*31.718+.07)); '
            'float3 tint=lerp(float3(1.,.88,.75),float3(.9,.94,1.),frac(seed*41.137+.43)); '
            'float3 hit=Projection.xzy+Capture; '
            'float floorFace=1.-step(-.449,hit.y), ceilingFace=step(3.049,hit.y); '
            'float sideFace=step(1.799,abs(hit.x)); '
            'float3 basic=lerp(float3(.10,.072,.043),float3(.17,.14,.10),ceilingFace); '
            'basic=lerp(basic,float3(.026,.016,.009),floorFace); '
            'basic*=lerp(.55,1.,saturate(hit.z/3.4))*(1.-sideFace*.18); '
            'room=lerp(basic,room,step(.75,S.y)); '
            'float3 inside=room*max(0.,Intensity) '
            '*tint*(gain*occupied*smoothstep(.58,.86,saturate(N))); '
            'float NoV=saturate(abs(dot(normalize(Normal),normalize(View)))); '
            'float fresnel=.04+.96*pow(1.-NoV,5.); '
            'float transmission=lerp((1.-fresnel)*(1.-fresnel),1.,saturate(GlassLayer)); '
            'return lerp(F,inside,saturate(Enabled)*step(.25,S.y))*transmission;')
    # The separate ThinTranslucent front sheet handles Fresnel when present.
    # Without that sheet this is a view-dependent approximation, not real glass.
    return g.custom(code, inputs, True, 'OOW calibrated baked HDR interior; constant per-window occupancy')


def add_puddles(g, roughness):
    """World XY depressions on upward ground faces; original graph outside pools."""
    p = u.MaterialProperty
    position = g.position()
    rain = g.scalar('RainIntensity')
    mask = g.custom(
        'float2 q=P.xy/220.+float2(sin(P.y/600.),sin(P.x/700.))*.25; '
        'float2 i=floor(q), f=frac(q); f=f*f*(3.-2.*f); '
        'float4 h=frac(sin(float4(dot(i,float2(127.1,311.7)), '
        'dot(i+float2(1,0),float2(127.1,311.7)), '
        'dot(i+float2(0,1),float2(127.1,311.7)), '
        'dot(i+float2(1,1),float2(127.1,311.7))))*43758.5453); '
        'float depression=lerp(lerp(h.x,h.y,f.x),lerp(h.z,h.w,f.x),f.y); '
        'float water=saturate(W); float edge=lerp(.18,.68,water); '
        # Shallow water is already smooth; depth expands coverage, not roughness.
        'return smoothstep(.02,.16,water)*(1.-smoothstep(edge-.045,edge+.045,depression))*smoothstep(.88,.98,Up.z);',
        {'P': position, 'W': g.scalar('Water'), 'Up': g.node(u.MaterialExpressionVertexNormalWS)},
        description='OOW low-frequency ground puddle coverage')
    g.output(g.custom('return lerp(R,min(R,.055+.025*saturate(Rain)),M);',
                      {'R': roughness, 'Rain': rain, 'M': mask}), p.MP_ROUGHNESS)
    g.output(g.custom('return C*(1.-.18*M);',
                      {'C': g.read(p.MP_BASE_COLOR, (0, 0, 0)), 'M': mask}, True), p.MP_BASE_COLOR)
    ripple = g.custom(
        'float2 q=P.xy/65., cell=floor(q); '
        'float seed=frac(sin(dot(cell,float2(127.1,311.7)))*43758.5453); '
        'float2 center=.2+.6*frac(sin(float2(seed*173.1,seed*297.7))*14537.1); '
        'float2 delta=frac(q)-center; float d=length(delta); '
        'float age=frac(T*1.15+seed), ring=d-age*.48; '
        'float slope=sin(ring*90.)*exp(-abs(ring)*36.)*(1.-age)*.045*saturate(Rain); '
        'float2 grad=delta/max(d,.001)*slope; return normalize(float3(-grad,1.));',
        {'P': position, 'T': g.node(u.MaterialExpressionTime), 'Rain': rain}, True,
        'OOW rain-driven expanding puddle rings')
    if g.material.get_editor_property('tangent_space_normal'):
        transform = g.node(u.MaterialExpressionTransform,
                           transform_source_type=u.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                           transform_type=u.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
        # Transform's display pin shortens to an empty name in UE 5.7;
        # MaterialEditingLibrary explicitly maps empty to its first input.
        g.connect(ripple, transform, '')
        ripple = transform
    original = g.read(p.MP_NORMAL, (0, 0, 1))
    g.output(g.custom('return normalize(lerp(O,R,M));',
                      {'O': original, 'R': ripple, 'M': mask}, True), p.MP_NORMAL)


def add_stone_wetness(g, wet, roughness):
    """Local vertical wet streaks over the existing damp masonry response."""
    p = u.MaterialProperty
    mask = g.custom(
        'float2 a=float2(abs(N.y)>.55?P.x:P.y,P.z)*.01; float mask=.08; '
        '[unroll] for(int k=0;k<2;k++) { '
        'float2 q=k==0?a*float2(.72,.12):float2(a.x*1.15,floor(a.y*.22)); '
        'float2 i=floor(q), f=frac(q); f=f*f*(3.-2.*f); '
        'float4 h=frac(sin(float4(dot(i,float2(127.1,311.7)), '
        'dot(i+float2(1,0),float2(127.1,311.7)), '
        'dot(i+float2(0,1),float2(127.1,311.7)), '
        'dot(i+float2(1,1),float2(127.1,311.7))))*43758.5453); '
        'mask+=lerp(lerp(h.x,h.y,f.x),lerp(h.z,h.w,f.x),f.y)*(k==0?.26:.16); } '
        'return saturate(W)*mask*(1.-smoothstep(.55,.9,abs(N.z)));',
        {'P': g.position(), 'N': g.node(u.MaterialExpressionVertexNormalWS), 'W': wet},
        description='OOW vertical masonry wet streaks; dry surfaces and upward roofs unchanged')
    g.output(g.custom('return C*(1.-.28*M);',
                      {'C': g.read(p.MP_BASE_COLOR, (0, 0, 0)), 'M': mask}, True), p.MP_BASE_COLOR)
    g.output(g.custom('return lerp(R,min(R,.24),saturate(M*2.));',
                      {'R': roughness, 'M': mask}), p.MP_ROUGHNESS)


def weather_master(base, profile, interior=False):
    key = (base.get_path_name(), profile, interior)
    if key in masters:
        return masters[key]
    # Explicit safe boundary: a Substrate/attributes master must not lose any
    # hidden UV, transmission, or custom-output channels through flattening.
    if base.get_editor_property('use_material_attributes'):
        raise RuntimeError('UseMaterialAttributes requires an attribute-preserving adapter: ' + base.get_path_name())
    if mel.get_material_property_input_node(base, u.MaterialProperty.MP_FRONT_MATERIAL):
        raise RuntimeError('Substrate FrontMaterial requires a BSDF adapter: ' + base.get_path_name())
    kind, wind, lighting = profile
    recipe = recipe_for(profile, interior)
    textures = window_interior_textures() if interior else None
    identity = base.get_path_name() + '/' + '_'.join(profile) + '_' + recipe
    material, created = duplicate(base, DEST + '/Masters', asset_name('M', identity), recipe)
    if created:
        g = Graph(material)
        p = u.MaterialProperty
        wet, night = g.scalar('Wetness'), g.scalar('Night')
        albedo, roughness, emission = (g.read(p.MP_BASE_COLOR, (0, 0, 0)),
                                       g.read(p.MP_ROUGHNESS, .5), g.read(p.MP_EMISSIVE_COLOR, (0, 0, 0)))
        darken, scale, floor = PROFILES[kind]
        g.output(g.custom('return C * lerp(1.0, %.5f, saturate(W));' % darken,
                          {'C': albedo, 'W': wet}, True), p.MP_BASE_COLOR)
        # Never make an already polished dry surface rougher when it gets wet.
        rough_code = 'float r = saturate(R); return lerp(r, min(r, max(%.5f, r*%.5f)), saturate(W));' % (floor, scale)
        if kind == 'glass':
            rough_code = 'float r = saturate(R); return max(.045, lerp(r, r*.82, saturate(W)) * lerp(1., .94, saturate(N)));'
        weather_roughness = g.custom(rough_code, {'R': roughness, 'W': wet, 'N': night})
        g.output(weather_roughness, p.MP_ROUGHNESS)
        if kind == 'ground':
            add_puddles(g, weather_roughness)
        elif kind == 'stone':
            add_stone_wetness(g, wet, weather_roughness)
        if lighting == 'lamp':
            gain = g.scalar('OOWLampGain', 1)
            g.output(g.custom('return E * G * smoothstep(.58,.86,saturate(N));',
                              {'E': emission, 'G': gain, 'N': night}, True), p.MP_EMISSIVE_COLOR)
        elif lighting == 'window':
            # One stable seed per primitive prevents occupancy cuts across a pane.
            # Merged windows share on/off state; no interiors or mesh splitting here.
            window_emission = g.custom('float3 cell=floor(P/280.); float h=frac(sin(dot(cell,float3(12.9898,78.233,37.719)))*43758.5453); '
                                       'return float3(.62,.36,.16)*step(.62,h)*smoothstep(.58,.86,saturate(N));',
                                       {'P': g.node(u.MaterialExpressionObjectPositionWS), 'N': night}, True)
            if interior:
                metadata = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=2)
                aperture = hero_aperture(g, metadata)
                window_emission = add_window_interior(g, window_emission, night, textures, aperture)
                material.set_editor_property('blend_mode', u.BlendMode.BLEND_MASKED)
                material.set_editor_property('opacity_mask_clip_value', .5)
                g.output(aperture, p.MP_OPACITY_MASK)
                # No diffuse tint or constant emission: all daytime window colour
                # comes from the current scene's native specular reflection.
                for prop, value in ((p.MP_BASE_COLOR, (0., 0., 0.)),
                                    (p.MP_SPECULAR, .5), (p.MP_METALLIC, 0.),
                                    (p.MP_AMBIENT_OCCLUSION, 1.),
                                    (p.MP_NORMAL, (0., 0., 1.))):
                    is_vector = isinstance(value, tuple)
                    target = g.vector(value) if is_vector else g.constant(value)
                    g.output(g.custom('return lerp(O,V,step(.25,S.y));',
                                      {'O': g.read(prop, value), 'V': target, 'S': metadata}, is_vector,
                                      'OOW opaque pane; preserve non-pane source faces'), prop)
                g.output(g.custom('return lerp(O,lerp(.20,.16,saturate(W)),step(.25,S.y));',
                                  {'O': weather_roughness, 'W': wet, 'S': metadata}), p.MP_ROUGHNESS)
                # ponytail: one low-resolution outdoor cube approximates distant
                # surroundings; native Lumen retains accurate local reflections.
                fallback = u.load_asset('/Engine/EngineResources/GrayDarkTextureCube')
                environment = g.node(u.MaterialExpressionTextureObjectParameter,
                    parameter_name='LocalWindowReflection', texture=fallback,
                    sampler_type=(u.MaterialSamplerType.SAMPLERTYPE_COLOR if fallback.get_editor_property('srgb')
                                  else u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR))
                capture_position = g.node(u.MaterialExpressionVectorParameter,
                                          parameter_name='LocalWindowCapturePosition')
                window_emission = g.custom(
                    '[branch] if (Aperture<.5 || GetRayTracingQualitySwitch() || Ready<.5 || S.y<.25 || distance(Camera,Capture)<1.) return E; '
                    'float3 environment=TextureCubeSampleLevel(LocalWindowReflection,LocalWindowReflectionSampler,R,2).rgb; '
                    'float NoV=saturate(abs(dot(normalize(N),normalize(V)))); '
                    'float fresnel=min(.4,.25+.75*pow(1.-NoV,5.))*lerp(1.,.12,smoothstep(.58,.86,saturate(Night))); '
                    'return E+environment*fresnel;',
                    {'E': window_emission, 'LocalWindowReflection': environment, 'S': metadata,
                     'Aperture': aperture, 'Night': night,
                     'Ready': g.scalar('LocalWindowReflectionReady'),
                     'R': g.node(u.MaterialExpressionReflectionVectorWS),
                     'Camera': g.node(u.MaterialExpressionCameraPositionWS), 'Capture': capture_position,
                     'N': g.node(u.MaterialExpressionPixelNormalWS),
                     'V': g.node(u.MaterialExpressionCameraVectorWS)}, True,
                    'Current outdoor HDR capture; skip its own six views to prevent feedback')
            g.output(window_emission, p.MP_EMISSIVE_COLOR)
        if kind == 'fabric' and wind == 'awning':
            add_awning_transmission(g, albedo, emission, night)
        if wind:
            old = g.read(p.MP_WORLD_POSITION_OFFSET, (0, 0, 0))
            direction = g.node(u.MaterialExpressionVectorParameter, parameter_name='WindDirection',
                               default_value=u.LinearColor(.8660254, -.5, 0, 0))
            position = g.position()
            minimum = g.node(u.MaterialExpressionScalarParameter, parameter_name='WindMinZ',
                             default_value=0., use_custom_primitive_data=True, primitive_data_index=0)
            height = g.node(u.MaterialExpressionScalarParameter, parameter_name='WindHeight',
                            default_value=100., use_custom_primitive_data=True, primitive_data_index=1)
            cloth = wind == 'awning'
            # Keep the canopy taut. Only its bottom 22% (the hanging valance)
            # bends, with a smooth attachment and no repeating rain impulses.
            cloth_code = (
                'float fraction=saturate((P.z-MinZ)/max(Height,.01)); '
                'float hem=1.-smoothstep(0.,.22,fraction); hem*=hem; '
                'float wind=sqrt(clamp(W/4.,0.,2.5)); '
                'float phase=dot(P.xy,float2(.006,.004)); '
                'float envelope=.85+.15*sin(T*.73+phase*.2); '
                'float swing=sin(T*12.566371+phase)*envelope; '
                'float ripple=sin(T*15.079645+phase*2.4)*.16; '
                'float2 direction=D.xy/max(length(D.xy),.001); '
                'float2 horizontal=direction*(swing+ripple)*wind*2.5; '
                'float vertical=sin(T*12.566371+phase+.6)*wind*.35; '
                'return O+float3(horizontal,vertical)*hem;')
            offset = g.custom(
                cloth_code if cloth else 'float height=max(Height,.01); float fraction=saturate((P.z-MinZ)/height); '
                'float anchor=%s; float amplitude=%s; '
                'float wind=sqrt(clamp(W/4.,0.,2.5)); float phase=dot(P.xy,float2(.0131,.0087)); '
                'float gust=.65+.35*sin(T*.73+phase*.2); '
                'float sway=sin(T*(1.5+wind*.3)+phase)*gust; '
                'float flutter=sin(T*8.1+phase*2.4)*.3; '
                'float age=frac(T*2.7+phase*.17); float impact=exp(-age*12.)*sin(age*35.)*saturate(Rain); '
                'float2 direction=D.xy/max(length(D.xy),.001); '
                'float2 horizontal=direction*(sway+flutter*.45)*wind*amplitude; '
                'float vertical=flutter*wind*%.3f+impact*%.3f; '
                'return O+float3(horizontal,vertical)*anchor;'
                % ('pow(fraction,1.25)', 'clamp(height*.055,4.5,32.)', 2., 2.5),
                {'P': position, 'MinZ': minimum, 'Height': height, 'T': g.node(u.MaterialExpressionTime),
                 'W': g.scalar('WindStrength', 8. / 3.6), 'Rain': g.scalar('RainIntensity'),
                 'D': direction, 'O': old}, True,
                'OOW v17 continuous 2 Hz valance swing' if cloth else 'OOW v8 anchored foliage gusts and leaf flutter')
            g.output(offset, p.MP_WORLD_POSITION_OFFSET)
            # Source motion is in metres; UE WPO is in centimetres. These cover
            # the worst-case hem swing or foliage gust and pad Nanite bounds.
            material.set_editor_property('max_world_position_offset_displacement', 6.0 if cloth else 60.0)
        ensure_mesh_usage(material)
        mel.recompile_material(material)
    else:
        ensure_mesh_usage(material)
    finish(material, base, recipe)
    masters[key] = material
    return material


def adapt(original, profile, source, interior=False, glass_backing=False):
    key = (original.get_path_name(), profile, interior, glass_backing)
    if key in instances:
        return instances[key]
    base, chain = probe(original)
    parent = weather_master(base, profile, interior)
    recipe = recipe_for(profile, interior)
    # Clone the whole chain: default glTF static switches live on plugin MIs,
    # not only on the imported leaf instance. Reparenting only the leaf loses them.
    for item in reversed(chain):
        identity = item.get_path_name() + '/' + '_'.join(profile) + '_' + recipe
        if glass_backing:
            identity += '_glassback'
        copied, created = duplicate(item, DEST + '/Instances', asset_name('MI', identity), recipe)
        if created:
            mel.set_material_instance_parent(copied, parent)
            if item == original and profile[2] == 'lamp':
                factors = source.get('emissiveFactor', [0, 0, 0])
                strength = source.get('extensions', {}).get('KHR_materials_emissive_strength', {}).get('emissiveStrength', 1)
                peak = max(factors) * strength
                mel.set_material_instance_scalar_parameter_value(copied, 'OOWLampGain', min(100., 2. / max(.02, peak)))
        interior_leaf = item == original and interior
        awning_leaf = item == original and profile[:2] == ('fabric', 'awning')
        if awning_leaf:
            from window_lookdev import TRANSMISSION_GAIN, OPTICAL_DEPTH
            mel.set_material_instance_scalar_parameter_value(copied, 'OOWAwningTransmission', TRANSMISSION_GAIN)
            mel.set_material_instance_scalar_parameter_value(copied, 'OOWAwningOpticalDepth', OPTICAL_DEPTH)
        if interior_leaf:
            for parameter, value in INTERIOR_OVERRIDES.items():
                mel.set_material_instance_scalar_parameter_value(copied, parameter, value)
            mel.set_material_instance_scalar_parameter_value(copied, 'OOWInteriorGlassLayer', 0.)
        if created or interior_leaf or awning_leaf:
            mel.update_material_instance(copied)
            finish(copied, item, recipe)
        parent = copied
    instances[key] = parent
    return parent


def water_material(scene_id):
    path = DEST + '/M_Water_' + scene_id + '_' + VERSION
    material = u.load_asset(path)
    if material:
        ensure_mesh_usage(material)
        finish(material)
        return material
    material = u.AssetToolsHelpers.get_asset_tools().create_asset(path.rsplit('/', 1)[1], DEST, u.Material, u.MaterialFactoryNew())
    if not material:
        raise RuntimeError('Cannot create native water material')
    material.set_editor_property('blend_mode', u.BlendMode.BLEND_OPAQUE)
    material.set_editor_property('tangent_space_normal', False)
    material.set_editor_property('two_sided', True)
    material.set_editor_property('max_world_position_offset_displacement', 15.0)
    g, p = Graph(material), u.MaterialProperty
    pos, time, wind = g.position(), g.node(u.MaterialExpressionTime), g.scalar('WindStrength', 2.2)
    inputs = {'P': pos, 'T': time, 'W': wind}
    coast = scene_id == 'coast'
    length, amplitude = (0.010, 6.0) if coast else (0.025, 1.1)
    waves = 'float k=%.6f; float w=clamp(W/8.,.15,1.7); float a=dot(P.xy,float2(k,k*.37))+T*1.1; float b=dot(P.xy,float2(-k*.64,k*1.7))-T*1.6; ' % length
    normal = waves + 'float2 slope=%.5f*w*(cos(a)*float2(k,k*.37)+.45*cos(b)*float2(-k*.64,k*1.7)); return normalize(float3(-slope,1.));' % amplitude
    displacement = waves + 'return float3(0,0,%.5f*w*(sin(a)+.45*sin(b)));' % amplitude
    g.output(g.custom(normal, inputs, True, 'OOW analytic world-space water normal'), p.MP_NORMAL)
    g.output(g.custom(displacement, inputs, True, 'OOW animated water height'), p.MP_WORLD_POSITION_OFFSET)
    g.output(g.vector((.014, .071, .09) if coast else (.025, .10, .095)), p.MP_BASE_COLOR)
    g.output(g.constant(0), p.MP_METALLIC)
    # Water F0 ~ .02 (IOR 1.333), instead of metallic/mirror coloration.
    g.output(g.constant(.255), p.MP_SPECULAR)
    g.output(g.custom('return lerp(.075,.17,saturate(W/18.));', {'W': wind}), p.MP_ROUGHNESS)
    ensure_mesh_usage(material)
    mel.recompile_material(material)
    finish(material)
    return material


def main():
    global u, mel, masters, instances, probes, interior_textures
    global add_awning_transmission, configure_window_lighting
    import unreal as u
    mel = u.MaterialEditingLibrary
    masters, instances, probes = {}, {}, {}
    interior_textures = None
    root = Path(u.Paths.project_dir()).parent
    sys.path.insert(0, str(root / 'Scripts'))
    from window_lookdev import add_awning_transmission, configure_window_lighting
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    ids = os.environ.get('OOW_MATERIAL_SCENES', 'alley,city,village,forest,coast').split(',')
    report, failures = [], []
    probe_only = os.environ.get('OOW_MATERIAL_PROBE_ONLY') == '1'
    kinds = set(filter(None, os.environ.get('OOW_MATERIAL_KINDS', '').split(',')))
    if kinds - PROFILES.keys():
        raise RuntimeError('Unknown OOW_MATERIAL_KINDS: ' + str(kinds - PROFILES.keys()))
    for scene_id in (value.strip() for value in ids if value.strip()):
        path = '/Game/Maps/' + scene_id.capitalize()
        if not levels.load_level(path):
            raise RuntimeError('Cannot load ' + path)
        metadata = json.loads((root / 'Migration' / 'Exported' / (scene_id + '.json')).read_text(encoding='utf-8'))
        nodes = {n['name']: n for n in metadata['nodes']}
        sources = glb_materials(root / 'Migration' / 'Exported' / (scene_id + '.glb'))
        counts = {'scene': scene_id, 'slots': 0, 'waterActors': 0, 'windActors': 0, 'hiddenCurtainActors': 0,
                  'interiorSlots': 0, 'glassFrontActors': 0, 'glassBackingSlots': 0, 'profiles': {}}
        for actor in actors.get_all_level_actors():
            if not isinstance(actor, u.StaticMeshActor):
                continue
            label = actor.get_actor_label()
            comp = actor.static_mesh_component
            tags = {str(tag) for tag in actor.tags}
            if tags & {'OOWHeroRoom', 'OOWHeroGlass'}:
                continue
            if 'OOWWindowGlassFront' in tags:
                if kinds and 'glass' not in kinds:
                    continue
                if not probe_only:
                    actor.set_actor_hidden_in_game(True)
                    comp.set_visibility(False)
                    comp.set_editor_property('visible_in_ray_tracing', False)
                counts['glassFrontActors'] += 1
                continue
            semantic = nodes.get(label) or next((v for k, v in nodes.items() if label.startswith(k)), None)
            if not semantic:
                continue
            if scene_id == 'alley' and source_curtain(semantic):
                if not kinds or 'glass' in kinds:
                    if not probe_only:
                        actor.set_actor_hidden_in_game(True)
                        comp.set_visibility(False)
                        comp.set_editor_property('evaluate_world_position_offset', False)
                        comp.set_editor_property('evaluate_world_position_offset_in_ray_tracing', False)
                        comp.set_editor_property('visible_in_ray_tracing', False)
                    counts['hiddenCurtainActors'] += 1
                continue
            if semantic.get('water') or 'OOWWater' in tags:
                if kinds:
                    continue
                if not probe_only:
                    water = water_material(scene_id)
                    for index in range(comp.get_num_materials()):
                        comp.set_material(index, water)
                    comp.set_editor_property('bounds_scale', 1.1)
                    comp.set_editor_property('evaluate_world_position_offset_in_ray_tracing', True)
                counts['waterActors'] += 1
                continue
            if semantic.get('motion') in ('foliage', 'awning'):
                counts['windActors'] += 1
            for index in range(comp.get_num_materials()):
                original = comp.get_material(index)
                if not original:
                    continue
                names = semantic.get('materials', [])
                name = names[index] if index < len(names) else original.get_name()
                source = sources.get(name, {})
                profile = classify(name, semantic.get('motion'), source, semantic)
                if kinds and profile[0] not in kinds:
                    continue
                try:
                    original = original_material(original)
                    probe(original)
                    if not probe_only:
                        interior = profile[2] == 'window' and 'OOWWindowInterior' in tags
                        glass_backing = interior and 'OOWWindowGlassBacking' in tags
                        replacement = adapt(original, profile, source, interior, glass_backing)
                        comp.set_material(index, replacement)
                        counts['interiorSlots'] += int(interior)
                        counts['glassBackingSlots'] += int(glass_backing)
                        if profile[1]:
                            configure_wind_bounds(comp)
                            comp.set_editor_property('bounds_scale', 1.0)
                            comp.set_editor_property('evaluate_world_position_offset', True)
                            comp.set_editor_property('world_position_offset_writes_velocity', True)
                            comp.set_editor_property('evaluate_world_position_offset_in_ray_tracing', True)
                    counts['slots'] += 1
                    category = '/'.join(profile)
                    counts['profiles'][category] = counts['profiles'].get(category, 0) + 1
                except Exception as error:
                    item = {'scene': scene_id, 'actor': label, 'material': original.get_path_name(), 'error': str(error)}
                    failures.append(item)
                    u.log_error('OOW_MATERIAL_FAILURE ' + json.dumps(item))
        if not probe_only:
            if failures:
                raise RuntimeError('Material repair failed; map not saved: ' + json.dumps(failures))
            if scene_id == 'alley' and not kinds:
                world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
                counts['interiorLighting'] = configure_window_lighting(root, world)
            levels.save_current_level()
        report.append(counts)
        report_name = ('window-surface-repair.json' if kinds == {'glass'} else 'surface-wetness-repair.json') if kinds else 'material-probe.json'
        (root / 'Migration' / report_name).write_text(json.dumps({'masters': probes, 'scenes': report, 'failures': failures}, indent=2), encoding='utf-8')
        u.log('OOW_MATERIAL_SCENE ' + json.dumps(counts))
    if failures:
        raise RuntimeError('%d material slots require attention; see Migration/material-probe.json' % len(failures))
    u.log('OOW_MATERIAL_COMPLETE ' + json.dumps(report))


def self_test():
    cyan_curtains = {
        'OOW_00728_Paris_Building_08_paris_building_08_9',
        'OOW_00739_Paris_Building_08_paris_building_08_9__2_',
        'OOW_00751_Paris_Building_08_paris_building_08_9__3_',
    }
    awning_control = 'OOW_00517_paris_building_04_16'
    assert source_curtain({'name': 'ordinary_curtain', 'materials': ['MASTER_Curtains']})
    for label in cyan_curtains:
        assert source_curtain({'name': label, 'materials': ['MASTER_Awning_Fabric_Cyan']})
        assert not source_curtain({'name': label, 'materials': ['MASTER_Concrete']})
    assert not source_curtain({'name': awning_control, 'materials': ['MASTER_Awning_Fabric_Cyan'],
                               'motion': 'awning'})
    alley_export = Path(__file__).resolve().parent.parent / 'Migration' / 'Exported' / 'alley.json'
    if alley_export.exists():
        alley_nodes = json.loads(alley_export.read_text(encoding='utf-8'))['nodes']
        by_name = {node['name']: node for node in alley_nodes}
        expected_curtains = {node['name'] for node in alley_nodes if node['materials'] == ['MASTER_Curtains']} | cyan_curtains
        assert len(expected_curtains) == 74
        assert {node['name'] for node in alley_nodes if source_curtain(node)} == expected_curtains
        assert all(by_name[label]['materials'] == ['MASTER_Awning_Fabric_Cyan'] for label in cyan_curtains)
        awning = by_name[awning_control]
        assert not source_curtain(awning)
        assert classify(awning['materials'][0], awning.get('motion'), semantic=awning) == ('fabric', 'awning', '')
        print('Alley curtain routing passed: 74 hidden targets; outdoor Cyan awning 00517 retains wind routing')
    assert classify('MASTER_Concrete', 'building') == ('stone', '', '')
    assert classify('MASTER_Awning_Fabric_Cyan', 'awning') == ('fabric', 'awning', '')
    assert classify('MASTER_Focus_Glass') == ('glass', '', 'window')
    assert classify('Streetlight_Glass') == ('generic', '', 'lamp')
    assert classify('Vespa_Odometer_Glass') == ('glass', '', '')
    assert classify('modular_urban_apartments_facade_glass')[2] == 'window'
    assert recipe_for(classify('MASTER_Focus_Glass')) == 'v3'
    assert recipe_for(classify('modular_urban_apartments_facade_glass')) == 'v3'
    assert recipe_for(classify('MASTER_Focus_Glass'), interior=True) == 'v16'
    assert recipe_for(classify('MASTER_Awning_Fabric_Cyan', 'awning')) == 'v17'
    assert recipe_for(classify('Foliage_Leaves', 'foliage')) == 'v8'
    assert recipe_for(classify('Foliage_Leaves')) == 'v2'
    for name in ('Pavement_Cobble_Leaves_BLENDSHADER', 'Pavement_Cobblestone_Wet_Leaves_BLENDSHADER'):
        assert classify(name) == ('ground', '', '')
        assert recipe_for(classify(name)) == 'v9'
    assert classify('Pavement_Leaves', 'foliage') == ('foliage', 'foliage', '')
    assert recipe_for(classify('MASTER_Concrete')) == 'v9'
    assert wind_anchor_data((-3000, -22000, 1860), (-3000, -22000, 2040)) == (1860, 180)
    for lower, upper in (((0, 0, 2), (0, 0, 1)), ((0, 0, 1), (1, 0, 2))):
        try:
            wind_anchor_data(lower, upper)
            raise AssertionError('Unsupported wind mesh orientation was accepted')
        except RuntimeError:
            pass
    assert all(recipe_for(classify(name)) == 'v2'
               for name in ('Streetlight_Glass', 'Vespa_Odometer_Glass', 'MASTER_Awning_Fabric_Cyan'))
    assert recipe_for(classify('Streetlight_Glass'), interior=True) == 'v2'
    assert classify('Material_42', 'foliage') == ('foliage', 'foliage', '')
    assert classify('MASTER_Building_Details')[1] == ''
    road = {'ancestors': ['', 'city-road-functional-zones'], 'car': -1}
    assert classify('Material_33', semantic=road) == ('ground', '', '')
    assert classify('Material_33', semantic={'ancestors': ['building'], 'car': -1})[0] == 'generic'
    assert classify('Material_33', semantic={**road, 'car': 2})[0] == 'generic'
    assert classify('MASTER_Concrete', semantic={'source': 'Paris_Building_09'})[0] == 'stone'
    original = '/Game/Scenes/City/city/Materials/Material_33.Material_33'
    v1, v2, v3, v4, v5, v6, v7, v8 = (DEST + '/Instances/' + version for version in ('v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8'))
    links = {v8: v7, v7: v6, v6: v5, v5: v4, v4: v3, v3: v2, v2: v1, v1: original}
    assert resolve_source_path(v8, links.get) == original
    assert resolve_source_path(v7, links.get) == original
    assert resolve_source_path(v6, links.get) == original
    assert resolve_source_path(v5, links.get) == original
    assert resolve_source_path(v4, links.get) == original
    assert resolve_source_path(v3, links.get) == original
    assert resolve_source_path(v2, links.get) == original
    assert resolve_source_path(original, links.get) == original
    for invalid in ({v1: v1}, {v1: ''}):
        try:
            resolve_source_path(v1, invalid.get)
            raise AssertionError('Invalid provenance was accepted')
        except RuntimeError:
            pass
    exported = Path(__file__).resolve().parent.parent / 'Migration' / 'Exported' / 'city.json'
    if exported.exists():
        nodes = json.loads(exported.read_text(encoding='utf-8'))['nodes']
        road_nodes = [n for n in nodes if 'city-road-functional-zones' in n.get('ancestors', [])]
        assert road_nodes and all(classify(n['materials'][0], n.get('motion'), semantic=n)[0] == 'ground' for n in road_nodes)
        assert all(classify(n['materials'][0], n.get('motion'), semantic=n)[0] != 'ground'
                   for n in nodes if n.get('car', -1) >= 0)
        print('City exported road routing passed:', len(road_nodes), 'ground nodes; all car nodes excluded')
    for darken, scale, floor in PROFILES.values():
        assert 0 < darken <= 1 and 0 < scale <= 1 and 0 < floor < 1
        for dry in (0., .07, .3, .9):
            assert min(dry, max(floor, dry * scale)) <= dry
    print('OOW v9 ground/stone, v2 surfaces/v3 windows/v16 interiors/v8 foliage/v17 awning routing, provenance/idempotency guards and wetness bounds passed')


if __name__ == '__main__':
    self_test() if '--self-test' in sys.argv else main()
