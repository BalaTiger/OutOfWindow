# Modern City facade sources

The current facade work is described in [city-facade.md](../../../Migration/city-facade.md). The final architecture has 98,168 triangles in 52 meshes / 192 material sections and 54 buildings (16 nearby, 18 skyline and 20 context). Six context meshes comprise four original building batches, a junction/plaza, and one batch of two added neighboring buildings outside the fixed camera's view. These two ordinary opaque buildings supply actual geometry for glass reflections. B01 and B07 receive modeled facade refinements and retain 630 complete hero panes; the two shared stone materials reuse the following texture set across existing stone surfaces.

## Travertine001

- Provider and source: [ambientCG Travertine001](https://ambientcg.com/view?id=Travertine001).
- License: [CC0 1.0 Universal](https://docs.ambientcg.com/license/).
- Download: [original 2K JPG archive](https://ambientcg.com/get?file=Travertine001_2K-JPG.zip), retrieved on 2026-09-24.
- Files: `Travertine001_2K-JPG_Color.jpg`, `Travertine001_2K-JPG_Roughness.jpg`, and `Travertine001_2K-JPG_NormalDX.jpg`.
- All three are unmodified 2048 × 2048 source images. The material is procedural, not photogrammetry. The source documents a repeating area of approximately 1.2 × 1.2 m.
- [source.json](source.json) records source URLs, license, physical scale and archive/image SHA256 hashes. The original ZIP remains in `.runtime/ue-city-facade/`; only the three required maps are used by the City stone materials.

## Unused office atlas

`office-atlas-v1.png` is an optional 2 × 2 office-interior image generated with the built-in image tool on 2026-09-24. It is **not connected to the current City materials or imported for this revision**. The current opaque facade material does not sample interior imagery.

This is an AI-generated image, not photography, a measured PBR surface, or interior geometry. The [full prompt and provenance](office-atlas-prompt.json) are retained for any future use. Its presence in the source folder does not demonstrate an implemented or validated interior effect.
