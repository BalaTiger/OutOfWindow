"""Night-only office bands on the existing distant curtain-wall box skins."""
import unreal as u

DISTANT_GLASS = {'CityModern_Skyline_Glass_Blue', 'CityModern_Skyline_Glass_Grey'}
DISTANT_LIGHTING_VERSION = 'city-distant-office-v1'
DISTANT_LIGHT_GAIN = .025


def apply_distant_lighting(g, night):
    """Use each box face's UVs, including the several buildings in one batch."""
    uv = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=0)
    local = g.node(u.MaterialExpressionTransformPosition,
                   transform_source_type=u.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD,
                   transform_type=u.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
    g.connect(g.position(), local, '')
    normal = g.node(u.MaterialExpressionVertexNormalWS)
    code = r'''
// Recover the source face dimensions from its unbroken 0..1 box UVs. Local
// coordinates preserve the existing floor ribbons when a skyline actor is scaled.
float2 dx = ddx(U), dy = ddy(U);
float det = dx.x * dy.y - dx.y * dy.x;
float inv = (det < 0. ? -1. : 1.) / max(abs(det), 1.e-12);
float3 du = (ddx(P) * dy.y - ddy(P) * dx.y) * inv;
float3 dv = (ddy(P) * dx.x - ddx(P) * dy.x) * inv;
float width = max(length(du) * .01, 1.);
float height = max(abs(dv.z) * .01, 1.);
float floors = max(2., floor(height / 3.5 + .5));
float3 centre = P - du * (U.x - .5) - dv * (U.y - .5);
// Quantization removes derivative roundoff without seeding individual windows.
float seed = dot(floor(centre * .01 + .37), float3(.1031, .11369, .13787));
float face = frac(sin(seed * 17.713) * 43758.5453);
float rowCoord = saturate(U.y) * floors;
float row = min(floor(rowCoord), floors - 1.);
float lease = floor((row + floor(face * 3.)) / (2. + floor(face * 3.)));
float leaseSeed = seed * 31.717 + lease * 13.173;
float phase = frac(sin(leaseSeed) * 43758.5453);
// Each tenant covers 7--18 source metres across several glass bays. Smooth
// changes between neighbouring tenants retain borrowed light at their edges.
float zoneWidth = clamp(width * (.25 + face * .13), 7., 18.);
float zoneCoord = U.x * width / zoneWidth + phase;
float zone = floor(zoneCoord);
float a = frac(sin(leaseSeed + zone * 27.619) * 43758.5453);
float b = frac(sin(leaseSeed + (zone + 1.) * 27.619) * 43758.5453);
float office = lerp(smoothstep(.23, .62, a), smoothstep(.23, .62, b),
                    smoothstep(.22, .78, frac(zoneCoord)));
float floorLevel = .75 + .25 * frac(sin(seed * 11.317 + row * 8.713) * 43758.5453);
float t = frac(rowCoord);
float aa = min(.24, max(fwidth(rowCoord), .003));
float opening = smoothstep(.08 - aa, .08 + aa, t)
                * (1. - smoothstep(.78 - aa, .78 + aa, t));
float ceiling = lerp(.16, 1., 1. - smoothstep(.14, .65, t));
// Average subpixel bands instead of making distant floors sparkle.
float band = lerp(opening * ceiling, .35, saturate(fwidth(rowCoord) - .4));
float3 tint = lerp(float3(.83, .9, 1.), float3(1., .87, .69), phase * .75 + .2);
float vertical = 1. - smoothstep(.1, .5, abs(Normal.z));
return tint * G * (.018 + .982 * office) * floorLevel * (.5 + face * .5)
       * band * vertical * smoothstep(.58, .86, Night);
'''
    g.output(g.custom(code, {'U': uv, 'P': local, 'Normal': normal, 'Night': night,
                             'G': g.constant(DISTANT_LIGHT_GAIN)}, True,
                      'Distant offices: continuous tenant zones and source-aligned floors'),
             u.MaterialProperty.MP_EMISSIVE_COLOR)
    u.EditorAssetLibrary.set_metadata_tag(g.material, 'OOWDistantLightingVersion', DISTANT_LIGHTING_VERSION)
