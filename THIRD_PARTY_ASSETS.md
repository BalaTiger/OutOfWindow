# Third-party assets

## Poly Haven — Pine Sapling Small

- Source: https://polyhaven.com/a/pine_sapling_small
- Authors: Rico Cilliers (modeling), Rob Tuytel (photography)
- Files used: 1K glTF geometry and PBR texture set
- License: CC0 1.0 Universal
- Local path: `public/assets/polyhaven/pine_sapling_small/`
- Usage: high-detail real-time foreground vegetation in the forest preset
- Modification: runtime scaling, placement, shadows, environment-map intensity

## Poly Haven — Modular PBR material set

- Sources:
  - https://polyhaven.com/a/asphalt_02
  - https://polyhaven.com/a/brushed_concrete
  - https://polyhaven.com/a/brown_planks_03
  - https://polyhaven.com/a/aerial_rocks_04
- Files used: 1K diffuse, OpenGL normal and roughness maps for each material
- License: CC0 1.0 Universal
- Local path: `public/assets/polyhaven/materials/`
- Usage: modular asphalt, concrete, wood and rock material profiles shared by all presets
- Modification: tiled UVs, anisotropic filtering, runtime wetness and environment-reflection response

## Poly Haven — Modular Urban Apartments Facade

- Source: https://polyhaven.com/a/modular_urban_apartments_facade
- Author: James Ray Cock
- Files used: 1K glTF geometry and PBR texture set
- Source detail: 118K triangles; 51.5 m-wide modular residential facade kit
- License: CC0 1.0 Universal
- Local path: `public/assets/polyhaven/models/modular_urban_apartments_facade/`
- Usage: near- and middle-distance residential blocks in the independent 都市 (city) scene
- Modification: 3 m modules assembled into closed, four-sided 21 m blocks with roofs, ground-floor doors and upper windows; repeated modules instanced per building; selected glass materials emit warm light at night

## Poly Haven — Modular Factory Facade

- Source: https://polyhaven.com/a/modular_factory_facade
- Author: James Ray Cock
- Files used: 1K glTF geometry and PBR texture set
- Source detail: 175K triangles; 53.3 m-wide modular industrial facade kit
- License: CC0 1.0 Universal
- Local path: `public/assets/polyhaven/models/modular_factory_facade/`
- Usage: textured industrial and warehouse perimeter blocks that break up repeated residential silhouettes
- Modification: modules assembled into four-storey facades with 3 m floor spacing, 6 m ground-floor loading doors, upper windows, piers and cornices; instanced repeated parts and recessed structural backing

## ambientCG — Road 001

- Source: https://ambientcg.com/view?id=Road001
- Author: ambientCG
- Files used: 1K JPG color, OpenGL normal, roughness and displacement maps
- License: CC0 1.0 Universal
- Local path: `public/assets/ambientcg/Road001/` and runtime-normalized copies in `public/assets/polyhaven/materials/road001/`
- Usage: PBR traffic lanes and cycle-lane surface in the city preset
- Modification: texture renaming, tiled UVs, anisotropic filtering and runtime rain response

## City of Helsinki — Helsinki 3D Mesh 2017

- Official source: https://www.hel.fi/en/decision-making/information-on-helsinki/maps-and-geospatial-data/helsinki-3d
- Download source: https://3d.hel.ninja/data/mesh/Helsinki3D-MESH_2017_OBJ_2km-250m_ZIP/
- Data provider: City of Helsinki
- Source tile: `Helsinki3D_2017_OBJ_668494x2.zip`
- License: CC BY 4.0
- Local runtime path: `public/assets/helsinki/helsinki-periphery-lod2.glb`
- Usage: distant city-mesh LOD2 in the independent 都市 scene, behind modular PBR blocks; no longer part of the Bistro view
- Modification: selected sub-tiles, recentered coordinates, OBJ-to-glTF conversion, geometry simplification, texture downsampling and reduced baked-light contrast for live sky lighting
- Required attribution: Helsinki 3D Mesh © City of Helsinki, licensed under CC BY 4.0; modified for real-time rendering

## Amazon Lumberyard / NVIDIA ORCA — Bistro Exterior

- Primary source: https://developer.nvidia.com/orca/amazon-lumberyard-bistro
- Converted OBJ archive: https://casual-effects.com/g3d/data10/index.html
- PBR texture conversion source: https://github.com/mmp/pbrt-v4-scenes/tree/master/bistro
- Author/copyright: Amazon Lumberyard, 2017
- License: CC BY 4.0
- Files used: LOD runtime conversion of the complete Bistro Exterior, retaining 132 materials and embedded BaseColor/normal data
- Local runtime path: `public/assets/orca/bistro/`
- Usage: independent 后巷 (alley) preset, including continuous Parisian façades, storefronts, balconies, roofs, street furniture, paving and vegetation; the original street camera is preserved
- 2026-09-09 runtime changes: masonry normals rebuilt with a 35-degree crease while preserving texture UVs; awning fabric and foliage receive constrained wind/rain vertex deformation; wetness, puddle reflections and ground impacts are generated at runtime. Original asset files remain unchanged.
- Modification: OBJ-to-glTF conversion, PBRT material-name reconciliation, alpha-material recovery, 768 px runtime textures, fixed-view near-geometry restoration for 26 architectural meshes inside the 70 m view cone, procedural hero window frames generated around visible glass, derived roughness/AO/height channels for masonry and pavement, optional Poly Haven CC0 plaster/cobblestone PBR replacement prepared by `scripts/download-real-bistro-pbr.mjs`, reduced geometry for the remaining distant meshes, no micro-shadow for railings and antennas, scene scaling and fixed-window camera composition. The 2026-09-08 runtime revision preserves ironwork alpha cutouts, calibrates glass/metal roughness, adds pavement rain response and emits light from existing lamp materials. The derived grayscale channels are conservative estimates from the licensed base-color maps; the optional real pack supplies diffuse, OpenGL normal, ARM and displacement channels when installed.

## NVIDIA ORCA — Emerald Square (research candidate, not bundled)

- Source: https://developer.nvidia.com/orca/nvidia-emerald-square
- Author: Nicholas Hull / NVIDIA, 2017
- License: CC BY-NC-SA 3.0
- Source detail: four tileable city blocks, 10,046,405 triangles
- Local staging path: `.runtime/emerald-square-source/`
- Status: isolated research candidate for city-periphery composition and LOD tests; it is not referenced by runtime code and is not included in the build
- Release restriction: do not ship as a commercial default asset without separate permission or replacement by a commercially compatible source

## Poly Haven — High-detail scene models

- Sources:
  - https://polyhaven.com/a/modular_street_seating
  - https://polyhaven.com/a/modular_fort_01
  - https://polyhaven.com/a/wine_barrel_01
  - https://polyhaven.com/a/wooden_crate_02
  - https://polyhaven.com/a/grass_bermuda_01
  - https://polyhaven.com/a/grass_medium_02
  - https://polyhaven.com/a/mountainside
  - https://polyhaven.com/a/rock_moss_set_01
  - https://polyhaven.com/a/coast_line_01
  - https://polyhaven.com/a/sand_rocks_small_01
  - https://polyhaven.com/a/coastal_cliff_01
- Files used: 1K glTF geometry and PBR texture sets
- License: CC0 1.0 Universal
- Local path: `public/assets/polyhaven/models/`
- Usage: village grass fields, stone architecture and props; forest mountainsides and moss-covered rocks; photogrammetry coastline, sand/rock formations and cliffs
- Modification: runtime scaling/placement, fixed-view composition, dynamic shadows and environment-map response

## Poly Haven — Terrain PBR materials

- Sources:
  - https://polyhaven.com/a/withered_grass
  - https://polyhaven.com/a/forest_ground_04
  - https://polyhaven.com/a/coast_sand_02
- Files used: diffuse, OpenGL normal, roughness and displacement maps
- License: CC0 1.0 Universal
- Usage: displaced rolling village terrain, forest floor and coast sand beneath the scanned hero geometry

## Three.js — Water normal texture

- Source: https://github.com/mrdoob/three.js/blob/dev/examples/textures/waternormals.jpg
- License: MIT (Three.js example asset)
- Local path: `public/assets/water/waternormals.jpg`
- Usage: animated normals for the planar-reflection ocean and PBR forest stream
- Modification: repeat wrapping and independent time-based UV motion

## Runtime environment lighting

The application does not use a bundled HDRI or depth backplate for its primary environment lighting or distant view. It captures an analytic Rayleigh/Mie sky with animated 2D cloud density into a half-float cube map. The analytic sky uses Three.js's MIT-licensed Sky addon. PMREM supplies both diffuse and roughness-dependent specular lighting; a second spherical-harmonic light is not added. Geometry, window glass and precipitation are excluded from this sky-only capture. The solar disc is excluded from the lighting capture because direct sunlight is provided separately. Capture preserves pending shadow updates and disposes the previous PMREM render target. Local lamp lighting and urban night skyglow are approximations; there is no full global illumination or volumetric cloud ray marching.

These assets are bundled locally. The application does not call the Poly Haven API at runtime.

## Generated visual reference (documentation only)

- Local file: `docs/alley-photoreal/reference-generated.png`
- Created with the built-in image generation tool as an edit of the project's rendered Bistro alley screenshot.
- The pictured architecture derives from the ORCA Bistro asset credited above; the project frame/UI is retained in the reference.
- Purpose: compare wet material appearance, water and lighting. This image is not loaded by the application as a backdrop or texture.
- Generation mode and full prompt: `docs/alley-photoreal/reference-prompt.md`.
