// Original modern avenue kit, in metres. Run: node unreal/Scripts/prepare_modern_city.mjs
// Optional preservation check: --verify-daylight-baseline=path/to/previous.glb
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import * as T from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

globalThis.FileReader = class {
  readAsArrayBuffer(blob) { blob.arrayBuffer().then(result => { this.result = result; this.onloadend?.({ target: this }); }); }
};

const output = new URL('../Art/City/', import.meta.url);
const baselineOption = '--verify-daylight-baseline=';
const baselineArgument = process.argv.find(argument => argument.startsWith(baselineOption));
const baselinePath = baselineArgument?.slice(baselineOption.length);
assert(!baselineArgument || baselinePath, 'Supply a GLB path after --verify-daylight-baseline=');
const groundY = 6.9;
const materialSpecs = [
  ['CityModern_Limestone', 0xc4bca9, .77, 0],
  ['CityModern_PaleStone', 0xcbd0cc, .68, 0],
  ['CityModern_Metal', 0x28333a, .36, .78],
  ['CityModern_Glass_Day_Blue', 0x526a75, .18, .65],
  ['CityModern_Glass_Day_Silver', 0x4b626d, .18, .65],
  ['Glass_Lit_CityModern_Warm', 0x526a75, .18, .65, 0xffc580, 0],
  ['CityModern_Roof', 0x596366, .82, .12],
  ['CityModern_LED', 0xe6e8dc, .4, .2, 0xffedcb, 2],
  ['CityModern_Skyline_Glass_Blue', 0x617680, .26, .60],
  ['CityModern_Skyline_Glass_Grey', 0x687a82, .29, .55],
  ['CityModern_Skyline_Spandrel', 0x8a979b, .64, .15],
  ['CityModern_RoofPlanting', 0x4b634a, .96, 0],
  ['CityModern_Context_Asphalt', 0x454a4b, .92, 0],
  ['CityModern_Hero_Glass', 0x526a75, .18, .60],
];
const heroGlass = materialSpecs.findIndex(([name]) => name === 'CityModern_Hero_Glass');
const heroBuildingNames = ['CityModern_B01_terrace', 'CityModern_B07_terrace'];
const heroWindowSeeds = new Set();
const nearGlassMaterials = new Set([3, 4, 5, heroGlass]);
const nightRows = [];
let activeBuildingName, nightPaneCount = 0, nightHeroPaneCount = 0;
const materials = materialSpecs.map(([name, color, roughness, metalness, emissive = 0, emissiveIntensity = 0]) =>
  new T.MeshStandardMaterial({ name, color, roughness, metalness, emissive, emissiveIntensity }));
const scene = new T.Group(); scene.name = 'OriginalModernCity';
let parts;
function add(geometry, mat, position, rotationY = 0, paneSeed = 0, nightRgb = [0, 0, 0]) {
  geometry.rotateY(rotationY); geometry.translate(...position);
  assert(geometry.attributes.uv, 'All source geometry must retain UV0');
  const uv1 = new Float32Array(geometry.attributes.position.count * 2);
  for (let vertex = 0; vertex < geometry.attributes.position.count; vertex++) uv1[vertex * 2] = paneSeed;
  geometry.setAttribute('uv1', new T.BufferAttribute(uv1, 2));
  // COLOR_0 carries UE night-light data. Generic glTF viewers multiply it into
  // BaseColor, so this asset needs the UE material that reads it only for emission.
  const color = new Float32Array(geometry.attributes.position.count * 3);
  for (let vertex = 0; vertex < geometry.attributes.position.count; vertex++) color.set(nightRgb, vertex * 3);
  geometry.setAttribute('color', new T.BufferAttribute(color, 3));
  const unindexed = geometry.index ? geometry.toNonIndexed() : geometry;
  unindexed.clearGroups(); parts[mat].push(unindexed);
}
function box(w, h, d, mat, x, y, z) { add(new T.BoxGeometry(w, h, d), mat, [x, y, z]); }
function bevelBox(w, h, d, mat, x, y, z) {
  const bevel = Math.min(.035, w / 6, h / 6, d / 6), shape = new T.Shape();
  shape.moveTo(-w / 2 + bevel, -h / 2 + bevel);
  shape.lineTo(w / 2 - bevel, -h / 2 + bevel);
  shape.lineTo(w / 2 - bevel, h / 2 - bevel);
  shape.lineTo(-w / 2 + bevel, h / 2 - bevel); shape.closePath();
  const geometry = new T.ExtrudeGeometry(shape, { depth: d - bevel * 2, steps: 1,
    bevelEnabled: true, bevelSize: bevel, bevelThickness: bevel, bevelSegments: 1, curveSegments: 1 });
  geometry.translate(0, 0, -d / 2 + bevel);
  add(geometry, mat, [x, y, z]);
}
function windowPane(w, h, mat, x, y, z, angle, paneSeed = 0, nightRgb) {
  assert(nightRgb?.length === 3 && nearGlassMaterials.has(mat));
  add(new T.PlaneGeometry(w, h), mat, [x, y, z], angle, paneSeed, nightRgb);
  nightPaneCount++; if (mat === heroGlass) nightHeroPaneCount++;
}
function windowSeed(key) {
  let hash = 2166136261;
  for (const char of key) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return Math.fround(((hash >>> 8) + .5) / 16777216);
}
// Office cores cover 3–8 adjoining panes. One or two neighbouring panes carry
// soft spill light; a whole row shares its floor brightness instead of window
// on/off noise. Irregular 2–4-floor leases keep stacked rows from forming diagonals.
function officeFloors(baseY, floors) {
  const result = [], key = `${activeBuildingName}:${baseY.toFixed(3)}`;
  for (let first = 0, group = 0; first < floors; group++) {
    const groupKey = `${key}:lease:${group}`, span = 2 + Math.floor(windowSeed(`${groupKey}:span`) * 3);
    const dim = windowSeed(`${groupKey}:dim`) < .16;
    const level = dim ? .14 + .14 * windowSeed(`${groupKey}:level`) : .48 + .38 * windowSeed(`${groupKey}:level`);
    const warmth = windowSeed(`${groupKey}:warmth`);
    for (let row = first; row < Math.min(floors, first + span); row++) result.push({ group,
      key: groupKey, brightness: level * (.90 + .16 * windowSeed(`${key}:${row}:brightness`)),
      tint: [1, .87 + warmth * .06, .70 + warmth * .13], dim });
    first += span;
  }
  return result;
}
function officeRow(baseY, row, side, bays, floor) {
  const key = `${floor.key}:face:${side}`, random = label => windowSeed(`${key}:${label}`);
  const two = bays >= 9 && random('two') < .46, gap = two ? 1 + Math.floor(random('gap') * 2) : 0;
  const maxFirst = two ? Math.min(6, bays - gap - 3) : Math.min(8, bays);
  const firstWidth = 3 + Math.floor(random('width0') * (maxFirst - 2));
  const secondWidth = two ? 3 + Math.floor(random('width1') * (Math.min(8, bays - gap - firstWidth) - 2)) : 0;
  const firstStart = Math.floor(random('start') * (bays - firstWidth - secondWidth - gap + 1));
  const offices = [firstWidth, ...(two ? [secondWidth] : [])].map((width, index) => {
    const start = firstStart + (index ? firstWidth + gap : 0);
    return { startBay: start, endBay: start + width - 1, corePaneCount: width,
      edgeTransitionPanes: 1 + Math.floor(random(`edge${index}`) * 2),
      strength: (.58 + .18 * random(`strength${index}`)) * floor.brightness,
      tint: [1, floor.tint[1] + (random(`tint${index}`) - .5) * .025,
        floor.tint[2] + (random(`tint${index}`) - .5) * .035] };
  });
  const borrowedLight = .035 + .025 * windowSeed(`${activeBuildingName}:${baseY}:${row}:borrowed`);
  const colors = Array.from({ length: bays }, (_, bay) => {
    const light = floor.tint.map(channel => channel * borrowedLight);
    for (const office of offices) {
      const distance = Math.max(office.startBay - bay, bay - office.endBay, 0);
      const weight = Math.max(0, 1 - distance / (office.edgeTransitionPanes + 1));
      for (let channel = 0; channel < 3; channel++) light[channel] = Math.max(light[channel],
        borrowedLight * floor.tint[channel] + weight * office.strength * office.tint[channel]);
    }
    return light.map(Math.fround);
  });
  let maxAdjacentChannelDifference = 0;
  for (let bay = 1; bay < bays; bay++) for (let channel = 0; channel < 3; channel++) {
    maxAdjacentChannelDifference = Math.max(maxAdjacentChannelDifference, Math.abs(colors[bay][channel] - colors[bay - 1][channel]));
  }
  nightRows.push({ buildingName: activeBuildingName, facadeBaseY: baseY, floorIndex: row, faceIndex: side,
    faceNormal: side < 2 ? [0, 0, side === 0 ? 1 : -1] : [side === 2 ? 1 : -1, 0, 0], bays,
    floorGroup: floor.group, floorBrightness: floor.brightness, dimFloor: floor.dim, borrowedLight,
    offices, paneRgb: colors, maxAdjacentChannelDifference });
  return colors;
}
function start() { parts = materials.map(() => []); }
function finish(name) {
  const used = parts.map((part, index) => ({ part, index })).filter(({ part }) => part.length);
  const geometry = mergeGeometries(used.map(({ part }) => mergeGeometries(part)), true);
  for (const attribute of ['uv', 'uv1', 'color']) {
    assert(geometry.attributes[attribute]?.count === geometry.attributes.position.count, `${name}: missing ${attribute}`);
    assert(geometry.attributes[attribute].array.every(Number.isFinite), `${name}: non-finite ${attribute}`);
  }
  const mesh = new T.Mesh(geometry, used.map(({ index }) => materials[index]));
  const heroGroup = geometry.groups.find(group => used[group.materialIndex].index === heroGlass);
  if (heroGroup) {
    assert(heroBuildingNames.includes(name), `Hero glazing unexpectedly assigned to ${name}`);
    assert(heroGroup.count % 6 === 0, 'Each hero pane must remain a complete two-triangle quad');
    for (let pane = heroGroup.start; pane < heroGroup.start + heroGroup.count; pane += 6) {
      const paneSeed = geometry.attributes.uv1.getX(pane);
      assert(paneSeed > 0 && paneSeed < 1 && !heroWindowSeeds.has(paneSeed), 'Hero pane seed collision/out of range');
      heroWindowSeeds.add(paneSeed);
      const corners = new Set();
      for (let vertex = pane; vertex < pane + 6; vertex++) {
        assert(geometry.attributes.uv1.getX(vertex) === paneSeed && geometry.attributes.uv1.getY(vertex) === 0,
          `${name}: hero seed must be constant over a full pane`);
        corners.add(`${geometry.attributes.uv.getX(vertex)},${geometry.attributes.uv.getY(vertex)}`);
      }
      assert(['0,0', '0,1', '1,0', '1,1'].every(corner => corners.has(corner)), `${name}: pane UV0 must cover 0..1`);
    }
    mesh.userData.heroWindowCount = heroGroup.count / 6;
  }
  mesh.name = name; scene.add(mesh); return mesh;
}

// Glazing is recessed 11 cm normally and 24 cm on the two hero buildings; all
// panes remain opaque. UV1.x gives their shader stable per-pane surface variation.
function facade({ x, z, w, d, y, h, floors, stone, style, seed, hero = false }) {
  box(w - (hero ? .52 : .24), h, d - (hero ? .52 : .24), 2, x, y + h / 2, z);
  const floorH = h / floors;
  const floorLighting = officeFloors(y, floors);
  for (let row = 0; row <= floors; row++) {
    (hero ? bevelBox : box)(w, row === 0 || row === floors ? (hero ? .18 : .27) : (hero ? .11 : .19),
      d, style === 'glass' ? 2 : stone, x, y + row * floorH, z);
  }
  for (let side = 0; side < 4; side++) {
    const sideFace = side >= 2, sign = side % 2 === 0 ? 1 : -1;
    const length = sideFace ? d : w;
    const bays = Math.max(3, Math.round(length / 2.9)), bayW = length / bays;
    for (let bay = 0; bay <= bays; bay++) {
      const offset = -length / 2 + bay * bayW;
      const isFin = style === 'fins' && bay % 2 === 0;
      const corner = bay === 0 || bay === bays;
      const width = corner ? (hero ? .17 : .25) : isFin ? .18 : (hero ? .06 : .075);
      const depth = isFin ? .52 : (hero ? .30 : .19);
      const moulding = hero && corner ? bevelBox : box;
      const centreOffset = hero ? -.04 : (depth - .19) / 2;
      if (sideFace) moulding(depth, h, width, isFin ? stone : 2, x + sign * (w / 2 + centreOffset), y + h / 2, z + offset);
      else moulding(width, h, depth, isFin ? stone : 2, x + offset, y + h / 2, z + sign * (d / 2 + centreOffset));
    }
    for (let row = 0; row < floors; row++) {
      const nightColors = officeRow(y, row, side, bays, floorLighting[row]);
      for (let bay = 0; bay < bays; bay++) {
      const code = (seed * 17 + side * 31 + row * 11 + bay * 7) % 29;
      const mat = hero ? heroGlass : code < 2 ? 5 : code < 5 ? 4 : 3;
      const paneSeed = hero ? windowSeed(`${seed}:${y.toFixed(3)}:${side}:${row}:${bay}`) : 0;
      const offset = -length / 2 + (bay + .5) * bayW;
      const wy = y + (row + .5) * floorH;
      const inset = hero ? .24 : .105, paneW = bayW - (hero ? .10 : .12), paneH = floorH - (hero ? .28 : .36);
      if (sideFace) windowPane(paneW, paneH, mat, x + sign * (w / 2 - inset), wy, z + offset, sign * Math.PI / 2, paneSeed, nightColors[bay]);
      else windowPane(paneW, paneH, mat, x + offset, wy, z + sign * (d / 2 - inset), sign === 1 ? 0 : Math.PI, paneSeed, nightColors[bay]);
      }
    }
  }
}

function roof(x, z, w, d, y, stone) {
  box(w, .23, d, stone, x, y + .115, z);
  for (const sign of [-1, 1]) {
    box(w, .65, .2, stone, x, y + .35, z + sign * (d / 2 - .1));
    box(.2, .65, d, stone, x + sign * (w / 2 - .1), y + .35, z);
  }
  box(w * .3, 1.75, d * .24, 6, x, y + .98, z - d * .13);
  for (let unit = 0; unit < 3; unit++) {
    const ux = x + (unit - 1) * 2.25;
    box(1.65, .7, 2.2, 1, ux, y + .58, z + d * .18);
    box(1.4, .06, 1.95, 2, ux, y + .97, z + d * .18);
    for (let blade = 0; blade < 5; blade++) box(.05, .08, 1.86, 6, ux - .52 + blade * .26, y + 1.02, z + d * .18);
  }
}

// Alternating avenue rhythm: low foreground terraces, then slender glass/fin towers.
// The four outer-row towers add skyline depth without closing the avenue's centre.
const buildings = [
  [-36, -3, 24, 29, 30, 'terrace', 0], [-41, -47, 28, 30, 46, 'fins', 1],
  [-35, -93, 22, 35, 55, 'glass', 1], [-43, -145, 32, 30, 67, 'terrace', 0],
  [-36, -197, 24, 31, 76, 'fins', 0], [-40, -250, 29, 34, 88, 'glass', 1],
  [38, -8, 26, 30, 33, 'terrace', 1], [40, -52, 26, 31, 48, 'glass', 1],
  [35, -99, 23, 32, 58, 'fins', 0], [44, -151, 33, 34, 70, 'glass', 1],
  [36, -208, 23, 34, 91, 'terrace', 1], [41, -262, 28, 34, 105, 'fins', 0],
  [-72, -86, 26, 34, 64, 'glass', 1], [75, -137, 31, 38, 76, 'fins', 0],
  [-74, -210, 33, 35, 100, 'glass', 1], [73, -274, 30, 37, 108, 'terrace', 0],
];
const buildingRecords = [];
for (const [index, [x, z, w, d, h, style, stone]] of buildings.entries()) {
  start();
  activeBuildingName = `CityModern_B${String(index + 1).padStart(2, '0')}_${style}`;
  const hero = index === 0 || index === 6;
  const podiumH = 5.2, towerY = groundY + podiumH;
  facade({ x, z, w: w + 4, d: d + 4, y: groundY, h: podiumH, floors: 1, stone, style: 'glass', seed: index, hero });
  // Strong pale storefront lintel and a projecting entrance canopy face the avenue.
  (hero ? bevelBox : box)(w + 4.3, hero ? .26 : .45, d + 4.3, stone, x, towerY + .1, z);
  const avenueSide = -Math.sign(x);
  box(2.7, .22, 6, 2, x + avenueSide * (w / 2 + 2.6), groundY + 3.4, z + d * .20);
  box(.16, 3.4, .16, 2, x + avenueSide * (w / 2 + 3.65), groundY + 1.7, z + d * .20 + 2.75);
  box(.16, 3.4, .16, 2, x + avenueSide * (w / 2 + 3.65), groundY + 1.7, z + d * .20 - 2.75);
  const towerH = h - podiumH;
  let roofX = x, roofZ = z, roofW = w, roofD = d;
  if (style === 'terrace') {
    const lowerH = Math.round(towerH * .62 / 3.3) * 3.3;
    facade({ x, z, w, d, y: towerY, h: lowerH, floors: Math.round(lowerH / 3.3), stone, style, seed: index, hero });
    const terraceY = towerY + lowerH;
    (hero ? bevelBox : box)(w + .3, hero ? .20 : .30, d + .3, stone, x, terraceY, z);
    if (hero) box(w - .10, .028, d - .10, 6, x, terraceY + .12, z);
    const rail = hero ? .045 : .07, postWidth = hero ? .045 : .06;
    for (const sign of [-1, 1]) {
      box(w, rail, rail, 2, x, terraceY + .85, z + sign * (d / 2 - .2));
      box(rail, rail, d, 2, x + sign * (w / 2 - .2), terraceY + .85, z);
      for (let post = 0; post <= 6; post++) {
        box(postWidth, .85, postWidth, 2, x - w / 2 + post * w / 6, terraceY + .425, z + sign * (d / 2 - .2));
        box(postWidth, .85, postWidth, 2, x + sign * (w / 2 - .2), terraceY + .425, z - d / 2 + post * d / 6);
      }
    }
    roofW = w * .78; roofD = d * .76; roofX = x + Math.sign(x) * w * .065; roofZ = z - d * .04;
    facade({ x: roofX, z: roofZ, w: roofW, d: roofD, y: terraceY + .15, h: towerH - lowerH - .15,
      floors: Math.max(2, Math.round((towerH - lowerH) / 3.3)), stone, style: 'glass', seed: index + 10, hero });
    // Fine sunbreakers and low linear planting give the inhabited roof terraces scale.
    const upperH = towerH - lowerH - .15;
    for (let blade = 0; blade <= Math.floor(roofD / 1.45); blade++) {
      box(hero ? .34 : .46, upperH, hero ? .055 : .085, stone, roofX + avenueSide * (roofW / 2 + .14), terraceY + .15 + upperH / 2,
        roofZ - roofD / 2 + blade * roofD / Math.floor(roofD / 1.45));
    }
    for (let planter = 0; planter < 3; planter++) {
      const pz = z - d * .30 + planter * d * .28, px = x + avenueSide * (w / 2 - 1.15);
      (hero ? bevelBox : box)(1.1, .62, 2.8, stone, px, terraceY + .46, pz);
      if (hero) {
        box(.93, .04, 2.62, 6, px, terraceY + .77, pz);
        for (let clump = 0; clump < 6; clump++) {
          const shrub = new T.IcosahedronGeometry(1, 0), vertices = shrub.attributes.position;
          for (let vertex = 0; vertex < vertices.count; vertex++) {
            const vx = vertices.getX(vertex), vy = vertices.getY(vertex), vz = vertices.getZ(vertex);
            const jitter = 1 + .16 * Math.sin(vx * 5 + vy * 7 + vz * 11 + clump);
            vertices.setXYZ(vertex, vx * jitter, vy * jitter, vz * jitter);
          }
          shrub.scale(.27, .29 + ((clump + planter) % 3) * .055, .44);
          shrub.computeVertexNormals();
          add(shrub, 11, [px + (clump % 2 ? .23 : -.23), terraceY + 1.02,
            pz - .84 + Math.floor(clump / 2) * .82], clump * 1.37);
        }
      } else {
        box(.88, .38, 2.56, 11, px, terraceY + .94, pz);
        box(.65, .11, 1.87, 11, px + .04, terraceY + 1.18, pz - .15);
      }
    }
    if (hero) for (const position of [-.20, .26]) {
      const bx = x + avenueSide * (w / 2 - 2.65), bz = z + d * position;
      for (let slat = 0; slat < 3; slat++) box(1.7, .065, .115, 6, bx, terraceY + .61, bz + (slat - 1) * .135);
      for (const dx of [-.65, .65]) for (const dz of [-.13, .13]) box(.055, .45, .055, 2,
        bx + dx, terraceY + .36, bz + dz);
    }
  } else {
    facade({ x, z, w, d, y: towerY, h: towerH, floors: Math.round(towerH / 3.3), stone, style, seed: index });
    if (style === 'glass') {
      // A pair of solid vertical service strips breaks the curtain-wall repetition.
      box(.65, towerH, .36, stone, x - w * .31, towerY + towerH / 2, z + d / 2 + .09);
      box(.36, towerH, .65, stone, x + w / 2 + .09, towerY + towerH / 2, z - d * .22);
    }
  }
  roof(roofX, roofZ, roofW, roofD, groundY + h, stone);
  const name = `CityModern_B${String(index + 1).padStart(2, '0')}_${style}`;
  const mesh = finish(name);
  mesh.geometry.computeBoundingBox();
  const bounds = mesh.geometry.boundingBox;
  assert(x < 0 ? bounds.max.x < -19 : bounds.min.x > 19, `${name} intrudes on the road or pavement`);
  buildingRecords.push({ name, style, centre: [x, groundY, z], footprint: [w + 4, d + 4], height: h + 1.855,
    triangles: mesh.geometry.attributes.position.count / 3, materialSlots: mesh.material.map(m => m.name),
    ...(hero ? { hero: true, heroWindowCount: mesh.userData.heroWindowCount } : {}) });
}

// Distant towers use continuous curtain-wall skins and thin floor ribbons, avoiding
// invisible individual panes. Three staggered rows keep sky gaps between silhouettes.
const skyline = [
  [-230, -405, 36, 39, 86, 'setback'], [-150, -435, 29, 33, 121, 'twin'],
  [-85, -395, 27, 31, 77, 'setback'], [85, -425, 32, 36, 112, 'setback'],
  [165, -405, 38, 40, 89, 'twin'], [250, -450, 33, 37, 132, 'setback'],
  [-285, -620, 43, 41, 126, 'setback'], [-190, -655, 36, 38, 153, 'setback'],
  [-110, -585, 32, 36, 116, 'twin'], [95, -625, 35, 39, 142, 'setback'],
  [185, -610, 42, 41, 103, 'setback'], [295, -670, 35, 38, 128, 'twin'],
  [-250, -885, 39, 44, 139, 'twin'], [-160, -935, 36, 39, 160, 'setback'],
  [-85, -865, 31, 34, 108, 'setback'], [90, -975, 37, 41, 145, 'twin'],
  [170, -875, 42, 43, 124, 'setback'], [270, -945, 38, 39, 152, 'setback'],
];
function distantVolume(x, z, w, d, y, h, glass) {
  box(w, h, d, glass, x, y + h / 2, z);
  const floors = Math.max(2, Math.round(h / 3.5));
  for (let floor = 0; floor <= floors; floor++) {
    box(w + .12, .075, d + .12, 10, x, y + floor * h / floors, z);
  }
  for (const sign of [-1, 1]) for (let bay = 0; bay <= 5; bay++) {
    box(.085, h, .09, 10, x - w / 2 + bay * w / 5, y + h / 2, z + sign * (d / 2 + .025));
    box(.09, h, .085, 10, x + sign * (w / 2 + .025), y + h / 2, z - d / 2 + bay * d / 5);
  }
  box(w + .22, .4, d + .22, 10, x, y + h, z);
}
for (const [index, [x, z, w, d, h, style]] of skyline.entries()) {
  start();
  const glass = index % 3 === 0 ? 9 : 8;
  const lowerH = Math.round(h * (style === 'twin' ? .71 : .78) / 3.5) * 3.5;
  distantVolume(x, z, w, d, groundY, lowerH, glass);
  if (style === 'twin') {
    for (const sign of [-1, 1]) {
      const topH = h - lowerH - (sign === -1 ? 5.25 : 0);
      distantVolume(x + sign * w * .265, z - d * .08, w * .38, d * .76, groundY + lowerH, topH, glass);
      box(w * .24, 1.4, d * .3, 10, x + sign * w * .265, groundY + lowerH + topH + .7, z - d * .08);
    }
  } else {
    const topW = w * .72, topD = d * .70, topH = h - lowerH;
    distantVolume(x + Math.sign(x) * w * .055, z - d * .035, topW, topD, groundY + lowerH, topH, glass);
    box(topW * .52, 2.1, topD * .48, 10, x, groundY + h + 1.05, z - d * .035);
  }
  const name = `CityModern_Skyline${String(index + 1).padStart(2, '0')}_${style}`;
  const mesh = finish(name);
  buildingRecords.push({ name, style: `distant_${style}`, centre: [x, groundY, z], footprint: [w, d], height: h + 2.1,
    triangles: mesh.geometry.attributes.position.count / 3, materialSlots: mesh.material.map(m => m.name) });
}

// Low/mid-rise city fabric hides the empty ground under the existing distant towers.
// Four spatial batches add depth without turning the skyline into one wall. The
// fifth supplies real offscreen neighbours behind the camera for facade reflections.
const contextBlocks = [
  { name: 'West', buildings: [
    [-36, -327, 28, 34, 51], [-40, -379, 32, 38, 38], [-65, -445, 42, 42, 57],
    [-114, -400, 54, 45, 35], [-161, -536, 62, 48, 42],
  ] },
  { name: 'East', buildings: [
    [38, -329, 28, 33, 44], [43, -381, 32, 38, 59], [71, -448, 43, 43, 48],
    [119, -404, 52, 42, 32], [169, -538, 62, 49, 46],
  ] },
  { name: 'Terminus', buildings: [
    [-31, -485, 48, 46, 50], [21, -474, 56, 40, 29], [56, -514, 32, 42, 68],
  ] },
  { name: 'Background', buildings: [
    [-245, -660, 80, 60, 44], [-143, -704, 84, 62, 36], [-39, -653, 83, 65, 39],
    [64, -705, 90, 61, 45], [174, -650, 92, 60, 34],
  ] },
  { name: 'Reflection', offscreenReflectionContext: true, buildings: [
    [59, 84, 32, 34, 52], [-140, 85, 44, 34, 52],
  ] },
];
const contextBuildings = [], contextGroups = [];
function recordContext(mesh, count) {
  mesh.geometry.computeBoundingBox();
  const bounds = mesh.geometry.boundingBox;
  contextGroups.push({ meshName: mesh.name, buildings: count, triangles: mesh.geometry.attributes.position.count / 3,
    primitives: mesh.material.length, bounds: { min: bounds.min.toArray(), max: bounds.max.toArray() } });
}
for (const [blockIndex, block] of contextBlocks.entries()) {
  start();
  for (const [index, [x, z, w, d, h]] of block.buildings.entries()) {
    const glass = (index + blockIndex) % 3 === 0 ? 9 : 8;
    const lowerH = h - 8.4;
    distantVolume(x, z, w, d, groundY, lowerH, glass);
    const topX = x + (index % 2 === 0 ? 1 : -1) * w * .08;
    // Broad stepped roofs retain a mid-rise silhouette below the existing towers.
    box(w * .69, 8.4, d * .72, glass, topX, groundY + h - 4.2, z - d * .06);
    for (const tier of [0, 1, 2]) box(w * .69 + .16, .18, d * .72 + .16, 10,
      topX, groundY + lowerH + tier * 4.2, z - d * .06);
    box(w * .25, 1.2, d * .21, 10, topX, groundY + h + .6, z - d * .10);
    contextBuildings.push({ name: `${block.name}_${index + 1}`, meshName: `CityModern_Context_${block.name}`,
      centre: [x, groundY, z], footprint: [w, d], height: h + 1.2,
      ...(block.offscreenReflectionContext ? { offscreenReflectionContext: true } : {}) });
  }
  recordContext(finish(`CityModern_Context_${block.name}`), block.buildings.length);
}

// The distant T junction gives the avenue a believable destination. Its plaza
// covers the unused road continuation behind the turn, far beyond moving traffic.
start();
box(310, .018, 19, 12, 0, groundY - .004, -409);
box(310, .022, 4.4, 10, 0, groundY + .008, -420.7);
for (const side of [-1, 1]) {
  box(145, .022, 4.4, 10, side * 82.5, groundY + .008, -397.3);
  for (let dash = 0; dash < 8; dash++) box(3.5, .022, .1, 10, side * (20 + dash * 15), groundY + .014, -409);
}
box(110, .022, 34, 10, 0, groundY + .008, -440);
recordContext(finish('CityModern_Context_Intersection'), 0);

// Twelve simple asymmetric LED poles. Light emission is visual only, without point lights.
const streetlights = [];
for (const side of [-1, 1]) for (let index = 0; index < 6; index++) {
  start();
  const x = side * 17.1, z = 23 - index * 40;
  box(.32, .22, .32, 6, x, groundY + .11, z);
  box(.14, 7.8, .16, 2, x, groundY + 3.9, z);
  box(2.8, .13, .18, 2, x - side * 1.33, groundY + 7.78, z);
  box(.85, .12, .34, 2, x - side * 2.3, groundY + 7.69, z);
  box(.7, .014, .24, 7, x - side * 2.3, groundY + 7.622, z);
  const name = `CityModern_LED_${side < 0 ? 'W' : 'E'}${index + 1}`;
  finish(name); streetlights.push({ name, position: [x - side * 2.3, groundY + 7.6, z] });
}

scene.updateMatrixWorld(true);
let triangles = 0, primitives = 0;
scene.traverse(node => { if (node.isMesh) { triangles += node.geometry.attributes.position.count / 3; primitives += node.material.length; } });
assert(triangles <= 100000, `Triangle budget exceeded: ${triangles}`);
assert(primitives <= 200, `Primitive budget exceeded: ${primitives}`);
const heroBuildings = buildingRecords.filter(building => building.hero);
const heroWindowCount = heroBuildings.reduce((count, building) => count + building.heroWindowCount, 0);
assert(heroBuildings.length === 2 && heroWindowCount === heroWindowSeeds.size, 'Hero window metadata/UV seed mismatch');
assert(heroBuildings.every(building => building.materialSlots.includes('CityModern_Hero_Glass') &&
  !building.materialSlots.some(name => name.startsWith('CityModern_Glass_Day_') || name.startsWith('Glass_Lit_'))),
'Hero windows must use their single shared opaque material slot');

// CPU visibility checks use the actual fixed camera and the skyline transform
// retained by build_city_lookdev.py. Only solid architecture can satisfy a probe.
const probeCamera = new T.Vector3(26, 37, 42);
const camera = new T.PerspectiveCamera(54, 1280 / 820, .1, 3000);
camera.position.copy(probeCamera); camera.lookAt(-22, 19, -115); camera.updateMatrixWorld(true);
const viewProjection = new T.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
const frustum = new T.Frustum().setFromProjectionMatrix(viewProjection);
const reflectionContext = contextBuildings.filter(building => building.offscreenReflectionContext).map(building => {
  const [x, y, z] = building.centre, [w, d] = building.footprint;
  // The 11 cm allowance encloses the actual projecting floor ribbons/corner strips.
  const bounds = new T.Box3(new T.Vector3(x - w / 2 - .11, y - .0375, z - d / 2 - .11),
    new T.Vector3(x + w / 2 + .11, y + building.height, z + d / 2 + .11));
  assert(!frustum.intersectsBox(bounds), `${building.name} enters the fixed camera frustum`);
  const cornerClips = [];
  for (const cx of [bounds.min.x, bounds.max.x]) for (const cy of [bounds.min.y, bounds.max.y]) {
    for (const cz of [bounds.min.z, bounds.max.z]) {
      const clip = new T.Vector4(cx, cy, cz, 1).applyMatrix4(viewProjection);
      assert(!(clip.w > 0 && Math.abs(clip.x) <= clip.w && Math.abs(clip.y) <= clip.w && Math.abs(clip.z) <= clip.w),
        `${building.name} has a visible corner`);
      cornerClips.push(clip.toArray());
    }
  }
  return { name: building.name, outsideFixedFrustum: true, cornerClips };
});
const reflectionMesh = scene.children.find(mesh => mesh.name === 'CityModern_Context_Reflection');
const reflectionProbes = [[40, 34, 1.96], [-36, 33, 6.62]].map(point => {
  const origin = new T.Vector3(...point), direction = origin.clone().sub(probeCamera).normalize().reflect(new T.Vector3(0, 0, 1));
  const hit = new T.Raycaster(origin, direction, .01, 500).intersectObject(reflectionMesh, false)[0];
  assert(hit, `Hero +Z pane at ${point} has no reflected neighbour`);
  return { pane: point, direction: direction.toArray(), hit: hit.point.toArray(), meshName: hit.object.name };
});
const skylineMeshes = scene.children.filter(mesh => mesh.name.startsWith('CityModern_Skyline'));
for (const mesh of skylineMeshes) {
  mesh.scale.set(.65, 1.5, .60); mesh.position.set(0, -3.45, -120);
}
scene.updateMatrixWorld(true);
const occluders = scene.children.filter(mesh => !mesh.name.includes('_LED_') && !mesh.name.endsWith('_Intersection'));
const visibilityProbes = [];
for (const [kind, xs, z] of [
  ['road_end', [-18, -9, 0, 9, 18], -972.6],
  ['tower_bases', Array.from({ length: 25 }, (_, i) => -300 + i * 25), -1100],
]) {
  for (const x of xs) {
    const target = new T.Vector3(x, groundY, z), direction = target.clone().sub(probeCamera);
    const ray = new T.Raycaster(probeCamera, direction.clone().normalize(), 0, direction.length());
    const hit = ray.intersectObjects(occluders, false)[0];
    assert(hit, `Uncovered ${kind} ground probe at ${x}, ${z}`);
    visibilityProbes.push({ kind, target: target.toArray(), occluder: hit.object.name, hit: hit.point.toArray() });
  }
}
for (const mesh of skylineMeshes) { mesh.scale.set(1, 1, 1); mesh.position.set(0, 0, 0); }
scene.updateMatrixWorld(true);
const glb = await new GLTFExporter().parseAsync(scene, { binary: true });
const bytes = Buffer.from(glb), hash = value => createHash('sha256').update(value).digest('hex');
// Compare data rather than buffer offsets: adding COLOR_0 moves every later
// bufferView, and each material primitive shares the building's full accessors.
function inspectGlb(buffer) {
  const jsonLength = buffer.readUInt32LE(12), json = JSON.parse(buffer.toString('utf8', 20, 20 + jsonLength));
  const binaryStart = 20 + jsonLength + 8, cache = new Map();
  const dimensions = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 };
  const componentBytes = { 5121: 1, 5123: 2, 5125: 4, 5126: 4 };
  function accessorData(index) {
    if (cache.has(index)) return cache.get(index);
    const accessor = json.accessors[index], view = json.bufferViews[accessor.bufferView];
    const elementBytes = dimensions[accessor.type] * componentBytes[accessor.componentType];
    const start = binaryStart + (view.byteOffset || 0) + (accessor.byteOffset || 0);
    const stride = view.byteStride || elementBytes;
    const packed = Buffer.alloc(accessor.count * elementBytes);
    for (let item = 0; item < accessor.count; item++) buffer.copy(packed, item * elementBytes,
      start + item * stride, start + item * stride + elementBytes);
    cache.set(index, packed); return packed;
  }
  function value(index, item, component = 0) {
    const accessor = json.accessors[index], size = componentBytes[accessor.componentType];
    const offset = (item * dimensions[accessor.type] + component) * size, data = accessorData(index);
    return accessor.componentType === 5126 ? data.readFloatLE(offset) : size === 4 ? data.readUInt32LE(offset)
      : size === 2 ? data.readUInt16LE(offset) : data.readUInt8(offset);
  }
  const geometryHash = createHash('sha256');
  for (const node of json.nodes.filter(n => n.mesh !== undefined)) {
    const mesh = json.meshes[node.mesh];
    geometryHash.update(JSON.stringify({ name: node.name, matrix: node.matrix, translation: node.translation,
      rotation: node.rotation, scale: node.scale }));
    for (const [index, primitive] of mesh.primitives.entries()) {
      geometryHash.update(JSON.stringify({ index, mode: primitive.mode, material: json.materials[primitive.material].name }));
      for (const semantic of ['POSITION', 'NORMAL', 'TEXCOORD_0', 'TEXCOORD_1', 'indices']) {
        const accessorIndex = semantic === 'indices' ? primitive.indices : primitive.attributes[semantic];
        assert(accessorIndex !== undefined, `${node.name}: missing ${semantic}`);
        const { componentType, count, type } = json.accessors[accessorIndex];
        geometryHash.update(JSON.stringify({ semantic, componentType, count, type }));
        geometryHash.update(accessorData(accessorIndex));
      }
    }
  }
  return { json, value, geometrySha256: geometryHash.digest('hex'), materialSha256: hash(JSON.stringify(json.materials)) };
}
const previousBytes = baselinePath ? await readFile(baselinePath) : null;
const before = previousBytes ? inspectGlb(previousBytes) : null, after = inspectGlb(bytes);
if (before) {
  assert.equal(after.geometrySha256, before.geometrySha256, 'Night data must not change positions/normals/UVs/indices/material slots');
  assert.equal(after.materialSha256, before.materialSha256, 'Night data must not change daylight materials');
}
const nearNames = buildingRecords.slice(0, buildings.length).map(building => building.name);
const glassNames = new Set([...nearGlassMaterials].map(index => materialSpecs[index][0]));
let actualNearPaneCount = 0, actualHeroPaneCount = 0, actualMin = Infinity, actualMax = -Infinity;
for (const node of after.json.nodes.filter(n => n.mesh !== undefined)) {
  for (const primitive of after.json.meshes[node.mesh].primitives) {
    const color = primitive.attributes.COLOR_0, indices = primitive.indices;
    assert(color !== undefined, `${node.name}: exported COLOR_0 missing`);
    const materialName = after.json.materials[primitive.material].name;
    const isPane = nearNames.includes(node.name) && glassNames.has(materialName);
    const count = after.json.accessors[indices].count;
    if (isPane) {
      assert(count % 6 === 0, 'Glazing must consist of indexed six-vertex panes');
      actualNearPaneCount += count / 6;
      if (materialName === 'CityModern_Hero_Glass') actualHeroPaneCount += count / 6;
    }
    for (let vertex = 0; vertex < count; vertex++) {
      const index = after.value(indices, vertex), first = after.value(indices, Math.floor(vertex / 6) * 6);
      for (let channel = 0; channel < 3; channel++) {
        const rgb = after.value(color, index, channel);
        if (isPane) {
          assert(rgb > .02 && rgb < .9 && rgb === after.value(color, first, channel), 'Pane light must be constant, soft and non-binary');
          actualMin = Math.min(actualMin, rgb); actualMax = Math.max(actualMax, rgb);
        } else assert(rgb === 0, `${node.name}: non-pane geometry must not receive near-office emission`);
      }
    }
  }
}
const continuousOfficeGroups = nightRows.every(row => row.offices.length >= 1 && row.offices.length <= 2
  && row.offices.every(office => office.corePaneCount >= 3 && office.corePaneCount <= 8
    && office.endBay - office.startBay + 1 === office.corePaneCount
    && office.startBay >= 0 && office.endBay < row.bays
    && office.edgeTransitionPanes >= 1 && office.edgeTransitionPanes <= 2));
const maxAdjacentChannelDifference = Math.max(...nightRows.map(row => row.maxAdjacentChannelDifference));
assert(continuousOfficeGroups && maxAdjacentChannelDifference < .36, 'Office rows contain isolated/binary window changes');
assert(actualNearPaneCount === nightPaneCount && actualHeroPaneCount === nightHeroPaneCount && nightHeroPaneCount === heroWindowCount);
assert(nightRows.reduce((count, row) => count + row.bays, 0) === actualNearPaneCount);
const sha256 = hash(bytes);
const nightLighting = {
  version: 'city-office-light-v1', colorSpace: 'linear RGB', buildingNames: nearNames,
  allNearPaneCount: actualNearPaneCount, heroPaneCount: actualHeroPaneCount,
  shaderInterface: 'Use COLOR_0 RGB only for Night emission, calibrated by the shared OFFICE_LIGHT_GAIN authored in the native UE material builder; do not multiply it into BaseColor. Every pane is constant across its six vertices. All other geometry has black COLOR_0.',
  layout: 'One or two contiguous 3–8-pane office cores per facade floor, with 1–2 panes of spill transition. Irregular 2–4-floor groups share a layout and warm-neutral tint; each floor varies gently. Inactive areas retain low borrowed light. Legacy lit material selection no longer determines lighting.',
  facesFloors: nightRows,
  checks: { passed: true, allPanesHaveColor: true, paneColorsConstant: true, nonGlassBlack: true,
    continuousOfficeGroups, maxAdjacentChannelDifference, actualColorRange: [actualMin, actualMax],
    floorGroupSpanRange: [2, 4], rowCount: nightRows.length },
  exportedChecks: { passed: true, allPrimitivesHaveColor0: true, actualNearPaneCount, actualHeroPaneCount,
    baselineCompared: Boolean(before), baselinePath: baselinePath ?? null,
    geometryUnchanged: before ? true : null, materialsUnchanged: before ? true : null, beforeGeometrySha256: before?.geometrySha256 ?? null,
    afterGeometrySha256: after.geometrySha256, beforeMaterialSha256: before?.materialSha256 ?? null,
    afterMaterialSha256: after.materialSha256, comparedSemantics: ['POSITION', 'NORMAL', 'TEXCOORD_0', 'TEXCOORD_1', 'indices', 'material slots', 'node transforms'],
    previousGlbSha256: previousBytes ? hash(previousBytes) : null, glbSha256: sha256 },
  sourceGeometry: { file: 'modern-city.glb', sha256 },
};
await mkdir(output, { recursive: true });
await writeFile(new URL('modern-city.glb', output), bytes);
const metadata = {
  name: 'Original Modern Avenue Architecture', file: 'modern-city.glb', generator: 'unreal/Scripts/prepare_modern_city.mjs',
  source: 'Original procedural geometry authored for OutOfWindow; no downloaded assets or textures.',
  license: 'CC0-1.0', licenseUrl: 'https://creativecommons.org/publicdomain/zero/1.0/',
  units: 'metres', groundY, axes: { up: '+Y', avenue: 'Z', unrealImport: 'glTF (x, y, z) maps to UE (x, z, y).' },
  buildings: buildingRecords, nearBuildingCount: buildings.length, skylineBuildingCount: skyline.length,
  heroBuildingNames, heroWindowCount, nightLighting,
  uv: { channels: ['UV0 / glTF TEXCOORD_0', 'UV1 / glTF TEXCOORD_1'],
    uv0: 'Native source UV0 retained for every vertex; each complete hero pane covers 0..1 independently.',
    uv1: 'Every vertex has UV1. For hero glazing UV1.x is one deterministic unique 0..1 seed shared by all six vertices of a pane; other geometry uses x=0. Authoring y=0 is unused because UE may invert V.',
    heroMaterial: 'CityModern_Hero_Glass', purpose: 'Stable per-pane opaque reflection/roughness variation; no interior geometry or imagery.',
    heroSeedRange: [Math.min(...heroWindowSeeds), Math.max(...heroWindowSeeds)], uniqueHeroSeeds: heroWindowSeeds.size },
  contextBuildings, contextBuildingCount: contextBuildings.length, contextGroups, contextMeshCount: contextGroups.length,
  visibility: { camera: probeCamera.toArray(), target: [-22, 19, -115], solidGroundProbes: visibilityProbes,
    offscreenReflectionContext: reflectionContext, reflectionProbes,
    note: 'CPU geometry ray tests, not a substitute for the final Unreal screenshot. Existing skyline actor scale/translation included.' },
  streetlights, triangles, meshCount: scene.children.length, primitives, bytes: glb.byteLength,
  materials: materialSpecs.map(([name, color, roughness, metalness, emissive = 0, emissiveIntensity = 0]) => ({ name, color, roughness, metalness, emissive, emissiveIntensity, opaque: true })),
  lighting: 'All near glazing uses linear COLOR_0 RGB for coherent warm-neutral floor offices at night. Legacy Glass_Lit material assignment retains its daylight appearance only. Hero UV1.x still provides unchanged reflection variation. Distant continuous skins and other geometry have black COLOR_0. CityModern_LED identifies streetlights; no real lights are embedded.',
  design: 'B01 and B07 feature beveled slim floor bands/corner trims, deeper opaque glazing, subdued terrace decks, thin rails, irregular low-poly shrub clusters and four benches. Eighteen skyline towers retain upper sky gaps; eighteen context buildings fill their bases in four batches, plus the distant T junction. Two additional offscreen neighbours behind the camera form a fifth context building batch and supply real reflection geometry. They remain opaque, normally visible and shadow-casting; no hidden-in-game or reflection-only geometry is used. Shared material primitives are merged.',
};
await writeFile(new URL('modern-city.json', output), JSON.stringify(metadata, null, 2) + '\n');
console.log(JSON.stringify({ triangles, meshes: scene.children.length, primitives, bytes: glb.byteLength,
  buildings: buildingRecords.length + contextBuildings.length, nearBuildings: buildings.length, skylineBuildings: skyline.length,
  contextBuildings: contextBuildings.length, contextMeshes: contextGroups.length, solidGroundProbes: visibilityProbes.length,
  streetlights: streetlights.length, heroBuildingNames, heroWindowCount, offscreenReflectionBuildings: reflectionContext.length,
  nightLighting: { version: nightLighting.version, allNearPaneCount: actualNearPaneCount, heroPaneCount: actualHeroPaneCount,
    floorFaces: nightRows.length, maxAdjacentChannelDifference, colorRange: [actualMin, actualMax],
    baselineCompared: Boolean(before), geometryUnchanged: before ? true : null, sha256 },
  heroWindows: heroBuildings.map(({ name, heroWindowCount }) => ({ name, heroWindowCount })) }, null, 2));
