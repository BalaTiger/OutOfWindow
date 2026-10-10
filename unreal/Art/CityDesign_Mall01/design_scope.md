# OutOfWindow City / shopping centre sample

Status: user approved background Blender mesh editing on 2026-10-07 through the source thread. This is authored mesh work executed by script, not GUI hand modeling and not a random city generator.

Independent output directory: `C:\Users\zhuzi\Documents\OutOfWindow\unreal\Art\CityDesign_Mall01\`.

## Reference and existing scene

- Accepted target, pixels inspected: `unreal/Art/City/city-window-target-v3.png`. Its README and provenance identify it as AI art direction. It provides an oblique roadside window camera, layered podiums, narrow facade members, open sky and believable street scale.
- Superseded target, pixels inspected: `city-modern-target-v2.png`.
- Current problem capture, pixels inspected: `city-facade-clear.png`. Broad repeated glazing dominates, floor rhythms are similar and a clear shopping destination is absent. This is a baseline, not the desired reference.
- Earlier city reference, pixels inspected: `docs/city-photoreal/reference-generated.png`; European/central-vista design history, not the active direction.
- Blender: `D:\Blender\blender.exe`, version 5.0.1, build hash a3db93c5b259. UE project declares 5.7.
- No AGENTS.md found in the project or ancestors, excluding dependency/generated caches.

## First group

Shopping centre: occupy the adjoining B01/B02 sites on the opposite side of the boulevard. The 44 m deep x 72 m long footprint uses UE metre X [-68,-24], Y [-62,10], with base Z=6.9. A four-level commercial volume, about 22-24 m above the pavement, stays lower than the prior 31.855/47.855 m towers. It can expose the neighboring skyline and gives the left foreground a deliberate horizontal silhouette. It is a design proposal, not a change to the map.

Commercial form: clipped near street corner, grounded masonry anchor volume, a recessed double-height main entrance, folded bronze entrance canopy, individual shopfronts, deep upper-level ceramic/stone openings, projecting cornice, a restrained upper dining terrace and enclosed rooftop service screen. Main circulation entrance is legible through geometry at approximately 12-14 m wide x 9 m high. Upper opaque facades dominate; glazing target about 35-45% of the principal visible elevation, about 65% at individual ground-floor shopfronts. Ratios are design targets to be checked on actual facade surface areas, not the ratio of all glass/backing meshes.

Adjacent building: rework only the B03 site in the independent scene: UE metre X [-48,-22], Y [-110,-76], base Z=6.9, height about 45 m. A warm brick/ceramic residential or hotel mass with pale stone corner piers, recessed grouped windows, balconies and a setback top provides a vertical counterpart. Glazing target 25-35% on main elevation; its floor rhythm and solid material language differ from the mall and existing office context.

Existing B07/right foreground and all other context are read-only imports for the proposed window view. In the isolated blend only, B01/B02/B03 are replaced with the sample; the original GLB and map are untouched. Mall street setback retains pedestrian space. Far wall and roof outline must be checked against B13 behind and B03/B04 farther along the avenue. Visibility conclusions remain provisional until the Blender review images.

## Scale and cameras

Source glTF metres: (x,y,z) maps to UE metres (x,z,y). Blender glTF import uses right-handed (x,-z,y), so Blender sample X [-68,-24], Y [-10,62], ground Z=6.9. UE cm camera [2600,4200,3700] becomes Blender metres [26,-42,37]; target UE cm [-2200,-11500,1900] becomes [-22,115,19]. The world-coordinate origin is retained for this first staging sample; export must not apply a second 100x conversion.

Window review: vertical FOV 54 degrees, Blender sensor fit vertical. The 1280x820 saved capture has horizontal FOV 76.994 degrees; the current 16:9 runtime has horizontal FOV 84.342 degrees. Deliver a fixed 16:9 sample view plus an architectural close view. The decorative frame remains outside the architecture.

## Deliverables and validation

Planned: `CityDesign_Mall01.blend`, separate architecture exports `.glb` and `.fbx`, `preview-window.png`, `preview-close.png`, `validation.json`, and this plan. Meshes remain editable; no random seed, scatter/city generator or Geometry Nodes city system. New architecture has applied positive scales, outward normals, named material partitions, meaningful UV0 and a separate lightmap UV1. Record face/triangle counts and world dimensions. Report open meshes and limitations rather than equating a material color render with final UE glass behavior.

CPU-only low-resolution Blender previews, one process, limited threads. No UE import, map placement, GPU render, deployment, shared script/material changes, Git commit or push. Notify source thread before any such integration step. Existing Git changes are preserved.
