import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';

const root = path.resolve('public/assets/orca/bistro');
const output = path.join(root, 'pbr');
const materialPattern = /^(Pavement_|MASTER_(Concrete|Brick)|Concrete\d?|Concrete_Striped|Plaster|Balcony_Concrete)/i;
const files = await fs.readdir(root);
await fs.mkdir(output, { recursive: true });

let generated = 0;
for (const file of files.filter(name => name.endsWith('_BaseColor.png'))) {
  const material = file.slice(0, -'_BaseColor.png'.length);
  if (!materialPattern.test(material)) continue;
  const source = path.join(root, file);
  const image = sharp(source).resize({ width: 512, height: 512, fit: 'cover' }).removeAlpha().grayscale().normalize();
  await Promise.all([
    image.clone().blur(0.65).linear(.82, 28).png({ compressionLevel: 9 }).toFile(path.join(output, `${material}_Roughness.png`)),
    image.clone().blur(1.8).linear(.72, 42).png({ compressionLevel: 9 }).toFile(path.join(output, `${material}_AO.png`)),
    image.clone().sharpen({ sigma: 1, m1: 0.8, m2: 1.2 }).linear(.9, 13).png({ compressionLevel: 9 }).toFile(path.join(output, `${material}_Height.png`)),
  ]);
  generated++;
}
console.log(`Generated derived Bistro PBR channels for ${generated} materials in ${output}`);
