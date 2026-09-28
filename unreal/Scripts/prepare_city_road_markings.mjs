// Original painted road markings; run: node unreal/Scripts/prepare_city_road_markings.mjs
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import * as T from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';

globalThis.FileReader = class {
  readAsArrayBuffer(blob) { blob.arrayBuffer().then(result => { this.result = result; this.onloadend?.({ target: this }); }); }
};
const output = new URL('../Art/City/', import.meta.url);
const trafficPath = new URL('../OutOfWindow/Source/OutOfWindow/WindowTraffic.cpp', import.meta.url);
const trafficSource = await readFile(trafficPath, 'utf8');
assert(trafficSource.includes('-Car.Direction * (220.f + Lane * 300.f)')
  && trafficSource.includes('Car.Direction * Car.Position * 100.f'), 'Traffic lane mapping changed; recheck marking direction.');
const sidewalk = JSON.parse(await readFile(new URL('city-sidewalk.json', output), 'utf8'));
const zRange = [-394, 36], paintOffsetM = .0025;
const surfaces = [
  { id: 'road', xRange: [-8.75, 8.75], topY: 6.87 },
  { id: 'parking_west', xRange: [-11.95, -8.75], topY: 6.89 },
  { id: 'parking_east', xRange: [8.75, 11.95], topY: 6.89 },
  { id: 'cycle_west', xRange: [-14.85, -12.05], topY: 6.90 },
];
const specs = [['CityRoadMarkings_White', 0xc5c4ba, .83], ['CityRoadMarkings_Yellow', 0xb4a75b, .84]];
const materials = specs.map(([name, color, roughness]) => new T.MeshStandardMaterial({ name, color, roughness }));
const data = specs.map(() => ({ position: [], normal: [], uv: [] }));
const paintedParts = [];
const bounds = points => ({ min: [Math.min(...points.map(p => p[0])), Math.min(...points.map(p => p[1]))],
  max: [Math.max(...points.map(p => p[0])), Math.max(...points.map(p => p[1]))] });
function polygon(points, surface, material, kind, id) {
  const triangles = T.ShapeUtils.triangulateShape(points.map(p => new T.Vector2(...p)), []);
  const target = data[material], y = surface.topY + paintOffsetM;
  for (const indices of triangles) {
    const p = indices.map(index => points[index]);
    // glTF is Y-up: positive 2D winding on X/Z needs reversing for the top face.
    if ((p[1][0] - p[0][0]) * (p[2][1] - p[0][1]) - (p[1][1] - p[0][1]) * (p[2][0] - p[0][0]) > 0) p.reverse();
    for (const [x, z] of p) { target.position.push(x, y, z); target.normal.push(0, 1, 0); target.uv.push(x, z); }
  }
  paintedParts.push({ kind, id, material: specs[material][0], surface: surface.id, y, boundsXZ: bounds(points), triangles: triangles.length });
}
function rectangle(x0, x1, z0, z1, surface, material, kind, id) {
  assert(x1 > x0 && z1 > z0);
  polygon([[x0, z0], [x0, z1], [x1, z1], [x1, z0]], surface, material, kind, id);
}
const road = surfaces[0], cycle = surfaces[3];
const lanes = [-5.2, -2.2, 2.2, 5.2].map(x => ({ centerX: x, directionZ: x < 0 ? 1 : -1,
  side: x < 0 ? 'west' : 'east', lane: Math.abs(x) > 3.5 ? 1 : 0 }));
const crosswalks = [-32.88, -131.28].map((centerZ, index) => ({ id: `crosswalk_${index + 1}`, centerZ,
  zRange: [centerZ - 2, centerZ + 2], xRange: [-14.85, 11.95], stripeWidth: .4, clearGap: .6,
  stripeLength: 4, longAxis: 'Z', pedestrianAxis: 'X', stripeCentersX: [], patches: [] }));
for (const crossing of crosswalks) {
  assert.equal(sidewalk.ramps.filter(ramp => Math.abs(ramp.centerZ - crossing.centerZ) < .001).length, 2);
  for (let index = 0; index < 27; index++) {
    const x = -14.45 + index;
    crossing.stripeCentersX.push(x);
    for (const surface of surfaces) {
      const x0 = Math.max(x - .2, surface.xRange[0]), x1 = Math.min(x + .2, surface.xRange[1]);
      if (x1 - x0 < .00001) continue;
      const id = `${crossing.id}_stripe_${index}_${surface.id}`;
      rectangle(x0, x1, ...crossing.zRange, surface, 0, 'crosswalkStripe', id);
      crossing.patches.push({ id, stripe: index, xRange: [x0, x1], surface: surface.id, topY: surface.topY + paintOffsetM });
    }
  }
}
function outsideCrossings(start, end, margin) {
  let pieces = [[start, end]];
  for (const crossing of crosswalks) {
    const [a, b] = [crossing.centerZ - margin, crossing.centerZ + margin];
    pieces = pieces.flatMap(([lo, hi]) => a >= hi || b <= lo ? [[lo, hi]]
      : [[lo, Math.min(a, hi)], [Math.max(b, lo), hi]].filter(([x, y]) => y - x > .001));
  }
  return pieces;
}
for (const x of [-.15, .15]) {
  for (const [a, b] of outsideCrossings(...zRange, 2.15)) rectangle(x - .075, x + .075, a, b, road, 1, 'doubleCenter', `center_${x}_${a}`);
}
for (const x of [-7, 7]) {
  for (const [a, b] of outsideCrossings(...zRange, 2.15)) rectangle(x - .075, x + .075, a, b, road, 0, 'roadEdge', `edge_${x}_${a}`);
}
const laneDashes = [];
for (const x of [-3.7, 3.7]) for (let z = zRange[0]; z + 2 <= zRange[1]; z += 6) {
  if (crosswalks.some(crossing => z < crossing.centerZ + 4 && z + 2 > crossing.centerZ - 4)) continue;
  const id = `lane_${x}_${z}`;
  rectangle(x - .075, x + .075, z, z + 2, road, 0, 'laneDash', id);
  laneDashes.push({ id, centerX: x, zRange: [z, z + 2] });
}
for (const x of [-14.7, -12.2]) {
  for (const [a, b] of outsideCrossings(...zRange, 2.15)) rectangle(x - .075, x + .075, a, b, cycle, 0, 'cycleEdge', `cycle_${x}_${a}`);
}

const stopLines = [], arrows = [];
for (const crossing of crosswalks) for (const directionZ of [-1, 1]) {
  const side = directionZ < 0 ? 'east' : 'west', centerZ = crossing.centerZ - directionZ * 3.15;
  const xRange = directionZ < 0 ? [.5, 6.925] : [-6.925, -.5];
  const id = `${crossing.id}_stop_${side}`;
  rectangle(...xRange, centerZ - .15, centerZ + .15, road, 0, 'stopLine', id);
  stopLines.push({ id, crosswalk: crossing.id, side, directionZ, centerZ, xRange, width: .3, crossingGap: 1 });
}
function arrow(lane, centerZ) {
  const { centerX: x, directionZ } = lane, z = distance => centerZ + directionZ * distance;
  const id = `arrow_${x}_${centerZ}`;
  polygon([[x - .18, z(-2.25)], [x + .18, z(-2.25)], [x + .18, z(.75)],
    [x + .65, z(.75)], [x, z(2.25)], [x - .65, z(.75)], [x - .18, z(.75)]], road, 0, 'arrow', id);
  arrows.push({ id, laneCenterX: x, side: lane.side, centerZ, directionZ, length: 4.5,
    tip: [x, z(2.25)], tail: [x, z(-2.25)], upstreamOfCrosswalk: crosswalks.find(c => Math.abs(c.centerZ - centerZ) < 20)?.id ?? null });
}
for (const lane of lanes) {
  for (const crossing of crosswalks) arrow(lane, crossing.centerZ - lane.directionZ * 14);
  arrow(lane, -265);
}

const parkingBays = [];
for (const side of ['west', 'east']) {
  const surface = surfaces.find(s => s.id === `parking_${side}`), sign = side === 'west' ? -1 : 1;
  const xRange = sign < 0 ? [-11.65, -9.05] : [9.05, 11.65];
  for (let z = -382; z + 6 <= 34; z += 6.5) {
    if (crosswalks.some(c => z < c.centerZ + 12 && z + 6 > c.centerZ - 12)) continue;
    const id = `parking_${side}_${z}`, [x0, x1] = xRange, z1 = z + 6, width = .1;
    rectangle(x0, x0 + width, z, z1, surface, 0, 'parkingBay', `${id}_outer`);
    rectangle(x1 - width, x1, z, z1, surface, 0, 'parkingBay', `${id}_inner`);
    rectangle(x0 + width, x1 - width, z, z + width, surface, 0, 'parkingBay', `${id}_front`);
    rectangle(x0 + width, x1 - width, z1 - width, z1, surface, 0, 'parkingBay', `${id}_rear`);
    parkingBays.push({ id, side, xRange, zRange: [z, z1], width: 2.6, length: 6, lineWidth: width });
  }
}

const scene = new T.Group(); scene.name = 'CityRoadMarkings';
const meshes = data.map((attributes, index) => {
  const geometry = new T.BufferGeometry();
  geometry.setAttribute('position', new T.Float32BufferAttribute(attributes.position, 3));
  geometry.setAttribute('normal', new T.Float32BufferAttribute(attributes.normal, 3));
  geometry.setAttribute('uv', new T.Float32BufferAttribute(attributes.uv, 2));
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  const mesh = new T.Mesh(geometry, materials[index]); mesh.name = specs[index][0]; scene.add(mesh);
  return { meshName: mesh.name, materialSlots: [mesh.material.name], triangles: geometry.attributes.position.count / 3,
    vertices: geometry.attributes.position.count, bounds: { min: geometry.boundingBox.min.toArray(), max: geometry.boundingBox.max.toArray() } };
});
scene.updateMatrixWorld(true);
const triangles = meshes.reduce((sum, mesh) => sum + mesh.triangles, 0);
assert(triangles < 8000 && meshes.length === 2);

const tests = [];
function ray(x, z, material = null) {
  const targets = material ? scene.children.filter(mesh => mesh.name === material) : scene.children;
  return new T.Raycaster(new T.Vector3(x, 8, z), new T.Vector3(0, -1, 0), 0, 2).intersectObjects(targets, false)[0];
}
function sample(x, z, expected) {
  const hit = ray(x, z), actual = hit?.point.y ?? null;
  return { point: [x, z], expected, actual, passed: expected === null ? !hit : actual !== null && Math.abs(actual - expected) < .00002 };
}
for (const crossing of crosswalks) {
  const samples = crossing.patches.map(patch => sample((patch.xRange[0] + patch.xRange[1]) / 2, crossing.centerZ, patch.topY));
  // Probe both sides of every long stripe and its clear gaps against actual merged triangles.
  for (const x of crossing.stripeCentersX) {
    const surface = surfaces.find(s => x >= s.xRange[0] && x <= s.xRange[1]);
    samples.push(sample(x, crossing.centerZ + 1.98, surface.topY + paintOffsetM));
    samples.push(sample(x + .22, crossing.centerZ, null));
    if (x + .5 < crossing.xRange[1]) samples.push(sample(x + .5, crossing.centerZ, null));
  }
  tests.push({ kind: 'crosswalk', id: crossing.id, passed: samples.every(s => s.passed)
    && crossing.patches.every(p => p.xRange[1] - p.xRange[0] <= .40001)
    && crossing.stripeCentersX.every((x, i, xs) => !i || Math.abs(x - xs[i - 1] - 1) < .00001), samples });
}
for (const stop of stopLines) {
  const crossing = crosswalks.find(c => c.id === stop.crosswalk);
  const samples = [sample((stop.xRange[0] + stop.xRange[1]) / 2, stop.centerZ, road.topY + paintOffsetM)];
  tests.push({ kind: 'upstreamStopLine', id: stop.id, directionZ: stop.directionZ,
    signedDistanceToCrossing: (crossing.centerZ - stop.centerZ) * stop.directionZ,
    passed: samples.every(s => s.passed) && (crossing.centerZ - stop.centerZ) * stop.directionZ > 3, samples });
}
for (const item of arrows) {
  const samplePoint = sample(item.laneCenterX, item.tip[1] - item.directionZ * .1, road.topY + paintOffsetM);
  tests.push({ kind: 'trafficDirection', id: item.id, directionZ: item.directionZ,
    tip: item.tip, tail: item.tail, passed: samplePoint.passed
      && (item.tip[1] - item.tail[1]) * item.directionZ > 4.49
      && item.directionZ === (item.laneCenterX < 0 ? 1 : -1), samples: [samplePoint] });
}
const vertices = scene.children.flatMap(mesh => {
  const positions = mesh.geometry.attributes.position, violations = [];
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i), y = positions.getY(i), z = positions.getZ(i);
    const valid = surfaces.some(s => x >= s.xRange[0] - .0001 && x <= s.xRange[1] + .0001
      && Math.abs(y - s.topY - paintOffsetM) < .000002);
    if (!valid || z < zRange[0] - .0001 || z > zRange[1] + .0001) violations.push([x, y, z]);
  }
  return violations;
});
tests.push({ kind: 'surfaceBoundsAndPaintHeight', id: 'all_export_vertices', passed: vertices.length === 0,
  checkedVertices: meshes.reduce((sum, mesh) => sum + mesh.vertices, 0), violations: vertices });
tests.push({ kind: 'parkingCrosswalkClearance', id: 'all_bays', passed: parkingBays.every(bay =>
  crosswalks.every(c => bay.zRange[1] <= c.centerZ - 12 || bay.zRange[0] >= c.centerZ + 12)), clearanceFromCenter: 12 });
tests.push({ kind: 'laneDashRhythm', id: 'all_dashes', passed: laneDashes.every(d => Math.abs(d.zRange[1] - d.zRange[0] - 2) < .0001),
  paintedLength: 2, normalGap: 4, exceptions: 'Whole dashes omitted around crosswalks and stop bars.' });
assert(tests.every(test => test.passed), `Marking geometry check failed: ${JSON.stringify(tests.filter(t => !t.passed))}`);

const glb = Buffer.from(await new GLTFExporter().parseAsync(scene, { binary: true }));
const sha256 = createHash('sha256').update(glb).digest('hex');
await mkdir(output, { recursive: true }); await writeFile(new URL('city-road-markings.glb', output), glb);
const metadata = {
  name: 'Original City Boulevard Road Markings', file: 'city-road-markings.glb', generator: 'unreal/Scripts/prepare_city_road_markings.mjs',
  source: 'Original project geometry; proportions informed by public road engineering drawings. Scene artwork, not an engineering compliance certification.',
  license: 'CC0-1.0', units: 'metres', axes: 'glTF Y up; UE (X,Y,Z)=(glTF x,z,y)*100, exactly once.',
  sourceURLs: ['https://ggzyfw.beijing.gov.cn/cmsbj/u/cms/cn.gov.bjggzyfw.www/202405/9279394527188.pdf',
    'https://hipac.huaian.gov.cn/upload/2024-09/e6584ffd-ae53-4c16-a86d-ac4532b59455.pdf'],
  coverageZ: zRange, paintOffsetM, surfaces, lanes, crosswalks, stopLines, arrows, parkingBays,
  lineSpecs: { laneDividersX: [-3.7, 3.7], lineWidth: .15, dashPaint: 2, dashGap: 4, edgeX: [-7, 7],
    doubleYellowCentersX: [-.15, .15], doubleYellowClearGap: .15, cycleEdgesX: [-14.7, -12.2], stopWidth: .3,
    parkingLineWidth: .1, parkingCrosswalkExclusionFromCenter: 12, arrowLength: 4.5 },
  removedLegacyActors: [...[39, 40, 41], ...Array.from({ length: 40 }, (_, i) => 44 + i)].map(i => `OOW_${String(i).padStart(5, '0')}_Mesh`),
  trafficSource: { file: 'unreal/OutOfWindow/Source/OutOfWindow/WindowTraffic.cpp', sha256: createHash('sha256').update(trafficSource).digest('hex'),
    mapping: 'X=-Direction*(2.2+3*Lane); glTF dZ/dt=Direction. East positive-X traffic moves toward -Z; west negative-X traffic moves toward +Z.',
    behavior: 'Existing continuous animated traffic is unchanged; painted crossing controls do not add a signal or stopping simulation.' },
  meshes, meshCount: meshes.length, materialCount: materials.length, primitives: meshes.length, triangles,
  counts: { crossings: crosswalks.length, crossingStripes: crosswalks.reduce((sum, c) => sum + c.stripeCentersX.length, 0),
    stripeSurfacePatches: crosswalks.reduce((sum, c) => sum + c.patches.length, 0), laneDashes: laneDashes.length,
    stopLines: stopLines.length, arrows: arrows.length, parkingBays: parkingBays.length, paintedParts: paintedParts.length },
  materials: specs.map(([name, color, roughness]) => ({ name, color, roughness, metalness: 0, opaque: true })),
  geometryChecks: { passed: true, method: 'Downward raycasts against final merged geometry plus all actual vertex bounds/heights and traffic-source direction checks.', tests },
  sourceGeometry: { file: 'city-road-markings.glb', sha256 }, sha256, bytes: glb.length,
};
await writeFile(new URL('city-road-markings.json', output), JSON.stringify(metadata, null, 2) + '\n');
console.log(JSON.stringify({ triangles, meshCount: meshes.length, counts: metadata.counts, geometryChecks: tests.length, sha256, bytes: glb.length }, null, 2));
