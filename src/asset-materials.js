import * as THREE from 'three';
import { toCreasedNormals } from 'three/addons/utils/BufferGeometryUtils.js';
import { BISTRO_REAL_PBR } from './bistro-pbr-config.js';

// Repair only masonry: imported normals can point almost sideways on flat walls.
// Keep texture UVs and a 35-degree crease so bevels stay smooth and corners stay hard.
export function repairBistroWallNormals(mesh) {
  const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  if (!materials.every(m=>/^(MASTER_Concrete|MASTER_Brick|Concrete|Plaster|Balcony_Concrete)/i.test(m.name))) return false;
  mesh.geometry = toCreasedNormals(mesh.geometry, 35*Math.PI/180);
  // Existing tangents describe the old normals. Let the shader derive the new basis.
  mesh.geometry.deleteAttribute('tangent');
  mesh.userData.wallNormalsRepaired = true;
  return true;
}

// Conservative semantic repairs for the legacy OBJ -> glTF Bistro conversion.
// These scalar estimates are a fallback until original ORM textures are restored.
export function calibrateBistroMaterial(material) {
  const name = material.name || '';
  const isBrick = /^(MASTER_Brick_|MASTER_Concrete_Grooved|MASTER_Concrete1$|Concrete3$)/i.test(name);
  const isPlaster = /^(MASTER_Concrete_Smooth|MASTER_Concrete_Plaster|MASTER_Concrete_White|MASTER_Concrete_Yellow|Balcony_Concrete|Plaster)/i.test(name);
  const isWall = isBrick || isPlaster || /^(MASTER_Concrete|MASTER_Brick|Concrete|Plaster|Balcony_Concrete)/i.test(name);
  const isPavement = /^Pavement_/i.test(name) && !/manhole/i.test(name);
  // The Bistro glTF carries base-color and normal maps, but no ORM/AO maps.
  // Keep the semantic flags on the material so RainResponse can supply the
  // missing fine-scale response in its shader instead of treating every
  // surface as a generic wall.
  if (isWall) {
    material.userData.bistroWallSurface = true;
    material.userData.bistroBrickSurface = isBrick;
    material.userData.bistroPlasterSurface = isPlaster || !isBrick;
    material.roughness = Math.max(material.roughness ?? 0.82, 0.76);
  }
  if (isPavement) {
    material.userData.bistroGroundSurface = true;
    material.roughness = Math.max(material.roughness ?? 0.86, 0.82);
  }
  if (/glass/i.test(name)) {
    material.metalness = 0;
    material.roughness = /frosted|dirty/i.test(name) ? .32 : .12;
    material.envMapIntensity = 1.05;
    if (/MASTER_Frosted_Glass/.test(name)) material.color.set(0xa5b3ad);
  } else if (/metal|manhole/i.test(name)) {
    material.metalness = /paint/i.test(name) ? .05 : .75;
    material.roughness = .38;
  } else if (/fabric|awning/i.test(name)) {
    material.metalness = 0;
    material.roughness = .92;
  }
  if (/^Foliage_/i.test(name) && material.transparent && material.map) {
    // Leaves are opaque cutouts. Sorted alpha blending stacks wet highlights
    // across many cards and makes the canopy look pale and translucent.
    material.alphaTest = .35;
    material.transparent = false;
    material.depthWrite = true;
  }
  if (/railing|forge_metal/i.test(name) && material.map) {
    // Keep alpha-cutout texture: removing it turns ironwork into solid panels.
    material.alphaTest = .5;
    material.transparent = false;
    material.depthWrite = true;
  }
  if (isPavement) {
    material.userData.rainSurface = {
      color: material.color.clone(), roughness: material.roughness,
      normalScale: material.normalScale?.clone(),
    };
  }
  if (/light_bulb|^Streetlight_Glass$|^Paris_StringLights_/i.test(name)) {
    material.emissive.set(0xffd6a0);
    material.emissiveMap = material.map;
    material.userData.nightEmission = true;
  }
  material.needsUpdate = true;
}

// The licensed Bistro conversion contains color and normal maps only. Until
// the optional CC0 pack is downloaded, generated grayscale channels are loaded
// beside the GLB and used as genuine roughness/AO/bump inputs.
export function loadBistroPbrChannels(material, loader, anisotropy = 4) {
  const isWall = material.userData.bistroWallSurface === true;
  const isGround = material.userData.bistroGroundSurface === true;
  if ((!isWall && !isGround) || !material.name) return Promise.resolve(false);
  const realBase = isGround ? BISTRO_REAL_PBR.ground : BISTRO_REAL_PBR.wall;
  const base = BISTRO_REAL_PBR.enabled ? realBase : `./assets/orca/bistro/pbr/${encodeURIComponent(material.name)}`;
  const prepareTexture = (texture, colorSpace = THREE.NoColorSpace) => {
    texture.colorSpace = colorSpace;
    texture.flipY = material.map?.flipY ?? false;
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.anisotropy = anisotropy;
    if (material.map) {
      texture.repeat.copy(material.map.repeat);
      texture.offset.copy(material.map.offset);
      texture.center.copy(material.map.center);
      texture.rotation = material.map.rotation;
      texture.updateMatrix();
    }
    return texture;
  };
  const load = (suffix, assign) => new Promise(resolve => {
    const filename = BISTRO_REAL_PBR.enabled
      ? ({ Diffuse: 'diff.jpg', Normal: 'nor_gl.jpg', Roughness: 'arm.jpg', AO: 'arm.jpg', Height: 'disp.jpg' }[suffix])
      : `${base}_${suffix}.png`;
    loader.load(BISTRO_REAL_PBR.enabled ? `${base}/${filename}` : filename, texture => {
      assign(prepareTexture(texture, suffix === 'Diffuse' ? THREE.SRGBColorSpace : THREE.NoColorSpace));
      resolve(true);
    }, undefined, () => resolve(false));
  });
  const channels = [
    ...(BISTRO_REAL_PBR.enabled ? [
      load('Diffuse', texture => { material.map = texture; }),
      load('Normal', texture => { material.normalMap = texture; }),
    ] : []),
    load('Roughness', texture => { material.roughnessMap = texture; }),
    load('AO', texture => {
      material.aoMap = texture;
      // The derived AO is a restrained contact-detail estimate from base color,
      // not a baked lightmap. Keep it subtle so it cannot blacken the façade.
      material.aoMapIntensity = isGround ? .28 : .18;
    }),
    load('Height', texture => {
      material.bumpMap = texture;
      material.bumpScale = isGround ? .028 : .012;
    }),
  ];
  return Promise.all(channels).then(results => {
    material.userData.bistroPbrChannels = results.filter(Boolean).length;
    material.needsUpdate = true;
    return results.some(Boolean);
  });
}

export function updateBistroWeather(material, rain, night) {
  // Wetness is spatial and persistent, applied by RainResponse in the shader.
  if (material.userData.nightEmission) {
    const lampNight = THREE.MathUtils.smoothstep(.58, .86, night);
    material.emissiveIntensity = .015 + lampNight * 1.55;
  }
}
