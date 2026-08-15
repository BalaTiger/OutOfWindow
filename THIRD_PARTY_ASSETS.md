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
- Usage: textured near- and middle-distance residential perimeter blocks
- Modification: modules are assembled into physically plausible elevations; doors remain on the ground floor, while upper floors use window modules and cornices

## Poly Haven — Modular Factory Facade

- Source: https://polyhaven.com/a/modular_factory_facade
- Author: James Ray Cock
- Files used: 1K glTF geometry and PBR texture set
- Source detail: 175K triangles; 53.3 m-wide modular industrial facade kit
- License: CC0 1.0 Universal
- Local path: `public/assets/polyhaven/models/modular_factory_facade/`
- Usage: textured industrial and warehouse perimeter blocks that break up repeated residential silhouettes
- Modification: modules are assembled into three-storey facades with ground-floor loading doors, upper windows, piers and cornices

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
- Usage: textured city-mesh LOD2 beyond the modular PBR perimeter, providing a continuous real-world skyline
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
- Usage: complete dense city preset, including continuous Parisian façades, storefronts, balconies, roofs, street furniture, paving and vegetation
- Modification: OBJ-to-glTF conversion, PBRT material-name reconciliation, alpha-material recovery, 512 px runtime textures, global LOD simplification, flat-metal treatment/no micro-shadow for railings and antennas, scene scaling and fixed-window camera composition

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

The application does not use a bundled HDRI or depth backplate for its primary environment lighting or distant view. It captures the current procedural sky, solar direction, clouds, weather and visible 3D scene into a half-float cube map. PMREM provides roughness-dependent specular lighting, and spherical harmonics from the same capture provide diffuse environment lighting. Reflective water is hidden during the environment capture to avoid recursive reflection.

These assets are bundled locally. The application does not call the Poly Haven API at runtime.
