import assimpjs from 'assimpjs';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const [fbxPath, outputPath] = process.argv.slice(2);
if (!fbxPath || !outputPath) {
  throw new Error('Usage: node scripts/convert-fbx-with-assimp.mjs <input.fbx> <output.glb>');
}

const ajs = await assimpjs();
const root = path.dirname(fbxPath);
const textureRoot = path.join(root, 'Textures');
const textureNames = (await readdir(textureRoot)).filter((name) => name.toLowerCase().endsWith('.png'));
const textureFiles = new Map();
for (let index = 0; index < textureNames.length; index += 1) {
  const name = textureNames[index];
  const content = new Uint8Array(await readFile(path.join(textureRoot, name)));
  textureFiles.set(name.toLowerCase(), content);
  textureFiles.set(`textures/${name}`.toLowerCase(), content);
  if ((index + 1) % 25 === 0) process.stdout.write(`\rtextures ${index + 1}/${textureNames.length}`);
}
const fbxName = path.basename(fbxPath);
const fbxContent = new Uint8Array(await readFile(fbxPath));

process.stdout.write('\nconverting FBX to glb2\n');
const result = process.env.ASSIMP_GEOMETRY_ONLY === '1' ? (() => {
  const fileList = new ajs.FileList();
  fileList.AddFile(fbxName, fbxContent);
  return ajs.ConvertFileList(fileList, 'glb2');
})() : ajs.ConvertFile(
  fbxName,
  'glb2',
  fbxContent,
  (fileName) => textureFiles.has(fileName.replaceAll('\\', '/').toLowerCase()) || textureFiles.has(path.basename(fileName).toLowerCase()),
  (fileName) => textureFiles.get(fileName.replaceAll('\\', '/').toLowerCase()) || textureFiles.get(path.basename(fileName).toLowerCase()),
);
if (!result.IsSuccess() || result.FileCount() === 0) {
  throw new Error(result.GetErrorCode?.() || 'Assimp conversion failed');
}

let written = false;
for (let index = 0; index < result.FileCount(); index += 1) {
  const file = result.GetFile(index);
  const name = file.GetPath?.() || file.GetName?.() || `output-${index}`;
  if (!name.toLowerCase().endsWith('.glb')) continue;
  await writeFile(outputPath, Buffer.from(file.GetContent()));
  written = true;
  process.stdout.write(`written ${outputPath}\n`);
}
if (!written) throw new Error('Assimp returned no GLB file');
