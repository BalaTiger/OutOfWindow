// Independent raised sidewalks. Run: node unreal/Scripts/prepare_city_sidewalk.mjs
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import * as T from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

globalThis.FileReader = class {
  readAsArrayBuffer(blob) { blob.arrayBuffer().then(result => { this.result = result; this.onloadend?.({ target: this }); }); }
};
const output = new URL('../Art/City/', import.meta.url);
const sidewalkTop = 7.04, bottomY = 6.84, zStart = -399.5, zEnd = 36;
const specs = [
  ['CitySidewalk_Paving', 0x858982, .84], ['CitySidewalk_Curbs', 0x8b8f86, .79],
  ['CitySidewalk_Base', 0x50544e, .96], ['CitySidewalk_Soil', 0x332d24, 1],
  ['CitySidewalk_Tactile', 0xa18b53, .87], ['CitySidewalk_Planting', 0x3b5540, .95],
];
const materials = specs.map(([name, color, roughness], index) => new T.MeshStandardMaterial({ name, color, roughness, vertexColors: index === 0 }));
const pavingPalette = { main: '#777871', service: '#565c59', warmAccent: '#7a756c', coolAccent: '#727773' };
const pavingBase = new T.Color(specs[0][1]).toArray();
const paletteTints = Object.fromEntries(Object.entries(pavingPalette).map(([name, hex]) =>
  [name, new T.Color(hex).toArray().map((channel, index) => channel / pavingBase[index])]));
const colorCounts = { main: 0, service: 0, warmAccent: 0, coolAccent: 0 };
function pavingTint(tile, walk) {
  const x = (tile.x0 + tile.x1) / 2, treeX = walk.side === 'west' ? -18.2 : 18.2;
  let seed = Math.imul(Math.round(tile.x0 * 1000) ^ 0x9e3779b9, 0x85ebca6b) ^ Math.round(tile.z0 * 1000);
  seed = Math.imul(seed ^ (seed >>> 16), 0x7feb352d); seed = (seed ^ (seed >>> 15)) >>> 0;
  const service = Math.abs(x - treeX) <= 1.50 || Math.abs(x - walk.streetEdgeX) < .95;
  const choice = seed % 100, name = service ? 'service' : choice < 8 ? 'warmAccent' : choice < 15 ? 'coolAccent' : 'main';
  const variation = 1 + ((seed >>> 8) % 101 - 50) * .0005;
  colorCounts[name]++;
  // One tint belongs to the original whole tile, including every piece left by
  // tree pits and post clearances. Variation is only +/-2.5% in linear light.
  return paletteTints[name].map(channel => channel * variation);
}
const parts = specs.map(() => []), counts = { pavingBlocks: 0, curbStones: 0, baseSections: 0, planterRimStones: 0,
  plantingClumps: 0, tactileDomes: 0 };
const rect = (x0, x1, z0, z1) => ({ x0, x1, z0, z1 });
const walks = [
  { side: 'west', x0: -21.35, x1: -14.85, streetEdgeX: -14.85, inward: -1, lowY: 6.90 },
  { side: 'east', x0: 11.95, x1: 21.35, streetEdgeX: 11.95, inward: 1, lowY: 6.89 },
];
const deckY = (_x, z) => sidewalkTop - .121 * T.MathUtils.clamp((-395.1 - z) / 4.4, 0, 1);
const baseTop = (x, z) => deckY(x, z) - .05;
const treePits = walks.flatMap(walk => Array.from({ length: 14 }, (_, index) => {
  const x = walk.side === 'west' ? -18.2 : 18.2, z = 14 - index * 23;
  return { id: `${walk.side}_${index}`, side: walk.side, center: [x, 6.95, z], size: [2.4, 2.4],
    soilY: 6.95, rimTopY: 7.20, rimOuterSize: [2.7, 2.7], rect: rect(x - 1.2, x + 1.2, z - 1.2, z + 1.2) };
}));
const ramps = walks.flatMap(walk => [-32.88, -131.28].map((z, index) => {
  const innerX = walk.streetEdgeX + walk.inward * 1.6;
  return { id: `${walk.side}_${index}`, side: walk.side, centerZ: z,
    streetEdgeX: walk.streetEdgeX, inward: walk.inward, innerX, lowY: walk.lowY, highY: sidewalkTop,
    rect: rect(Math.min(innerX, walk.streetEdgeX), Math.max(innerX, walk.streetEdgeX), z - 1.5, z + 1.5) };
}));
// Existing 16 cm canopy columns require local holes, not removal of the overhead canopy footprint.
const entrances = [
  ['B01', -20.35, [.05, 5.55]], ['B03', -20.35, [-88.75, -83.25]],
  ['B05', -20.35, [-193.55, -188.05]], ['B07', 21.35, [-4.75, .75]],
  ['B09', 19.85, [-95.35, -89.85]], ['B11', 20.85, [-203.95, -198.45]],
].flatMap(([building, x, zs]) => zs.map((z, index) => ({ id: `${building}_${index}`, building,
  center: [x, sidewalkTop, z], rect: rect(x - .11, x + .11, z - .11, z + .11) })));

function subtract(source, hole) {
  const x0 = Math.max(source.x0, hole.x0), x1 = Math.min(source.x1, hole.x1);
  const z0 = Math.max(source.z0, hole.z0), z1 = Math.min(source.z1, hole.z1);
  if (x0 >= x1 || z0 >= z1) return [source];
  return [rect(source.x0, x0, source.z0, source.z1), rect(x1, source.x1, source.z0, source.z1),
    rect(x0, x1, source.z0, z0), rect(x0, x1, z1, source.z1)]
    .filter(piece => piece.x1 - piece.x0 > .00001 && piece.z1 - piece.z0 > .00001);
}
function cut(source, holes) { return holes.reduce((pieces, hole) => pieces.flatMap(piece => subtract(piece, hole)), [source]); }
function add(geometry, material, tint = [1, 1, 1]) {
  const flat = geometry.index ? geometry.toNonIndexed() : geometry;
  assert(material === 0 || tint.every(channel => channel === 1), 'Only paving uses vertex tint');
  const colors = new Float32Array(flat.attributes.position.count * 3);
  for (let vertex = 0; vertex < flat.attributes.position.count; vertex++) colors.set(tint, vertex * 3);
  flat.setAttribute('color', new T.BufferAttribute(colors, 3));
  flat.clearGroups(); assert(flat.attributes.uv, 'Every source mesh needs UV0'); parts[material].push(flat);
}

// A real closed block, optionally with a small top chamfer. UV0 is measured in
// metres on each face; each rectangle can also follow a sloped top/bottom surface.
function block(r, top, bottom, material, bevel = 0, tint = [1, 1, 1]) {
  if (r.x1 - r.x0 < .012 || r.z1 - r.z0 < .012) return false;
  const topAt = typeof top === 'number' ? () => top : top;
  const bottomAt = typeof bottom === 'number' ? () => bottom : bottom;
  const b = Math.min(bevel, (r.x1 - r.x0) / 5, (r.z1 - r.z0) / 5);
  const xz = [[r.x0, r.z0], [r.x0, r.z1], [r.x1, r.z1], [r.x1, r.z0]];
  const low = xz.map(([x, z]) => [x, bottomAt(x, z), z]);
  const edge = xz.map(([x, z]) => [x, topAt(x, z) - b, z]);
  const inset = [[r.x0 + b, r.z0 + b], [r.x0 + b, r.z1 - b], [r.x1 - b, r.z1 - b], [r.x1 - b, r.z0 + b]]
    .map(([x, z]) => [x, topAt(x, z), z]);
  assert(low.every((v, i) => v[1] < edge[i][1] - .001), 'Block has no positive thickness');
  const positions = [], normals = [], uv = [];
  function quad(points) {
    for (const [a, b, c] of [[0, 1, 2], [0, 2, 3]]) {
      const n = new T.Vector3().subVectors(new T.Vector3(...points[b]), new T.Vector3(...points[a]))
        .cross(new T.Vector3().subVectors(new T.Vector3(...points[c]), new T.Vector3(...points[a]))).normalize();
      for (const index of [a, b, c]) {
        const v = points[index]; positions.push(...v); normals.push(n.x, n.y, n.z);
        uv.push(...(Math.abs(n.y) > .7 ? [v[0], v[2]] : Math.abs(n.x) > .7 ? [v[2], v[1]] : [v[0], v[1]]));
      }
    }
  }
  quad([...low].reverse());
  for (let i = 0; i < 4; i++) {
    const j = (i + 1) % 4; quad([low[i], low[j], edge[j], edge[i]]);
    if (b > 0) quad([edge[i], edge[j], inset[j], inset[i]]);
  }
  quad(inset);
  const geometry = new T.BufferGeometry();
  geometry.setAttribute('position', new T.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('normal', new T.Float32BufferAttribute(normals, 3));
  geometry.setAttribute('uv', new T.Float32BufferAttribute(uv, 2));
  add(geometry, material, tint); return true;
}

for (const walk of walks) {
  const holes = [...treePits.filter(p => p.side === walk.side).map(p => p.rect),
    ...ramps.filter(r => r.side === walk.side).map(r => r.rect), ...entrances.map(e => e.rect)];
  // Split the base at the slope break so a long slab cannot interpolate the
  // final junction descent underneath otherwise level pavers.
  for (const [start, end] of [[zStart, -395.1], [-395.1, zEnd]]) {
    for (const piece of cut(rect(walk.x0, walk.x1, start, end), holes)) {
      if (block(piece, baseTop, bottomY, 2)) counts.baseSections++;
    }
  }
  const pavingX0 = walk.inward === 1 ? walk.x0 + .22 : walk.x0;
  const pavingX1 = walk.inward === -1 ? walk.x1 - .22 : walk.x1;
  for (const [z0, z1, width, length, bevel] of [[-110, 36, .6, 1.2, .006], [-395.1, -110, 1.2, 2.4, .002], [zStart, -395.1, 1.2, 1.1, .002]]) {
    for (let z = z0; z < z1 - .001; z += length) for (let x = pavingX0; x < pavingX1 - .001; x += width) {
      const tile = rect(x, Math.min(x + width, pavingX1), z, Math.min(z + length, z1));
      const tint = pavingTint(tile, walk);
      for (const piece of cut(tile, holes)) {
        const joint = .004;
        const inset = rect(piece.x0 + joint, piece.x1 - joint, piece.z0 + joint, piece.z1 - joint);
        if (block(inset, deckY, (x, z) => deckY(x, z) - .05, 0, bevel, tint)) counts.pavingBlocks++;
      }
    }
  }
  const curbX0 = Math.min(walk.streetEdgeX, walk.streetEdgeX + walk.inward * .22);
  const curbX1 = Math.max(walk.streetEdgeX, walk.streetEdgeX + walk.inward * .22);
  for (let z = zStart; z < zEnd - .001; z += 1.2) {
    for (const piece of cut(rect(curbX0, curbX1, z + .003, Math.min(z + 1.197, zEnd)), ramps.filter(r => r.side === walk.side).map(r => r.rect))) {
      if (block(piece, deckY, bottomY, 1, .012)) counts.curbStones++;
    }
  }
}

function rampY(ramp, x, z) {
  const inward = T.MathUtils.clamp((x - ramp.streetEdgeX) * ramp.inward / 1.6, 0, 1);
  const across = T.MathUtils.clamp((1.5 - Math.abs(z - ramp.centerZ)) / .45, 0, 1);
  return ramp.highY - (ramp.highY - ramp.lowY) * (1 - inward) * across;
}
for (const ramp of ramps) {
  const zCuts = [ramp.centerZ - 1.5, ramp.centerZ - 1.05, ramp.centerZ + 1.05, ramp.centerZ + 1.5];
  for (let band = 0; band < 3; band++) {
    // Flared sides keep the outside boundary at deck level; the centre has a 9% cross-fall.
    block(rect(ramp.rect.x0, ramp.rect.x1, zCuts[band], zCuts[band + 1]),
      (x, z) => rampY(ramp, x, z), bottomY, 0, 0, paletteTints.main);
  }
  const xA = ramp.streetEdgeX + ramp.inward * .2, xB = ramp.streetEdgeX + ramp.inward * .8;
  const tactile = rect(Math.min(xA, xB), Math.max(xA, xB), ramp.centerZ - 1.035, ramp.centerZ + 1.035);
  block(tactile, (x, z) => rampY(ramp, x, z) + .012, (x, z) => rampY(ramp, x, z) + .002, 4, .002);
  for (let x = tactile.x0 + .045; x < tactile.x1 - .02; x += .09) for (let z = tactile.z0 + .045; z < tactile.z1 - .02; z += .09) {
    const dome = new T.ConeGeometry(.018, .006, 6);
    dome.translate(x, rampY(ramp, x, z) + .015, z); add(dome, 4); counts.tactileDomes++;
  }
}

for (const pit of treePits) {
  const [x, , z] = pit.center;
  block(pit.rect, 6.95, 6.89, 3);
  // The 2.4 m root opening is not narrowed by the raised 15 cm planter border.
  const borders = [rect(x - 1.35, x - 1.2, z - 1.35, z + 1.35), rect(x + 1.2, x + 1.35, z - 1.35, z + 1.35),
    rect(x - 1.2, x + 1.2, z - 1.35, z - 1.2), rect(x - 1.2, x + 1.2, z + 1.2, z + 1.35)];
  for (const border of borders) { block(border, 7.20, 6.92, 1, .015); counts.planterRimStones++; }
  for (const dx of [-.83, .83]) for (const dz of [-.83, .83]) {
    for (let layer = 0; layer < 2; layer++) {
      const plant = new T.IcosahedronGeometry(1, 0), vertices = plant.attributes.position;
      for (let vertex = 0; vertex < vertices.count; vertex++) {
        const px = vertices.getX(vertex), py = vertices.getY(vertex), pz = vertices.getZ(vertex);
        const variation = 1 + .16 * Math.sin(px * 7 + py * 11 + pz * 5 + x + z + layer);
        vertices.setXYZ(vertex, px * variation, py * variation, pz * variation);
      }
      plant.scale(layer ? .16 : .25, layer ? .19 : .23, layer ? .18 : .24);
      plant.rotateY(x + z + layer); plant.translate(x + dx + layer * .08, 7.11 + layer * .15, z + dz);
      plant.computeVertexNormals(); add(plant, 5); counts.plantingClumps++;
    }
  }
}

const scene = new T.Group(); scene.name = 'CitySidewalk';
const meshes = parts.map((geometries, index) => {
  const geometry = mergeGeometries(geometries);
  assert(geometry.attributes.uv.count === geometry.attributes.position.count, 'UV0 was lost');
  assert(geometry.attributes.color.count === geometry.attributes.position.count, 'COLOR_0 was lost');
  assert(geometry.attributes.color.array.every(channel => Number.isFinite(channel) && channel > 0 && channel <= 1));
  if (index !== 0) assert(geometry.attributes.color.array.every(channel => channel === 1), 'Non-paving colors must be white');
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  const mesh = new T.Mesh(geometry, materials[index]); mesh.name = specs[index][0]; scene.add(mesh);
  return { meshName: mesh.name, materialSlots: [mesh.material.name], triangles: geometry.attributes.position.count / 3,
    vertices: geometry.attributes.position.count, bounds: { min: geometry.boundingBox.min.toArray(), max: geometry.boundingBox.max.toArray() } };
});
scene.updateMatrixWorld(true);
const triangles = meshes.reduce((sum, mesh) => sum + mesh.triangles, 0);
assert(triangles <= 150000, `Sidewalk exceeds the 150k triangle budget: ${triangles}`);
assert(meshes.length === 6 && ramps.length === 4 && treePits.length === 28);

// Validate actual merged surfaces rather than repeating the construction parameters.
const tests = [];
function ray(x, z, names = null) {
  const targets = names ? scene.children.filter(mesh => names.includes(mesh.name)) : scene.children;
  return new T.Raycaster(new T.Vector3(x, 20, z), new T.Vector3(0, -1, 0), 0, 30).intersectObjects(targets, false)[0];
}
function sample(x, z, expected, names = null) {
  const hit = ray(x, z, names), actual = hit ? hit.point.y : null;
  return { point: [x, z], expected, actual, meshName: hit?.object.name ?? null,
    passed: expected === null ? !hit : actual !== null && Math.abs(actual - expected) < .003 };
}
for (const walk of walks) {
  const curb = sample(walk.streetEdgeX + walk.inward * .11, 24.24, sidewalkTop, ['CitySidewalk_Curbs']);
  tests.push({ kind: 'curb', id: walk.side, ...curb });
  const x = walk.side === 'west' ? -20.8 : 12.6;
  tests.push({ kind: 'top', id: walk.side, ...sample(x, 25.4, sidewalkTop, ['CitySidewalk_Paving']) });
}
for (const ramp of ramps) {
  const samples = [.025, .9, 1.575].map(distance => {
    const x = ramp.streetEdgeX + ramp.inward * distance;
    return sample(x, ramp.centerZ, rampY(ramp, x, ramp.centerZ), ['CitySidewalk_Paving', 'CitySidewalk_Base', 'CitySidewalk_Curbs']);
  });
  tests.push({ kind: 'ramp', id: ramp.id, passed: samples.every(s => s.passed), samples });
}
for (const pit of treePits) {
  const [x, , z] = pit.center;
  const soil = sample(x, z, 6.95), aperture = sample(x, z, null, ['CitySidewalk_Paving', 'CitySidewalk_Base']);
  tests.push({ kind: 'treePit', id: pit.id, passed: soil.passed && aperture.passed, samples: [soil, aperture] });
}
for (const z of [25, -32.88, -80, -131.28, -193, -310, -400]) for (const x of [-14.75, -8, 0, 8, 11.85]) {
  tests.push({ kind: 'roadClearance', id: `${x}_${z}`, ...sample(x, z, null) });
}
for (const entry of entrances) tests.push({ kind: 'entryClearance', id: entry.id, ...sample(entry.center[0], entry.center[2], null) });
for (const walk of walks) {
  const x = walk.side === 'west' ? -20.8 : 12.6;
  const samples = [-395.11, -397.31, -399.48].map(z => sample(x, z, deckY(x, z), ['CitySidewalk_Paving']));
  tests.push({ kind: 'junctionTransition', id: walk.side, passed: samples.every(s => s.passed), samples });
}
assert(tests.every(test => test.passed), `Geometry raycast failed: ${JSON.stringify(tests.filter(t => !t.passed))}`);
const glb = await new GLTFExporter().parseAsync(scene, { binary: true });
const bytes = Buffer.from(glb), sha256 = createHash('sha256').update(bytes).digest('hex');
const jsonLength = bytes.readUInt32LE(12), exported = JSON.parse(bytes.toString('utf8', 20, 20 + jsonLength));
const colorChecks = [];
for (const mesh of exported.meshes) for (const primitive of mesh.primitives) {
  const accessor = exported.accessors[primitive.attributes.COLOR_0];
  assert(accessor && accessor.type === 'VEC3' && accessor.componentType === 5126, `${mesh.name}: missing float COLOR_0 RGB`);
  const view = exported.bufferViews[accessor.bufferView];
  assert(!view.byteStride || view.byteStride === 12);
  const rgb = new Float32Array(bytes.buffer, bytes.byteOffset + 28 + jsonLength + (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0), accessor.count * 3);
  const unique = new Set();
  for (let vertex = 0; vertex < rgb.length; vertex += 9) {
    for (let channel = 0; channel < 3; channel++) assert(rgb[vertex + channel] === rgb[vertex + 3 + channel]
      && rgb[vertex + channel] === rgb[vertex + 6 + channel], `${mesh.name}: tint interpolates within a face`);
    unique.add(`${rgb[vertex]},${rgb[vertex + 1]},${rgb[vertex + 2]}`);
  }
  const paving = exported.materials[primitive.material].name === 'CitySidewalk_Paving';
  assert(paving ? unique.size > 4 : unique.size === 1 && unique.has('1,1,1'));
  colorChecks.push({ material: exported.materials[primitive.material].name, rgbCount: accessor.count,
    uniqueTints: unique.size, constantPerTriangle: true, nonPavingWhite: !paving });
}
await mkdir(output, { recursive: true }); await writeFile(new URL('city-sidewalk.glb', output), bytes);
const metadata = {
  name: 'Independent Raised City Sidewalks', file: 'city-sidewalk.glb', generator: 'unreal/Scripts/prepare_city_sidewalk.mjs',
  source: 'Original project geometry; no external models or textures.', license: 'CC0-1.0', units: 'metres',
  axes: 'glTF Y up; UE (X,Y,Z)=(glTF x,z,y)*100, exactly once.', sidewalkTop,
  coverage: { requestedZ: [-405, 36], actualZ: [zStart, zEnd],
    reason: 'The existing T-junction asphalt begins at z=-399.5; the last 4.4 m joins its shoulder without occupying the road.' },
  sidewalks: walks, ramps, treePits, entranceClearances: entrances,
  junctionTransitions: walks.map(w => ({ id: w.side, zRange: [-399.5, -395.1], topYRange: [6.919, 7.04], slope: .0275 })),
  meshes, meshCount: meshes.length, materialCount: materials.length, primitives: meshes.length, triangles, counts,
  materials: specs.map(([name, color, roughness]) => ({ name, color, roughness, metalness: 0, opaque: true })),
  pavingColorDesign: { baseColorSRGB: '#858982', paletteSRGB: pavingPalette,
    curbsSRGB: '#8b8f86', tactileSRGB: '#a18b53', tileColorCounts: colorCounts,
    bands: { treeServiceHalfWidth: 1.50, streetServiceWidth: .95, method: 'Classify the original tile centre; never subdivide geometry for color.' },
    attribute: 'COLOR_0 RGB / Unreal VertexColor RGB',
    shader: 'Multiply Paving base-color RGB by VertexColor RGB in linear space. No additional sRGB/gamma conversion; other materials have white vertex color.',
    tintEncoding: 'linear(paletteSRGB) / linear(#858982), with stable +/-2.5% linear brightness per original tile. Every cut fragment retains its parent tile tint.',
    exportedChecks: colorChecks },
  geometryChecks: { passed: true, method: 'Downward raycasts against the actual final merged geometry; no source-parameter-only checks.', tests },
  sourceGeometry: { file: 'city-sidewalk.glb', sha256 }, sha256, bytes: bytes.length,
  construction: 'Closed raised base slabs; 5 cm thick individually chamfered pavers, fine 0.6x1.2 m near the camera and coarser beyond z=-110. Segmented chamfered kerbs, four flared crosswalk ramps, tactile pads and domes. Twenty-eight open tree pits have raised 15 cm wide stone planter rims and sparse opaque planting confined inside the beds. Twelve local canopy-post clearances avoid entrance intrusion.',
};
await writeFile(new URL('city-sidewalk.json', output), JSON.stringify(metadata, null, 2) + '\n');
console.log(JSON.stringify({ triangles, meshes: meshes.length, bytes: bytes.length, counts, ramps: ramps.length,
  treePits: treePits.length, geometryChecks: tests.length, passed: true, sha256 }, null, 2));
