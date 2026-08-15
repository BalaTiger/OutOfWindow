import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import sharp from 'sharp';

const [input, output, sizeArg = '1024', mode = 'resize'] = process.argv.slice(2);
if (!input || !output) {
  throw new Error('Usage: node scripts/downsize-gltf-textures.mjs <input> <output> [max-size] [resize|relight]');
}

const maxSize = Number(sizeArg);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const document = await io.read(input);
const textures = document.getRoot().listTextures();

for (let index = 0; index < textures.length; index += 1) {
  const texture = textures[index];
  const image = texture.getImage();
  if (!image) continue;
  const pipeline = sharp(image, { failOn: 'none' });
  const metadata = await pipeline.metadata();
  const shouldResize = Math.max(metadata.width ?? 0, metadata.height ?? 0) > maxSize;
  if (!shouldResize && mode !== 'relight') continue;
  let processed = pipeline;
  if (mode === 'relight') {
    // Photogrammetry albedo contains capture-time illumination. Compress its
    // contrast so the live sun, weather and environment map can dominate.
    processed = processed.linear(.78, 28).modulate({ saturation: .88 });
  }
  const resized = await processed
    .resize({ width: maxSize, height: maxSize, fit: 'inside', withoutEnlargement: true })
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toBuffer();
  texture.setImage(resized).setMimeType('image/png');
  process.stdout.write(`\rtextures ${index + 1}/${textures.length}`);
}

await io.write(output, document);
process.stdout.write(`\nwritten ${output}\n`);
