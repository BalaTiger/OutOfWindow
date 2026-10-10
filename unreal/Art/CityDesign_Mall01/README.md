# CityDesign Mall01 — first review sample

This is a deliberately designed shopping centre and adjacent masonry building, made with Blender 5.0.1 background mesh operations after the user approved that execution method. It is not GUI hand modeling. No random city generator or Geometry Nodes city system is used.

## Files

- `CityDesign_Mall01.blend`: named editable architectural parts, two hidden consolidated export meshes, read-only original City context, three review cameras and a CPU daylight setup. Images are packed.
- `CityDesign_Mall01_Architecture.glb` and `.fbx`: only the two new buildings. Keep their authored world positions for this first staging sample. Do not import the original part collections as a thousand separate UE actors.
- `preview-window.png`: the fixed City roadside view, 960x540, VFOV54 degrees.
- `preview-close.png`: the mall's entrance, clipped corner, commercial floors and roof pavilion, 1100x760.
- `preview-neighbor.png`: masonry window reveals, balconies and the setback top, 1000x760.
- `validation.json`: actual saved-mesh audit. `export_audit_final.json`: independent GLB attribute/texture check. `validation-fbx.json`: FBX import round-trip audit from a fresh temporary scene.
- `Textures/Neighbor_Brick_BaseColor.png` and `Neighbor_Brick_Normal.png`: 512px original shader tiles baked on CPU. The normal is Blender/OpenGL tangent space. The stone image is embedded in the blend and GLB.
- `design_scope.md` and `design_manifest.json`: design intent, camera mapping and original reference provenance.

## Actual model data

| New architecture | Editable mesh parts | Vertices | Polygons | Triangles |
| --- | ---: | ---: | ---: | ---: |
| Shopping centre | 401 | 25,686 | 28,161 | 49,736 |
| Adjacent building | 604 | 31,024 | 29,116 | 58,552 |
| Total | 1,005 | 56,710 | 57,277 | 108,288 |

Exports consolidate this into **two meshes, 15 materials and 16 material sections**. The editable meshes retain individual names; the export proxies are hidden in `Export_Architecture_Batched`.

The mall core is 44x72 m, base Z6.9 m, roof pavilion top Z31.3 m (24.4 m above the design base). Including foundation, plaza, canopy and fins, its measured Blender world bounds are X[-68.160,-19.000], Y[-18.000,62.000], Z[6.550,31.300]. Its upper principal street elevation has 44.01% rectangular glazing by the authored opening schedule. Shopfronts and the double-height entrance have greater glazing; this is not a measured whole-building percentage.

The adjacent core is 26x34 m, base Z6.9 m; rooftop service top is Z52.0 m (45.1 m above base). Including projecting balconies/trim, its measured bounds are X[-48.600,-19.850], Y[74.400,110.650], Z[6.600,52.000]. Its upper street elevation has approximately 32.53% glazing after completing the actual masonry jambs, heads and sills.

The stored-mesh audit reports PASS: zero objects with errors or warnings, finite data, positive applied unit scales, valid UV0/UV1, zero degenerate geometry, zero negatively wound closed shells. Open converted lettering attachments are allowed and individually recorded. Export UV1 was independently repacked per whole building. UV island overlap, self-intersection and production texel density were not independently tested.

The independent GLB check reports PASS for two meshes, 15 materials, three embedded image textures, valid indices, finite attributes, unit normals and UV0 texture mapping. FBX import round-trip also reports PASS, retaining metre coordinates, two meshes, UV0/UV1 and 108,288 triangles. All three final CPU previews were inspected as pixels after the last geometry refinement.

`protected-input-checks.json` confirms unchanged hashes for the original City map, original modern-city GLB, shared city build script and Run-Unreal script. GLB SHA256: `0c8093dfad665e35c0101980e19115b945b829a50385c014a516b041cb0aa617`.

## Coordinate and integration notes

One Blender unit is one metre, right-handed Z up. Blender = (glTF x,-glTF z,glTF y). The original project imports glTF metres to UE centimetres as (100*x,100*z,100*y), so UE = (100*BlenderX,-100*BlenderY,100*BlenderZ). The GLB preserves this mapping. Do not apply a second metre-to-centimetre conversion.

Window camera Blender position is [26,-42,37], target [-22,115,19], VFOV54. This gives HFOV84.342 for 16:9, while the old 1280x820 saved map audit gives HFOV76.994. Their physical view direction is identical. WindowFrame remains separate from the architecture.

The mall occupies the old B01/B02 pair; the adjacent building occupies old B03 only in this independent blend. B07 and other old towers remain context. The mesh/sample does not alter the old City map, camera, director, shared build scripts, weather assets or deployment. Future UE placement must also exclude old B01/B03 entrance assemblies. The portal threshold is Z7.04 m to meet the existing pavement.

Before UE import, trial-map placement or GPU rendering, coordinate a time with source thread `01a10c3a-641b-7194-9e41-495d32680026`. No UE import or render has been performed. UE material behavior, glass/transmission mapping, lightmap overlap, collision, Nanite settings and runtime performance remain unverified. The pictures are Blender CPU architectural reviews, not UE captures or a proof of parity with the generated target.

## Sources and reconstruction

Pixels of accepted `../City/city-window-target-v3.png` were inspected before designing forms. Earlier v2 and current `city-facade-clear.png` were separately inspected as design history and a problem baseline.

Architecture and baked brick tile are original project work. The brick is a shader approximation, not a measured scan. Limestone color reuses unmodified ambientCG Travertine001 (CC0) from `../City/Facade/`. Linden planting and existing context preserve the project's licensed source: Amazon Lumberyard Bistro (2017), ORCA, CC BY4.0, modified by OutOfWindow. See the root `THIRD_PARTY_ASSETS.md` and original City art notes.

Use installed `D:\Blender\blender.exe`, one process at a time. Run `build_city_sample.py` with `--background --factory-startup --threads 1 --python ... -- <this directory>`, then load the saved blend and run `refine_facade_returns.py`, then `validate_city_sample.py` with its report path, and finally `render_saved_sample.py`. CPU preview helper fixes render threads to one. The refinement helper calls `repair_text_and_export.py` to refresh export copies and remove world-precision degenerate text triangles.

Blender 5.0 uses Sky `MULTIPLE_SCATTERING`; the older `NISHITA` enum is unavailable. Baking and rendering in the same live process hit this installation's `OpenImageIO_Util.dll` mesh-sync crash. A bake-plane-only scene followed by fresh-process CPU rendering completed. Build/export and preview are therefore separate, with logs retained here.
