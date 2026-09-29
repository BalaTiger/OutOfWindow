"""Build the camera-attached frame and local sliding-raindrop materials.

Run in UE with no concurrent asset writer. Only generated DesktopFrame assets
are saved; no map is loaded or changed. Frame UV0 is in centimetres, with U
across the grain and V along it. Runtime MIDs set Color (linear RGB), Roughness,
Metallic and Grain; Grain=0 gives plain rubber/metal without wood relief.
M_WindowRainGlass uses centimetre UV0 with V pointing up, tangent-space normals
and RainIntensity [0,1]. Dry glass has zero opacity and zero refraction offset.
"""
from pathlib import Path
import sys


FOLDER = '/Game/Materials/OOW/DesktopFrame'
NAME = 'M_DesktopFrame'
RECIPE = 'desktop-frame-v1'
RAIN_NAME = 'M_WindowRainGlass'
RAIN_RECIPE = 'window-rain-glass-v3'
RAIN_PERIOD = 256.0

# Smooth, irregular fibres instead of periodic bands. The analytic gradients
# give the finish a shallow relief; screen-space filtering prevents fine grain
# from shimmering on the narrow rails. All frequencies are per centimetre.
WOOD = r'''
struct OakNoise
{
    float hash(float2 p)
    {
        float3 q = frac(float3(p.x, p.y, p.x) * .1031);
        q += dot(q, q.yzx + 33.33);
        return frac((q.x + q.y) * q.z);
    }
    float3 noise(float2 p)
    {
        float2 i = floor(p), f = frac(p);
        float2 s = f*f*(3.0 - 2.0*f);
        float2 ds = 6.0*f*(1.0 - f);
        float a = hash(i), b = hash(i + float2(1,0));
        float c = hash(i + float2(0,1)), d = hash(i + 1.0);
        float crossTerm = a - b - c + d;
        return float3(a + (b-a)*s.x + (c-a)*s.y + crossTerm*s.x*s.y - .5,
                      ds.x*((b-a) + crossTerm*s.y),
                      ds.y*((c-a) + crossTerm*s.x));
    }
    float3 layer(float2 p, float2 frequency, float2 footprint)
    {
        float filter = 1.0 - smoothstep(.35, 1.0, max(footprint.x*frequency.x,
                                                                  footprint.y*frequency.y));
        return noise(p * frequency) * float3(1.0, frequency) * filter;
    }
};
OakNoise oak;
float2 footprint = fwidth(UV);
float3 broad = oak.layer(UV + float2(17.2, 8.3), float2(.38, .019), footprint);
// A slow, irregular drift makes the fibres meander through the sawn board.
float2 p = UV + float2(broad.x * .7, 0);
float3 fibre = oak.layer(p + float2(3.8, 37.1), float2(2.4, .12), footprint);
float3 pore = oak.layer(p + float2(19.7, 4.2), float2(10.5, .72), footprint);
return broad * .50 + fibre * .34 + pore * .16;
'''


RAIN = r'''
struct WindowDrops
{
    float mergeAt, waveSeed;
    float3 hash(float2 p)
    {
        float3 q = frac(float3(p.x, p.y, p.x) * float3(.1031, .1030, .0973));
        q += dot(q, q.yxz + 33.33);
        return frac((q.xxy + q.yzz) * q.zyx);
    }
    // Packed local coverage and convex drop slopes, without a base water film.
    float3 bead(float2 p, float2 radius, float2 footprint)
    {
        float2 q = p / radius;
        float aa = clamp(max(footprint.x/radius.x, footprint.y/radius.y), .06, .6);
        float mask = 1.0 - smoothstep(1.0-aa, 1.0+aa, length(q));
        return float3(mask, q * mask);
    }
    // Fall distance at cycle phase ph [0,1]: a slow base acceleration, a
    // gentle two-cycle sway from uneven surface friction, and one sudden
    // speedup where the drop merges with another or hits a clean patch.
    // speedOf is its analytic derivative; the trail solver inverts travelOf,
    // so drop motion and residue timing can never drift apart.
    float travelOf(float ph)
    {
        return ph*.55 + ph*ph*.45 + .045*sin(ph*12.566 + waveSeed)
             + .09*smoothstep(mergeAt-.03, mergeAt+.03, ph);
    }
    float speedOf(float ph)
    {
        float u = saturate((ph-(mergeAt-.03))/.06);
        return .55 + .9*ph + .565*cos(ph*12.566 + waveSeed)
             + .09*(6.0*u-6.0*u*u)/.06;
    }
};
WindowDrops drops;
float rain = saturate(Rain);
if (rain <= 0.0) return float3(0,0,0);
float2 footprint = max(fwidth(UV), .001);

// Each cell has its own phase, size and 8/16-second cycle. All cycles divide
// the Time node's 256-second period, avoiding a jump in long desktop sessions.
float2 cellSize = float2(2.4, 6.8);
float2 cell = floor(UV / cellSize);
float3 seed = drops.hash(cell + 19.7);
float cycle = seed.z < .5 ? 8.0 : 16.0;
float phase = frac(T / cycle + seed.y);
drops.mergeAt = .2 + .55*frac(seed.x*7.31);
drops.waveSeed = seed.x*21.0;
float travel = min(drops.travelOf(phase), 1.0);
float speed = drops.speedOf(phase);
// Drops do not slide straight: a slow primary sway plus a faster jitter give
// each cell its own meandering course, with per-cell frequency and phase so
// neighbouring drops never move in lockstep.
float wanderFreq = 1.0 + seed.x*1.5;
float wanderPhase = phase*6.283185*wanderFreq + seed.y*6.283185;
float wanderNow = sin(wanderPhase)*.14 + sin(phase*29.515 + seed.x*39.0)*.06;
float2 centre = float2((seed.y-.5)*cellSize.x*.66 + wanderNow,
                      (.42 - .84*travel)*cellSize.y);
float2 p = (frac(UV/cellSize)-.5)*cellSize - centre;
float alive = smoothstep(0.0, .08, phase) * (1.0-smoothstep(.90, 1.0, phase));
float enabled = saturate((rain-seed.x)*10.0) * alive;
// The drop sheds water into its trail as it falls, so it shrinks; faster
// drops stretch along the fall direction.
float width = lerp(.24, .34, seed.z) * (1.0 - .45*travel);
float stretch = 1.0 + clamp(speed-1.0, 0.0, 1.2)*.55;
float3 falling = drops.bead(p, float2(width, width*1.65*stretch), footprint) * enabled;

// Residue trails: the trace follows the actual course, re-evaluating the
// meander at the phase when the drop passed each height, and fades with the
// time since deposition — a slow drop leaves a short fresh trace, a fast one
// a long thinning trace, so trail and motion always match.
float tailWidth = lerp(.05, .075, seed.z);
float tailAA = max(footprint.x*.6, .006);
float travelAt = max(travel - p.y/(.84*cellSize.y), 0.0);
// Newton refinement of the quadratic first guess against the true motion.
float phaseAt = (-.55 + sqrt(.3025 + 1.8*travelAt))/.9;
for (int it=0; it<2; it++)
    phaseAt -= (drops.travelOf(phaseAt)-travelAt)/max(drops.speedOf(phaseAt),.1);
phaseAt = clamp(phaseAt, 0.0, 1.0);
float ageSince = max(phase - phaseAt, 0.0); // cycle units since the drop passed
float wanderThen = sin(phaseAt*6.283185*wanderFreq + seed.y*6.283185)*.14
                 + sin(phaseAt*29.515 + seed.x*39.0)*.06;
float tailX = p.x + wanderNow - wanderThen;
float residue = 1.0 - smoothstep(0.0, .30+.15*seed.x, ageSince);
float tail = (1.0-smoothstep(tailWidth, tailWidth+tailAA, abs(tailX)))
           * smoothstep(width*.5, width*1.5, p.y)
           * residue
           * step(.38, seed.z) * enabled * .24;
float2 tailSlope = float2(clamp(tailX/tailWidth, -1.0, 1.0)*tail*.25, 0);

// Small pinned beads appear between the sliding drops; no uniform haze or tint.
float2 smallCellSize = float2(1.4, 1.8);
float2 smallCell = floor((UV+float2(41.3,17.9))/smallCellSize);
float3 smallSeed = drops.hash(smallCell + 63.1);
float2 smallP = (frac((UV+float2(41.3,17.9))/smallCellSize)-.5)*smallCellSize
              - (smallSeed.xy-.5)*smallCellSize*.68;
float smallPhase = frac(T/8.0 + smallSeed.z);
float smallLife = smoothstep(0.0,.12,smallPhase)*(1.0-smoothstep(.72,1.0,smallPhase));
float radius = lerp(.065, .11, smallSeed.z);
float3 pinned = drops.bead(smallP, float2(radius, radius*1.15), footprint)
              * saturate((rain-smallSeed.x)*8.0) * smallLife * .65;
return float3(saturate(falling.x+pinned.x+tail),
              clamp(falling.yz+pinned.yz+tailSlope, -1.0, 1.0));
'''


def build_rain_glass(u, surface):
    """Local droplet coverage only; keep the entire dry pane optically neutral."""
    lib = u.MaterialEditingLibrary
    path = FOLDER + '/' + RAIN_NAME
    material = u.load_asset(path)
    if material and not isinstance(material, u.Material):
        raise RuntimeError('Expected a generated material at ' + path)
    if not material:
        material = u.AssetToolsHelpers.get_asset_tools().create_asset(
            RAIN_NAME, FOLDER, u.Material, u.MaterialFactoryNew())
    if not material:
        raise RuntimeError('Cannot create ' + path)
    lib.delete_all_material_expressions(material)
    material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
    material.set_editor_property('translucency_lighting_mode',
                                 u.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    material.set_editor_property('translucency_pass', u.MaterialTranslucencyPass.MTP_BEFORE_DOF)
    material.set_editor_property('use_material_attributes', False)
    material.set_editor_property('tangent_space_normal', True)
    material.set_editor_property('two_sided', True)
    material.set_editor_property('disable_depth_test', False)
    material.set_editor_property('use_translucency_vertex_fog', False)
    # PNO is neutral outside individual drops. A pane-wide IOR would move the
    # whole background even where opacity is zero in the legacy material path.
    material.set_editor_property('refraction_method', u.RefractionMode.RM_PIXEL_NORMAL_OFFSET)
    material.set_editor_property('refraction_depth_bias', 0.0)
    graph, prop = surface.Graph(material), u.MaterialProperty
    uv = graph.node(u.MaterialExpressionTextureCoordinate, coordinate_index=0)
    time = graph.node(u.MaterialExpressionTime, override_period=True, period=RAIN_PERIOD)
    rain = graph.scalar('RainIntensity', 0)
    detail = graph.custom(RAIN, {'UV': uv, 'T': time, 'Rain': rain}, True,
                          'Centimetre water drops falling along negative V')
    graph.output(graph.vector((.015, .018, .02)), prop.MP_BASE_COLOR)
    graph.output(graph.constant(0), prop.MP_METALLIC)
    graph.output(graph.constant(.045), prop.MP_ROUGHNESS)
    graph.output(graph.custom('return saturate(D.x)*.26;', {'D': detail},
                              description='Transparent between drops'), prop.MP_OPACITY)
    graph.output(graph.custom('return saturate(D.x)*.255;', {'D': detail},
                              description='Water specular only within drops'), prop.MP_SPECULAR)
    graph.output(graph.custom('return normalize(float3(D.yz*.65,1.0));',
                              {'D': detail}, True, 'Convex droplet tangent normal'), prop.MP_NORMAL)
    graph.output(graph.custom('return 1.0 + saturate(D.x)*.025;', {'D': detail},
                              description='Local lens distortion; 1 means none'), prop.MP_REFRACTION)
    lib.layout_material_expressions(material)
    lib.recompile_material(material)
    assert {str(n) for n in lib.get_scalar_parameter_names(material)} == {'RainIntensity'}
    for output in (prop.MP_OPACITY, prop.MP_NORMAL, prop.MP_REFRACTION):
        assert lib.get_material_property_input_node(material, output), str(output)
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWRecipe', RAIN_RECIPE)
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWGenerator', 'Scripts/build_desktop_frame.py')
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWUV0', 'centimetres; V points up; rain falls along -V')
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWRole', 'local rain lenses; no base film; independent of UI')
    if not u.EditorAssetLibrary.save_loaded_asset(material):
        raise RuntimeError('Cannot save ' + path)
    u.log('OOW_WINDOW_RAIN_GLASS_MATERIAL ' + path + ' ' + RAIN_RECIPE)


def main():
    import unreal as u

    # Reuse the existing expression/connection checks without running its build.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_surface_materials as surface
    surface.u, surface.mel = u, u.MaterialEditingLibrary
    lib = u.MaterialEditingLibrary
    path = FOLDER + '/' + NAME
    material = u.load_asset(path)
    if material and not isinstance(material, u.Material):
        raise RuntimeError('Expected a generated material at ' + path)
    if not material:
        u.EditorAssetLibrary.make_directory(FOLDER)
        material = u.AssetToolsHelpers.get_asset_tools().create_asset(
            NAME, FOLDER, u.Material, u.MaterialFactoryNew())
    if not material:
        raise RuntimeError('Cannot create ' + path)

    # Rebuild in place so existing runtime/asset references keep their identity.
    lib.delete_all_material_expressions(material)
    material.set_editor_property('blend_mode', u.BlendMode.BLEND_OPAQUE)
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
    material.set_editor_property('use_material_attributes', False)
    material.set_editor_property('tangent_space_normal', True)
    material.set_editor_property('two_sided', False)
    graph, prop = surface.Graph(material), u.MaterialProperty
    uv = graph.node(u.MaterialExpressionTextureCoordinate, coordinate_index=0)
    grain = graph.scalar('Grain', 1)
    detail = graph.custom(WOOD, {'UV': uv}, True, 'Filtered oak fibres, UV0 in cm')
    colour = graph.node(u.MaterialExpressionVectorParameter, parameter_name='Color',
                        default_value=u.LinearColor(.20, .09, .032, 1))
    roughness = graph.scalar('Roughness', .36)
    metallic = graph.scalar('Metallic', 0)
    graph.output(graph.custom('return saturate(C * (1.0 + saturate(G)*D.x*.32));',
                              {'C': colour, 'G': grain, 'D': detail}, True,
                              'Low-contrast smoked oak albedo'), prop.MP_BASE_COLOR)
    graph.output(graph.custom('return clamp(R + saturate(G)*D.x*.05, .04, 1.0);',
                              {'R': roughness, 'G': grain, 'D': detail},
                              description='Satin finish roughness'), prop.MP_ROUGHNESS)
    graph.output(graph.custom('return normalize(float3(-D.yz*saturate(G)*.006, 1.0));',
                              {'G': grain, 'D': detail}, True,
                              'Shallow wood pore normal'), prop.MP_NORMAL)
    graph.output(graph.custom('return saturate(M);', {'M': metallic},
                              description='Metallic fraction'), prop.MP_METALLIC)
    graph.output(graph.constant(.5), prop.MP_SPECULAR)
    lib.layout_material_expressions(material)
    lib.recompile_material(material)

    # Check the runtime interface and actual lit outputs before saving the asset.
    assert {str(n) for n in lib.get_scalar_parameter_names(material)} == {'Grain', 'Roughness', 'Metallic'}
    assert {str(n) for n in lib.get_vector_parameter_names(material)} == {'Color'}
    for output in (prop.MP_BASE_COLOR, prop.MP_ROUGHNESS, prop.MP_NORMAL, prop.MP_METALLIC):
        assert lib.get_material_property_input_node(material, output), str(output)
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWRecipe', RECIPE)
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWGenerator', 'Scripts/build_desktop_frame.py')
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWUV0', 'centimetres: U across grain, V along grain')
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWRole', 'lit foreground frame; independent of UI visibility')
    if not u.EditorAssetLibrary.save_loaded_asset(material):
        raise RuntimeError('Cannot save ' + path)
    u.log('OOW_DESKTOP_FRAME_MATERIAL ' + path + ' ' + RECIPE)
    build_rain_glass(u, surface)


if __name__ == '__main__':
    main()
