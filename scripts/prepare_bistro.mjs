import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';

const projectRoot = path.resolve(import.meta.dirname, '..');
const sourceRoot = path.join(projectRoot, '.runtime', 'bistro-source');
const bistroRoot = path.join(projectRoot, 'public', 'assets', 'orca', 'bistro');
const textureRoot = path.join(bistroRoot, 'textures');
const rawRoot = 'https://raw.githubusercontent.com/mmp/pbrt-v4-scenes/master/bistro';
const materialUrl = `${rawRoot}/materials.pbrt`;
const maxTextureSize = 1024;

await fs.mkdir(textureRoot, { recursive: true });
await fs.mkdir(sourceRoot, { recursive: true });

async function fetchBuffer(url, attempts = 4) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const response = await fetch(url, { headers: { 'user-agent': 'OutOfWindow-Demo' } });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return Buffer.from(await response.arrayBuffer());
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, attempt * 1200));
    }
  }
  throw lastError;
}

const materialText = (await fetchBuffer(materialUrl)).toString('utf8');
await fs.writeFile(path.join(sourceRoot, 'materials.pbrt'), materialText);

const textureDeclarations = new Map();
const texturePattern = /Texture\s+"([^"]+)"[\s\S]*?"string filename"\s*\[\s*"textures\/([^"]+\.png)"\s*\]/g;
for (const match of materialText.matchAll(texturePattern)) textureDeclarations.set(match[1], match[2]);

const materialMap = new Map();
const materialStarts = [...materialText.matchAll(/MakeNamedMaterial\s+"([^"]+)"/g)];
for (let i = 0; i < materialStarts.length; i++) {
  const start = materialStarts[i];
  const block = materialText.slice(start.index, materialStarts[i + 1]?.index ?? materialText.length);
  const reflectance = block.match(/"texture reflectance"\s+"([^"]+)"/)?.[1];
  const normal = block.match(/"string normalmap"\s+"textures\/([^"]+\.png)"/)?.[1];
  const baseColor = reflectance ? textureDeclarations.get(reflectance) : undefined;
  materialMap.set(start[1], { baseColor, normal });
}

const originalMtl = await fs.readFile(path.join(sourceRoot, 'exterior.mtl'), 'utf8');
const usedMaterials = [...originalMtl.matchAll(/^newmtl\s+(.+)$/gm)].map((match) => match[1].trim());
const requiredFiles = new Set();
for (const name of usedMaterials) {
  const entry = materialMap.get(name) ?? materialMap.get(`${name}.DoubleSided`);
  if (entry?.baseColor) requiredFiles.add(entry.baseColor);
  if (entry?.normal) requiredFiles.add(entry.normal);
}

const files = [...requiredFiles];
console.log(`Preparing ${files.length} PBR textures for ${usedMaterials.length} Bistro materials...`);
let cursor = 0;
let completed = 0;
const failures = [];

async function worker() {
  while (cursor < files.length) {
    const index = cursor++;
    const filename = files[index];
    const output = path.join(textureRoot, filename);
    try {
      const existing = await fs.stat(output).catch(() => null);
      if (!existing || existing.size < 1024) {
        const input = await fetchBuffer(`${rawRoot}/textures/${encodeURIComponent(filename)}`);
        await sharp(input)
          .resize({ width: maxTextureSize, height: maxTextureSize, fit: 'inside', withoutEnlargement: true })
          .png({ compressionLevel: 9, adaptiveFiltering: true })
          .toFile(output);
      } else {
        const metadata = await sharp(output).metadata();
        if ((metadata.width ?? 0) > maxTextureSize || (metadata.height ?? 0) > maxTextureSize) {
          const temporary = `${output}.resized`;
          await sharp(output)
            .resize({ width: maxTextureSize, height: maxTextureSize, fit: 'inside', withoutEnlargement: true })
            .png({ compressionLevel: 9, adaptiveFiltering: true })
            .toFile(temporary);
          await fs.rename(temporary, output);
        }
      }
    } catch (error) {
      failures.push(`${filename}: ${error.message}`);
    }
    completed += 1;
    if (completed % 10 === 0 || completed === files.length) console.log(`${completed}/${files.length} textures prepared`);
  }
}

await Promise.all(Array.from({ length: 6 }, () => worker()));
if (failures.length) throw new Error(`Texture preparation failed:\n${failures.join('\n')}`);

const blocks = originalMtl.split(/(?=^newmtl\s+)/gm);
const runtimeBlocks = blocks.map((block) => {
  const name = block.match(/^newmtl\s+(.+)$/m)?.[1].trim();
  if (!name) return block;
  const clean = block.split(/\r?\n/).filter((line) => !/^\s*map_/i.test(line)).join('\n').trimEnd();
  const entry = materialMap.get(name) ?? materialMap.get(`${name}.DoubleSided`);
  const maps = [];
  if (entry?.baseColor) maps.push(`\tmap_Kd textures/${entry.baseColor}`);
  if (entry?.normal) maps.push(`\tmap_bump textures/${entry.normal}`);
  return `${clean}\n${maps.join('\n')}\n\n`;
});
await fs.writeFile(path.join(sourceRoot, 'exterior.runtime.mtl'), runtimeBlocks.join(''));

const sourceObj = path.join(sourceRoot, 'exterior.obj');
const runtimeObj = path.join(sourceRoot, 'exterior.runtime.obj');
const sourceHandle = await fs.open(sourceObj, 'r');
const targetHandle = await fs.open(runtimeObj, 'w');
try {
  const stream = sourceHandle.createReadStream({ encoding: 'utf8' });
  let firstChunk = true;
  for await (let chunk of stream) {
    if (firstChunk) {
      chunk = chunk.replace(/mtllib\s+exterior\.mtl/i, 'mtllib exterior.runtime.mtl');
      firstChunk = false;
    }
    await targetHandle.write(chunk);
  }
} finally {
  await sourceHandle.close();
  await targetHandle.close();
}

await fs.writeFile(path.join(sourceRoot, 'runtime-material-map.json'), JSON.stringify(Object.fromEntries(materialMap), null, 2));
console.log(`Runtime OBJ and ${files.length} 1K PBR textures are ready.`);
