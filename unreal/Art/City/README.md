# Modern City assets and visual direction

Accepted art direction: [city-window-target-v3.png](city-window-target-v3.png), created with the built-in image tool. [Full prompt](city-window-target-v3.json). It depicts a modern business district viewed obliquely from a roadside building. This is an AI target, not an engine capture. The earlier European and central-vista targets are superseded.

The current facade revision is recorded in [city-facade.md](../../Migration/city-facade.md), including its validation status. Historical packaged captures from the earlier weather/skyline revision are [sunny with the independent graphite frame](city-cloudmotion-end.png), [rainy daylight](city-weather-rain.png) and [rain at night](city-weather-rainnight.png). The rainy daylight benchmark hides the frame. Their [weather/skyline measurements](../../Migration/city-weather.md) and [verification data](../../Migration/city-weather-verification.json) describe that earlier build, not the current facade revision. The `city-implemented-*` captures and `city-modern-verification.json` are older history before the weather update.

`modern-city.glb` is original project geometry: 54 buildings (16 foreground, 18 distant towers and 20 context buildings) plus 12 slim LED poles, totaling 98,168 triangles in 52 meshes / 192 material sections. The context geometry uses six meshes: four batches of the original 18 context buildings, one distant T junction/plaza, and one batch containing two added neighboring buildings outside the fixed camera's view. The original context buildings fill the bare ground below the towers and hide the unused road continuation; their lower silhouettes preserve sky above the existing towers. The two offscreen neighbors supply actual geometry for glass reflections while remaining ordinary opaque, shadow-casting buildings, not reflection-only surfaces. Deep window reveals, floor bands, setbacks, roof screens and terrace details are modeled. Glass uses opaque reflective PBR surfaces appropriate to this fixed distant view; the buildings do not contain the furnished interiors suggested by the reference. `traffic-sedan.glb` adds a 916-triangle, six-material sedan with wheel arches, windows, tires, hubs and lamps. The car is 4.30 × 1.803 × 1.45 m; front is glTF +Z, ground is Y=0. Generator scripts and numerical checks accompany both assets.

The current B01/B07 facade refinement adds beveled, slimmer floor bands and corner trims, deeper window recesses, thinner rails, terrace decks, irregular shrub clusters and four benches. Their 630 complete panes carry stable UV1 seeds for restrained glass color, roughness and reflected-image variation. The two shared stone materials use the original ambientCG Travertine001 color, roughness and DirectX normal maps at the documented 1.2 m scale; these shared materials also improve other existing stone surfaces. See [facade asset sources](Facade/README.md) and the [implementation record](../../Migration/city-facade.md).

The generated `Facade/office-atlas-v1.png` is an unused optional source asset. It is not connected to the current City materials or imported for this revision; it is an AI-generated image, not photography or a measured PBR material. Its [full generation prompt](Facade/office-atlas-prompt.json) is retained. This revision prioritizes exterior modeling and PBR surfaces, without adding furnished interior geometry or an interior image layer.

Night lighting now groups all 13,724 near-building panes into continuous floor/office zones with softer edges and low borrowed light. Linear `COLOR_0` is authored per complete pane and read only by native night emission; it must not tint the daytime base color. All other architecture and entrance geometry uses black night data. Shared `OFFICE_LIGHT_GAIN` in the native material builder controls intensity, with a brighter ceiling side and darker lower glazing. This adds no geometry, real lights or material sections. See [office lighting and verification](../../Migration/city-office-night.md).

The earlier context revision added 9,372 triangles, five meshes and 14 material sections. The current generator retains its 30 ground sightline checks from the fixed roadside camera against solid buildings, including the saved skyline transform. These CPU checks do not replace engine captures. The saved-map audit checks the geometry hash, separate context counts, context world bounds and facade data after reimport.

The City map owns the roadside camera and exterior scene only. Its decorative window frame is supplied independently by `AWindowFrame`, with a stable style ID (`oak`, `ivory`, `graphite`) and a choice retained across scene changes. No frame or sill from the target image is baked into City. Future collection/unlock data can refer to the same style IDs without duplicating city maps; this change does not implement collection rewards or an economy.

Rebuild the original geometry with `node unreal/Scripts/prepare_modern_city.mjs`, `node unreal/Scripts/prepare_city_vehicle.mjs`, `node unreal/Scripts/prepare_city_sidewalk.mjs`, `node unreal/Scripts/prepare_city_entrances.mjs` and `node unreal/Scripts/prepare_city_road_markings.mjs`, then run `build_city_lookdev.py` through UE. The normal `Run-Unreal.ps1 -Mode Import` sequence applies it after the legacy material import. `audit_city_lookdev.py` independently reloads the saved map and checks the camera, traffic, trees, materials and instance transforms.

## Modeled street level

`city-sidewalk.glb` replaces the old zero-thickness sidewalk strips (legacy actors 37, 38, 42, 43). It contains raised paving, slab thickness, segmented curbs, four crossing ramps, planted tree beds, and a graded connection to the far junction. The retained road/cycle/parking geometry stays in place. Pavers are merged into a small number of native Nanite meshes rather than separate actors per slab. Geometry checks sample the exported mesh surfaces; the saved-map audit checks the imported source hashes, bounds, thickness, tree positions and materials.

The concrete grain reuses unmodified Bistro `Concrete3` color and normal maps under CC BY 4.0. `Sidewalk/source.json` records provenance and normal convention. The paving joints and raised edges come from geometry. Rain darkens concrete and reduces roughness without flattening the modeled surfaces.

The current paving palette uses stable per-slab `COLOR_0` linear multipliers on the shared paving material: warm grey pedestrian bands, deeper grey service strips, and sparse cool/grey-brown variation. Kerbs and planters use a softer medium grey; tactile pads use subdued ochre. Geometry, ramps and tree-pit openings are unchanged by recoloring.

`city-road-markings.glb` replaces all 40 old line actors, including the wrongly oriented crosswalk stripes, with two paint batches (1,352 triangles). It follows the existing traffic directions, marks two lanes in each direction, and gives crosswalks an upstream stop line and parking clearance. The obsolete cross-street planes 39–41 are removed; five legacy grounding/asphalt/parking/cycle surfaces remain. `build_city_roads.py` assigns native City-only materials using Poly Haven Asphalt 02 at its 3m source scale. Dry aggregate is rough, damp asphalt retains grain, and only sparse low spots reach smooth-water roughness. This replaces the legacy ground shader's broad mirror-like rain response without changing other maps.

`city-entrances.glb` adds six street-facing entrance assemblies with portal depth, door hardware and entrance flooring, plus access doors on the actual B01/B04/B07/B11 terrace platforms. The terrace thresholds meet the existing deck surfaces, with clear approaches checked against the source building meshes. The additions reuse the existing native stone, metal and opaque glazing materials. `import_city_sidewalk.py` can update these two asset packages on the saved City map without rebuilding towers; the complete City build also calls it, so a future rebuild retains these additions.

## Licensed planting asset

`OOW_City_Linden.glb` is a reusable realistic linden for a landscaped metropolitan boulevard. It uses the project's existing licensed source, so no model download is required.

| Property | Value |
| --- | --- |
| Source | Amazon Lumberyard Bistro (2017), NVIDIA ORCA |
| License | [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/) |
| Source/license verification | [NVIDIA ORCA asset page](https://developer.nvidia.com/orca/amazon-lumberyard-bistro), checked 2026-09-24 |
| Source mesh | `Linde_Tree_Large_linde_tree_large`, index 972 |
| Geometry | 47,990 triangles, 2 material sections |
| Dimensions | 9.86 × 11.00 × 12.93 m in glTF X/Y/Z |
| Origin | Trunk foot centered horizontally; lowest root at Y=0 |
| Coordinates | glTF Y up, metres; UE imports once to Z up, centimetres |
| Textures | External PNGs in `textures/`; preserve the relative folder |
| Leaves | Two-sided alpha mask, cutoff 0.35; shared green leaf atlas |

Modifications: extracted the complete source tree; recentered at the trunk foot; resized uniformly to 11 m height; combined orange and green canopy sections under the existing green atlas (the silhouettes and UV layouts match); adjusted material tint for summer planting; converted leaf translucency to an alpha mask. Geometry, source UVs and source textures are preserved. The leaf normal is omitted because its source is a flat placeholder. The trunk retains its original normal texture.

Required credit for redistribution: **Amazon Lumberyard Bistro (2017), Open Research Content Archive (ORCA), CC BY 4.0. Modified by OutOfWindow.** Retain the project's full `THIRD_PARTY_ASSETS.md` with distributions.

Use instanced static meshes and native distance LODs. Each near tree is 47,990 triangles; repeated foliage also carries alpha-mask pixel cost. Source GLB is the full reusable mesh, not a distance-optimized LOD. A 0.65–1.0 instance scale covers 7.15–11 m street planting. Keep native pivots when placing instances; no second metre/centimetre conversion is needed after importing.

Rebuild and verify from the project root:

```powershell
python unreal/Scripts/prepare_city_assets.py
python unreal/Scripts/prepare_city_assets.py --self-test
```

The deterministic manifest records dimensions, triangle count and SHA-256. The preparation script does not run Unreal or change maps. Poly Haven Street Lamp 01 and 02 were researched but excluded: their Victorian ornament does not fit the modern metropolitan direction.
