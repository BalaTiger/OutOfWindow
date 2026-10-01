"""Build a project-owned volumetric storm-cell material for a controlled A/B.

Run through Unreal's Python editor commandlet; this only creates /Game/Weather
assets and a build report. It does not change maps or the engine cloud material.
The runtime can bind MI_OOW_StormCells_v2 to its existing VolumetricCloudComponent.
The native graph is duplicated and retained; StormClouds smoothly blends its
extinction/albedo/ambient occlusion into storm cells between 0.15 and 0.75.

Coordinates and shape controls are kilometres; Extinction is inverse metres.
StormClouds, Cloud_GlobalCoverage, Cloud_GlobalDensity and the two Layout_*
parameters retain the runtime's current weather/wind names. Additional OOW_*
parameters control cell spacing, the base/tower/anvil silhouette, and colours.
No clock-scaled wind: Layout_GlobalTexturePlacement is the already integrated
wind displacement, converted from layout UV to kilometres using its scale.
"""
import hashlib
import json
from pathlib import Path

import unreal as u


FOLDER = '/Game/Weather'
MASTER_NAME = 'M_OOW_StormCells_v2'
INSTANCE_NAME = 'MI_OOW_StormCells_v2'
RECIPE = 'storm-cells-v2'
NATIVE_MASTER = '/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud'
NATIVE_INSTANCE = '/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst'
NOISE_PATH = '/Engine/EngineSky/VolumetricClouds/VT_PerlinWorley_Balanced'
LIB = u.MaterialEditingLibrary
CONSERVATIVE_CODE = 'return float4(Native.r + Blend, Native.g, Native.b, Native.a);'


# Nine neighbouring cells make the silhouette continuous across grid borders.
# Two volume-texture reads provide rounded breakup and smaller erosion; the
# analytic envelope owns the broad base, narrower tower, and upper anvil.
# Noise is sampled only when the envelope/background deck contains matter.
SHAPE_CODE = r'''
float h = saturate(Height);
if (Storm <= 0.15)
    return float3(0.0, h, 0.0);
float layoutScale = max(LayoutScale, 1.0);
float scale = layoutScale / 32.0;
float3 p = Position * 0.00001;
p.xy -= Placement.xy * layoutScale + OffsetKm.xy;
float spacing = max(CellSpacingKm * scale, 1.0);
float2 grid = floor(p.xy / spacing);
float coverage = saturate(Coverage);
float coverageRadius = lerp(0.82, 1.20, coverage);
float envelope = 0.0;

[unroll] for (int j = -1; j <= 1; ++j)
{
    [unroll] for (int i = -1; i <= 1; ++i)
    {
        float2 key = grid + float2(i, j);
        // Stable cell variation, using arithmetic rather than trigonometric noise.
        float3 hash = frac(float3(key.x, key.y, key.x) * float3(0.1031, 0.1030, 0.0973));
        hash += dot(hash, hash.yzx + 33.33);
        float3 random = frac((hash.xxy + hash.yzz) * hash.zyx);
        float2 centre = (key + 0.5 + (random.xy - 0.5) * 0.28) * spacing;
        float top = lerp(0.82, 1.0, random.z);
        float localHeight = h / top;
        float vertical = smoothstep(0.0, 0.035, localHeight)
            * (1.0 - smoothstep(0.90, 1.0, localHeight));
        float radius = lerp(BaseRadiusKm, TowerRadiusKm,
            smoothstep(0.12, 0.50, localHeight));
        radius = lerp(radius, AnvilRadiusKm,
            smoothstep(0.64, 0.83, localHeight));
        radius *= scale * coverageRadius * lerp(0.88, 1.12, random.z);
        // A small height-dependent lean reads as wind shear, not a cylinder.
        float2 delta = p.xy - centre - ShearKm.xy * localHeight * localHeight;
        float radial = length(delta) / max(radius, 0.05);
        float body = 1.0 - smoothstep(0.56, 1.08, radial);
        envelope = max(envelope, body * vertical);
    }
}

// A translucent lower deck holds a rainy sky together without making the
// visible window patch a solid, featureless ceiling. It is separate from cells.
float deckBand = smoothstep(0.015, 0.075, h)
    * (1.0 - smoothstep(0.18, 0.28, h));
if (envelope <= 0.0 && deckBand <= 0.0)
    return float3(0.0, h, 0.0);

float3 noisePosition = float3(p.xy, p.z) / max(scale, 0.05);
float4 coarse = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(noisePosition * 0.42 + float3(0.17, 0.31, 0.09)), 0);
float4 fine = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(noisePosition * 1.65 + float3(0.63, 0.12, 0.47)), 0);
float erosion = (0.55 - coarse.r) * max(Erosion, 0.0)
    + (0.52 - fine.g) * 0.10;
float cells = saturate((envelope - erosion) * 1.65) * step(0.001, envelope);
float deck = deckBand * smoothstep(0.22, 0.78, coarse.r);
float stormWeight = lerp(0.50, 1.0, saturate(Storm));
// Runtime density is compatible with the old material, but cells use a lower
// coefficient to preserve edge transmission and visible volume at kilometre size.
float extinction = max(Density, 0.0) * stormWeight
    * (0.15 * cells + max(DeckStrength, 0.0) * deck);
return float3(extinction, h, cells);
'''


class Graph:
    """The same explicit connect-and-check pattern as build_surface_materials."""
    def __init__(self, material):
        self.material = material
        self.index = 0

    def node(self, cls, **properties):
        self.index += 1
        node = LIB.create_material_expression(self.material, cls,
            -1800 + self.index * 40, self.index * 65)
        if not node:
            raise RuntimeError('Cannot create ' + str(cls))
        for key, value in properties.items():
            node.set_editor_property(key, value)
        return node, ''

    def scalar(self, name, value):
        return self.node(u.MaterialExpressionScalarParameter,
            parameter_name=name, default_value=float(value))

    def vector(self, name, value):
        return self.node(u.MaterialExpressionVectorParameter,
            parameter_name=name, default_value=u.LinearColor(*value))

    def connect(self, source, target, pin):
        if not LIB.connect_material_expressions(source[0], source[1], target[0], pin):
            raise RuntimeError('Cannot connect ' + pin)

    def output(self, source, prop):
        if not LIB.connect_material_property(source[0], source[1], prop):
            raise RuntimeError('Cannot connect property ' + str(prop))

    def custom(self, code, inputs, vector=False, description='OOW storm cells', output_type=None):
        pins = []
        for name in inputs:
            pin = u.CustomInput()
            pin.set_editor_property('input_name', name)
            pins.append(pin)
        node = self.node(u.MaterialExpressionCustom, code=code, inputs=pins,
            description=description,
            output_type=output_type if output_type is not None else (
                u.CustomMaterialOutputType.CMOT_FLOAT3 if vector
                else u.CustomMaterialOutputType.CMOT_FLOAT1))
        for name, source in inputs.items():
            self.connect(source, node, name)
        return node

    def channel(self, source, channel):
        node = self.node(u.MaterialExpressionComponentMask,
            r=channel == 'r', g=channel == 'g', b=channel == 'b', a=False)
        self.connect(source, node, '')
        return node

    def read(self, prop, fallback):
        node = LIB.get_material_property_input_node(self.material, prop)
        if node:
            return node, LIB.get_material_property_input_node_output_name(self.material, prop)
        return fallback

    def lerp(self, native, candidate, weight):
        node = self.node(u.MaterialExpressionLinearInterpolate)
        self.connect(native, node, 'A')
        self.connect(candidate, node, 'B')
        self.connect(weight, node, 'Alpha')
        return node


def generated_duplicate(name, cls, source, code_hash):
    path = FOLDER + '/' + name
    asset = u.load_asset(path)
    if asset:
        recipe = str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWRecipe'))
        recorded_hash = str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWCodeHash'))
        complete = str(u.EditorAssetLibrary.get_metadata_tag(asset, 'OOWBuildComplete'))
        if not isinstance(asset, cls) or recipe != RECIPE or recorded_hash != code_hash or complete != 'true':
            raise RuntimeError('Refusing unrelated asset ' + path)
        return asset, False
    asset = u.EditorAssetLibrary.duplicate_asset(source.get_path_name(), path)
    if not asset:
        raise RuntimeError('Cannot create ' + path)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWRecipe', RECIPE)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWSource', source.get_path_name())
    return asset, True


def finish(asset, code_hash):
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWCodeHash', code_hash)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWBuildComplete', 'true')
    if not u.EditorAssetLibrary.save_loaded_asset(asset):
        raise RuntimeError('Could not save ' + asset.get_path_name())


def preserve_native_conservative_density(graph, weight, native_override=None):
    # The native graph caches layout/profile values in ConservativeDensity G/B/A.
    # Preserve those channels and the same advanced-output expression; only add
    # a positive R value during blending so native empty-space culling cannot
    # remove cells whose locations differ from the original 2D weather texture.
    prefix = graph.material.get_path_name() + ':'
    advanced = [node for node in u.ObjectIterator(u.MaterialExpressionVolumetricAdvancedMaterialOutput)
        if node.get_path_name().startswith(prefix)]
    if len(advanced) != 1:
        raise RuntimeError('Expected one native Volumetric Advanced Output')
    output = advanced[0]
    pins = dict(zip(map(str, LIB.get_material_expression_input_names(output)),
        LIB.get_inputs_for_material_expression(graph.material, output)))
    pin = next((name for name in pins if name.replace(' ', '').lower() == 'conservativedensity'), None)
    if pin is None:
        raise RuntimeError('Native advanced output has no ConservativeDensity pin')
    source = pins[pin]
    if native_override is not None:
        native = native_override
    elif source:
        name = LIB.get_input_node_output_name_for_material_expression(output, source)
        if name is None:
            raise RuntimeError('Cannot read native ConservativeDensity output')
        native = source, name
    else:
        native = graph.node(u.MaterialExpressionConstant4Vector, constant=u.LinearColor(1, 1, 1, 0))
    # Native ConservativeDensity is float4. A generic Add of float4 and float3
    # is rejected by SM6; spell out all four channels and preserve its cache.
    conservative = graph.custom(CONSERVATIVE_CODE, {'Native': native, 'Blend': weight},
        description='Storm conservative bound preserving native RGBA cache',
        output_type=u.CustomMaterialOutputType.CMOT_FLOAT4)
    graph.connect(conservative, (output, ''), pin)
    return conservative[0]


def main():
    u.EditorAssetLibrary.make_directory(FOLDER)
    noise = u.load_asset(NOISE_PATH)
    if not isinstance(noise, u.VolumeTexture):
        raise RuntimeError('Missing native volume noise: ' + NOISE_PATH)
    native_master = u.load_asset(NATIVE_MASTER)
    native_instance = u.load_asset(NATIVE_INSTANCE)
    if not isinstance(native_master, u.Material) or not isinstance(native_instance, u.MaterialInstanceConstant):
        raise RuntimeError('Missing native cloud source assets')
    script_path = Path(u.Paths.project_dir()).parent / 'Scripts' / 'build_storm_clouds.py'
    code_hash = hashlib.sha256(script_path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
    material, created = generated_duplicate(MASTER_NAME, u.Material, native_master, code_hash)
    if not created:
        instance, new_instance = generated_duplicate(INSTANCE_NAME, u.MaterialInstanceConstant,
            native_instance, code_hash)
        if new_instance:
            LIB.set_material_instance_parent(instance, material)
            finish(instance, code_hash)
        elif instance.get_editor_property('parent') != material:
            raise RuntimeError('Existing storm cloud instance has a different parent')
        u.log('OOW_STORM_CLOUD_MATERIAL_REUSED ' + instance.get_path_name())
        return
    graph = Graph(material)
    # Cloud ray marching initializes AbsoluteWorldPosition for each sample.
    # WorldPosition_NoOffsets is not initialized in UE's cloud shader, so the
    # surface-material "exclude offsets" setting would pin every cell at origin.
    position = graph.node(u.MaterialExpressionWorldPosition,
        world_position_shader_offset=u.WorldPositionIncludedOffsets.WPT_DEFAULT)
    attributes = graph.node(u.MaterialExpressionCloudSampleAttribute)
    height = attributes[0], 'NormAltitudeInLayer'
    noise_object = graph.node(u.MaterialExpressionTextureObjectParameter,
        parameter_name='OOW_StormNoise', texture=noise,
        sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    scalars = {
        'StormClouds': LIB.get_material_default_scalar_parameter_value(native_master, 'StormClouds'),
        'Cloud_GlobalCoverage': LIB.get_material_default_scalar_parameter_value(native_master, 'Cloud_GlobalCoverage'),
        'Cloud_GlobalDensity': LIB.get_material_default_scalar_parameter_value(native_master, 'Cloud_GlobalDensity'),
        'Layout_CloudGlobalScale': LIB.get_material_default_scalar_parameter_value(native_master, 'Layout_CloudGlobalScale'),
        'OOW_CellSpacingKm': 4.0,
        'OOW_BaseRadiusKm': 1.15,
        'OOW_TowerRadiusKm': 0.70,
        'OOW_AnvilRadiusKm': 1.85,
        'OOW_CellErosion': 0.48,
        'OOW_DeckStrength': 0.003,
    }
    vectors = {
        'Layout_GlobalTexturePlacement': (0.0, 0.0, 0.0, 0.0),
        'OOW_StormOffsetKm': (0.0, 0.0, 0.0, 0.0),
        'OOW_StormShearKm': (0.30, 0.12, 0.0, 0.0),
        'OOW_StormBaseAlbedo': (0.50, 0.54, 0.59, 1.0),
        'OOW_StormTopAlbedo': (0.91, 0.92, 0.94, 1.0),
    }
    scalar_nodes = {name: graph.scalar(name, value) for name, value in scalars.items()}
    vector_nodes = {name: graph.vector(name, value) for name, value in vectors.items()}
    weight = graph.custom('return smoothstep(0.15, 0.75, saturate(Storm));',
        {'Storm': scalar_nodes['StormClouds']}, description='Native to storm-cell weather transition')
    native_extinction = graph.read(u.MaterialProperty.MP_SUBSURFACE_COLOR,
        graph.node(u.MaterialExpressionConstant3Vector, constant=u.LinearColor(0, 0, 0, 1)))
    native_albedo = graph.read(u.MaterialProperty.MP_BASE_COLOR,
        graph.node(u.MaterialExpressionConstant3Vector, constant=u.LinearColor(1, 1, 1, 1)))
    # For an unconnected native AO, match the component's default bottom-sky
    # occlusion approximation instead of silently replacing it with uniform 1.
    default_native_ao = graph.custom('return saturate(0.5 + Height);', {'Height': height},
        description='Native default cloud-bottom sky visibility')
    native_ao = graph.read(u.MaterialProperty.MP_AMBIENT_OCCLUSION, default_native_ao)
    shape = graph.custom(SHAPE_CODE, {
        'Position': position, 'Height': height, 'NoiseTex': noise_object,
        'Storm': scalar_nodes['StormClouds'],
        'Coverage': scalar_nodes['Cloud_GlobalCoverage'],
        'Density': scalar_nodes['Cloud_GlobalDensity'],
        'LayoutScale': scalar_nodes['Layout_CloudGlobalScale'],
        'Placement': vector_nodes['Layout_GlobalTexturePlacement'],
        'OffsetKm': vector_nodes['OOW_StormOffsetKm'],
        'ShearKm': vector_nodes['OOW_StormShearKm'],
        'CellSpacingKm': scalar_nodes['OOW_CellSpacingKm'],
        'BaseRadiusKm': scalar_nodes['OOW_BaseRadiusKm'],
        'TowerRadiusKm': scalar_nodes['OOW_TowerRadiusKm'],
        'AnvilRadiusKm': scalar_nodes['OOW_AnvilRadiusKm'],
        'Erosion': scalar_nodes['OOW_CellErosion'],
        'DeckStrength': scalar_nodes['OOW_DeckStrength'],
    }, vector=True, description='Storm cell extinction / height / local density')
    extinction = graph.channel(shape, 'r')
    # Volume-domain Extinction is the RGB SubsurfaceColor property, NOT Opacity.
    # UE VolumetricCloud.usf reads GetMaterialSubsurfaceDataRaw for this coefficient.
    graph.output(graph.lerp(native_extinction, extinction, weight), u.MaterialProperty.MP_SUBSURFACE_COLOR)
    albedo = graph.custom('return lerp(Base.rgb, Top.rgb, smoothstep(0.10, 0.76, Height));', {
        'Base': vector_nodes['OOW_StormBaseAlbedo'],
        'Top': vector_nodes['OOW_StormTopAlbedo'], 'Height': height,
    }, vector=True, description='Storm base / upper crown albedo')
    graph.output(graph.lerp(native_albedo, albedo, weight), u.MaterialProperty.MP_BASE_COLOR)
    ambient = graph.custom('return lerp(0.16, 0.86, smoothstep(0.06, 0.72, Height));',
        {'Height': height}, description='Occluded sky illumination below storm cells')
    graph.output(graph.lerp(native_ao, ambient, weight), u.MaterialProperty.MP_AMBIENT_OCCLUSION)
    preserve_native_conservative_density(graph, weight)
    # Native advanced-output phase/shadow/multiple-scattering settings and the
    # lightning/emissive graph remain intact; runtime still disables lightning.
    LIB.layout_material_expressions(material)
    LIB.recompile_material(material)
    finish(material, code_hash)
    instance, new_instance = generated_duplicate(INSTANCE_NAME, u.MaterialInstanceConstant,
        native_instance, code_hash)
    if not new_instance:
        raise RuntimeError('New master unexpectedly has an existing instance')
    LIB.set_material_instance_parent(instance, material)
    finish(instance, code_hash)
    report = {
        'recipe': RECIPE, 'master': material.get_path_name(),
        'instance': instance.get_path_name(), 'noise': NOISE_PATH,
        'shapeCodeSha256': hashlib.sha256(SHAPE_CODE.encode()).hexdigest(),
        'codeSha256': code_hash,
        'scalarDefaults': scalars, 'vectorDefaults': vectors,
        'volumeTextureSamples': 2, 'maxNeighbourCells': 9,
        'materialDomain': 'Volume', 'extinctionProperty': 'SubsurfaceColor',
        'mapsModified': False,
        'nativeMasterDuplicated': NATIVE_MASTER,
        'nativeInstanceOverridesPreserved': NATIVE_INSTANCE,
        'nativeTransition': 'smoothstep(0.15, 0.75, StormClouds)',
        'nativeAdvancedOutputPreserved': True,
        'stormWorldPosition': 'WPT_DEFAULT (absolute cloud ray-sample position)',
        'compilationVerified': False,
        'recommendedLayerBottomKm': 1.0, 'recommendedLayerHeightKm': 6.0,
        'note': 'Asset generation requests compilation; a real-RHI capture and shader log are required to verify it.',
    }
    target = Path(u.Paths.project_dir()).parent / 'Migration' / 'storm-cloud-material.json'
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_STORM_CLOUD_MATERIAL ' + json.dumps(report))


if __name__ == '__main__':
    main()
