# Unreal migration asset inventory

This is the original browser-to-Unreal migration inventory, audited 2026-09-23 against src/main.js and src/scene-pack.js. Historical CITY_PERIPHERY_PREP.md contains an older city camera, so the migration JSON uses that executable configuration.

**City override, 2026-09-24:** the current Unreal City map is redesigned by `Scripts/build_city_lookdev.py`. Its architecture has 54 buildings: 16 nearby, 18 skyline towers and 20 context buildings. The context geometry uses six meshes: four batches of the original 18 middle/background buildings, one distant junction mesh, and a batch of two added neighbors outside the fixed camera's view that supply actual geometry for glass reflections. Architecture totals are 98,168 triangles in 52 meshes / 192 material sections, including 12 LED poles. The map also contains 28 instanced linden trees and 16 detailed traffic sedans. The new camera is on a roadside building, approximately 30 m above the road. The original City construction and camera below describe migration history only. See `Art/City/README.md`, `Migration/city-facade.md`, `Migration/city-modern-build.json` and `Migration/city-modern-audit.json` for current assets and checks. Window frames are a separate runtime selection shared across scenes.

Preferred carrier: export each runtime world.groups scene to glTF, including procedural geometry. The JSON is an exact camera/asset-placement/semantic reference and a reconstruction fallback, not a second transform layer over already placed exports.

**City office lighting, 2026-09-24:** the 16 nearby buildings now author continuous floor/office lighting for 13,724 panes in `modern-city.glb` COLOR_0. Geometry, UVs and material sections are unchanged. Native City materials read this channel only for night emission; standard glTF viewers may multiply it into base color. Entrance geometry explicitly uses black COLOR_0 to keep shared door glass from glowing. See `Migration/city-office-night.md` and `Migration/city-office-night-verification.json`.

**City night rain and road lighting, 2026-09-24:** distant glass now has native continuous office bands. The saved map uses 18 downward street lamps, including six farther poles reusing the original LED meshes and materials. Traffic adds at most eight pooled headlight spot components. Rain cards are shorter and fade near the camera. No new third-party asset or license. See `Migration/city-night-weather.md` and `Migration/city-night-weather-verification.json`.

**Latest City road/color override, 2026-09-24:** `city-road-markings.glb` supplies two paint meshes / 1,352 triangles, replacing the 40 legacy line actors and removing three obsolete cross-street surfaces. Five legacy road/ground surfaces now remain. Their City-only native materials reuse Poly Haven Asphalt 02 at 3m world scale; dry/wet asphalt retains rough aggregate and only sparse low spots become smooth water. Existing pavement geometry keeps six batches and gains stable whole-slab vertex colors for warm-grey walking bands, deep-grey service strips and restrained accents. Current saved-map and performance evidence: `Migration/city-road-color-verification.json`.

**City street-level addition, 2026-09-24:** `city-sidewalk.glb` adds 131,336 triangles in six native Nanite material batches, replacing four flat legacy sidewalk actors while retaining 48 road actors. It models elevated paving, segmented curbs, four crossing ramps and 28 planted tree beds. `city-entrances.glb` adds 8,360 triangles in seven meshes / 31 material sections: six street entrances and access doors on the four actual terrace buildings (B01/B04/B07/B11). Door thresholds and clear walking strips are checked against the existing architecture. Concrete3 color/normal maps are reused from licensed ORCA Bistro; see `Art/City/Sidewalk/source.json` and `Migration/city-sidewalk.md`.

| Scene | Actual construction | Asset instances | Assemblies |
|---|---|---:|---:|
| city / 都市 | 12 four-sided apartment blocks, 3 factory facades, Helsinki skyline; procedural roads, traffic, trees and towers | 5 | 15 |
| alley / 后巷 | Bistro near package with 3 street-seating instances | 4 | 0 |
| village / 雾隐村庄 | Rolling field, lane, fort modules, grass, pines, barrels and crates | 32 | 0 |
| forest / 深山呼吸 | Rolling forest floor, river ribbon, 16 pines, 3 mountainsides and 5 moss-rock clusters | 24 | 0 |
| coast / 潮汐海岸 | Displaced coast sand, 6 scan instances, water plane and animated foam | 6 | 0 |

## Coordinate and camera contract

Three world is right-handed, Y-up and metre-scaled. Manifest conversion is Unreal centimetres (X,Y,Z)=(Three.x,Three.z,Three.y)*100. The importer must match that convention exactly once. This matches the verified UE 5.7 glTF Interchange (X,Z,Y) conversion. Verify with calibration points and do not convert twice. The manifest preserves vertical FOV; Unreal horizontal FOV must be recalculated for the current aspect.

Alley camera: [-20,23,-208] m toward [-46,23,-246], vertical FOV 55 degrees. Under the manifest conversion it is [-2000,-20800,2300] cm toward [-4600,-24600,2300] cm. Nearby paving is around 7.05–7.17 m, placing the camera approximately 16 m above it.

Bistro near wrapper: translation [-10,6.7914363039,-205] m; uniform scale 0.0164842686; rotation Y=0. This comes from actual glTF node/accessor bounds, including normalized quantized POSITION accessors. Do not assume the source asset's numeric coordinates are already the final world metres.

## Export and material boundaries

- Export Bistro near as the sole scene carrier. The far GLB is a reference-only legacy duplicate. It must not be instantiated/imported as a second full scene. Re-enable all near architectural nodes before export; the browser's main-camera LOD visibility must not remove offscreen reflection/GI/shadow geometry.
- near is 164,234,472 bytes and far is 153,011,180 bytes in this audit. Both contain 157 embedded 768px images, 125 materials and no native ORM/AO texture entries. New engine import alone does not increase source texture quality.
- MASTER_Details_Dark is correctly deduplicated to MASTER_Building_Details. Their original BaseColor and Normal files are identical. Concrete is an incorrect replacement for these window shutters and trim.
- Source glTF export does not retain onBeforeCompile wind/wetness, dynamic normal scrolling, custom foam GLSL, sky, weather particles, or reflection-capture behavior. Recreate these as native engine materials/components. Preserve actor placement and material IDs.
- Preserve alpha cutouts on vegetation/ironwork and import OpenGL normal maps with exactly one normal-Y convention conversion. Do not double-apply the browser's normal repair or model placement.
- Named assembly recipes point to exact source functions for roofs, railings, balcony planters, repeated windows and traffic. Export is preferable to reconstructing those functions independently.

## Licensing and included scope

Licensing metadata is transcribed from THIRD_PARTY_ASSETS.md, with its primary source URLs retained in the JSON. Bundle the full attribution record alongside engine content/build outputs.

- Amazon Lumberyard Bistro (2017), via NVIDIA ORCA: CC BY 4.0; modified source/conversion/material mapping must remain credited.
- City of Helsinki 3D Mesh 2017, tile Helsinki3D_2017_OBJ_668494x2: CC BY 4.0. Required credit: Helsinki 3D Mesh © City of Helsinki, licensed under CC BY 4.0; modified for real-time rendering.
- Poly Haven models and material sets: CC0. The road001 directory is the normalized ambientCG Road001 material, also CC0, despite living under a polyhaven path.
- Three.js waternormals.jpg: MIT according to the repository attribution record. Retain the Three.js notice when redistributing.
- Emerald Square is explicitly excluded: isolated research material under CC BY-NC-SA 3.0, absent from the runtime. Do not bulk-import .runtime.
- Unused boulder_01 and experimental Bistro variants are not migration sources.

## Validation performed

Parsed every referenced glTF/GLB JSON and calculated hierarchical accessor bounds without decoding texture payloads. Checked all selected fort part names exist, all source paths exist, all five camera records are present and every full-model placement is serialized as a Three world matrix. No source runtime files were changed.
