import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { openSync, readSync, closeSync, readFileSync } from 'node:fs';
import * as THREE from 'three';
import { calibrateBistroMaterial } from '../src/asset-materials.js';

const assets = new URL('../public/assets/orca/bistro/', import.meta.url);
const readJson = url => JSON.parse(readFileSync(url, 'utf8'));

function readGlbJson(url) {
  const fd = openSync(url, 'r');
  try {
    const header = Buffer.alloc(20);
    readSync(fd, header, 0, header.length, 0);
    assert.equal(header.toString('ascii', 0, 4), 'glTF');
    const json = Buffer.alloc(header.readUInt32LE(12));
    readSync(fd, json, 0, json.length, 20);
    return JSON.parse(json.toString());
  } finally {
    closeSync(fd);
  }
}

test('Dark details share the existing building-details textures', () => {
  const hash = name => createHash('sha256').update(readFileSync(new URL(name, assets))).digest('hex');
  for (const channel of ['BaseColor', 'Normal']) {
    assert.equal(hash(`MASTER_Details_Dark_${channel}.png`), hash(`MASTER_Building_Details_${channel}.png`));
  }
});

test('Restored dark-detail geometry retains its atlas instead of concrete', () => {
  const source = readJson(new URL('bistro-exterior.gltf', assets));
  const near = readGlbJson(new URL('bistro-exterior-near-768.glb', assets));
  const restored = new Set(readJson(new URL('../docs/alley-photoreal/near-geometry.json', import.meta.url)).meshes.map(mesh => mesh.name));
  const targetNodes = new Map(near.nodes.map(node => [node.name, node]));
  let checked = 0;
  for (const node of source.nodes) {
    if (node.mesh === undefined || !restored.has(node.name)) continue;
    source.meshes[node.mesh].primitives.forEach((primitive, index) => {
      if (source.materials[primitive.material].name !== 'MASTER_Details_Dark') return;
      const target = near.meshes[targetNodes.get(node.name).mesh].primitives[index];
      assert.equal(near.materials[target.material].name, 'MASTER_Building_Details', node.name);
      checked++;
    });
  }
  assert.ok(checked > 0, 'The regression must cover restored dark-detail geometry');
});

test('Architectural glass is restrained while streetlights retain night emission', () => {
  for (const name of ['MASTER_Glass_Dirty', 'MASTER_Glass_Clean', 'MASTER_Glass_Exterior', 'MASTER_Focus_Glass', 'MASTER_Frosted_Glass']) {
    const material = new THREE.MeshStandardMaterial({ name, emissive: 0x777777 });
    calibrateBistroMaterial(material);
    assert.equal(material.emissive.getHex(), 0, name);
    if (name === 'MASTER_Glass_Dirty') assert.ok(material.color.r < .1 && material.color.g < .1 && material.color.b < .1);
  }
  const lamp = new THREE.MeshStandardMaterial({ name: 'Streetlight_Glass' });
  calibrateBistroMaterial(lamp);
  assert.equal(lamp.userData.nightEmission, true);
  assert.notEqual(lamp.emissive.getHex(), 0);
});
