import { readFile, writeFile } from 'node:fs/promises';

const [input, output] = process.argv.slice(2);
if (!input || !output) {
  throw new Error('Usage: node scripts/patch-fbx-texture-extension.mjs <input.fbx> <output.fbx>');
}

const data = await readFile(input);
const from = Buffer.from('.dds');
const to = Buffer.from('.png');
let replacements = 0;

for (let offset = 0; offset <= data.length - from.length; offset += 1) {
  if (!data.subarray(offset, offset + from.length).equals(from)) continue;
  to.copy(data, offset);
  replacements += 1;
  offset += from.length - 1;
}

await writeFile(output, data);
process.stdout.write(`patched ${replacements} texture references\n`);
