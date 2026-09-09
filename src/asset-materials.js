import { toCreasedNormals } from 'three/addons/utils/BufferGeometryUtils.js';

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
  const isWall = /^(MASTER_Concrete|MASTER_Brick|Concrete|Plaster|Balcony_Concrete)/i.test(name);
  const isPavement = /^Pavement_/i.test(name) && !/manhole/i.test(name);
  // The Bistro glTF carries base-color and normal maps, but no ORM/AO maps.
  // Keep the semantic flags on the material so RainResponse can supply the
  // missing fine-scale response in its shader instead of treating every
  // surface as a generic wall.
  if (isWall) {
    material.userData.bistroWallSurface = true;
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

export function updateBistroWeather(material, rain, night) {
  // Wetness is spatial and persistent, applied by RainResponse in the shader.
  if (material.userData.nightEmission) material.emissiveIntensity = .015 + night * 2.4;
}
