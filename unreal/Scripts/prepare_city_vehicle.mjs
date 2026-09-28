// Original distant-traffic sedan. Run: node unreal/Scripts/prepare_city_vehicle.mjs
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import * as T from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// GLTFExporter only needs asynchronous Blob reads for this texture-free model.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) {
    blob.arrayBuffer().then(result => {
      this.result = result;
      this.onloadend?.({ target: this });
    });
  }
};

const output = new URL('../Art/City/', import.meta.url);
const materials = [
  new T.MeshStandardMaterial({ name: 'Sedan_Paint', color: 0xb8bdc1, roughness: .31, metalness: .58 }),
  new T.MeshStandardMaterial({ name: 'Sedan_Glass', color: 0x24343f, roughness: .22, metalness: .32 }),
  new T.MeshStandardMaterial({ name: 'Sedan_TireTrim', color: 0x161a1d, roughness: .82 }),
  new T.MeshStandardMaterial({ name: 'Sedan_Alloy', color: 0x899297, roughness: .36, metalness: .8 }),
  new T.MeshStandardMaterial({ name: 'Sedan_Headlamps', color: 0xeee6cf, emissive: 0xffeac0, emissiveIntensity: .35, roughness: .28 }),
  new T.MeshStandardMaterial({ name: 'Sedan_Taillamps', color: 0x9b1816, emissive: 0xff241c, emissiveIntensity: .25, roughness: .35 }),
];
const parts = materials.map(() => []);
function part(geometry, material, position = [0, 0, 0], rotation = [0, 0, 0]) {
  geometry.applyMatrix4(new T.Matrix4().compose(
    new T.Vector3(...position), new T.Quaternion().setFromEuler(new T.Euler(...rotation)), new T.Vector3(1, 1, 1)));
  geometry.deleteAttribute('uv');
  const unindexed = geometry.index ? geometry.toNonIndexed() : geometry;
  unindexed.clearGroups();
  parts[material].push(unindexed);
}
function box(size, material, position) { part(new T.BoxGeometry(...size), material, position); }
function face(vertices, material) {
  const geometry = new T.BufferGeometry();
  geometry.setAttribute('position', new T.Float32BufferAttribute(vertices.flat(), 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.computeVertexNormals();
  part(geometry, material);
}

// Extrusion follows the side profile, including genuine wheel-arch openings.
// Shape x becomes vehicle z; the extrusion's z becomes vehicle x.
const silhouette = new T.Shape();
silhouette.moveTo(-2.10, .34);
for (const [z, y] of [[-2.10, .68], [-1.94, .82], [-1.35, .94], [.89, .94], [1.82, .83], [2.10, .68], [2.10, .34]]) {
  silhouette.lineTo(z, y);
}
for (const center of [1.31, -1.31]) {
  silhouette.lineTo(center + .375, .33);
  for (let step = 1; step <= 8; step++) {
    const angle = Math.PI * step / 8;
    silhouette.lineTo(center + .375 * Math.cos(angle), .33 + .375 * Math.sin(angle));
  }
}
silhouette.lineTo(-2.10, .34);
silhouette.closePath();
const body = new T.ExtrudeGeometry(silhouette, { depth: 1.68, steps: 1, bevelEnabled: true,
  bevelThickness: .03, bevelSize: .025, bevelSegments: 1, curveSegments: 1 });
body.translate(0, 0, -.84);
part(body, 0, [0, 0, 0], [0, -Math.PI / 2, 0]);

// Narrower roof and raked front/rear glass supply the recognizable sedan shape.
const LF = [-.80, .94, .93], RF = [.80, .94, .93];
const LB = [-.80, .94, -1.36], RB = [.80, .94, -1.36];
const lF = [-.66, 1.41, .31], rF = [.66, 1.41, .31];
const lB = [-.66, 1.41, -.72], rB = [.66, 1.41, -.72];
face([LF, RF, rF, lF], 0);
face([RB, LB, lB, rB], 0);
face([RF, RB, rB, rF], 0);
face([LB, LF, lF, lB], 0);
face([lF, rF, rB, lB], 0);
// Slight crown on the painted roof catches a broad highlight.
face([lF, [-.57, 1.45, .24], [-.57, 1.45, -.65], lB], 0);
face([rB, [.57, 1.45, -.65], [.57, 1.45, .24], rF], 0);
face([[-.57, 1.45, .24], [.57, 1.45, .24], [.57, 1.45, -.65], [-.57, 1.45, -.65]], 0);
face([lF, rF, [.57, 1.45, .24], [-.57, 1.45, .24]], 0);
face([rB, lB, [-.57, 1.45, -.65], [.57, 1.45, -.65]], 0);

face([[-.738, 1.003, .856], [.738, 1.003, .856], [.607, 1.366, .379], [-.607, 1.366, .379]], 1);
face([[.738, 1.003, -1.282], [-.738, 1.003, -1.282], [-.607, 1.366, -.787], [.607, 1.366, -.787]], 1);
for (const side of [-1, 1]) {
  const point = (y, z) => [side * (.80 - (y - .94) / .47 * .14 + .004), y, z];
  const frontWindow = [point(1.00, .785), point(1.00, -.20), point(1.365, -.20), point(1.365, .27)];
  const rearWindow = [point(1.00, -.29), point(1.00, -1.23), point(1.365, -.67), point(1.365, -.29)];
  face(side === 1 ? frontWindow : frontWindow.reverse(), 1);
  face(side === 1 ? rearWindow : rearWindow.reverse(), 1);
  box([.012, .021, .15], 3, [side * .871, .84, -.06]);
  box([.012, .021, .15], 3, [side * .871, .84, -.98]);
  // Thin sill and trim stay legible at the intended elevated camera distance.
  box([.015, .05, 1.76], 2, [side * .866, .335, 0]);
  for (const z of [-1.31, 1.31]) {
    part(new T.CylinderGeometry(.33, .33, .16, 12), 2, [side * .82, .33, z], [0, 0, Math.PI / 2]);
    part(new T.CylinderGeometry(.21, .21, .013, 12), 3, [side * .89, .33, z], [0, 0, Math.PI / 2]);
    part(new T.CylinderGeometry(.07, .07, .015, 8), 2, [side * .894, .33, z], [0, 0, Math.PI / 2]);
  }
  box([.42, .105, .04], 4, [side * .555, .67, 2.13]);
  box([.42, .11, .04], 5, [side * .555, .675, -2.13]);
}
box([.62, .10, .025], 2, [0, .525, 2.1325]);
box([.43, .09, .028], 3, [0, .415, 2.136]);
box([.43, .09, .028], 3, [0, .475, -2.136]);
box([1.46, .055, .025], 2, [0, .37, -2.1225]);

// One mesh and six primitives: every car can reuse the same native static mesh.
const geometry = mergeGeometries(parts.map(group => mergeGeometries(group)), true);
geometry.computeBoundingBox();
const size = geometry.boundingBox.getSize(new T.Vector3());
const triangles = geometry.attributes.position.count / 3;
assert(triangles <= 1500, `Sedan triangle budget exceeded: ${triangles}`);
assert(Math.abs(size.x - 1.803) < .005 && Math.abs(size.y - 1.45) < .001 && Math.abs(size.z - 4.30) < .001);
assert(Math.abs(geometry.boundingBox.min.y) < .00001, 'Tires must contact y = 0');
const car = new T.Mesh(geometry, materials);
car.name = 'TrafficSedan';
car.userData = { originalAsset: true, frontAxis: '+Z', upAxis: '+Y', metresPerUnit: 1 };
const glb = await new GLTFExporter().parseAsync(car, { binary: true });
await mkdir(output, { recursive: true });
await writeFile(new URL('traffic-sedan.glb', output), Buffer.from(glb));
const metadata = {
  name: 'Original City Traffic Sedan', file: 'traffic-sedan.glb', generator: 'unreal/Scripts/prepare_city_vehicle.mjs',
  source: 'Original procedural geometry authored for OutOfWindow; no external models or textures.',
  license: 'CC0-1.0', licenseUrl: 'https://creativecommons.org/publicdomain/zero/1.0/',
  axes: { front: '+Z', up: '+Y', width: 'X', units: 'metres', groundY: 0,
    unrealImport: 'glTF (x, y, z) maps to UE (x, z, y); vehicle front is UE +Y before actor rotation.' },
  dimensionsMetres: { width: +size.x.toFixed(4), height: +size.y.toFixed(4), length: +size.z.toFixed(4) },
  triangles, meshCount: 1, materialSlots: materials.map((material, index) => ({ index, name: material.name })),
  bytes: glb.byteLength, intendedView: 'Moving road traffic at elevated city camera distances; opaque glazing and static wheels.',
};
await writeFile(new URL('traffic-sedan.json', output), JSON.stringify(metadata, null, 2) + '\n');
console.log(JSON.stringify({ ...metadata, path: fileURLToPath(new URL('traffic-sedan.glb', output)) }, null, 2));
