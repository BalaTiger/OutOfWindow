"""Create one owned v7 candidate from v6 for normal window-camera cloud views.

Run with Unreal Editor's Python commandlet. No maps or old materials change.
An existing v7 can be updated only after byte-identical backups of both v7
assets are present in OOW_V7_BACKUP_DIR. Unexpected edits are never overwritten.
All coordinates are km; cloud extinction parameters are inverse metres.
"""
from pathlib import Path
import hashlib
import json
import math
import os
import sys

import unreal as u

SCRIPTS = Path(u.Paths.project_dir()).parent / 'Scripts'
sys.path.insert(0, str(SCRIPTS))
import build_storm_clouds as base

LIB = u.MaterialEditingLibrary
MASTER = '/Game/Weather/M_OOW_WindowClouds_v7'
INSTANCE = '/Game/Weather/MI_OOW_WindowClouds_v7'
SOURCE_MASTER = '/Game/Weather/M_OOW_StormCells_v6'
SOURCE_INSTANCE = '/Game/Weather/MI_OOW_StormCells_v6'
RECIPE = 'window-clouds-v7'
LABELS = {
    'support': 'OOW v7 fair-cloud analytic support',
    'density': 'OOW v7 fair-cloud porous volume density',
    'weight': 'OOW v7 ordinary-cloud property weight',
    'albedo': 'OOW v7 ordinary-cloud single-scattering albedo',
    'ambient': 'OOW v7 ordinary-cloud local sky occlusion',
    'cirrus': 'OOW v7 high patches and anisotropic fibres',
    'bound': 'OOW v7 conservative support retaining native GBA',
}
DEFAULTS = {
    'OOW_FairCloudStrength': 0.0,
    'OOW_FairCloudDensity': 0.0016,
    'OOW_FairCloudCoverage': 0.4,
    'OOW_OvercastWeight': 0.0,
    'OOW_CloudAmbientOcclusion': 1.0,
}

# Nine stable neighbouring cells, each with three rounded lobes. Their true
# support is independent of optical density and excludes empty gaps completely.
# The vertical cut at h=0 gives a common condensation base, not a floating ball.
SUPPORT_CODE = r'''
float h = Height;
if (h <= 0.0 || h >= 1.0 || FairStrength <= 0.0 || (Coverage <= 0.0 && Overcast <= 0.0))
    return float3(0.0, 0.0, saturate(h));
float cover = saturate(Coverage);
float overcast = saturate(Overcast);
float layoutScale = max(LayoutScale, 1.0);
float scale = layoutScale / 32.0;
float2 p = Position.xy * 0.00001 - Placement.xy * layoutScale - OffsetKm.xy;
float spacing = max(CellSpacingKm, 1.0) * scale * lerp(1.0, 0.84, cover);
float2 grid = floor(p / spacing);
float occupancy = lerp(0.10, 1.0, sqrt(cover));
float baseRadius = lerp(1.25, 2.15, cover) * scale;
float envelope = 0.0;
[unroll] for (int j = -1; j <= 1; ++j)
{
    [unroll] for (int i = -1; i <= 1; ++i)
    {
        float2 key = grid + float2(i, j);
        float3 hash = frac(float3(key.x, key.y, key.x) * float3(0.1031, 0.1030, 0.0973));
        hash += dot(hash, hash.yzx + 33.33);
        float3 random = frac((hash.xxy + hash.yzz) * hash.zyx);
        if (random.z > occupancy) continue;
        float2 centre = (key + 0.5 + (random.xy - 0.5) * 0.40) * spacing;
        float radius = baseRadius * lerp(0.83, 1.15, random.y);
        float top = lerp(0.72, 1.0, random.x);
        float lh = h / top;
        float2 delta = (p - centre - float2(0.12, 0.045) * scale * lh * lh) / max(radius, 0.05);
        float e0 = sqrt(dot(delta, delta) + pow((lh - 0.40) / 0.50, 2.0));
        float2 d1 = (delta - float2(0.42, 0.13)) / 0.70;
        float e1 = sqrt(dot(d1, d1) + pow((lh - 0.59) / 0.35, 2.0));
        float2 d2 = (delta + float2(0.35, 0.19)) / 0.66;
        float e2 = sqrt(dot(d2, d2) + pow((lh - 0.62) / 0.33, 2.0));
        float lobes = 1.0 - smoothstep(0.56, 1.04, min(e0, min(e1, e2)));
        float base = smoothstep(0.0, 0.035, lh) * (1.0 - smoothstep(0.94, 1.0, lh));
        envelope = max(envelope, lobes * base);
    }
}
// Only the overcast base moves: ordinary cumulus support is unchanged.
if (overcast <= 0.0) return float3(envelope, 0.0, h);
// Four corners of the existing arithmetic hash, smoothly interpolated in XY.
// Bottom depends only on the drifting world-space XY field, never on h.
float2 sheetCell = floor(p / 3.0);
float2 sheetFrac = frac(p / 3.0);
sheetFrac = sheetFrac * sheetFrac * (3.0 - 2.0 * sheetFrac);
float4 keyX = sheetCell.x + float4(0.0, 1.0, 0.0, 1.0);
float4 keyY = sheetCell.y + float4(0.0, 0.0, 1.0, 1.0);
float4 hx = frac(keyX * 0.1031);
float4 hy = frac(keyY * 0.1030);
float4 hz = frac(keyX * 0.0973);
float4 q = hx * (hy + 33.33) + hy * (hz + 33.33) + hz * (hx + 33.33);
hx += q; hy += q; hz += q;
float4 corners = frac((hx + hy) * hz);
float sheetNoise = lerp(lerp(corners.x, corners.y, sheetFrac.x),
                        lerp(corners.z, corners.w, sheetFrac.x), sheetFrac.y);
float sheetBottom = lerp(0.24, 0.40, sheetNoise);
float sheetTop = sheetBottom + 0.46;
float sheetBand = smoothstep(sheetBottom, sheetBottom + 0.06, h)
    * (1.0 - smoothstep(sheetTop - 0.10, sheetTop, h));
return float3(envelope, sheetBand * overcast, h);
'''

# Only these two existing volume-noise reads add breakup. The coarse octave
# changes density inside each analytic mass; the fine octave erodes its edge.
# A translucent overcast base remains continuous but varies in space and height.
DENSITY_CODE = r'''
float h = Support.z;
if (FairStrength <= 0.0 || (Support.x <= 0.0 && Support.y <= 0.0))
    return float3(0.0, h, 0.0);
float layoutScale = max(LayoutScale, 1.0);
float scale = layoutScale / 32.0;
float3 p = Position * 0.00001;
p.xy -= Placement.xy * layoutScale + OffsetKm.xy;
p.z = h * max(LayerHeightKm, 0.01);
p /= max(scale, 0.05);
float detail = saturate(DetailStrength);
// Clamp texture-coordinate frequency, not the unverified texture feature size.
// Two 3D reads remain: broad density/scallops and smaller edge/interior breakup.
float fineFrequency = 1.0 / max(DetailScaleKm, 0.55);
float4 coarse = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(p * lerp(0.42, fineFrequency * 0.26, detail) + float3(0.17, 0.31, 0.09)), 0);
// A bounded world-space 3D warp breaks aligned detail without another sample.
float3 warp = detail * 0.18 * (float3(coarse.g, coarse.r, coarse.g) - 0.5);
float4 fine = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(p * lerp(1.65, fineFrequency, detail) + warp + float3(0.63, 0.12, 0.47)), 0);
float broadShape = coarse.r * 0.75 + coarse.g * 0.25;
float edgeWeight = 1.0 - smoothstep(0.20, 0.78, Support.x);
float broadCut = max(0.0, 0.62 - broadShape) * 0.80;
float fineNicks = max(0.0, 0.58 - fine.g) * (0.10 + 0.18 * edgeWeight);
float legacyErosion = max(0.0, (0.57 - coarse.r) * 0.36 + (0.56 - fine.g) * 0.16);
float erosion = lerp(legacyErosion, broadCut + fineNicks, detail);
// Only subtract inside the old envelope. Never create density outside support.
float body = saturate((Support.x - erosion) * lerp(1.32, 1.55, detail))
    * step(0.00001, Support.x);
float lobe = smoothstep(0.28, 0.80, broadShape);
float breakup = smoothstep(0.25, 0.82, fine.r);
float interior = (0.22 + 0.78 * lobe * lobe) * (0.62 + 0.38 * breakup);
// Broaden density valleys/heads around a reference value; this is not mean-OD
// normalization. Heads may exceed one so their optical contrast is not clipped.
float structuredInterior = max(0.04, 0.35 + 1.80 * (interior - 0.35));
float cells = body * lerp(1.0, structuredInterior, detail);
float sheetStructure = 0.45 + 0.55 * smoothstep(0.18, 0.83, coarse.g * 0.70 + fine.r * 0.30);
float extinction = max(Density, 0.0) * lerp(1.0, max(DetailDensityScale, 0.05), detail) * cells
    // Old height-band integral .705; shifted band integral .38.
    // Preserve approximate column optical depth before spatial noise modulation.
    + max(SheetDensity, 0.0) * (0.705 / 0.38) * Support.y * sheetStructure;
return float3(extinction, h, cells);
'''

# Actual anisotropy in XY: patch long/short radii differ by about 8:1. Stable
# world-space patch placement and integrated wind avoid camera-facing cards.
# The altitude input remains the existing absolute 8-10 km normalized height.
CIRRUS_CODE = r'''
float h = Height;
if (h <= 0.0 || h >= 1.0 || CirrusStrength <= 0.0 || CirrusDensity <= 0.0 || CirrusCoverage <= 0.0) return 0.0;
float band = smoothstep(0.30, 0.36, h) * (1.0 - smoothstep(0.60, 0.66, h));
if (band <= 0.0) return 0.0;
float cirrusScale = max(CirrusScaleKm, 1.0);
float2 p = Position.xy * 0.00001 - Placement.xy * max(LayoutScale, 1.0);
float spacing = cirrusScale * 1.7;
float2 grid = floor(p / spacing);
float occupancy = saturate(saturate(CirrusCoverage) * 18.0);
float envelope = 0.0;
float2 fibreAxis = normalize(float2(0.92, 0.38));
[unroll] for (int j = -1; j <= 1; ++j)
{
    [unroll] for (int i = -1; i <= 1; ++i)
    {
        float2 key = grid + float2(i, j);
        float3 hash = frac(float3(key.x, key.y, key.x) * float3(0.1131, 0.1093, 0.1017));
        hash += dot(hash, hash.yzx + 31.71);
        float3 random = frac((hash.xxy + hash.yzz) * hash.zyx);
        if (random.z > occupancy) continue;
        float2 centre = (key + 0.5 + (random.xy - 0.5) * 0.32) * spacing;
        float2 axis = normalize(fibreAxis + float2(-fibreAxis.y, fibreAxis.x) * (random.x - 0.5) * 0.40);
        float2 delta = p - centre;
        float u = dot(delta, axis) / (cirrusScale * lerp(0.78, 1.15, random.y));
        float v = dot(delta, float2(-axis.y, axis.x)) / (cirrusScale * lerp(0.09, 0.16, random.x));
        float patch = 1.0 - smoothstep(0.62, 1.04, sqrt(u*u + v*v));
        envelope = max(envelope, patch);
    }
}
if (envelope <= 0.0) return 0.0;
float2 across = float2(-fibreAxis.y, fibreAxis.x);
float3 cp = float3(dot(p, fibreAxis) / cirrusScale, dot(p, across) / (cirrusScale * 0.16), h * 0.65);
float4 coarse = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(cp * 0.80 + float3(0.21, 0.53, 0.07)), 0);
float4 fine = Texture3DSampleLevel(NoiseTex, NoiseTexSampler,
    frac(cp * 1.65 + float3(0.71, 0.19, 0.44)), 0);
float fibres = smoothstep(0.32, 0.68, coarse.r * 0.72 + fine.g * 0.28);
float erodedEnvelope = saturate(envelope - max(0.0, 0.56 - fine.g) * 0.40);
float density = erodedEnvelope * fibres * (0.50 + 0.50 * coarse.g);
// The old height profile integrates to .8425; the thin profile integrates to .30.
// Normalize height-only column extinction instead of expanding patch occupancy.
return max(CirrusDensity, 0.0) * (0.8425 / 0.30) * band * density * saturate(CirrusStrength);
'''

WEIGHT_CODE = 'return saturate(FairStrength) * LowMask;'
ALBEDO_CODE = r'''
float h = saturate(Height);
float top = smoothstep(0.06, 0.88, h);
float3 ordinary = lerp(float3(0.94,0.955,0.97), float3(0.975,0.98,0.985), top);
float3 overcast = lerp(float3(0.66,0.69,0.74), float3(0.80,0.82,0.86), top);
return lerp(ordinary, overcast, saturate(Overcast));
'''
AMBIENT_CODE = r'''
float top = smoothstep(0.035, 0.86, saturate(Height));
float ordinary = lerp(0.40, 0.92, top);
float overcast = lerp(0.18, 0.80, top);
return saturate(lerp(ordinary, overcast, saturate(Overcast)) * max(AmbientScale, 0.0));
'''
BOUND_CODE = r'''
float nativeLow = (Native.r * (Density > 0.0 ? 1.0 : 0.0) + Sheet) * Low;
float fairLow = ((FairDensity > 0.0 ? FairSupport.r : 0.0)
    + (Sheet > 0.0 ? FairSupport.g : 0.0)) * Low;
return float4(lerp(nativeLow, fairLow, saturate(FairStrength)) + HighExtinction, Native.gba);
'''
CODE_BY_LABEL = dict(zip((LABELS[k] for k in LABELS),
    (SUPPORT_CODE, DENSITY_CODE, WEIGHT_CODE, ALBEDO_CODE, AMBIENT_CODE, CIRRUS_CODE, BOUND_CODE)))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scoped_nodes(material):
    prefix = material.get_path_name() + ':'
    return [node for node in u.ObjectIterator(u.MaterialExpression)
            if node.get_path_name().startswith(prefix)]


def inputs(material, node):
    return dict(zip(map(str, LIB.get_material_expression_input_names(node)),
                    LIB.get_inputs_for_material_expression(material, node)))


def source_output(node, source):
    if source is None:
        raise RuntimeError('Missing source at ' + node.get_path_name())
    return source, LIB.get_input_node_output_name_for_material_expression(node, source)


def one(nodes, predicate, label):
    found = [node for node in nodes if predicate(node)]
    if len(found) != 1:
        raise RuntimeError('Expected one ' + label + ', found ' + str(len(found)))
    return found[0]


def custom_by_label(nodes, label):
    return one(nodes, lambda n: isinstance(n, u.MaterialExpressionCustom)
               and str(n.get_editor_property('description')) == label, label)


def add_input(graph, node, name, source):
    pins = list(node.get_editor_property('inputs'))
    if name not in [str(p.get_editor_property('input_name')) for p in pins]:
        pin = u.CustomInput()
        pin.set_editor_property('input_name', name)
        pins.append(pin)
        node.set_editor_property('inputs', pins)
    graph.connect(source, (node, ''), name)


def assert_backup(assets):
    backup_dir = os.environ.get('OOW_V7_BACKUP_DIR', '')
    if not backup_dir:
        raise RuntimeError('Owned v7 update requires OOW_V7_BACKUP_DIR containing current exact asset backups')
    for asset in assets:
        name = asset.get_name() + '.uasset'
        current = Path(u.Paths.project_content_dir()) / 'Weather' / name
        backup = Path(backup_dir) / name
        if not current.is_file() or not backup.is_file() or sha(current) != sha(backup):
            raise RuntimeError('Missing or mismatched current v7 backup: ' + name)


def optional_property(node, name):
    try:
        value = node.get_editor_property(name)
        return value if isinstance(value, (int, float, bool, str)) else str(value)
    except Exception:
        return None


def owned_hashes(nodes):
    return {label: hashlib.sha256(str(custom_by_label(nodes, label).get_editor_property('code')).encode()).hexdigest()
            for label in CODE_BY_LABEL}


def finish(asset, code_hash, node_hashes=None):
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWRecipe', RECIPE)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWCodeHash', code_hash)
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWGraphGeneratorHash', sha(SCRIPTS / 'build_storm_clouds.py'))
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWSource', SOURCE_MASTER if isinstance(asset, u.Material) else SOURCE_INSTANCE)
    if node_hashes is not None:
        u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWOwnedNodeHashes', json.dumps(node_hashes, sort_keys=True))
    u.EditorAssetLibrary.set_metadata_tag(asset, 'OOWBuildComplete', 'true')
    if not u.EditorAssetLibrary.save_loaded_asset(asset):
        raise RuntimeError('Cannot save ' + asset.get_path_name())


def set_verified_defaults(material, instance):
    # UE 5.7 MaterialEditingLibrary.cpp:1165-1174 writes and updates correctly,
    # but its unassigned bResult makes this setter always return false. Validate
    # the actual graph parameter list, written override and effective readback.
    known = {str(name) for name in LIB.get_scalar_parameter_names(material)}
    if not set(DEFAULTS).issubset(known):
        raise RuntimeError('v7 graph is missing expected scalar parameters: ' + str(set(DEFAULTS)-known))
    for name,value in DEFAULTS.items():
        LIB.set_material_instance_scalar_parameter_value(instance,name,value)
    overrides = {}
    for override in instance.get_editor_property('scalar_parameter_values'):
        info = override.get_editor_property('parameter_info')
        name = str(info.get_editor_property('name'))
        if name in DEFAULTS:
            overrides[name] = float(override.get_editor_property('parameter_value'))
    for name,value in DEFAULTS.items():
        effective = float(LIB.get_material_instance_scalar_parameter_value(instance,name))
        if name not in overrides or not math.isclose(overrides[name],value,rel_tol=1e-6,abs_tol=1e-8) \
            or not math.isclose(effective,value,rel_tol=1e-6,abs_tol=1e-8):
            raise RuntimeError('v7 scalar override/readback did not match: ' + name)


def source_assets():
    source_master, source_instance = u.load_asset(SOURCE_MASTER),u.load_asset(SOURCE_INSTANCE)
    for asset, cls in ((source_master,u.Material),(source_instance,u.MaterialInstanceConstant)):
        if not isinstance(asset,cls) or str(u.EditorAssetLibrary.get_metadata_tag(asset,'OOWRecipe')) != 'storm-layers-v6' \
            or str(u.EditorAssetLibrary.get_metadata_tag(asset,'OOWBuildComplete')) != 'true':
            raise RuntimeError('Missing complete owned v6 source')
    if source_instance.get_editor_property('parent') != source_master:
        raise RuntimeError('Source v6 instance parent changed')
    return source_master, source_instance


def verify_owned_master(material):
    if not isinstance(material,u.Material) or str(u.EditorAssetLibrary.get_metadata_tag(material,'OOWRecipe')) != RECIPE \
        or str(u.EditorAssetLibrary.get_metadata_tag(material,'OOWBuildComplete')) != 'true':
        raise RuntimeError('Refusing unrelated or incomplete v7 master')
    nodes = scoped_nodes(material)
    actual = owned_hashes(nodes)
    recorded = str(u.EditorAssetLibrary.get_metadata_tag(material,'OOWOwnedNodeHashes'))
    if not recorded or json.loads(recorded) != actual:
        raise RuntimeError('Owned v7 custom code has unexpected edits; refusing overwrite')
    return nodes, actual


def report(material, instance, code_hash, updated, recovered=False):
    nodes = scoped_nodes(material)
    advanced = one(nodes, lambda n: isinstance(n, u.MaterialExpressionVolumetricAdvancedMaterialOutput), 'advanced output')
    ambient_node = LIB.get_material_property_input_node(material, u.MaterialProperty.MP_AMBIENT_OCCLUSION)
    extinction_node = LIB.get_material_property_input_node(material, u.MaterialProperty.MP_SUBSURFACE_COLOR)
    if ambient_node is None or extinction_node is None:
        raise RuntimeError('v7 ambient occlusion or extinction property is disconnected')
    payload = dict(recipe=RECIPE, master=MASTER, instance=INSTANCE, sourceMaster=SOURCE_MASTER,
        scriptSha256=code_hash, graphGeneratorSha256=sha(SCRIPTS / 'build_storm_clouds.py'),
        updatedOwnedV7=updated, recoveredSavedMasterWithoutInstance=recovered,
        defaults=DEFAULTS, instanceScalarValues={name:float(LIB.get_material_instance_scalar_parameter_value(instance,name))
            for name in DEFAULTS}, highAltitudeKm=[8, 10],
        lowLayer='Absolute low altitude from preserved OOW_LowBottomKm and OOW_LowHeightKm',
        lowCells=dict(maxNeighbourCells=9, analyticLobesPerCell=3, volumeNoiseSamples=2,
            radiusKmAtLayout32=[1.25,2.15], spacingKmAtDefault4=[3.36,4.0], variableTopFraction=[0.72,1.0]),
        lowDensity=dict(mode='3D inward scallops, warped edge nicks and porous interior',
            volumeNoiseSamples=2, minimumDetailScaleKm=0.55,
            defaultTextureCyclesPerKmAtLayout32=[0.26/0.55,1.0/0.55],
            detailWarpTextureMaxPerAxis=0.09, densityContrastReference=0.35,
            densityContrastGain=1.80, structuredInteriorRange=[0.04,1.52],
            supportExpanded=False, meanColumnOpticalDepthPreserved=False),
        highPatches=dict(maxNeighbourCells=9, volumeNoiseSamples=2, fixedWorldAxes=True,
            longShortAxisRatio='approximately 8:1; varies per patch', noiseLongShortAxisRatio=6.25,
            normalizedAltitudeSupport=[0.30,0.66], effectiveAltitudeSupportKm=[8.60,9.32],
            oldHeightBandIntegral=0.8425, heightBandIntegral=0.30, heightDensityNormalization=0.8425/0.30),
        overcast=dict(continuousSheet=True, spatialDensityModulation=True, cloudAmbientOcclusion=[0.18,0.80]),
        actualMultiScatteringApproximationOctaveCount=optional_property(advanced,'multi_scattering_approximation_octave_count'),
        actualRayMarchVolumeShadow=optional_property(advanced,'ray_march_volume_shadow'),
        advancedSettingsChanged=False, nativeConservativeGbaPreserved=True,
        ambientOcclusionConnected=ambient_node.get_name(), extinctionConnected=extinction_node.get_name(),
        ownedNodeHashes=owned_hashes(nodes), compilationVerified=False, mapsModified=False,
        materialSaved=True, instanceSaved=True)
    path = Path(u.Paths.project_dir()).parent / 'Migration' / 'window-clouds-v7-material.json'
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n',encoding='utf-8')
    u.log('OOW_WINDOW_CLOUDS ' + json.dumps(payload, ensure_ascii=False))


def main():
    code_hash = sha(__file__)
    material, instance = u.load_asset(MASTER), u.load_asset(INSTANCE)
    if material or instance:
        # Recovery is intentionally limited to the observed first-build state:
        # complete owned master on disk, no instance saved yet. Exact current
        # master backup and exact current HLSL hashes are required beforehand.
        if material and instance is None:
            nodes,actual = verify_owned_master(material)
            expected = {label:hashlib.sha256(code.encode()).hexdigest()
                        for label,code in CODE_BY_LABEL.items()}
            if actual != expected:
                raise RuntimeError('Partial-v7 recovery requires exact current owned shader code')
            if str(u.EditorAssetLibrary.get_metadata_tag(material,'OOWGraphGeneratorHash')) != sha(SCRIPTS/'build_storm_clouds.py'):
                raise RuntimeError('Partial-v7 recovery graph generator changed')
            assert_backup((material,))
            _,source_instance = source_assets()
            instance = u.EditorAssetLibrary.duplicate_asset(SOURCE_INSTANCE,INSTANCE)
            if not isinstance(instance,u.MaterialInstanceConstant):
                raise RuntimeError('Cannot recreate unsaved v7 instance from owned v6')
            LIB.set_material_instance_parent(instance,material)
            if instance.get_editor_property('parent') != material:
                raise RuntimeError('Recovered instance did not acquire v7 master parent')
            set_verified_defaults(material,instance)
            finish(instance,code_hash)
            finish(material,code_hash,actual)
            report(material,instance,code_hash,False,True)
            return
        for asset, cls in ((material,u.Material),(instance,u.MaterialInstanceConstant)):
            if not isinstance(asset,cls) or str(u.EditorAssetLibrary.get_metadata_tag(asset,'OOWRecipe')) != RECIPE:
                raise RuntimeError('Refusing unrelated or incomplete v7 asset')
            if str(u.EditorAssetLibrary.get_metadata_tag(asset,'OOWBuildComplete')) != 'true':
                raise RuntimeError('Refusing incomplete v7 asset')
        if instance.get_editor_property('parent') != material:
            raise RuntimeError('v7 instance parent changed')
        nodes,_ = verify_owned_master(material)
        if all(str(u.EditorAssetLibrary.get_metadata_tag(a,'OOWCodeHash')) == code_hash for a in (material,instance)):
            report(material,instance,code_hash,False)
            u.log('OOW_WINDOW_CLOUDS_REUSED ' + INSTANCE)
            return
        assert_backup((material,instance))
        for label, code in CODE_BY_LABEL.items():
            custom_by_label(nodes,label).set_editor_property('code',code)
        LIB.recompile_material(material)
        finish(material,code_hash,owned_hashes(nodes))
        finish(instance,code_hash)
        report(material,instance,code_hash,True)
        return
    source_master, source_instance = source_assets()
    material = u.EditorAssetLibrary.duplicate_asset(SOURCE_MASTER,MASTER)
    if not material:
        raise RuntimeError('Cannot duplicate v6 master')
    u.EditorAssetLibrary.set_metadata_tag(material,'OOWRecipe',RECIPE)
    u.EditorAssetLibrary.set_metadata_tag(material,'OOWBuildComplete','false')
    graph = base.Graph(material)
    nodes = scoped_nodes(material)
    combined = one(nodes,lambda n:isinstance(n,u.MaterialExpressionCustom)
        and str(n.get_editor_property('code')).strip()=='return A + B;','v6 layer combiner')
    combined_inputs = inputs(material,combined)
    native_low = source_output(combined,combined_inputs['A'])
    low_height = one(nodes,lambda n:isinstance(n,u.MaterialExpressionCustom)
        and str(n.get_editor_property('description'))=='Original low-cloud normalized altitude','v6 low height')
    cirrus = one(nodes,lambda n:isinstance(n,u.MaterialExpressionCustom)
        and 'CirrusDensity' in str(n.get_editor_property('code')),'v6 high layer')
    bound = one(nodes,lambda n:isinstance(n,u.MaterialExpressionCustom)
        and str(n.get_editor_property('description'))=='Density-aware cloud bound retaining native low cache','v6 conservative bound')
    bound_inputs = inputs(material,bound)
    low_mask = source_output(bound,bound_inputs['Low'])
    cirrus_inputs = inputs(material,cirrus)
    position = source_output(cirrus,cirrus_inputs['Position'])
    placement = source_output(cirrus,cirrus_inputs['Placement'])
    layout_scale = source_output(cirrus,cirrus_inputs['LayoutScale'])
    noise = source_output(cirrus,cirrus_inputs['NoiseTex'])

    def scalar(name,value):
        found=[n for n in nodes if isinstance(n,u.MaterialExpressionScalarParameter)
               and str(n.get_editor_property('parameter_name'))==name]
        if found:
            return found[0],''
        return graph.scalar(name,value)

    def vector(name,value):
        found=[n for n in nodes if isinstance(n,u.MaterialExpressionVectorParameter)
               and str(n.get_editor_property('parameter_name'))==name]
        if found:
            return found[0],''
        return graph.vector(name,value)

    fair={name:scalar(name,value) for name,value in DEFAULTS.items()}
    support=graph.custom(SUPPORT_CODE,{
        'Position':position,'Height':(low_height,''),'Placement':placement,'LayoutScale':layout_scale,
        'OffsetKm':vector('OOW_StormOffsetKm',(0,0,0,0)),
        'CellSpacingKm':scalar('OOW_CellSpacingKm',4),
        'Coverage':fair['OOW_FairCloudCoverage'],'FairStrength':fair['OOW_FairCloudStrength'],
        'Overcast':fair['OOW_OvercastWeight']},vector=True,description=LABELS['support'])
    sheet=source_output(bound,bound_inputs['Sheet'])
    density=graph.custom(DENSITY_CODE,{
        'Position':position,'Support':support,'NoiseTex':noise,'Placement':placement,'LayoutScale':layout_scale,
        'OffsetKm':vector('OOW_StormOffsetKm',(0,0,0,0)),
        'LayerHeightKm':scalar('OOW_LowHeightKm',2.5),
        'FairStrength':fair['OOW_FairCloudStrength'],'Density':fair['OOW_FairCloudDensity'],'SheetDensity':sheet,
        'DetailStrength':scalar('OOW_DetailStrength',1),'DetailScaleKm':scalar('OOW_DetailScaleKm',.35),
        'DetailDensityScale':scalar('OOW_DetailDensityScale',1.35)},vector=True,description=LABELS['density'])
    weight=graph.custom(WEIGHT_CODE,{'FairStrength':fair['OOW_FairCloudStrength'],'LowMask':low_mask},description=LABELS['weight'])
    fair_extinction=graph.channel(density,'r')
    graph.connect(graph.lerp(native_low,fair_extinction,weight),(combined,''),'A')
    native_albedo=graph.read(u.MaterialProperty.MP_BASE_COLOR,None)
    native_ambient=graph.read(u.MaterialProperty.MP_AMBIENT_OCCLUSION,None)
    if native_albedo is None or native_ambient is None:
        raise RuntimeError('v6 native albedo or ambient occlusion unexpectedly disconnected')
    albedo=graph.custom(ALBEDO_CODE,{'Height':(low_height,''),'Overcast':fair['OOW_OvercastWeight']},vector=True,description=LABELS['albedo'])
    ambient=graph.custom(AMBIENT_CODE,{'Height':(low_height,''),'Overcast':fair['OOW_OvercastWeight'],
        'AmbientScale':fair['OOW_CloudAmbientOcclusion']},description=LABELS['ambient'])
    graph.output(graph.lerp(native_albedo,albedo,weight),u.MaterialProperty.MP_BASE_COLOR)
    graph.output(graph.lerp(native_ambient,ambient,weight),u.MaterialProperty.MP_AMBIENT_OCCLUSION)
    cirrus.set_editor_property('code',CIRRUS_CODE)
    cirrus.set_editor_property('description',LABELS['cirrus'])
    cirrus.set_editor_property('output_type',u.CustomMaterialOutputType.CMOT_FLOAT1)
    add_input(graph,bound,'FairStrength',fair['OOW_FairCloudStrength'])
    add_input(graph,bound,'FairDensity',fair['OOW_FairCloudDensity'])
    add_input(graph,bound,'FairSupport',support)
    bound.set_editor_property('code',BOUND_CODE)
    bound.set_editor_property('description',LABELS['bound'])
    # No phase, octave, shadow mode, atmosphere or map setting is changed.
    LIB.layout_material_expressions(material)
    LIB.recompile_material(material)
    finish(material,code_hash,owned_hashes(scoped_nodes(material)))
    instance=u.EditorAssetLibrary.duplicate_asset(SOURCE_INSTANCE,INSTANCE)
    if not instance:
        raise RuntimeError('Cannot duplicate v6 instance')
    LIB.set_material_instance_parent(instance,material)
    if instance.get_editor_property('parent') != material:
        raise RuntimeError('v7 instance did not acquire candidate master parent')
    set_verified_defaults(material,instance)
    finish(instance,code_hash)
    report(material,instance,code_hash,False)


if __name__=='__main__':
    main()
