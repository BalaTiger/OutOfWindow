import fs from 'node:fs/promises';
import path from 'node:path';
import * as THREE from 'three';
import { SCENE_VIEWS } from '../src/scene-pack.js';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { prune, unpartition } from '@gltf-transform/functions';

const root = path.resolve('public/assets/orca/bistro');
const source = JSON.parse(await fs.readFile(path.join(root, 'bistro-exterior.gltf'), 'utf8'));
const packed = await fs.readFile(path.join(root, 'bistro-exterior-lod-safe-768.glb'));
const target = JSON.parse(packed.subarray(20, 20 + packed.readUInt32LE(12)));
const sourceNodeMatrix = node => node.matrix ? new THREE.Matrix4().fromArray(node.matrix) : new THREE.Matrix4().compose(
  new THREE.Vector3(...(node.translation || [0, 0, 0])), new THREE.Quaternion(...(node.rotation || [0, 0, 0, 1])), new THREE.Vector3(...(node.scale || [1, 1, 1])));
function bounds(document, node) {
  const box = new THREE.Box3();
  for (const primitive of document.meshes[node.mesh].primitives) {
    const accessor = document.accessors[primitive.attributes.POSITION];
    box.union(new THREE.Box3(new THREE.Vector3(...accessor.min), new THREE.Vector3(...accessor.max)));
  }
  return box.applyMatrix4(sourceNodeMatrix(node));
}
const whole = new THREE.Box3();
source.nodes.filter(node => node.mesh !== undefined).forEach(node => whole.union(bounds(source, node)));
const size = whole.getSize(new THREE.Vector3()), scale = 190 / Math.max(size.x, size.y, size.z);
const placement = new THREE.Matrix4().compose(new THREE.Vector3(-10, -1 - whole.min.y * scale, -205), new THREE.Quaternion(), new THREE.Vector3(scale, scale, scale));
const view = SCENE_VIEWS.alley, camera = new THREE.PerspectiveCamera(view.fov, 1.8, .2, 520);
camera.position.fromArray(view.position); camera.lookAt(new THREE.Vector3(...view.target)); camera.updateMatrixWorld();
const frustum = new THREE.Frustum().setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse));
const triangleCount = (document, node) => document.meshes[node.mesh].primitives.reduce((sum, p) => sum + document.accessors[p.indices ?? p.attributes.POSITION].count / 3, 0);
const targetByName = new Map(target.nodes.map(node => [node.name, node]));
const selected = source.nodes.filter(node => {
  if (node.mesh === undefined || !/building|balcony/i.test(node.name)) return false;
  const box = bounds(source, node).applyMatrix4(placement);
  const extent = box.getSize(new THREE.Vector3());
  const architectural = source.meshes[node.mesh].primitives.some(p => /wood|doors|details|trim|concrete|brick|plaster|ornament/i.test(source.materials[p.material]?.name));
  const previous = targetByName.get(node.name);
  return previous && architectural && box.distanceToPoint(camera.position) < 70 && frustum.intersectsBox(box)
    && triangleCount(source, node) > triangleCount(target, previous);
});
const report = selected.map(node => ({ name: node.name, before: triangleCount(target, targetByName.get(node.name)), after: triangleCount(source, node) }));
console.log(JSON.stringify({ meshes: report.length, trianglesBefore: report.reduce((s, n) => s + n.before, 0), trianglesAfter: report.reduce((s, n) => s + n.after, 0), sample: report.slice(0, 12) }, null, 2));
if (process.argv.includes('--inspect')) process.exit(0);

const originalBuffer = await fs.readFile(path.join(root, source.buffers[0].uri));
const binaryOffset = 20 + packed.readUInt32LE(12);
const pieces = [packed.subarray(binaryOffset + 8, binaryOffset + 8 + packed.readUInt32LE(binaryOffset))];
let byteLength = pieces[0].length;
const viewMap = new Map(), accessorMap = new Map();
const materialMap = new Map(target.materials.map((m, i) => [m.name, i]));
function resolveMaterial(name) {
  if (materialMap.has(name)) return materialMap.get(name);
  const normalize = value => value.replace(/\.DoubleSided|_BLENDSHADER|\d+/gi, '').replace(/_+$/g, '');
  const stem = normalize(name);
  const match = [...materialMap.keys()].find(candidate => normalize(candidate) === stem);
  if (match !== undefined) return materialMap.get(match);
  // The safe conversion intentionally removes a few tiny dark-detail
  // materials. Reuse a neutral masonry material rather than dropping the
  // original high-resolution primitive and creating a hole in the frame.
  if (/details_dark|building_details|focus_ornament/i.test(name)) return materialMap.get('MASTER_Concrete') ?? 0;
  return undefined;
}
function copyAccessor(index) {
  if (accessorMap.has(index)) return accessorMap.get(index);
  const accessor = structuredClone(source.accessors[index]);
  if (accessor.sparse) throw new Error('Sparse source accessors require a separate conversion.');
  if (!viewMap.has(accessor.bufferView)) {
    const original = source.bufferViews[accessor.bufferView];
    const padding = (4 - byteLength % 4) % 4;
    if (padding) { pieces.push(Buffer.alloc(padding)); byteLength += padding; }
    const bytes = originalBuffer.subarray(original.byteOffset || 0, (original.byteOffset || 0) + original.byteLength);
    viewMap.set(accessor.bufferView, target.bufferViews.length);
    target.bufferViews.push({ ...original, buffer: 0, byteOffset: byteLength });
    pieces.push(bytes); byteLength += bytes.length;
  }
  accessor.bufferView = viewMap.get(accessor.bufferView);
  const next = target.accessors.length; target.accessors.push(accessor); accessorMap.set(index, next); return next;
}
for (const node of selected) {
  const previous = targetByName.get(node.name);
  const mesh = structuredClone(source.meshes[node.mesh]);
  for (const primitive of mesh.primitives) {
    Object.keys(primitive.attributes).forEach(key => { primitive.attributes[key] = copyAccessor(primitive.attributes[key]); });
    if (primitive.indices !== undefined) primitive.indices = copyAccessor(primitive.indices);
    const sourceMaterialName = source.materials[primitive.material].name;
    primitive.material = resolveMaterial(sourceMaterialName);
    if (primitive.material === undefined) throw new Error(`Missing target material: ${sourceMaterialName}`);
  }
  previous.mesh = target.meshes.length; target.meshes.push(mesh);
  for (const field of ['translation', 'rotation', 'scale', 'matrix']) {
    if (node[field]) previous[field] = node[field]; else delete previous[field];
  }
}
target.buffers[0].byteLength = byteLength;
target.asset.extras = { ...target.asset.extras, nearGeometry: 'original ORCA architectural meshes within the alley view frustum and 70m of the fixed camera' };
const json = Buffer.from(JSON.stringify(target));
const jsonPadded = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)]);
const binary = Buffer.concat([...pieces, Buffer.alloc((4 - byteLength % 4) % 4)]);
const header = Buffer.alloc(20); header.write('glTF'); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + jsonPadded.length + binary.length, 8);
header.writeUInt32LE(jsonPadded.length, 12); header.write('JSON', 16);
const binaryHeader = Buffer.alloc(8); binaryHeader.writeUInt32LE(binary.length); binaryHeader.write('BIN\0', 4);
const outputPath = path.join(root, 'bistro-exterior-near-768.glb');
const temporaryPath = `${outputPath}.raw`;
await fs.writeFile(temporaryPath, Buffer.concat([header, jsonPadded, binaryHeader, binary]));
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const optimized = await io.read(temporaryPath);
prune(optimized);
unpartition(optimized);
await io.write(outputPath, optimized);
await fs.rm(temporaryPath);
await fs.mkdir(path.resolve('docs/alley-photoreal'), { recursive: true });
await fs.writeFile(path.resolve('docs/alley-photoreal/near-geometry.json'), JSON.stringify({ source: 'bistro-exterior.gltf', texturePackage: 'bistro-exterior-near-768.glb', meshes: report }, null, 2));



