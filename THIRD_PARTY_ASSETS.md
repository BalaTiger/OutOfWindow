# Third-party assets

## Poly Haven — Pine Sapling Small

- Source: https://polyhaven.com/a/pine_sapling_small
- Authors: Rico Cilliers (modeling), Rob Tuytel (photography)
- Files used: 1K glTF geometry and PBR texture set
- License: CC0 1.0 Universal
- Local path: `public/assets/polyhaven/pine_sapling_small/`
- Usage: high-detail real-time foreground vegetation in the forest preset
- Modification: runtime scaling, placement, shadows, environment-map intensity

## Poly Haven — Joburg Central Sunset

- Source: https://polyhaven.com/a/sunset_jhbcentral
- Authors: Dimitrios Savva (photography), Greg Zaal (processing)
- File used: 1K HDR environment map
- License: CC0 1.0 Universal
- Local path: `public/assets/polyhaven/hdri/sunset_jhbcentral_1k.hdr`
- Usage: image-based lighting and PBR reflections
- Modification: converted at runtime to a prefiltered environment map using Three.js PMREM

These assets are bundled locally. The application does not call the Poly Haven API at runtime.
