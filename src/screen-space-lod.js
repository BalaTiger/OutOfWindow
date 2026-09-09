import * as THREE from 'three';

// LOD controller for fixed-window scenes. It deliberately does not use
// THREE.LOD.position: large imported buildings often have an origin far from
// the visible facade, so the decision is based on the cluster's world bounds.
export class ScreenSpaceLodManager {
  constructor() {
    this.entries = [];
    this.frustum = new THREE.Frustum();
    this.projectionView = new THREE.Matrix4();
    this.lastUpdate = -Infinity;
    this.dirty = true;
  }

  registerCluster(id, nearNodes, farNodes) {
    const near = nearNodes.filter(Boolean);
    const far = farNodes.filter(Boolean);
    if (!near.length || !far.length) return;
    this.entries.push({ id, near, far, level: 'near', box: new THREE.Box3(), sphere: new THREE.Sphere() });
    this.setVisible(this.entries.at(-1), 'near');
    this.dirty = true;
  }

  markDirty() { this.dirty = true; }

  setVisible(entry, level) {
    entry.near.forEach(node => { node.visible = level === 'near'; });
    entry.far.forEach(node => { node.visible = level !== 'near'; });
    entry.level = level;
  }

  wantedLevel(entry, pixels) {
    if (entry.level === 'near') return pixels < 80 ? 'far' : 'near';
    return pixels > 110 ? 'near' : 'far';
  }

  update(camera, viewportHeight, elapsed = 0, force = false) {
    if (!force && !this.dirty && elapsed - this.lastUpdate < .1) return;
    this.lastUpdate = elapsed;
    this.dirty = false;
    camera.updateMatrixWorld(true);
    this.projectionView.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this.frustum.setFromProjectionMatrix(this.projectionView);
    const focalPixels = viewportHeight / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
    for (const entry of this.entries) {
      entry.box.makeEmpty();
      entry.near.forEach(node => {
        node.updateWorldMatrix(true, false);
        entry.box.expandByObject(node);
      });
      if (entry.box.isEmpty()) continue;
      entry.box.getBoundingSphere(entry.sphere);
      if (!this.frustum.intersectsBox(entry.box)) {
        entry.near.forEach(node => { node.visible = false; });
        entry.far.forEach(node => { node.visible = false; });
        continue;
      }
      const viewCenter = entry.sphere.center.clone().applyMatrix4(camera.matrixWorldInverse);
      const depth = Math.max(-viewCenter.z - entry.sphere.radius, camera.near);
      const pixels = entry.sphere.radius * focalPixels / Math.max(depth, .01);
      this.setVisible(entry, this.wantedLevel(entry, pixels));
    }
  }
}
