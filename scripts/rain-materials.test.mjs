import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';
import { calibrateBistroMaterial } from '../src/asset-materials.js';
import { RainResponse } from '../src/rain-response.js';

test('different rain shader variants cannot share a material program cache entry', () => {
  const response = new RainResponse();
  const programs = new Map();
  for (const name of ['MASTER_Brick_01', 'MASTER_Brick_02', 'MASTER_Concrete_Plaster', 'Pavement_01', 'Wood', 'Fabric', 'Foliage_Leaves']) {
    const material = new THREE.MeshStandardMaterial({ name });
    calibrateBistroMaterial(material);
    response.attachSurface(material);
    const shader = { ...THREE.ShaderLib.standard, uniforms: {} };
    material.onBeforeCompile(shader);
    const key = material.customProgramCacheKey();
    if (programs.has(key)) assert.equal(shader.fragmentShader, programs.get(key), `${name} collides with a different shader`);
    else programs.set(key, shader.fragmentShader);
    material.dispose();
  }
  assert.equal(programs.size, 6, 'only the two brick materials should share a shader');
  response.reflector.getRenderTarget().dispose();
  response.reflector.geometry.dispose();
  response.reflector.material.dispose();
  response.neutral.dispose();
});

test('puddles retain lit paving and introduce no light of their own', () => {
  const response = new RainResponse();
  const material = new THREE.MeshStandardMaterial({ name: 'Pavement_01' });
  calibrateBistroMaterial(material);
  response.attachSurface(material);
  const shader = { ...THREE.ShaderLib.standard, uniforms: {} };
  material.onBeforeCompile(shader);
  // The final blend is component-wise: execute one grayscale channel of the
  // actual shader expression, so a fixed ambient tint fails this regression.
  const expression = shader.fragmentShader.match(/vec3 waterLight=([^;]+);/)[1];
  const waterLight = new Function('totalDiffuse', 'reflectionWeight', 'reflected', 'reflectedLight', 'totalEmissiveRadiance', `return ${expression};`);
  assert.equal(waterLight(0, .12, 0, { directSpecular: 0 }, 0), 0);
  assert.ok(waterLight(1, .12, 0, { directSpecular: 0 }, 0) > .5, 'face-on water must preserve the lit stone below');
  const light = [0.3, 0.2, 0.1];
  const sample = scale => waterLight(light[0] * scale, .12, light[1] * scale, { directSpecular: light[2] * scale }, 0);
  assert.ok(Math.abs(sample(2) - sample(1) * 2) < 1e-12, 'water must respond to incident illumination');
  response.reflector.getRenderTarget().dispose();
  response.reflector.geometry.dispose();
  response.reflector.material.dispose();
  response.neutral.dispose();
  material.dispose();
});
