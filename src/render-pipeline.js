import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { FXAAShader } from 'three/addons/shaders/FXAAShader.js';

export const RENDER_QUALITY = {
  eco: { label: '节能', pixelRatio: 1, ao: false, aoScale: .5 },
  balanced: { label: '均衡', pixelRatio: 1.25, ao: true, aoScale: .65 },
  high: { label: '精细', pixelRatio: 1.65, ao: true, aoScale: 1 },
};

export class RenderPipeline {
  constructor(renderer, scene, camera) {
    this.renderer = renderer;
    this.composer = new EffectComposer(renderer);
    for (const target of [this.composer.renderTarget1, this.composer.renderTarget2]) {
      target.depthTexture = new THREE.DepthTexture(target.width, target.height, THREE.UnsignedIntType);
    }
    this.composer.addPass(new RenderPass(scene, camera));
    this.ao = new GTAOPass(scene, camera);
    this.ao.updateGtaoMaterial({ radius: 1.3, thickness: 1, distanceFallOff: .8, samples: 16 });
    this.ao.updatePdMaterial({ radius: 5, depthPhi: 2, normalPhi: 3, samples: 8 });
    this.ao.blendIntensity = .55;
    // Reconstruct normals from the beauty depth. This preserves alpha-tested
    // foliage and avoids drawing every building again with an override material.
    const renderAO = this.ao.render.bind(this.ao);
    this.ao.setGBuffer(this.composer.readBuffer.depthTexture);
    this.ao.gtaoMaterial.needsUpdate = this.ao.pdMaterial.needsUpdate = true;
    this.ao.render = (renderer, write, read, ...args) => {
      this.ao.setGBuffer(read.depthTexture);
      renderAO(renderer, write, read, ...args);
    };
    this.composer.addPass(this.ao);
    this.composer.addPass(new OutputPass());
    this.fxaa = new ShaderPass(FXAAShader);
    this.composer.addPass(this.fxaa);
  }

  resize(width, height, quality) {
    const preset = RENDER_QUALITY[quality];
    const dpr = Math.min(devicePixelRatio, preset.pixelRatio);
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(width, height, false);
    this.composer.setPixelRatio(dpr);
    this.composer.setSize(width, height);
    this.ao.enabled = preset.ao;
    this.ao.setSize(Math.max(1, Math.round(width*dpr*preset.aoScale)), Math.max(1, Math.round(height*dpr*preset.aoScale)));
    this.fxaa.material.uniforms.resolution.value.set(1/(width*dpr), 1/(height*dpr));
  }

  render(dt) { this.composer.render(dt); }
}
