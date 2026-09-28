// Original, opaque street entrance additions. Run: node unreal/Scripts/prepare_city_entrances.mjs
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import * as T from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

globalThis.FileReader = class {
  readAsArrayBuffer(blob) { blob.arrayBuffer().then(result => { this.result = result; this.onloadend?.({ target: this }); }); }
};
const output = new URL('../Art/City/', import.meta.url);
const city = JSON.parse(await readFile(new URL('modern-city.json', output), 'utf8'));
const sourceGlb = await readFile(new URL('modern-city.glb', output));
const floorY = 7.04;
const wanted = [1, 3, 5, 7, 9, 11].map(index => `CityModern_B${String(index).padStart(2, '0')}_`);
const buildings = city.buildings.filter(building => wanted.some(prefix => building.name.startsWith(prefix)));
assert.equal(buildings.length, 6);
const materialSpecs = [
  ['CityModern_Limestone', 0xc4bca9, .77, 0],
  ['CityModern_PaleStone', 0xcbd0cc, .68, 0],
  ['CityModern_Metal', 0x28333a, .36, .78],
  ['CityModern_Glass_Day_Silver', 0x4b626d, .18, .65],
  ['CityModern_Roof', 0x596366, .82, .12],
];
const materials = materialSpecs.map(([name, color, roughness, metalness]) =>
  new T.MeshStandardMaterial({ name, color, roughness, metalness }));
const scene = new T.Group(); scene.name = 'OriginalCityEntrances';
const records = [];
const detailParts = new Map(), balconyAccess = [];
const round = number => Number(number.toFixed(5));
let parts, entry, features;

function add(geometry, material, u, y, z) {
  geometry.translate(entry.facadeX + entry.streetDirection * u, floorY + y, entry.centreZ + z);
  assert(geometry.attributes.uv, 'Every entrance surface needs UV0');
  geometry.setAttribute('uv1', new T.Float32BufferAttribute(new Float32Array(geometry.attributes.position.count * 2), 2));
  // Shared office-glass materials read this channel only for nighttime emission.
  // Doors carry explicit black, avoiding the engine's default white vertex color.
  geometry.setAttribute('color', new T.Float32BufferAttribute(new Float32Array(geometry.attributes.position.count * 3), 3));
  const plain = geometry.index ? geometry.toNonIndexed() : geometry;
  plain.clearGroups(); parts[material].push(plain);
}
function box(depth, height, width, material, u, y, z = 0) {
  add(new T.BoxGeometry(depth, height, width), material, u, y, z);
}
function stoneBox(depth, height, width, material, u, y, z = 0) {
  const bevel = Math.min(.022, depth / 5, height / 5, width / 5);
  const shape = new T.Shape();
  shape.moveTo(-depth / 2 + bevel, -height / 2 + bevel);
  shape.lineTo(depth / 2 - bevel, -height / 2 + bevel);
  shape.lineTo(depth / 2 - bevel, height / 2 - bevel);
  shape.lineTo(-depth / 2 + bevel, height / 2 - bevel); shape.closePath();
  const geometry = new T.ExtrudeGeometry(shape, { depth: width - bevel * 2, steps: 1,
    bevelEnabled: true, bevelSize: bevel, bevelThickness: bevel, bevelSegments: 1, curveSegments: 1 });
  geometry.translate(0, 0, -width / 2 + bevel);
  add(geometry, material, u, y, z);
}
function cylinder(radius, length, material, u, y, z, axis = 'y') {
  const geometry = new T.CylinderGeometry(radius, radius, length, 8, 1);
  if (axis === 'u') geometry.rotateZ(Math.PI / 2);
  add(geometry, material, u, y, z);
}

for (const building of buildings) {
  const [x, , z] = building.centre, [width, depth] = building.footprint;
  const streetDirection = -Math.sign(x), facadeX = x + streetDirection * width / 2;
  const centreZ = z + (depth - 4) * .20;
  const sidewalkOuterX = x < 0 ? -21.35 : 21.35;
  const sidewalkStartU = (sidewalkOuterX - facadeX) * streetDirection;
  const stone = building.materialSlots.includes('CityModern_Limestone') ? 0 : 1;
  entry = { building: building.name, facadeX, centreZ, streetDirection, sidewalkOuterX, sidewalkStartU };
  parts = materials.map(() => []); features = [];

  // Fill only the setback between facade and sidewalk: the separate sidewalk owns
  // all floor geometry beyond this seam, so there are no coplanar slab surfaces.
  const apronBack = -.12, apronWidth = 4.82;
  box(sidewalkStartU - apronBack, .16, apronWidth, 4, (sidewalkStartU + apronBack) / 2, -.08);
  features.push('Level, step-free approach at Y=7.04; apron ends exactly at sidewalk outer edge');

  // The existing canopy underside is Y=10.19. A smaller stone portal sits below
  // it, while both old posts at u=1.65,z=+/-2.75 remain fully clear.
  stoneBox(1.40, 2.82, .32, stone, .68, 1.41, -2.20);
  stoneBox(1.11, 2.82, .32, stone, .535, 1.41, 2.20);
  stoneBox(1.46, .28, 4.78, stone, .69, 2.93);
  // Inner metal reveals and the dark soffit supply actual depth and occlusion.
  box(1.27, 2.71, .035, 2, .70, 1.355, -2.025);
  box(.99, 2.71, .035, 2, .56, 1.355, 2.025);
  box(1.28, .045, 4.02, 4, .69, 2.765);
  for (let slat = 0; slat < 7; slat++) box(.043, .055, 3.98, 2, .17 + slat * .16, 2.715);
  // Short stone returns and foot blocks give the base an asymmetric silhouette.
  stoneBox(.47, .42, .59, stone, 1.145, .21, -2.20);
  stoneBox(.33, .19, .47, stone, .90, .095, 2.20);
  if (building.style === 'fins') for (let rib = 0; rib < 3; rib++)
    box(.075, 2.57, .045, 2, 1.39, 1.405, -2.31 + rib * .11);
  features.push('Beveled projecting stone portal, deep side returns, metal reveals and seven soffit slats');

  // Opaque doors stand 0.43m in front of the old opaque facade; neither a fake
  // hole nor an interior behind the existing solid building shell is required.
  const doorU = .43, doorHeight = 2.42, doorWidth = 2.42;
  for (const side of [-1, 1]) {
    const leafZ = side * .6025;
    box(.045, 2.21, 1.145, 3, doorU, 1.275, leafZ);
    box(.077, .17, 1.19, 2, doorU + .014, .085, leafZ);
    for (const edge of [-1, 1]) box(.085, doorHeight, .045, 2, doorU + .025, doorHeight / 2, leafZ + edge * .59);
    box(.085, .05, 1.19, 2, doorU + .025, doorHeight - .025, leafZ);
    // Real round pull handles with two short brackets, not painted marks.
    const handleZ = side * .16;
    cylinder(.022, .46, 2, doorU + .19, 1.11, handleZ);
    for (const hy of [.94, 1.28]) cylinder(.018, .16, 2, doorU + .105, hy, handleZ, 'u');
    box(.09, .075, .26, 2, doorU + .025, 2.355, side * .83);
    // Fixed sidelights and their substantial jambs complete the full-width lobby.
    box(.034, 2.22, .665, 3, doorU - .035, 1.25, side * 1.595);
    for (const edgeZ of [1.225, 1.965]) box(.145, 2.70, .06, 2, doorU + .012, 1.35, side * edgeZ);
    box(.14, .15, .76, 2, doorU, .075, side * 1.595);
  }
  box(.033, .235, 3.86, 3, doorU - .035, 2.565);
  box(.15, .065, 3.97, 2, doorU + .01, 2.425);
  box(.15, .055, 3.97, 2, doorU + .01, 2.715);
  // A 12mm sill reads as a separate entry piece without a raised step.
  box(.26, .012, doorWidth + .06, 4, doorU + .04, .006);
  features.push('Double opaque glass door, kickplates, transom, fixed sidelights, separate round pull handles and 12mm sill');

  // Small three-dimensional fixtures sit in front of the sidelights, not inside
  // the original wall: a grouped mail panel and a plain stone address plaque.
  box(.17, .57, .49, 2, .62, 1.26, -1.65);
  for (let row = 0; row < 3; row++) for (const column of [-1, 1]) {
    const fixtureZ = -1.65 + column * .118, fixtureY = 1.08 + row * .18;
    box(.018, .157, .216, 4, .713, fixtureY, fixtureZ);
    box(.022, .014, .158, 2, .733, fixtureY + .033, fixtureZ);
    cylinder(.012, .014, 2, .738, fixtureY - .032, fixtureZ + .065, 'u');
  }
  stoneBox(.085, .235, .47, 1, .62, 2.08, 1.64);
  box(.10, .265, .165, 2, .64, 1.56, 1.68);
  box(.015, .077, .09, 3, .70, 1.62, 1.68);
  cylinder(.015, .02, 1, .71, 1.49, 1.68, 'u');
  features.push('Six mail slots with lock geometry, plain stone address plaque and intercom');

  const used = parts.map((part, index) => ({ part, index })).filter(({ part }) => part.length);
  const geometry = mergeGeometries(used.map(({ part }) => mergeGeometries(part)), true);
  geometry.computeBoundingBox();
  assert(geometry.attributes.position.array.every(Number.isFinite));
  for (const attribute of ['uv', 'uv1']) assert.equal(geometry.attributes[attribute].count, geometry.attributes.position.count);
  const meshName = building.name.replace('CityModern_', 'CityEntrance_');
  const mesh = new T.Mesh(geometry, used.map(({ index }) => materials[index]));
  mesh.name = meshName; scene.add(mesh);
  const bounds = { min: geometry.boundingBox.min.toArray().map(round), max: geometry.boundingBox.max.toArray().map(round) };
  const entrancePosition = [facadeX + streetDirection * doorU, floorY, centreZ].map(round);
  const portalStreetU = 1.4275;
  assert(portalStreetU < 1.65 - .08, `${meshName}: keep the old canopy posts clear`);
  assert(2.495 < 2.75 - .08, `${meshName}: keep the old posts clear in Z`);
  assert(bounds.max[1] < 10.19 - .04, `${meshName}: portal must remain below the existing canopy`);
  const treeSideEdge = x < 0 ? -19.55 : 19.55;
  const closestPortalX = facadeX + streetDirection * portalStreetU;
  assert(x < 0 ? closestPortalX < treeSideEdge : closestPortalX > treeSideEdge, `${meshName}: tree-bed collision`);
  records.push({ ...entry, meshName, entrancePosition, bounds, floorY, doorHeight, doorWidth,
    doorFrontU: doorU + .0425, portalStreetU, portalWidth: 4.99, portalHeight: 3.07,
    canopyPostCentres: [-2.75, 2.75].map(dz => [facadeX + streetDirection * 1.65, 6.9, centreZ + dz].map(round)),
    apron: { u: [apronBack, round(sidewalkStartU)], z: [round(centreZ - apronWidth / 2), round(centreZ + apronWidth / 2)], topY: floorY },
    triangles: geometry.attributes.position.count / 3, materialSlots: mesh.material.map(material => material.name), features });
  detailParts.set(building.name, parts);
}

// Every actual near-row terrace has one inhabited setback platform; the narrow
// horizontal storey bands are not additional balconies. Give each platform a
// recognizable exterior door on its camera-facing +Z wall.
const balconyMeshes = [];
for (const building of city.buildings.filter(item => [1, 4, 7, 11].some(index => item.name.startsWith(`CityModern_B${String(index).padStart(2, '0')}_`)))) {
  assert.equal(building.style, 'terrace');
  const [x, , z] = building.centre, w = building.footprint[0] - 4, d = building.footprint[1] - 4;
  const h = building.height - 1.855, towerY = 12.1, lowerH = Math.round((h - 5.2) * .62 / 3.3) * 3.3;
  const terraceY = towerY + lowerH, deckY = terraceY + (building.hero ? .134 : .15);
  const roofX = x + Math.sign(x) * w * .065, roofZ = z - d * .04, roofW = w * .78, roofD = d * .76;
  const doorX = roofX - Math.sign(x) * roofW * .29, wallZ = roofZ + roofD / 2;
  const doorZ = wallZ + .25, doorWidth = 1.06, doorHeight = 2.35;
  const stone = building.materialSlots.includes('CityModern_Limestone') ? 0 : 1;
  entry = { facadeX: 0, centreZ: 0, streetDirection: 1 };
  parts = detailParts.get(building.name) ?? materials.map(() => []);
  const worldBox = (width, height, depth, material, px, py, pz) => box(width, height, depth, material, px, py - floorY, pz);
  const worldStone = (width, height, depth, material, px, py, pz) => stoneBox(width, height, depth, material, px, py - floorY, pz);
  // The forward leaf and deep metal jambs cover a small patch of the old opaque
  // facade. A 1.06m clear opening and a threshold at the real deck level read as
  // access, with no floating door or invented interior behind the solid shell.
  worldBox(doorWidth, 2.19, .035, 3, doorX, deckY + 1.22, doorZ);
  worldBox(doorWidth + .02, .18, .075, 2, doorX, deckY + .09, doorZ + .013);
  for (const side of [-1, 1]) {
    worldBox(.07, doorHeight, .23, 2, doorX + side * (doorWidth / 2 + .035), deckY + doorHeight / 2, wallZ + .225);
    worldStone(.16, 2.52, .26, stone, doorX + side * .68, deckY + 1.26, wallZ + .13);
  }
  worldBox(doorWidth + .14, .075, .23, 2, doorX, deckY + doorHeight - .0375, wallZ + .225);
  worldStone(1.53, .16, .39, stone, doorX, deckY + 2.47, wallZ + .195);
  worldBox(doorWidth + .17, .012, .38, 4, doorX, deckY + .006, wallZ + .205);
  // A tall side panel, pull handle and closer distinguish this from neighboring windows.
  worldBox(.23, 2.18, .11, 2, doorX + .90, deckY + 1.09, wallZ + .22);
  for (let groove = 0; groove < 5; groove++) worldBox(.18, .025, .026, 4,
    doorX + .90, deckY + .68 + groove * .16, wallZ + .285);
  cylinder(.021, .43, 2, doorX + .38, deckY + 1.10 - floorY, wallZ + .40);
  for (const handleY of [.95, 1.25]) worldBox(.029, .029, .14, 2, doorX + .38, deckY + handleY, wallZ + .34);
  worldBox(.25, .075, .10, 2, doorX - .27, deckY + 2.25, wallZ + .31);
  const corridorWidth = 1.10, corridorZ = [wallZ + .43, z + d / 2 - .38];
  assert(corridorZ[1] - corridorZ[0] >= .9);
  const planterX = x - Math.sign(x) * (w / 2 - 1.15);
  assert(Math.abs(doorX - planterX) - .55 > corridorWidth / 2, `${building.name}: access crosses a planter`);
  if (building.hero) {
    const benchX = x - Math.sign(x) * (w / 2 - 2.65);
    assert(Math.abs(doorX - benchX) - .85 > corridorWidth / 2, `${building.name}: access crosses a bench`);
  }
  const meshName = building.name.replace('CityModern_', 'CityEntrance_');
  const used = parts.map((part, index) => ({ part, index })).filter(({ part }) => part.length);
  const geometry = mergeGeometries(used.map(({ part }) => mergeGeometries(part)), true);
  geometry.computeBoundingBox();
  const old = scene.children.find(mesh => mesh.name === meshName);
  if (old) { old.geometry.dispose(); old.geometry = geometry; old.material = used.map(({ index }) => materials[index]); }
  else { const mesh = new T.Mesh(geometry, used.map(({ index }) => materials[index])); mesh.name = meshName; scene.add(mesh); }
  const actual = { building: building.name, meshName,
    bounds: { min: geometry.boundingBox.min.toArray().map(round), max: geometry.boundingBox.max.toArray().map(round) },
    triangles: geometry.attributes.position.count / 3, materialSlots: used.map(({ index }) => materials[index].name) };
  const streetEntry = records.find(record => record.building === building.name);
  if (streetEntry) Object.assign(streetEntry, actual);
  else balconyMeshes.push(actual);
  balconyAccess.push({ building: building.name, meshName, platform: 'Single setback terrace', deckY: round(deckY),
    doorPosition: [doorX, deckY, doorZ].map(round), wallZ: round(wallZ), facing: '+Z',
    doorHeight, doorWidth, thresholdHeight: .012, clearPassageWidth: corridorWidth,
    clearPassageBounds: { min: [doorX - corridorWidth / 2, deckY, corridorZ[0]].map(round),
      max: [doorX + corridorWidth / 2, deckY + 2.10, corridorZ[1]].map(round) },
    note: 'Opaque door stands forward of the existing wall; no new transparent material or inaccessible interior.' });
}

// Decode POSITION/index data from the actual GLB to verify the emitted package
// and ray-check the door against both its own frame and the old opaque shell.
function readGlb(buffer) {
  assert.equal(buffer.toString('ascii', 0, 4), 'glTF');
  const jsonBytes = buffer.readUInt32LE(12), json = JSON.parse(buffer.toString('utf8', 20, 20 + jsonBytes));
  const bin = buffer.subarray(28 + jsonBytes);
  const attribute = accessorId => {
    const accessor = json.accessors[accessorId], view = json.bufferViews[accessor.bufferView];
    const types = { 5126: Float32Array, 5125: Uint32Array, 5123: Uint16Array, 5121: Uint8Array };
    const type = types[accessor.componentType], size = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }[accessor.type];
    assert(!view.byteStride || view.byteStride === size * type.BYTES_PER_ELEMENT, 'This geometry uses packed GLB attributes');
    return new T.BufferAttribute(new type(bin.buffer, bin.byteOffset + (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0), accessor.count * size), size);
  };
  return { json, meshes: json.nodes.filter(node => node.mesh !== undefined).map(node => {
    const primitives = json.meshes[node.mesh].primitives.map(primitive => {
      const geometry = new T.BufferGeometry(); geometry.setAttribute('position', attribute(primitive.attributes.POSITION));
      if (primitive.indices !== undefined) geometry.setIndex(attribute(primitive.indices));
      for (const name of ['TEXCOORD_0', 'TEXCOORD_1']) assert(primitive.attributes[name] !== undefined);
      const mesh = new T.Mesh(geometry, new T.MeshBasicMaterial({ side: T.DoubleSide }));
      mesh.userData.material = json.materials[primitive.material].name; return mesh;
    });
    return { name: node.name, primitives };
  }) };
}
const glb = Buffer.from(await new GLTFExporter().parseAsync(scene, { binary: true, onlyVisible: true }));
const emitted = readGlb(glb), existing = readGlb(sourceGlb);
assert.equal(emitted.meshes.length, 7);
const doorVisibility = [], balconyVisibility = [], meshRecords = [...records, ...balconyMeshes];
for (const record of meshRecords) {
  const decoded = emitted.meshes.find(mesh => mesh.name === record.meshName);
  const old = existing.meshes.find(mesh => mesh.name === record.building);
  assert(decoded && old);
  const actualBounds = new T.Box3();
  let actualTriangles = 0;
  for (const primitive of decoded.primitives) {
    primitive.geometry.computeBoundingBox(); actualBounds.union(primitive.geometry.boundingBox);
    actualTriangles += (primitive.geometry.index?.count ?? primitive.geometry.attributes.position.count) / 3;
  }
  assert.equal(actualTriangles, record.triangles);
  assert.deepEqual(actualBounds.min.toArray().map(round), record.bounds.min);
  assert.deepEqual(actualBounds.max.toArray().map(round), record.bounds.max);
  for (const leaf of record.entrancePosition ? [-1, 1] : []) {
    const origin = new T.Vector3(record.facadeX + record.streetDirection * 4, floorY + 1.75, record.centreZ + leaf * .6);
    const ray = new T.Raycaster(origin, new T.Vector3(-record.streetDirection, 0, 0), 0, 5);
    const doorHit = ray.intersectObjects(decoded.primitives)[0], oldHit = ray.intersectObjects(old.primitives)[0];
    assert(doorHit && oldHit && doorHit.distance < oldHit.distance - .3, `${record.meshName}: door hidden in old facade`);
    assert.equal(doorHit.object.userData.material, 'CityModern_Glass_Day_Silver', `${record.meshName}: door blocked by new geometry`);
    doorVisibility.push({ meshName: record.meshName, leaf, doorDistance: round(doorHit.distance), oldFacadeDistance: round(oldHit.distance), clear: true });
  }
}
for (const access of balconyAccess) {
  const decoded = emitted.meshes.find(mesh => mesh.name === access.meshName);
  const old = existing.meshes.find(mesh => mesh.name === access.building);
  const [x, y, z] = access.doorPosition;
  const ray = new T.Raycaster(new T.Vector3(x, y + 1.7, z + 3), new T.Vector3(0, 0, -1), 0, 5);
  const doorHit = ray.intersectObjects(decoded.primitives)[0], oldHit = ray.intersectObjects(old.primitives)[0];
  assert(doorHit && oldHit && doorHit.distance < oldHit.distance - .25, `${access.building}: balcony door hidden by old wall`);
  assert.equal(doorHit.object.userData.material, 'CityModern_Glass_Day_Silver');
  const down = new T.Raycaster(new T.Vector3(x, y + .30, z + .10), new T.Vector3(0, -1, 0), 0, .5);
  const deckHit = down.intersectObjects(old.primitives)[0], thresholdHit = down.intersectObjects(decoded.primitives)[0];
  assert(deckHit && thresholdHit, `${access.building}: threshold has no real deck beneath it`);
  assert(Math.abs(deckHit.point.y - access.deckY) < .0002, `${access.building}: wrong terrace deck level`);
  assert(Math.abs(thresholdHit.point.y - deckHit.point.y - access.thresholdHeight) < .0002, `${access.building}: threshold floats above deck`);
  // Probe the complete walking strip, not just the center: floor is below each ray.
  for (const lane of [-.5, 0, .5]) for (const bodyY of [.15, .55, 1.20, 1.90]) {
    const [min, max] = [access.clearPassageBounds.min, access.clearPassageBounds.max];
    const walk = new T.Raycaster(new T.Vector3(x + lane, y + bodyY, min[2]), new T.Vector3(0, 0, 1), 0, max[2] - min[2]);
    assert.equal(walk.intersectObjects([...old.primitives, ...decoded.primitives]).length, 0,
      `${access.building}: terrace access blocked at lane ${lane}, height ${bodyY}`);
  }
  access.validation = { doorVisibleBeforeOldFacade: true, walkingStripRaysPassed: 12,
    actualDeckY: round(deckHit.point.y), actualThresholdTopY: round(thresholdHit.point.y),
    actualThresholdHeight: round(thresholdHit.point.y - deckHit.point.y), thresholdSeatedOnDeck: true };
  balconyVisibility.push({ building: access.building, doorDistance: round(doorHit.distance), oldFacadeDistance: round(oldHit.distance),
    ...access.validation, clear: true });
}
const triangles = meshRecords.reduce((sum, record) => sum + record.triangles, 0);
const primitives = meshRecords.reduce((sum, record) => sum + record.materialSlots.length, 0);
assert(triangles <= 20000, 'Keep this entrance kit below the requested triangle budget');
const metadata = {
  name: 'Original Avenue Entrance Details', file: 'city-entrances.glb', generator: 'unreal/Scripts/prepare_city_entrances.mjs',
  source: 'Original procedural entrance geometry authored for OutOfWindow; no downloaded assets or textures.',
  sourceGeometry: { file: 'modern-city.glb', sha256: createHash('sha256').update(sourceGlb).digest('hex') },
  sha256: createHash('sha256').update(glb).digest('hex'),
  license: 'CC0-1.0', licenseUrl: 'https://creativecommons.org/publicdomain/zero/1.0/', units: 'metres',
  axes: { up: '+Y', avenue: 'Z', unrealImport: 'glTF (x, y, z) maps to UE (x, z, y).' },
  floorY, meshCount: scene.children.length, triangles, primitives, bytes: glb.byteLength, entrances: records,
  meshes: meshRecords.map(({ building, meshName, bounds, triangles, materialSlots }) => ({ building, meshName, bounds, triangles, materialSlots })),
  balconyAccess,
  materials: materialSpecs.map(([name, color, roughness, metalness]) => ({ name, color, roughness, metalness, opaque: true })),
  validation: { actualGlbBoundsAndTriangles: true, canopyPostClearance: true, canopyUndersideClearance: true,
    treeBedClearance: true, apronEndsAtSidewalkEdge: true, doorVisibility, balconyVisibility,
    note: 'CPU geometry verification; final Unreal lighting and fixed-camera visibility require screenshot review.' },
  geometryChecks: { streetDoorRays: doorVisibility, balconyDoorAndThresholdRays: balconyVisibility,
    terraceWalkingRays: balconyAccess.length * 12, allPassed: true },
};
await writeFile(new URL('city-entrances.glb', output), glb);
await writeFile(new URL('city-entrances.json', output), JSON.stringify(metadata, null, 2) + '\n');
console.log(JSON.stringify({ triangles, meshes: scene.children.length, primitives, bytes: glb.byteLength,
  doorRaysPassed: doorVisibility.length, balconyDoors: balconyAccess.length, balconyRaysPassed: balconyVisibility.length,
  buildings: meshRecords.map(record => record.building) }, null, 2));
