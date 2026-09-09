import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { Water } from 'three/addons/objects/Water.js';
import { MATERIAL_PROFILES, SCENE_PACK, SCENE_VIEWS } from './scene-pack.js';
import { createAtmosphere } from './atmosphere.js';
import { RenderPipeline, RENDER_QUALITY } from './render-pipeline.js';
import { calibrateBistroMaterial, updateBistroWeather, repairBistroWallNormals } from './asset-materials.js';
import { solarPosition, localCalendar, periodName } from './solar-time.js';
import { RainResponse } from './rain-response.js';
import './styles.css';

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const lerp = (a, b, t) => a + (b - a) * t;
const smoothstep = (a, b, x) => {
  const t = clamp((x - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};

function seededRandom(seed = 1) {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

const SCENES = {
  city: { index: '01 / 05', title: '都市', description: '沿着开阔的街道望去，楼群与远处天光慢慢铺开。', accent: 0xa6c7d5 },
  alley: { index: '02 / 05', title: '后巷', description: '石板路转过街角，红色雨篷与窗灯陪着一天流逝。', accent: 0xc9ad92 },
  village: { index: '03 / 05', title: '雾隐村庄', description: '田埂与屋瓦顺着山势铺开，晨雾在低处缓缓散去。', accent: 0xb4c990 },
  forest: { index: '04 / 05', title: '深山呼吸', description: '林冠随风轻摆，溪水穿过长满苔藓的岩石。', accent: 0x7fa38a },
  coast: { index: '05 / 05', title: '潮汐海岸', description: '海面收集天光，潮线与沿海公路一起延伸向远方。', accent: 0x79b8c7 },
};

const WMO = {
  0: ['晴朗', '☀'], 1: ['大致晴朗', '◐'], 2: ['局部多云', '◒'], 3: ['阴天', '☁'],
  45: ['有雾', '≋'], 48: ['冻雾', '≋'],
  51: ['小毛毛雨', '⌁'], 53: ['毛毛雨', '⌁'], 55: ['较强毛毛雨', '⌁'],
  61: ['小雨', '⌁'], 63: ['中雨', '⌁'], 65: ['大雨', '⌁'],
  71: ['小雪', '✣'], 73: ['中雪', '✣'], 75: ['大雪', '✣'], 77: ['米雪', '✣'],
  80: ['阵雨', '⌁'], 81: ['较强阵雨', '⌁'], 82: ['强阵雨', '⌁'],
  85: ['阵雪', '✣'], 86: ['强阵雪', '✣'],
  95: ['雷暴', 'ϟ'], 96: ['雷暴伴冰雹', 'ϟ'], 99: ['强雷暴', 'ϟ'],
};

function weatherModeFromCode(code) {
  if ([45, 48].includes(code)) return 'fog';
  if ([71, 73, 75, 77, 85, 86].includes(code)) return 'snow';
  if ([51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99].includes(code)) return 'rain';
  return 'clear';
}

class LivingWorld {
  constructor(canvas) {
    this.canvas = canvas;
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x7c91a0, 0.007);
    this.camera = new THREE.PerspectiveCamera(48, innerWidth / innerHeight, 0.1, 450);
    this.camera.position.set(0, 9, 22);
    this.cameraTarget = new THREE.Vector3(0, 3.5, -22);
    this.camera.lookAt(this.cameraTarget);
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.65));
    // CSS owns the canvas display size; only size the WebGL drawing buffer here.
    this.renderer.setSize(innerWidth, innerHeight, false);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.shadowMap.autoUpdate = false;
    this.renderer.toneMapping = THREE.AgXToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.info.autoReset = false;
    this.quality = 'balanced';
    this.pipeline = new RenderPipeline(this.renderer, this.scene, this.camera);

    this.clock = new THREE.Clock();
    this.groups = {};
    this.cars = [];
    this.swayGroups = [];
    this.lightMaterials = [];
    this.waveMaterials = [];
    this.waterSurfaces = [];
    this.animatedWaterMaterials = [];
    this.surfaceMaterials = [];
    this.bistroMaterials = new Set();
    this.rainResponse = new RainResponse();
    this.urbanWindowMaterials = new Map();
    this.streetLights = [];
    this.cloudMeshes = [];
    this.activeScene = 'city';
    this.hour = 19.7;
    this.weather = 'clear';
    this.weatherData = { cloudCover: 35, windSpeed: 8, precipitation: 0 };
    this.location = { latitude: 31.23, longitude: 121.47, timezone: 'Asia/Shanghai' };
    this.frameSamples = [];
    this.dynamicEnvironmentDirty = true;
    this.dynamicEnvironmentPending = false;
    this.nextEnvironmentUpdate = 0;
    this.preloadExpectedRegistered = false;
    this.preloadFinished = false;
    this.preloadPromise = new Promise(resolve => { this.resolvePreload = resolve; });
    this.setBootProgress('resource', 2, '正在建立场景资源队列…');
    if (import.meta.env.DEV) {
      window.__livingWorld = this;
      window.__THREE = THREE;
    }

    this.makeLights();
    this.setupDynamicEnvironment();
    this.makeMaterialLibrary();
    this.makePhysicalGlass();
    this.makeSky();
    this.makeClouds();
    this.buildScenes();
    this.loadHeroAssets();
    this.makeWeather();
    this.switchScene('city', false);
    this.bindEvents();
    this.applyAtmosphere();
    this.animate();
  }

  makeLights() {
    this.hemisphere = new THREE.HemisphereLight(0xa9c8db, 0x18231f, .12);
    this.scene.add(this.hemisphere);
    this.sun = new THREE.DirectionalLight(0xffe1b2, 3.2);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.camera.left = -95;
    this.sun.shadow.camera.right = 95;
    this.sun.shadow.camera.top = 70;
    this.sun.shadow.camera.bottom = -45;
    this.sun.shadow.camera.near = 1;
    this.sun.shadow.camera.far = 260;
    this.sun.shadow.bias = -0.00008;
    this.sun.shadow.normalBias = .055;
    this.scene.add(this.sun, this.sun.target);
    this.sun.target.position.set(0, 0, -25);
    this.fillLight = new THREE.DirectionalLight(0x7896c8, .35);
    this.fillLight.position.set(-25, 35, 20);
    this.scene.add(this.fillLight);
  }

  setupDynamicEnvironment() {
    this.environmentTarget = new THREE.WebGLCubeRenderTarget(128, {
      type: THREE.HalfFloatType,
      generateMipmaps: true,
      minFilter: THREE.LinearMipmapLinearFilter,
    });
    this.environmentCamera = new THREE.CubeCamera(.5, 300, this.environmentTarget);
    this.environmentCamera.position.set(0, 12, -18);
    this.scene.add(this.environmentCamera);
    this.pmrem = new THREE.PMREMGenerator(this.renderer);
    this.pmrem.compileCubemapShader();
    document.documentElement.dataset.environment = 'runtime-capture-pending';
  }

  makeMaterialLibrary() {
    const loader = new THREE.TextureLoader();
    const anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy());
    const loadTexture = (url, color = false, repeat = [1, 1]) => {
      const texture = loader.load(url, () => { this.dynamicEnvironmentDirty = true; });
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
      texture.repeat.set(...repeat);
      texture.anisotropy = anisotropy;
      if (color) texture.colorSpace = THREE.SRGBColorSpace;
      return texture;
    };
    this.materialLibrary = {};
    Object.entries(MATERIAL_PROFILES).forEach(([name, profile]) => {
      const params = { ...profile };
      delete params.asset; delete params.repeat; delete params.normalScale; delete params.wet;
      if (profile.asset) {
        const base = `./assets/polyhaven/materials/${profile.asset}`;
        params.map = loadTexture(`${base}/diffuse.jpg`, true, profile.repeat);
        params.normalMap = loadTexture(`${base}/normal.jpg`, false, profile.repeat);
        params.roughnessMap = loadTexture(`${base}/roughness.jpg`, false, profile.repeat);
        if (profile.displacementScale !== undefined) {
          params.displacementMap = loadTexture(`${base}/displacement.jpg`, false, profile.repeat);
        }
        params.normalScale = new THREE.Vector2(profile.normalScale, profile.normalScale);
      }
      const material = new THREE.MeshPhysicalMaterial(params);
      material.userData.profile = name;
      material.userData.baseRoughness = profile.roughness ?? .5;
      material.userData.baseClearcoat = profile.clearcoat ?? 0;
      material.userData.baseEnvMapIntensity = profile.envMapIntensity ?? 1;
      this.materialLibrary[name] = material;
      if (!['architecturalGlass','paintedMetal'].includes(name)) this.rainResponse.attachSurface(material);
      this.surfaceMaterials.push(material);
    });
    document.documentElement.dataset.materialProfiles = Object.keys(this.materialLibrary).join(',');
    document.documentElement.dataset.scenePackStyle = SCENE_PACK.style;
  }

  setBootProgress(stage, percent, detail) {
    const labels = { resource: '加载场景资源', shader: '预编译材质与着色器', ready: '窗景已准备' };
    document.documentElement.dataset.preloadStage = stage;
    document.documentElement.dataset.preloadProgress = String(Math.round(percent));
    const label = document.querySelector('#bootStage');
    const detailNode = document.querySelector('#bootDetail');
    const bar = document.querySelector('#bootProgressBar');
    if (label) label.textContent = labels[stage] || stage;
    if (detailNode) detailNode.textContent = detail;
    if (bar) bar.style.width = `${Math.max(2, Math.min(100, percent))}%`;
  }

  updateBootResourceProgress() {
    const states = Object.values(this.assetStatus || {});
    const total = states.reduce((sum, state) => sum + state.total, 0);
    const complete = states.reduce((sum, state) => sum + state.loaded + state.failed, 0);
    const failed = states.reduce((sum, state) => sum + state.failed, 0);
    const percent = total ? 5 + complete / total * 72 : 5;
    this.setBootProgress('resource', percent, failed ? `场景资源 ${complete}/${total} · ${failed} 项失败` : `场景资源 ${complete}/${total}`);
    if (!this.preloadExpectedRegistered || this.preloadFinished || !total || complete < total) return;
    this.preloadFinished = true;
    document.documentElement.dataset.preloadAssets = 'ready';
    this.warmupPrograms().then(() => {
      document.documentElement.dataset.preloadComplete = 'true';
      this.setBootProgress('ready', 100, failed ? '部分资源失败，已使用可用场景继续' : '场景、材质和着色器已就绪');
      this.resolvePreload?.();
      setTimeout(() => document.querySelector('#bootLoader')?.classList.add('ready'), 350);
    }).catch(error => {
      console.error('Shader warmup failed', error);
      document.documentElement.dataset.preloadComplete = 'true';
      this.setBootProgress('ready', 100, '着色器预编译跳过，已进入窗景');
      this.resolvePreload?.();
      setTimeout(() => document.querySelector('#bootLoader')?.classList.add('ready'), 350);
    });
  }

  async warmupPrograms() {
    this.setBootProgress('shader', 80, '正在编译共享 PBR、雨景和环境着色器…');
    const saved = {
      activeScene: this.activeScene,
      cameraPosition: this.camera.position.clone(),
      cameraTarget: this.cameraTarget.clone(),
      fov: this.camera.fov,
      visibility: Object.entries(this.groups).map(([name, group]) => [name, group.visible]),
    };
    try {
      Object.values(this.groups).forEach(group => { group.visible = true; group.updateWorldMatrix(true, true); });
      for (const view of Object.values(SCENE_VIEWS)) {
        this.camera.position.fromArray(view.position);
        this.camera.lookAt(new THREE.Vector3(...view.target));
        this.camera.fov = view.fov;
        this.camera.updateProjectionMatrix();
        if (this.renderer.compileAsync) await this.renderer.compileAsync(this.scene, this.camera);
        else this.renderer.compile(this.scene, this.camera);
      }
      this.setBootProgress('shader', 96, '共享着色器编译完成，正在恢复首个场景…');
    } finally {
      saved.visibility.forEach(([name, visible]) => { this.groups[name].visible = visible; });
      this.activeScene = saved.activeScene;
      this.camera.position.copy(saved.cameraPosition);
      this.cameraTarget.copy(saved.cameraTarget);
      this.camera.fov = saved.fov;
      this.camera.updateProjectionMatrix();
      this.camera.lookAt(this.cameraTarget);
      this.scheduleEnvironmentUpdate(.12);
    }
  }

  materialFor(profileName, tint) {
    const source = this.materialLibrary[profileName];
    if (!source) return this.mat(tint ?? 0x888888);
    const material = source.clone();
    if (!['architecturalGlass','paintedMetal'].includes(profileName)) this.rainResponse.attachSurface(material);
    material.userData = { ...source.userData };
    if (tint !== undefined) material.color.set(tint);
    this.surfaceMaterials.push(material);
    return material;
  }

  scheduleEnvironmentUpdate(delay = .12) {
    this.dynamicEnvironmentDirty = true;
    this.nextEnvironmentUpdate = Math.max(this.clock.elapsedTime + delay, this.nextEnvironmentUpdate);
  }

  refreshDynamicEnvironment() {
    if (this.dynamicEnvironmentPending) return;
    this.dynamicEnvironmentPending = true;
    this.dynamicEnvironmentDirty = false;
    const hidden = [...Object.values(this.groups), this.physicalGlass, this.rain, this.snow].filter(Boolean);
    const visibility = hidden.map(object => object.visible);
    const shadowUpdate = this.renderer.shadowMap.needsUpdate;
    let nextTarget;
    try {
      hidden.forEach(object => { object.visible = false; });
      // Capture sky only. Do not consume a pending shadow refresh with all
      // shadow casters hidden, or sunlight loses its occlusion after every update.
      this.renderer.shadowMap.needsUpdate = false;
      this.skyMaterial.uniforms.solarDisc.value = 0;
      this.environmentCamera.update(this.renderer, this.scene);
      nextTarget = this.pmrem.fromCubemap(this.environmentTarget.texture);
      this.scene.environment = nextTarget.texture;
      // Own and dispose the render target, not only its texture attachment.
      this.runtimeEnvironmentTarget?.dispose();
      this.runtimeEnvironmentTarget = nextTarget;
      document.documentElement.dataset.environment = 'linear-sky-pmrem';
      this.environmentRevision = (this.environmentRevision ?? 0) + 1;
      document.documentElement.dataset.environmentRevision = String(this.environmentRevision);
    } catch (error) {
      if (nextTarget !== this.runtimeEnvironmentTarget) nextTarget?.dispose();
      this.dynamicEnvironmentDirty = true;
      console.error('Environment capture failed', error);
    } finally {
      this.skyMaterial.uniforms.solarDisc.value = 1;
      hidden.forEach((object, i) => { object.visible = visibility[i]; });
      this.renderer.shadowMap.needsUpdate = shadowUpdate;
      this.dynamicEnvironmentPending = false;
      this.nextEnvironmentUpdate = this.clock.elapsedTime + 1.5;
    }
  }

  makePhysicalGlass() {
    this.physicalGlass = new THREE.Mesh(
      new THREE.PlaneGeometry(31, 19),
      new THREE.MeshPhysicalMaterial({
        color: 0xd8eef2, roughness: .08, transmission: 0, thickness: .008,
        ior: 1.52, clearcoat: 1, clearcoatRoughness: .04,
        transparent: true, opacity: .018, envMapIntensity: .35,
        depthWrite: false, side: THREE.DoubleSide,
      }),
    );
    this.physicalGlass.position.set(0, 7.8, 18.2);
    this.physicalGlass.renderOrder = 20;
    this.scene.add(this.physicalGlass);
  }

  loadHeroAssets() {
    const loader = new GLTFLoader();
    let loaded = 0;
    const onReady = () => {
      loaded += 1;
      document.documentElement.dataset.heroModels = String(loaded);
      this.renderer.shadowMap.needsUpdate = true;
      this.scheduleEnvironmentUpdate(1.4);
    };
    const load = (url, ready) => new Promise(resolve => loader.load(url, gltf => {
      try {
        this.prepareLicensedAsset(gltf.scene);
        ready(gltf.scene);
        onReady();
        resolve(true);
      } catch (error) {
        document.documentElement.dataset.modelLoadError = url + ': ' + error.message;
        console.error('Model preparation failed', url, error);
        resolve(false);
      }
    }, undefined, error => {
      document.documentElement.dataset.modelLoadError = url + ': ' + (error?.message || 'load error');
      console.error('Model load failed', url, error);
      resolve(false);
    }));
    this.pendingAssetLoads = Object.fromEntries(Object.keys(SCENES).map(name => [name, []]));
    this.assetStatus = Object.fromEntries(Object.keys(SCENES).map(name => [name, { total: 0, loaded: 0, failed: 0, requested: false }]));
    this.assetLoadCounts = {};
    this.updateAssetState = name => {
      const state = this.assetStatus[name];
      document.documentElement.dataset[name + 'Assets'] = state.failed ? 'error' : state.loaded === state.total ? 'ready' : state.requested ? 'loading' : 'pending';
      if (name === 'city' && state.loaded === state.total) document.documentElement.dataset.cityAsset = 'PolyHaven_Urban_Blocks';
    };
    let assetLoadChain = Promise.resolve();
    const loadDeferred = (sceneNames, url, ready) => {
      sceneNames.forEach(name => { this.assetStatus[name].total++; this.updateAssetState(name); });
      let started = false;
      const execute = () => {
        if (started) return;
        started = true;
        sceneNames.forEach(name => { this.assetStatus[name].requested = true; this.updateAssetState(name); });
        // One queue prevents concurrent city/alley GLB decode peaks; shared
        // assets (seating, vegetation) are decoded only once per app session.
        assetLoadChain = assetLoadChain.then(async () => {
          this.assetLoadCounts[url] = (this.assetLoadCounts[url] || 0) + 1;
          const success = await load(url, ready);
          sceneNames.forEach(name => {
            this.assetStatus[name][success ? 'loaded' : 'failed']++;
            this.updateAssetState(name);
          });
          this.updateBootResourceProgress();
        });
      };
      sceneNames.forEach(name => this.pendingAssetLoads[name].push(execute));
      // Decode every scene during the opening screen. Scene switching is now
      // only a visibility/camera change and never starts a GLTF request.
      execute();
    };
    const loadCity = (url, ready) => loadDeferred(['city'], url, ready);

    loadDeferred(['alley'], './assets/orca/bistro/bistro-exterior-lod-safe-768.glb', (source) => {
      const simplifiedMetal = /antenna|railing|forge_metal|metal_pipe|chimneys_metal|streetlight_metal|grain_metal/i;
      source.traverse((node) => {
        if (!node.isMesh) return;
        repairBistroWallNormals(node);
        node.castShadow = true;
        node.receiveShadow = true;
        const materials = Array.isArray(node.material) ? node.material : [node.material];
        const usesFlatMicroMetal = materials.filter(Boolean).every((material) => simplifiedMetal.test(material.name || ''));
        if (usesFlatMicroMetal) node.castShadow = false;
        materials.filter(Boolean).forEach((material) => {
          if (this.bistroMaterials.has(material)) return;
          calibrateBistroMaterial(material);
          if (/pavement|concrete|brick|plaster|wood|fabric|foliage|roof/i.test(material.name)) this.rainResponse.attachSurface(material);
          this.bistroMaterials.add(material);
        });
      });
      const city = this.placeLicensedModel(source, this.groups.alley, {
        position: [-10, -1, -205], targetSize: 190, rotationY: 0,
      });
      city.name = 'ORCA_Bistro_Exterior';
      let textureCount = 0;
      let normalCount = 0;
      let roughnessCount = 0;
      let aoCount = 0;
      this.bistroMaterials.forEach(material => {
        if (material.map) textureCount++;
        if (material.normalMap) normalCount++;
        if (material.roughnessMap) roughnessCount++;
        if (material.aoMap) aoCount++;
      });
      document.documentElement.dataset.alleyTextureBaseColor = String(textureCount);
      document.documentElement.dataset.alleyTextureNormal = String(normalCount);
      document.documentElement.dataset.alleyTextureRoughness = String(roughnessCount);
      document.documentElement.dataset.alleyTextureAo = String(aoCount);
      document.documentElement.dataset.alleyTexturePbr = roughnessCount && aoCount ? 'orm-complete' : 'basecolor-normal-shader-wetness';
      city.updateWorldMatrix(true, true);
      city.traverse(mesh => {
        if (!mesh.isMesh) return;
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        if (materials.every(m=>/Awnings?.*Fabric/i.test(m.name))) this.rainResponse.attachMotion(mesh,'awning');
        else if (materials.every(m=>/^Foliage_/i.test(m.name) && !/Trunk|branches/i.test(m.name))) this.rainResponse.attachMotion(mesh);
      });
      this.rainResponse.registerScene('alley', this.groups.alley, [-78,-290,86,96]);
      const lampPositions = [];
      city.traverse(node => {
        if (!node.isMesh || node.material?.name !== 'Streetlight_Glass') return;
        const bounds = new THREE.Box3().setFromObject(node);
        if (bounds.getSize(new THREE.Vector3()).length() < 3) lampPositions.push(bounds.getCenter(new THREE.Vector3()));
      });
      const alleyCamera = new THREE.Vector3(...SCENE_VIEWS.alley.position);
      lampPositions.sort((a, b) => a.distanceToSquared(alleyCamera) - b.distanceToSquared(alleyCamera));
      lampPositions.slice(0, 4).forEach(position => {
        const lamp = new THREE.PointLight(0xffc58b, 0, 22, 2);
        lamp.position.copy(position);
        this.groups.alley.add(lamp);
        this.streetLights.push(lamp);
      });
      this.applyAtmosphere();
      document.documentElement.dataset.alleyAsset = 'ORCA_Bistro_Exterior_LOD_CC-BY-4.0';
      this.renderer.shadowMap.needsUpdate = true;
    });

    loadDeferred(['forest', 'village'], './assets/polyhaven/pine_sapling_small/pine_sapling_small_1k.gltf', (source) => {
      const placements = [
        [-12,-1,6,5.4,.15],[13,-1,3,4.8,-.3],[-22,-1,-10,6.2,.4],[22,-1,-16,5.8,-.6],
        [-7,-1,-22,4.2,.8],[9,-1,-28,4.6,-.9],[-29,-1,-36,6.5,.25],[30,-1,-42,6.2,-.35],
        [-39,-1,-55,7,.5],[41,-1,-62,6.8,-.4],[-18,-1,-71,5.7,.24],[17,-1,-79,6.1,-.3],
        [-48,-1,-90,7.4,.18],[49,-1,-102,7.8,-.22],[-6,-1,-112,6.4,.35],[27,-1,-124,7.2,-.42],
      ];
      placements.forEach(([x,y,z,s,r], index) => {
        const tree = index === 0 ? source : source.clone(true);
        tree.position.set(x,y,z); tree.scale.setScalar(s); tree.rotation.y = r;
        this.groups.forest.add(tree);
      });
      [[-34,-1,-48,4.2,.2],[35,-1,-61,4.8,-.35],[-45,-1,-92,5.1,.5]].forEach(([x,y,z,s,r]) => {
        const tree = source.clone(true);
        tree.position.set(x,y,z); tree.scale.setScalar(s); tree.rotation.y = r;
        this.groups.village.add(tree);
      });
    });

    loadDeferred(['village'], './assets/polyhaven/models/grass_bermuda_01/grass_bermuda_01_1k.gltf', (source) => {
      [
        [-34,-1,2,30,.08],[-15,-1,-3,27,-.2],[12,-1,1,29,.18],[34,-1,-7,32,-.12],
        [-28,-1,-18,34,.25],[-5,-1,-22,30,-.28],[22,-1,-18,32,.12],[42,-1,-27,35,-.2],
        [-40,-1,-39,38,.22],[-14,-1,-44,34,-.12],[15,-1,-39,36,.3],[37,-1,-53,39,-.26],
        [-31,-1,-66,41,.14],[-3,-1,-72,37,-.22],[27,-1,-67,40,.18],
      ].forEach(([x,y,z,s,r]) => {
        this.placeLicensedModel(source, this.groups.village, { position: [x,y,z], targetSize: s, rotationY: r });
      });
    });

    loadDeferred(['village'], './assets/polyhaven/models/grass_medium_02/grass_medium_02_1k.gltf', (source) => {
      [[10,-1,-32,20,.1],[-20,-1,-70,25,-.18]].forEach(([x,y,z,s,r]) => {
        this.placeLicensedModel(source, this.groups.village, { position: [x,y,z], targetSize: s, rotationY: r });
      });
    });

    loadDeferred(['city', 'alley'], './assets/polyhaven/models/modular_street_seating/modular_street_seating_1k.gltf', (source) => {
      [[-39,6.91,-211,.58,.72],[31,6.91,-221,.52,-2.36],[-58,6.91,-247,.48,.7]].forEach(([x,y,z,s,r]) => {
        this.placeLicensedModel(source, this.groups.alley, { position: [x,y,z], targetSize: s * 5.2, rotationY: r });
      });
      [[-18,7.08,-12], [18,7.08,-40], [-18,7.08,-68], [18,7.08,-96]].forEach(position => {
        this.placeLicensedModel(source, this.groups.city, { position, targetSize: 3, rotationY: Math.PI / 2 });
      });
    });

    loadCity('./assets/polyhaven/models/modular_urban_apartments_facade/modular_urban_apartments_facade_1k.gltf', (source) => {
      for (const [side, depths, floors] of [
        [-1, [-5,-35,-65,-95,-125,-155], [6,7,5,8,6,7]],
        [1, [-18,-48,-78,-108,-138,-168], [7,5,8,6,7,6]],
      ]) depths.forEach((z, index) => this.addApartmentBlock(source, [side*35, 7, z], floors[index]));
      document.documentElement.dataset.cityPeriphery = 'polyhaven-cc0-pbr-midground';
      this.applyAtmosphere();
      this.scheduleEnvironmentUpdate(1.4);
    });

    loadCity('./assets/polyhaven/models/modular_factory_facade/modular_factory_facade_1k.gltf', (source) => {
      [
        [-42, 7, -209, 1.4, .08], [3, 7, -235, 1.3, 0], [45, 7, -221, 1.6, -.08],
      ].forEach(([x, y, z, scale, rotation]) => this.addFactoryFacade(source, [x, y, z], scale, rotation));
      document.documentElement.dataset.cityIndustrialPeriphery = 'polyhaven-cc0-modular-factory-pbr';
      this.scheduleEnvironmentUpdate(1.4);
    });

    loadCity('./assets/helsinki/helsinki-periphery-lod2.glb', (source) => {
      source.traverse((node) => {
        if (!node.isMesh) return;
        node.castShadow = false;
        node.receiveShadow = false;
        const materials = Array.isArray(node.material) ? node.material : [node.material];
        materials.filter(Boolean).forEach((material) => {
          material.roughness = Math.max(.72, material.roughness ?? .72);
          material.metalness = 0;
          material.envMapIntensity = .68;
          material.color.multiplyScalar(.88);
          material.needsUpdate = true;
        });
      });
      const skyline = this.placeLicensedModel(source, this.groups.city, {
        position: [0, 6.45, -380], targetSize: 430, rotationY: .05,
      });
      skyline.name = 'Helsinki_CC-BY_4_Periphery_LOD2';
      // The source origin is not its center. Keep the entire scan behind the
      // authored street, rather than letting a hillside intersect the courtyard.
      const skylineBounds = new THREE.Box3().setFromObject(skyline);
      skyline.position.x -= skylineBounds.getCenter(new THREE.Vector3()).x;
      skyline.position.z += -290 - skylineBounds.max.z;
      skyline.position.y += Math.min(0, 46 - skylineBounds.max.y);
      document.documentElement.dataset.cityFarPeriphery = 'helsinki-textured-city-mesh-cc-by-4-lod2';
      this.rainResponse.registerScene('city', this.groups.city, [-24,-210,48,246]);
      this.scheduleEnvironmentUpdate(1.8);
    });

    loadDeferred(['village'], './assets/polyhaven/models/modular_fort_01/modular_fort_01_1k.gltf', (source) => {
      const gate = this.assetPart(source, 'modular_fort_01_wall_thin_gate_01');
      const tower = this.assetPart(source, 'modular_fort_01_tower_round');
      const wall = this.assetPart(source, 'modular_fort_01_wall_thin_straight_01');
      if (gate) this.placeLicensedModel(gate, this.groups.village, { position: [3,-1,-27], targetSize: 15, rotationY: .08 });
      if (tower) {
        this.placeLicensedModel(tower, this.groups.village, { position: [-12,-1,-30], targetSize: 11.5, rotationY: -.12 });
        this.placeLicensedModel(tower, this.groups.village, { position: [18,-1,-38], targetSize: 10.5, rotationY: .2 });
      }
      if (wall) {
        this.placeLicensedModel(wall, this.groups.village, { position: [-27,-1,-38], targetSize: 15, rotationY: .22 });
        this.placeLicensedModel(wall, this.groups.village, { position: [31,-1,-48], targetSize: 17, rotationY: -.2 });
      }
    });

    loadDeferred(['village'], './assets/polyhaven/models/wine_barrel_01/wine_barrel_01_1k.gltf', (source) => {
      [[-6,-1,-5,1.25,.2],[-4.7,-1,-5.4,1.1,-.15],[11,-1,-15,1.2,.5]].forEach(([x,y,z,s,r]) => {
        this.placeLicensedModel(source, this.groups.village, { position: [x,y,z], targetSize: s, rotationY: r });
      });
    });

    loadDeferred(['village'], './assets/polyhaven/models/wooden_crate_02/wooden_crate_02_1k.gltf', (source) => {
      [[-8,-1,-7,1.5,.2],[-6.7,-1,-7.2,1.2,-.3],[12,-1,-17,1.35,.5]].forEach(([x,y,z,s,r]) => {
        this.placeLicensedModel(source, this.groups.village, { position: [x,y,z], targetSize: s, rotationY: r });
      });
    });

    loadDeferred(['forest'], './assets/polyhaven/models/mountainside/mountainside_1k.gltf', (source) => {
      [[-42,-1,-68,38,.18,10],[40,-1,-92,43,-.32,14],[-13,-1,-136,55,.08,22]].forEach(([x,y,z,s,r,drop]) => {
        const mountain = this.placeLicensedModel(source, this.groups.forest, { position: [x,y,z], targetSize: s, rotationY: r });
        mountain.position.y -= drop;
      });
    });

    loadDeferred(['forest'], './assets/polyhaven/models/rock_moss_set_01/rock_moss_set_01_1k.gltf', (source) => {
      [[-7,-.9,1,8,.2],[8,-.9,-10,7,-.5],[-12,-.9,-22,11,.6],[10,-.9,-35,9,.12],[-15,-.9,-54,13,-.4]].forEach(([x,y,z,s,r]) => {
        this.placeLicensedModel(source, this.groups.forest, { position: [x,y,z], targetSize: s, rotationY: r });
      });
    });

    loadDeferred(['coast'], './assets/polyhaven/models/coastal_cliff_01/coastal_cliff_01_1k.gltf', (source) => {
      [[-50,-1,-51,58,-.18,5],[-61,-1,-103,72,.22,8]].forEach(([x,y,z,s,r,drop]) => {
        const cliff = this.placeLicensedModel(source, this.groups.coast, { position: [x,y,z], targetSize: s, rotationY: r });
        cliff.position.y -= drop;
      });
    });

    loadDeferred(['coast'], './assets/polyhaven/models/coast_line_01/coast_line_01_1k.gltf', (source) => {
      [[-34,-1,-38,56,.08,3.5],[-48,-1,-94,64,-.08,5]].forEach(([x,y,z,s,r,drop]) => {
        const shoreline = this.placeLicensedModel(source, this.groups.coast, { position: [x,y,z], targetSize: s, rotationY: r });
        shoreline.position.y -= drop;
      });
    });

    loadDeferred(['coast'], './assets/polyhaven/models/sand_rocks_small_01/sand_rocks_small_01_1k.gltf', (source) => {
      [[-12,-.95,-6,20,.15,1.8],[-24,-.95,-53,26,-.18,2.6]].forEach(([x,y,z,s,r,drop]) => {
        const rocks = this.placeLicensedModel(source, this.groups.coast, { position: [x,y,z], targetSize: s, rotationY: r });
        rocks.position.y -= drop;
      });
    });
    this.preloadExpectedRegistered = true;
    this.updateBootResourceProgress();
  }

  prepareLicensedAsset(source) {
    source.traverse((node) => {
      if (!node.isMesh) return;
      node.castShadow = true;
      node.receiveShadow = true;
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      materials.filter(Boolean).forEach((material) => {
        material.envMapIntensity = 1.12;
        for (const key of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap']) {
          if (material[key]) material[key].anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy());
        }
        material.needsUpdate = true;
      });
    });
  }

  assetPart(source, name) {
    const part = source.getObjectByName(name);
    if (!part) return null;
    const clone = part.clone(true);
    clone.position.set(0, 0, 0);
    clone.rotation.set(0, 0, 0);
    clone.scale.set(1, 1, 1);
    return clone;
  }

  placeLicensedModel(source, parent, { position, targetSize, rotationY = 0 }) {
    const model = source.clone(true);
    model.position.set(0, 0, 0);
    model.rotation.set(0, rotationY, 0);
    model.scale.set(1, 1, 1);
    model.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3());
    const scale = targetSize / Math.max(size.x, size.y, size.z, .001);
    model.scale.setScalar(scale);
    model.position.set(position[0], position[1] - bounds.min.y * scale, position[2]);
    parent.add(model);
    return model;
  }

  addApartmentFacade(source, position, rotationY, floors, parent) {
    const facade = new THREE.Group();
    facade.name = 'PolyHaven_Apartment_Facade';
    const addPart = (name, x, y) => {
      const part = this.assetPart(source, name);
      if (!part) return;
      const lit = Math.abs(Math.round(x*2 + y*3 + floors*7 + rotationY*10)) % 5 === 0;
      if (name.startsWith('window_') && lit) part.traverse(mesh => {
        if (!mesh.isMesh) return;
        const lightWindow = material => {
          if (!material.name.endsWith('_glass')) return material;
          if (!this.urbanWindowMaterials.has(material.uuid)) {
            const warm = material.clone();
            warm.emissive.set(0xffc28a);
            warm.emissiveIntensity = 0;
            this.urbanWindowMaterials.set(material.uuid, warm);
          }
          return this.urbanWindowMaterials.get(material.uuid);
        };
        mesh.material = Array.isArray(mesh.material) ? mesh.material.map(lightWindow) : lightWindow(mesh.material);
      });
      part.position.set(x, y, 0);
      facade.add(part);
    };
    // Modules occupy x=[-3,0], y=[0,3] metres, with a lower-right origin.
    for (const x of [-7.5,-4.5,-1.5,1.5,4.5,7.5,10.5]) {
      addPart('wall_door_window_small_01', x, 0);
      addPart('door_window_small_01', x, 0);
      for (let floor=1; floor<floors; floor++) {
        const variant = String((floor-1)%3+1).padStart(2, '0');
        addPart('wall_window_centered_double_' + variant, x, floor*3);
        addPart('window_centered_double_' + variant, x, floor*3);
      }
      addPart('cornice_standard_standard_01', x, floors*3);
      addPart('crown_standard_standard_01', x, floors*3);
    }
    for (const x of [-10.5,10.5]) for (let floor=0; floor<floors; floor++) addPart('wall_pier_standard_01', x, floor*3);
    // A few irregular balconies make the repeated facade modules read as
    // inhabited city blocks. They are deliberately sparse so the authored
    // window rhythm and the fixed composition remain visible.
    const balconySlab = this.materialFor('concrete', 0x8d918d);
    const rail = this.materialFor('paintedMetal', 0x30383b);
    const planterMat = this.materialFor('concrete', 0x626b68);
    const foliageMat = this.materialFor('foliage', 0x3c654d);
    for (let floor = 1; floor < floors - 1; floor++) {
      for (const x of [-7.5, -1.5, 4.5, 10.5]) {
        if ((Math.round(x * 2) + floor + Math.round(rotationY * 4)) % 3 !== 0) continue;
        const balcony = new THREE.Group(); balcony.name = 'urban-balcony';
        const slab = new THREE.Mesh(new THREE.BoxGeometry(2.35, .14, .9), balconySlab);
        slab.position.set(x, floor * 3 - .12, .5); slab.castShadow = true; slab.receiveShadow = true; balcony.add(slab);
        [-1, 0, 1].forEach(offset => {
          const post = new THREE.Mesh(new THREE.BoxGeometry(.045, .72, .045), rail);
          post.position.set(x + offset * .82, floor * 3 + .28, .92); balcony.add(post);
        });
        const topRail = new THREE.Mesh(new THREE.BoxGeometry(2.4, .045, .045), rail);
        topRail.position.set(x, floor * 3 + .64, .92); balcony.add(topRail);
        const planter = new THREE.Mesh(new THREE.BoxGeometry(.62, .18, .25), planterMat);
        planter.position.set(x + .48, floor * 3 + .04, .7); balcony.add(planter);
        const plant = new THREE.Mesh(new THREE.IcosahedronGeometry(.24, 1), foliageMat);
        plant.position.set(x + .48, floor * 3 + .27, .7); plant.castShadow = true; balcony.add(plant);
        facade.add(balcony);
      }
    }
    facade.position.set(...position);
    facade.rotation.y = rotationY;
    parent.add(facade);
    return facade;
  }

  addApartmentBlock(source, position, floors) {
    const block = new THREE.Group();
    block.name = 'PolyHaven_Urban_Block';
    // Four authored elevations plus a textured roof form a closed block.
    // These assets were previously thin, isolated perimeter facades.
    this.addApartmentFacade(source, [0,0,10.5], 0, floors, block);
    this.addApartmentFacade(source, [10.5,0,0], Math.PI/2, floors, block);
    this.addApartmentFacade(source, [0,0,-10.5], Math.PI, floors, block);
    this.addApartmentFacade(source, [-10.5,0,0], -Math.PI/2, floors, block);
    const roof = new THREE.Mesh(new THREE.PlaneGeometry(21,21), this.materialFor('concrete', 0x777b7b));
    roof.rotation.x = -Math.PI/2;
    roof.position.y = floors*3+.7;
    roof.receiveShadow = true;
    block.add(roof);
    this.instanceStaticArchitecture(block);
    block.position.set(...position);
    this.groups.city.add(block);
    return block;
  }

  instanceStaticArchitecture(group) {
    // Batch repeated authored modules while retaining per-building culling.
    group.updateMatrixWorld(true);
    const inverse = group.matrixWorld.clone().invert();
    const batches = new Map();
    group.traverse(mesh => {
      if (!mesh.isMesh) return;
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      const key = [mesh.geometry.uuid, ...materials.map(m=>m.uuid), mesh.castShadow, mesh.receiveShadow].join(':');
      if (!batches.has(key)) batches.set(key, { mesh, matrices: [] });
      batches.get(key).matrices.push(new THREE.Matrix4().multiplyMatrices(inverse, mesh.matrixWorld));
    });
    group.clear();
    for (const { mesh, matrices } of batches.values()) {
      const batch = new THREE.InstancedMesh(mesh.geometry, mesh.material, matrices.length);
      batch.name = mesh.name;
      batch.castShadow = mesh.castShadow;
      batch.receiveShadow = mesh.receiveShadow;
      matrices.forEach((matrix,index) => batch.setMatrixAt(index,matrix));
      batch.instanceMatrix.needsUpdate = true;
      batch.computeBoundingSphere();
      group.add(batch);
    }
  }

  addFactoryFacade(source, position, scale, rotationY) {
    const facade = new THREE.Group();
    const bays = [-9, -6, -3, 0, 3, 6, 9, 12];
    const addPart = (name, x, y, z = 0) => {
      const part = this.assetPart(source, name);
      if (!part) return;
      part.position.set(x, y, z);
      facade.add(part);
    };
    bays.forEach(x => {
      // Garage spans two 3 m bays; ordinary modules span one.
      if (x !== 0) {
        addPart(x === 3 ? 'wall_door_garage_door_01' : 'wall_window_centered_large_01', x, 0);
        addPart(x === 3 ? 'door_garage_door_01' : 'window_centered_large_01', x, 0);
      }
      for (const y of [3, 6, 9]) {
        addPart('wall_window_centered_large_02', x, y);
        addPart('window_centered_large_02', x, y);
      }
      addPart('cornice02_standard_standard_01', x, 12);
      addPart('crown_standard_standard_01', x, 12.16);
    });
    for (const x of [-12, 12]) {
      for (const y of [0,3,6,9]) addPart('wall_pier_standard_01', x, y);
      addPart('cornice02_pier_standard_01', x, 12);
    }
    const shell = new THREE.Mesh(new THREE.BoxGeometry(24, 12.46, 8), this.materialFor('concrete', 0x686c6b));
    shell.position.set(0, 6.23, -4.3);
    shell.castShadow = true;
    shell.receiveShadow = true;
    facade.add(shell);
    this.instanceStaticArchitecture(facade);
    facade.position.set(...position);
    facade.rotation.y = rotationY;
    facade.scale.setScalar(scale);
    this.groups.city.add(facade);
    return facade;
  }

  makeSky() {
    this.sky = createAtmosphere();
    this.skyMaterial = this.sky.material;
    this.scene.add(this.sky);
  }

  makeClouds() {
    this.cloudGroup = new THREE.Group();
    this.scene.add(this.cloudGroup);
    document.documentElement.dataset.clouds = 'dynamic-2d-optical-depth';
  }

  baseGroup(name) {
    const group = new THREE.Group();
    group.name = name;
    this.groups[name] = group;
    this.scene.add(group);
    return group;
  }

  mat(color, roughness = .82, metalness = .03) {
    const material = new THREE.MeshPhysicalMaterial({ color, roughness, metalness, envMapIntensity: .75, clearcoat: metalness > .2 ? .25 : 0, clearcoatRoughness: .32 });
    this.surfaceMaterials.push(material);
    return material;
  }

  addGround(group, color, y = -1, profile = 'rock') {
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(220, 220), this.materialFor(profile, color));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, y, -45);
    ground.receiveShadow = true;
    group.add(ground);
    return ground;
  }

  addTerrain(group, profile, { width = 220, depth = 220, y = -1, z = -45, relief = 1, seed = 1 } = {}) {
    const geometry = new THREE.PlaneGeometry(width, depth, 120, 120);
    const positions = geometry.attributes.position;
    const random = seededRandom(seed);
    const phases = [random() * 8, random() * 8, random() * 8];
    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i);
      const localDepth = positions.getY(i);
      const broad = Math.sin(x * .045 + phases[0]) * Math.cos(localDepth * .038 + phases[1]);
      const rolling = Math.sin((x + localDepth) * .022 + phases[2]) + Math.cos((x - localDepth) * .017);
      const nearCalm = smoothstep(5, 38, Math.abs(localDepth - depth * .42));
      positions.setZ(i, (broad * .62 + rolling * .38) * relief * (.35 + nearCalm * .65));
    }
    geometry.computeVertexNormals();
    const terrain = new THREE.Mesh(geometry, this.materialFor(profile));
    terrain.rotation.x = -Math.PI / 2;
    terrain.position.set(0, y, z);
    terrain.receiveShadow = true;
    group.add(terrain);
    return terrain;
  }

  makeRibbonGeometry(length = 150, segments = 80, width = 10) {
    const positions = [];
    const uvs = [];
    const indices = [];
    for (let i = 0; i <= segments; i++) {
      const t = i / segments;
      const z = 18 - t * length;
      const center = Math.sin(t * 7.2) * 4.2 + Math.sin(t * 2.1) * 2.8;
      const halfWidth = width * (.42 + t * .18 + Math.sin(t * 5) * .05);
      positions.push(center - halfWidth, 0, z, center + halfWidth, 0, z);
      uvs.push(0, t * 12, 1, t * 12);
      if (i < segments) {
        const a = i * 2;
        indices.push(a, a + 2, a + 1, a + 2, a + 3, a + 1);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    return geometry;
  }

  buildScenes() {
    this.buildCity();
    this.baseGroup('alley');
    this.buildVillage();
    this.buildForest();
    this.buildCoast();
  }

  buildCity() {
    const group = this.baseGroup('city');
    const random = seededRandom(921);
    this.addCityCars(group, random);
    this.buildCityRoadLayout();
    this.buildCityStreetDressing(group);
    this.buildCityDistantLayer(group);
  }

  buildCityStreetDressing(group) {
    // Small, repeatable details give the broad procedural road a readable
    // scale at the fixed window camera: curb lips, paving joints and planted
    // street trees break up the single grey plane without changing the route.
    const curb = this.materialFor('concrete', 0x777b78);
    const joint = this.materialFor('concrete', 0x666b68);
    const vertical = (x, z, length, rotation = 0) => {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(.22, .16, length), curb);
      mesh.position.set(x, 7.02, z); mesh.rotation.y = rotation;
      mesh.receiveShadow = true; group.add(mesh);
    };
    vertical(-15.05, -87, 246); vertical(15.05, -87, 246);
    vertical(-23.6, -194, 190, Math.PI / 2); vertical(23.6, -194, 190, Math.PI / 2);
    for (let z = 26; z > -205; z -= 7) {
      for (const x of [-18.2, 18.2]) {
        const seam = new THREE.Mesh(new THREE.BoxGeometry(6.2, .018, .055), joint);
        seam.position.set(x, 6.95, z); seam.receiveShadow = true; group.add(seam);
      }
    }
    const trees = [[-18.1, -31, 1.35], [18.1, -57, 1.15], [-18.1, -91, 1.25], [18.1, -119, 1.05]];
    trees.forEach(([x, z, scale], index) => this.addStreetTree(group, x, z, scale, index));
  }

  addStreetTree(group, x, z, scale, seed = 0) {
    const tree = new THREE.Group(); tree.name = 'city-street-tree';
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(.13 * scale, .2 * scale, 2.4 * scale, 8), this.materialFor('wood', 0x4a4036));
    trunk.position.y = 1.2 * scale; trunk.castShadow = true; tree.add(trunk);
    const planter = new THREE.Mesh(new THREE.CylinderGeometry(.58 * scale, .48 * scale, .56 * scale, 12), this.materialFor('concrete', 0x747977));
    planter.position.y = .28 * scale; planter.castShadow = true; planter.receiveShadow = true; tree.add(planter);
    const crown = new THREE.Group(); crown.name = 'city-tree-crown';
    const foliage = this.materialFor('foliage', [0x345943, 0x3c664d, 0x294b3b][seed % 3]);
    [[0,3.5,0,1.15],[.72,3.1,.12,.82],[-.62,3.18,.2,.9],[.08,4.25,-.12,.72]].forEach(([ox, oy, oz, radius]) => {
      const leaf = new THREE.Mesh(new THREE.IcosahedronGeometry(radius * scale, 2), foliage);
      leaf.position.set(ox * scale, oy * scale, oz * scale); leaf.castShadow = true; crown.add(leaf);
    });
    tree.add(crown); tree.position.set(x, 6.92, z); group.add(tree);
    crown.traverse(node => { if (node.isMesh) this.rainResponse.attachMotion(node, 'foliage'); });
    return tree;
  }

  buildCityDistantLayer(group) {
    const concreteTints = [0x747c82, 0x8b9191, 0x687178, 0x9a9c98];
    const glassTints = [0x486879, 0x587785, 0x3e5e6b];
    const towers = [
      [-30, -184, 11, 27, 12, 0], [-12, -205, 15, 38, 14, 1], [10, -194, 13, 31, 13, 2],
      [30, -221, 18, 46, 15, 3], [-43, -238, 16, 35, 14, 1], [49, -260, 20, 54, 16, 2],
    ];
    towers.forEach(([x, z, width, height, depth, tint], index) => {
      const tower = new THREE.Group(); tower.name = 'city-distant-tower';
      const body = new THREE.Mesh(new THREE.BoxGeometry(width, height, depth), this.materialFor('concrete', concreteTints[tint]));
      body.position.y = height / 2 + 6.9; body.castShadow = true; body.receiveShadow = true; tower.add(body);
      const glass = this.materialFor('architecturalGlass', glassTints[index % glassTints.length]);
      const front = new THREE.Mesh(new THREE.PlaneGeometry(width * .86, height * .72), glass);
      front.position.set(0, height * .55 + 6.9, depth / 2 + .012); tower.add(front);
      const mullion = this.materialFor('paintedMetal', 0x424b50);
      for (let col = -2; col <= 2; col++) {
        const bar = new THREE.Mesh(new THREE.BoxGeometry(.075, height * .72, .08), mullion);
        bar.position.set(col * width * .17, height * .55 + 6.9, depth / 2 + .05); tower.add(bar);
      }
      for (let row = 1; row < 7; row++) {
        const bar = new THREE.Mesh(new THREE.BoxGeometry(width * .86, .06, .08), mullion);
        bar.position.set(0, 6.9 + row * height * .1, depth / 2 + .05); tower.add(bar);
      }
      const roof = new THREE.Mesh(new THREE.BoxGeometry(width * .78, .18, depth * .72), this.materialFor('paintedMetal', 0x3f494e));
      roof.position.y = height + 7.0; roof.castShadow = true; tower.add(roof);
      tower.position.set(x, 0, z); group.add(tower);
    });
  }

  makeRoadStrip(group, start, end, width, material, y = 6.86, lateralOffset = 0) {
    const a = new THREE.Vector2(start[0], start[1]);
    const b = new THREE.Vector2(end[0], end[1]);
    const direction = b.clone().sub(a).normalize();
    const normal = new THREE.Vector2(-direction.y, direction.x);
    a.addScaledVector(normal, lateralOffset);
    b.addScaledVector(normal, lateralOffset);
    const half = normal.clone().multiplyScalar(width * .5);
    const length = a.distanceTo(b);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
      a.x - half.x, y, a.y - half.y,
      a.x + half.x, y, a.y + half.y,
      b.x - half.x, y, b.y - half.y,
      b.x + half.x, y, b.y + half.y,
    ], 3));
    const repeat = material.map?.repeat ?? new THREE.Vector2(1, 1);
    const u = width / (4 * repeat.x), v = length / (4 * repeat.y);
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, u, 0, 0, v, u, v], 2));
    geometry.setIndex([0, 1, 2, 2, 1, 3]);
    geometry.computeVertexNormals();
    const strip = new THREE.Mesh(geometry, material);
    strip.receiveShadow = true;
    group.add(strip);
    return strip;
  }

  buildCityRoadLayout() {
    if (this.cityRoadLayout) return;
    const group = new THREE.Group();
    group.name = 'city-road-functional-zones';
    this.cityRoadLayout = group;
    this.groups.city.add(group);

    const underlay = new THREE.Mesh(new THREE.CircleGeometry(640, 96), this.materialFor('concrete', 0x777a76));
    underlay.name = 'city-grounding-underlay';
    underlay.rotation.x = -Math.PI / 2;
    underlay.position.set(0, 6.72, -100);
    underlay.receiveShadow = true;
    group.add(underlay);

    const routeStart = [0, 36];
    const routeEnd = [0, -210];
    const road = this.materialFor('roadSurface', 0x444542);
    const parking = this.materialFor('asphalt', 0x393b3d);
    const sidewalk = this.materialFor('concrete', 0x9c9e98);
    const cycleLane = this.materialFor('roadSurface', 0x6b4a42);
    this.makeRoadStrip(group, routeStart, routeEnd, 17.5, road, 6.87);
    this.makeRoadStrip(group, routeStart, routeEnd, 3.2, parking, 6.89, -10.35);
    this.makeRoadStrip(group, routeStart, routeEnd, 3.2, parking, 6.89, 10.35);
    this.makeRoadStrip(group, routeStart, routeEnd, 2.8, cycleLane, 6.90, -13.45);
    this.makeRoadStrip(group, routeStart, routeEnd, 6.5, sidewalk, 6.88, -18.1);
    this.makeRoadStrip(group, routeStart, routeEnd, 6.5, sidewalk, 6.88, 15.2);

    const crossStart = [-95, -194];
    const crossEnd = [95, -194];
    this.makeRoadStrip(group, crossStart, crossEnd, 15, road, 6.865);
    this.makeRoadStrip(group, crossStart, crossEnd, 3.2, parking, 6.885, -9.4);
    this.makeRoadStrip(group, crossStart, crossEnd, 3.2, parking, 6.885, 9.4);
    this.makeRoadStrip(group, crossStart, crossEnd, 5.8, sidewalk, 6.88, -14);
    this.makeRoadStrip(group, crossStart, crossEnd, 5.8, sidewalk, 6.88, 14);

    const marking = new THREE.MeshStandardMaterial({ color: 0xc7c3b5, roughness: .86, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
    const a = new THREE.Vector2(...routeStart);
    const b = new THREE.Vector2(...routeEnd);
    const direction = b.clone().sub(a).normalize();
    const normal = new THREE.Vector2(-direction.y, direction.x);
    const length = a.distanceTo(b);
    for (let distance = 8; distance < length - 5; distance += 11) {
      const center = a.clone().addScaledVector(direction, distance);
      const dashStart = center.clone().addScaledVector(direction, -2.1);
      const dashEnd = center.clone().addScaledVector(direction, 2.1);
      this.makeRoadStrip(group, [dashStart.x, dashStart.y], [dashEnd.x, dashEnd.y], .18, marking, 6.925);
    }
    for (const ratio of [.28, .68]) {
      const center = a.clone().lerp(b, ratio);
      for (let stripe = -4; stripe <= 4; stripe += 1) {
        const stripeCenter = center.clone().addScaledVector(direction, stripe * .72);
        const stripeStart = stripeCenter.clone().addScaledVector(normal, -7.5);
        const stripeEnd = stripeCenter.clone().addScaledVector(normal, 7.5);
        this.makeRoadStrip(group, [stripeStart.x, stripeStart.y], [stripeEnd.x, stripeEnd.y], .34, marking, 6.93);
      }
    }
  }

  addCityCars(group, random) {
    const colors = [0x292e34, 0xaeb4b1, 0x783e36, 0x394d68];
    for (let i = 0; i < 16; i++) {
      const car = new THREE.Group();
      const body = new THREE.Mesh(new THREE.BoxGeometry(1, .34, 1.9), this.materialFor('paintedMetal', colors[i % colors.length]));
      body.castShadow = true; car.add(body);
      const lampMat = new THREE.MeshBasicMaterial({ color: i % 2 ? 0xff3f28 : 0xffe7ad });
      const lamp = new THREE.Mesh(new THREE.BoxGeometry(.7, .11, .06), lampMat);
      lamp.position.set(0, .05, i % 2 ? .98 : -.98); car.add(lamp);
      const direction = i % 2 ? -1 : 1;
      const routeStart = new THREE.Vector3(0, 7.38, 16);
      const routeEnd = new THREE.Vector3(0, 7.38, -198);
      const routeDirection = routeEnd.clone().sub(routeStart).normalize();
      const laneOffset = new THREE.Vector3(-routeDirection.z, 0, routeDirection.x).multiplyScalar(direction * (i % 4 < 2 ? 2.2 : 5.2));
      const pathT = random();
      car.position.lerpVectors(routeStart, routeEnd, pathT).add(laneOffset);
      car.rotation.y = Math.atan2(routeDirection.x * direction, routeDirection.z * direction);
      car.userData = {
        speed: .015 + random() * .012,
        direction,
        pathT,
        routeStart,
        routeEnd,
        laneOffset,
      };
      group.add(car); this.cars.push(car);
    }
  }

  addTree(group, x, z, scale = 1, color = 0x31523e) {
    const tree = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(.16 * scale, .25 * scale, 2.2 * scale, 6), this.materialFor('wood', 0x4a3b2d));
    trunk.position.y = .1 * scale; trunk.castShadow = true; tree.add(trunk);
    const foliage = new THREE.Mesh(new THREE.ConeGeometry(1.45 * scale, 4.8 * scale, 8), this.materialFor('foliage', color));
    foliage.position.y = 2.6 * scale; foliage.castShadow = true; tree.add(foliage);
    tree.position.set(x, 0, z); group.add(tree); return tree;
  }

  addHouse(group, x, z, scale = 1, wallColor = 0xc6bda6) {
    const house = new THREE.Group();
    const base = new THREE.Mesh(new THREE.BoxGeometry(4 * scale, 2.5 * scale, 3.3 * scale), this.materialFor('concrete', wallColor));
    base.position.y = .25 * scale; base.castShadow = true; base.receiveShadow = true; house.add(base);
    const roof = new THREE.Mesh(new THREE.ConeGeometry(3.25 * scale, 1.5 * scale, 4), this.materialFor('wood', 0x403b36));
    roof.rotation.y = Math.PI / 4; roof.position.y = 2.25 * scale; roof.scale.z = .8; roof.castShadow = true; house.add(roof);
    const windowMat = new THREE.MeshBasicMaterial({ color: 0xffc36e, transparent: true, opacity: .15 });
    this.lightMaterials.push(windowMat);
    const window = new THREE.Mesh(new THREE.PlaneGeometry(.75 * scale, .65 * scale), windowMat);
    window.position.set(.8 * scale, .45 * scale, 1.66 * scale); house.add(window);
    house.position.set(x, 0, z); group.add(house); return house;
  }

  buildVillage() {
    const group = this.baseGroup('village');
    const random = seededRandom(309);
    this.addTerrain(group, 'fieldSurface', { y: -1.25, z: -45, relief: 4.2, seed: 309 });
    const lane = new THREE.Mesh(new THREE.PlaneGeometry(7, 145), this.materialFor('rock', 0x4b4941));
    lane.rotation.x = -Math.PI / 2; lane.rotation.z = -.13; lane.position.set(4, -.72, -42); lane.receiveShadow = true; group.add(lane);
  }

  buildForest() {
    const group = this.baseGroup('forest');
    const random = seededRandom(704);
    this.addTerrain(group, 'forestGround', { y: -1.3, z: -45, relief: 6.8, seed: 704 });
    const streamNormals = new THREE.TextureLoader().load('./assets/water/waternormals.jpg');
    streamNormals.wrapS = streamNormals.wrapT = THREE.RepeatWrapping;
    streamNormals.repeat.set(2.5, 22);
    const streamMat = new THREE.MeshPhysicalMaterial({
      color: 0x2b6f7b, roughness: .12, metalness: 0, transmission: .45,
      thickness: .32, ior: 1.333, clearcoat: 1, clearcoatRoughness: .06,
      normalMap: streamNormals, normalScale: new THREE.Vector2(.42, .7),
      transparent: true, opacity: .88, envMapIntensity: 1.65, side: THREE.DoubleSide,
    });
    const stream = new THREE.Mesh(this.makeRibbonGeometry(155, 88, 11), streamMat);
    stream.position.set(0, -.72, 0); group.add(stream);
    this.animatedWaterMaterials.push(streamMat);
  }

  buildCoast() {
    const group = this.baseGroup('coast');
    const random = seededRandom(118);
    this.addTerrain(group, 'coastSand', { width: 118, depth: 210, y: -1.3, z: -45, relief: 3.4, seed: 118 }).position.x = -55;
    const oceanNormals = new THREE.TextureLoader().load('./assets/water/waternormals.jpg', (texture) => {
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    });
    const ocean = new Water(new THREE.PlaneGeometry(170, 180), {
      textureWidth: 512, textureHeight: 512, waterNormals: oceanNormals,
      sunDirection: new THREE.Vector3(.4,.7,-.4), sunColor: 0xffe0b2,
      waterColor: 0x062f43, distortionScale: 1.9, alpha: .8, fog: true,
    });
    ocean.rotation.x = -Math.PI / 2;
    ocean.position.set(32, -1.05, -48);
    ocean.material.uniforms.size.value = .11;
    group.add(ocean);
    this.waterSurfaces.push(ocean);
    this.makeShoreFoam(group);
  }

  makeShoreFoam(group) {
    const material = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, side: THREE.DoubleSide,
      uniforms: { time: { value: 0 } },
      vertexShader: `varying vec2 vUv; void main(){vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
      fragmentShader: `
        uniform float time; varying vec2 vUv;
        float noise(vec2 p){return sin(p.x*17.0+sin(p.y*9.0))*sin(p.y*31.0-p.x*5.0);}
        void main(){
          float edge=1.0-smoothstep(.1,.52,abs(vUv.x-.5));
          float tide=.5+.5*sin(vUv.y*22.0-time*.9+noise(vUv*11.0)*2.5);
          float broken=smoothstep(.68,.96,tide+noise(vUv*19.0)*.22);
          float alpha=edge*broken*.2;
          gl_FragColor=vec4(vec3(.82,.92,.91),alpha);
        }`,
    });
    const foam = new THREE.Mesh(new THREE.PlaneGeometry(13, 160, 1, 80), material);
    foam.rotation.x = -Math.PI / 2;
    foam.rotation.z = -.035;
    foam.position.set(-13, -.94, -48);
    foam.renderOrder = 3;
    group.add(foam);
    this.waveMaterials.push(material);
  }

  makeWeather() {
    const random = seededRandom(87);
    const rainPositions = [];
    for (let i = 0; i < 900; i++) {
      const x = (random() - .5) * 110, y = random() * 62, z = 18 - random() * 125;
      rainPositions.push(x, y, z, x - .12, y - 1.8 - random() * 1.7, z);
    }
    const rainGeo = new THREE.BufferGeometry();
    rainGeo.setAttribute('position', new THREE.Float32BufferAttribute(rainPositions, 3));
    this.rain = new THREE.LineSegments(rainGeo, new THREE.LineBasicMaterial({ color: 0xb8d2dd, transparent: true, opacity: .34, depthWrite: false }));
    this.rainResponse.clipRain(this.rain.material);
    this.rain.visible = false; this.scene.add(this.rain);

    const snowPositions = [];
    for (let i = 0; i < 850; i++) snowPositions.push((random() - .5) * 100, random() * 55, 18 - random() * 115);
    const snowGeo = new THREE.BufferGeometry();
    snowGeo.setAttribute('position', new THREE.Float32BufferAttribute(snowPositions, 3));
    this.snow = new THREE.Points(snowGeo, new THREE.PointsMaterial({ color: 0xffffff, size: .22, transparent: true, opacity: .72, depthWrite: false }));
    this.snow.visible = false; this.scene.add(this.snow);
  }

  switchScene(name, animate = true) {
    if (!this.groups[name]) return;
    const changed = this.activeScene !== name;
    this.activeScene = name;
    this.rainResponse.setScene(name);
    document.documentElement.dataset.activeScene = name;
    this.assetStatus[name].requested = true;
    this.updateAssetState(name);
    if (this.pendingAssetLoads?.[name]?.length) {
      const queued = this.pendingAssetLoads[name].splice(0);
      queued.forEach((startLoad) => startLoad());
    }
    Object.entries(this.groups).forEach(([key, group]) => { group.visible = key === name; });
    const setup = { ...SCENE_VIEWS[name] };
    if (import.meta.env.DEV && (name === 'city' || name === 'alley')) {
      const params = new URLSearchParams(location.search);
      const readVector = (key, fallback) => {
        const values = params.get(key)?.split(',').map(Number);
        return values?.length === 3 && values.every(Number.isFinite) ? values : fallback;
      };
      setup.position = readVector('camera', setup.position);
      setup.target = readVector('target', setup.target);
      const debugFov = Number(params.get('fov'));
      if (Number.isFinite(debugFov) && debugFov >= 30 && debugFov <= 70) setup.fov = debugFov;
    }
    this.baseCamera = new THREE.Vector3(...setup.position);
    this.baseTarget = new THREE.Vector3(...setup.target);
    this.camera.fov = setup.fov;
    this.camera.updateProjectionMatrix();
    this.scene.fog.density = setup.fog;
    this.targetFog = setup.fog;
    this.lightTarget = new THREE.Vector3(...setup.lightTarget);
    this.environmentCamera.position.set(...setup.environment);
    this.lastShadowHour = null;
    this.renderer.shadowMap.needsUpdate = true;
    if (!animate || changed) { this.camera.position.copy(this.baseCamera); this.cameraTarget.copy(this.baseTarget); this.camera.lookAt(this.cameraTarget); }
    this.scheduleEnvironmentUpdate(.18);
    this.applyAtmosphere();
  }

  setWeather(mode, data = this.weatherData) {
    this.weather = mode;
    this.weatherData = { ...this.weatherData, ...data };
    const actual = mode === 'live' ? weatherModeFromCode(this.weatherData.weatherCode ?? 1) : mode;
    this.activeWeather = actual;
    this.rainResponse.setWeather(actual, mode === 'live' ? this.weatherData : { ...this.weatherData, precipitation: actual === 'rain' ? 2.5 : 0 });
    this.rain.visible = actual === 'rain';
    this.snow.visible = actual === 'snow';
    const cloud = mode === 'live' ? (this.weatherData.cloudCover ?? 35) / 100 : actual === 'clear' ? .12 : actual === 'fog' ? .88 : .78;
    this.cloudAmount = cloud;
    this.applyAtmosphere();
    this.scheduleEnvironmentUpdate(.18);
  }

  setTime(hour) {
    this.hour = (hour + 24) % 24;
    this.applyAtmosphere();
    document.documentElement.dataset.solarElevation = (this.solarPosition().elevation * 180 / Math.PI).toFixed(2);
  }

  solarPosition() {
    return solarPosition(this.location, this.hour, this.solarDate ?? new Date());
  }

  applyAtmosphere() {
    if (!this.skyMaterial) return;
    const { elevation, azimuth } = this.solarPosition();
    const sunHeight = Math.sin(elevation);
    const daylight = smoothstep(-.12, .18, sunHeight);
    const night = 1 - daylight;
    this.rainResponse.uniforms.rwLight.value = .025 + daylight * .975;
    const horizonGlow = Math.exp(-Math.pow(sunHeight / .22, 2));
    const storm = this.activeWeather === 'rain' ? .42 : this.activeWeather === 'fog' ? .35 : 0;
    const cloud = this.cloudAmount ?? .3;

    const topNight = new THREE.Color(0x040b18), topDay = new THREE.Color(0x4f8fbd);
    const horizonNight = new THREE.Color(0x101b31), horizonDay = new THREE.Color(0xb9d6dd);
    const horizonDawn = new THREE.Color(0xe79468);
    const top = topNight.clone().lerp(topDay, daylight).lerp(new THREE.Color(0x48545d), storm);
    const horizon = horizonNight.clone().lerp(horizonDay, daylight).lerp(horizonDawn, horizonGlow * .72).lerp(new THREE.Color(0x697278), storm);
    this.skyMaterial.uniforms.sunColor.value.set(horizonGlow > .25 ? 0xffc178 : 0xffeed0);
    this.skyMaterial.uniforms.daylight.value = daylight;
    this.skyMaterial.uniforms.cloudCoverage.value = clamp(cloud, 0, 1);
    this.skyMaterial.uniforms.turbidity.value = 2 + cloud * 5;
    this.skyMaterial.uniforms.rayleigh.value = 2.2;
    this.skyMaterial.uniforms.mieCoefficient.value = .004 + cloud * .006;
    this.skyMaterial.uniforms.mieDirectionalG.value = .8;

    const distance = 100;
    const sunDir = new THREE.Vector3(Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation), -Math.cos(azimuth) * Math.cos(elevation)).normalize();
    this.skyMaterial.uniforms.sunDirection.value.copy(sunDir);
    this.skyMaterial.uniforms.sunPosition.value.copy(sunDir).multiplyScalar(450000);
    const lightTarget = this.lightTarget ?? new THREE.Vector3(0, 4, -25);
    this.sun.target.position.copy(lightTarget);
    this.sun.position.copy(lightTarget).addScaledVector(sunDir, distance);
    this.sun.color.set(0xfff4e5).lerp(new THREE.Color(0xffac65), horizonGlow * .8);
    this.sun.intensity = 3.6 * smoothstep(-.015, .08, sunHeight) * (1 - cloud * .93);
    this.hemisphere.intensity = .012 + daylight * .025;
    this.hemisphere.color.set(top);
    // Low urban night fill plus local practical lamps; the sun remains below
    // the horizon. This is an art-directed skyglow, not a computed moon model.
    this.fillLight.intensity = night * .16;
    this.scene.environmentIntensity = .82 + cloud * daylight * .22;
    const clearUrbanDay = this.activeScene === 'city' && this.activeWeather === 'clear' && daylight > .35;
    this.renderer.toneMappingExposure = clearUrbanDay
      ? 1.12 + horizonGlow * .12
      : 2.2 * night + (.9 + cloud * .38) * daylight + horizonGlow * .12;
    this.streetLights.forEach(light => { light.intensity = night * 65; });
    const shadowHourDelta = this.lastShadowHour == null
      ? 24
      : Math.min(Math.abs(this.hour - this.lastShadowHour), 24 - Math.abs(this.hour - this.lastShadowHour));
    if (shadowHourDelta >= .08) {
      this.lastShadowHour = this.hour;
      this.renderer.shadowMap.needsUpdate = true;
    }
    this.scene.fog.color.copy(horizon).lerp(new THREE.Color(0xb8c2bf), this.activeWeather === 'fog' ? .45 : 0);
    const urbanFogScale = clearUrbanDay ? .72 : 1;
    this.scene.fog.density = (this.targetFog ?? .007) * urbanFogScale * (this.activeWeather === 'fog' ? 3.2 : this.activeWeather === 'rain' ? 1.5 : 1);
    this.lightMaterials.forEach((mat, index) => { mat.opacity = clamp(.04 + night * (.45 + (index % 4) * .13), .04, .92); });
    this.bistroMaterials.forEach(material => updateBistroWeather(material, this.activeWeather === 'rain', night));
    this.urbanWindowMaterials.forEach(material => { material.emissiveIntensity = night * .65; });
    this.surfaceMaterials.forEach((mat) => {
      const profile = MATERIAL_PROFILES[mat.userData.profile];
      if (!profile) return;
      // RainResponse applies spatial wetness in the shader, preserving dry
      // regions and gradually draining puddles after the rain stops.
      mat.roughness = mat.userData.baseRoughness;
      mat.clearcoat = mat.userData.baseClearcoat;
    });
    if (this.physicalGlass) {
      this.physicalGlass.material.roughness = this.activeWeather === 'rain' ? .2 : .08;
      this.physicalGlass.material.opacity = this.activeWeather === 'fog' ? .04 : .018;
    }
    this.waveMaterials.forEach((mat) => { if (mat.uniforms.night) mat.uniforms.night.value = night; });
    this.waterSurfaces.forEach((water) => {
      water.material.uniforms.sunDirection.value.copy(sunDir);
      water.material.uniforms.sunColor.value.set(horizonGlow > .18 ? 0xd18b58 : 0x81999c).multiplyScalar(.42);
      water.material.uniforms.waterColor.value.set(daylight > .25 ? 0x14536a : 0x071b31);
      water.material.uniforms.distortionScale.value = this.activeWeather === 'rain' ? 3.2 : 2.1;
    });
    this.cloudMeshes.forEach((mesh) => { mesh.material.opacity = .035 + cloud * .4; mesh.material.color.copy(new THREE.Color(0xdde3e2).lerp(new THREE.Color(0x657078), storm + night * .25)); });
    const environmentSignature = `${Math.round(this.hour * 12)}:${this.activeWeather}:${Math.round(cloud * 10)}:${this.activeScene}`;
    if (environmentSignature !== this.environmentSignature) {
      this.environmentSignature = environmentSignature;
      this.scheduleEnvironmentUpdate(.16);
    }
  }

  bindEvents() {
    const resize = () => {
      const width = this.canvas.clientWidth || innerWidth;
      const height = this.canvas.clientHeight || innerHeight;
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.pipeline.resize(width, height, this.quality);
    };
    addEventListener('resize', resize);
    this.resizeObserver = new ResizeObserver(resize);
    this.resizeObserver.observe(this.canvas);
    requestAnimationFrame(resize);
    this.resizeRendering = resize;
  }

  setQuality(quality) {
    if (!RENDER_QUALITY[quality]) return;
    this.quality = quality;
    this.resizeRendering();
    document.documentElement.dataset.renderQuality = quality;
  }

  updateWeatherParticles(dt, elapsed) {
    // Keep precipitation around the current window, including the translated
    // city preset. Previously all rain/snow remained near the world origin.
    this.rain.position.set(this.camera.position.x, this.camera.position.y - 18, this.camera.position.z - 8);
    this.snow.position.copy(this.rain.position);
    const wind = this.rainResponse.uniforms.rwWind.value.x;
    const windZ = this.rainResponse.uniforms.rwWind.value.y;
    if (this.rain.visible) {
      const pos = this.rain.geometry.attributes.position.array;
      for (let i = 0; i < pos.length; i += 6) {
        const streakLength = pos[i + 4] - pos[i + 1];
        pos[i + 1] -= dt * 18; pos[i + 4] -= dt * 18; pos[i] += wind * dt; pos[i + 2] += windZ * dt;
        pos[i + 3] = pos[i] - wind * streakLength / 18;
        pos[i + 5] = pos[i + 2] - windZ * streakLength / 18;
        if (pos[i] > 55) { pos[i] -= 110; pos[i + 3] -= 110; }
        if (pos[i] < -55) { pos[i] += 110; pos[i + 3] += 110; }
        if (pos[i+2] > 32) { pos[i+2] -= 150; pos[i+5] -= 150; }
        if (pos[i+2] < -118) { pos[i+2] += 150; pos[i+5] += 150; }
        if (pos[i + 1] < -2) { const lift = 58; pos[i + 1] += lift; pos[i + 4] += lift; }
      }
      this.rain.geometry.attributes.position.needsUpdate = true;
    }
    if (this.snow.visible) {
      const pos = this.snow.geometry.attributes.position.array;
      for (let i = 0; i < pos.length; i += 3) {
        pos[i + 1] -= dt * 3.2; pos[i] += Math.sin(elapsed * .7 + i) * dt * .35 + wind * dt;
        if (pos[i] > 50) pos[i] -= 100;
        if (pos[i] < -50) pos[i] += 100;
        if (pos[i + 1] < -2) pos[i + 1] += 57;
      }
      this.snow.geometry.attributes.position.needsUpdate = true;
    }
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    const frameTime = this.clock.getDelta();
    const dt = Math.min(frameTime, .05);
    const elapsed = this.clock.elapsedTime;
    this.rainResponse.update(dt,elapsed);
    if (this.activeScene === 'alley' && this.sun.intensity > .1 && elapsed - (this.lastWindShadowUpdate ?? 0) > .25) {
      this.renderer.shadowMap.needsUpdate = true;
      this.lastWindShadowUpdate = elapsed;
    }
    this.skyMaterial.uniforms.cloudTime.value = elapsed;
    this.skyMaterial.uniforms.cloudWind.value.copy(this.rainResponse.uniforms.rwWind.value).multiplyScalar(.0035);
    this.camera.position.lerp(this.baseCamera, .035);
    this.cameraTarget.lerp(this.baseTarget, .035);
    this.camera.lookAt(this.cameraTarget);
    if (this.physicalGlass) {
      const glassDirection = this.cameraTarget.clone().sub(this.camera.position).normalize();
      this.physicalGlass.position.copy(this.camera.position).addScaledVector(glassDirection, 3.8);
      this.physicalGlass.quaternion.copy(this.camera.quaternion);
    }

    if (this.dynamicEnvironmentDirty && !this.dynamicEnvironmentPending && elapsed >= this.nextEnvironmentUpdate) {
      this.refreshDynamicEnvironment();
    }

    this.cloudGroup.children.forEach((cloud, index) => {
      cloud.position.x += dt * (.18 + (this.weatherData.windSpeed ?? 8) * .018) * (index % 3 + 1);
      if (cloud.position.x > 115) cloud.position.x = -115;
    });
    this.cars.forEach((car) => {
      if (!car.parent.visible) return;
      car.userData.pathT += dt * car.userData.speed * car.userData.direction;
      if (car.userData.pathT > 1) car.userData.pathT = 0;
      if (car.userData.pathT < 0) car.userData.pathT = 1;
      car.position.lerpVectors(car.userData.routeStart, car.userData.routeEnd, car.userData.pathT).add(car.userData.laneOffset);
    });
    this.waveMaterials.forEach((mat) => { mat.uniforms.time.value = elapsed; });
    this.waterSurfaces.forEach((water) => { water.material.uniforms.time.value += dt * .7; });
    this.animatedWaterMaterials.forEach((material) => {
      if (!material.normalMap) return;
      material.normalMap.offset.x = (elapsed * .018) % 1;
      material.normalMap.offset.y = (elapsed * -.055) % 1;
    });
    this.swayGroups.forEach((group, index) => { if (group.parent.visible) group.rotation.z = Math.sin(elapsed * .55 + index) * .0035 * (1 + (this.weatherData.windSpeed ?? 8) / 10); });
    this.updateWeatherParticles(dt, elapsed);
    this.renderer.info.reset();
    this.rainResponse.renderReflection(this.renderer,this.scene,this.camera,this.quality,[this.physicalGlass,this.rain,this.snow].filter(Boolean));
    this.pipeline.render(dt);

    this.frameSamples.push(frameTime);
    if (this.frameSamples.length > 45) {
      const fps = Math.round(1 / (this.frameSamples.reduce((a, b) => a + b, 0) / this.frameSamples.length));
      const label = $('#fpsLabel'); if (label) label.textContent = `${Math.min(fps, 99)} FPS`;
      this.frameSamples.length = 0;
    }
  }
}

class AmbientAudio {
  constructor() { this.enabled = false; this.ctx = null; }
  async toggle(scene) {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      const length = this.ctx.sampleRate * 3;
      const buffer = this.ctx.createBuffer(1, length, this.ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
      this.noise = this.ctx.createBufferSource(); this.noise.buffer = buffer; this.noise.loop = true;
      this.filter = this.ctx.createBiquadFilter(); this.filter.type = 'lowpass';
      this.gain = this.ctx.createGain(); this.gain.gain.value = 0;
      this.noise.connect(this.filter).connect(this.gain).connect(this.ctx.destination); this.noise.start();
    }
    this.enabled = !this.enabled;
    await this.ctx.resume();
    const frequency = (scene === 'city' || scene === 'alley') ? 650 : scene === 'coast' ? 420 : 850;
    this.filter.frequency.setTargetAtTime(frequency, this.ctx.currentTime, .8);
    this.gain.gain.setTargetAtTime(this.enabled ? .032 : 0, this.ctx.currentTime, .35);
    return this.enabled;
  }
}

const world = new LivingWorld($('#world'));
const audio = new AmbientAudio();
window.appState = { liveTime: true, weatherMode: 'live', liveContext: null, weather: null };

function displayTime(hour, minute) {
  $('#timeLabel').textContent = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  $('#periodLabel').textContent = periodName(hour + minute / 60, world.solarPosition());
}

async function getLiveContext() {
  if (window.outOfWindow) return window.outOfWindow.getLiveContext();
  try {
    const geo = await fetch('https://ipwho.is/?fields=success,city,region,country,latitude,longitude,timezone').then((r) => r.json());
    const query = new URLSearchParams({ latitude: geo.latitude, longitude: geo.longitude, current: 'temperature_2m,apparent_temperature,is_day,precipitation,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m', timezone: 'auto' });
    const forecast = await fetch(`https://api.open-meteo.com/v1/forecast?${query}`).then((r) => r.json());
    return { location: { city: geo.city, region: geo.region, country: geo.country, latitude: geo.latitude, longitude: geo.longitude, timezone: geo.timezone?.id || forecast.timezone }, weather: { temperature: forecast.current.temperature_2m, apparentTemperature: forecast.current.apparent_temperature, weatherCode: forecast.current.weather_code, isDay: forecast.current.is_day, precipitation: forecast.current.precipitation, cloudCover: forecast.current.cloud_cover, windSpeed: forecast.current.wind_speed_10m, windDirection: forecast.current.wind_direction_10m, windGustSpeed: forecast.current.wind_gusts_10m }, fallback: false };
  } catch { return { location: { city: '上海', country: '中国', latitude: 31.23, longitude: 121.47, timezone: 'Asia/Shanghai' }, weather: { temperature: 22, weatherCode: 1, cloudCover: 35, windSpeed: 8 }, fallback: true }; }
}

async function syncWeather() {
  $('#syncState').textContent = '正在同步本地天空';
  $('#refreshWeather').classList.add('spinning');
  const data = await getLiveContext();
  window.appState.liveContext = data;
  window.appState.weather = data.weather;
  world.location = data.location;
  syncClock();
  const [weatherText, icon] = WMO[data.weather.weatherCode] || ['天气变化中', '◌'];
  $('#locationName').textContent = [data.location.city, data.location.region].filter((item, index, arr) => item && arr.indexOf(item) === index).slice(0, 2).join(' · ') || data.location.country;
  $('#temperature').textContent = `${Math.round(data.weather.temperature)}°`;
  $('#weatherText').textContent = `${weatherText} · 风 ${Math.round(data.weather.windSpeed || 0)} km/h`;
  $('#weatherIcon').textContent = icon;
  $('#syncState').textContent = data.fallback ? '离线演示数据' : '实时天空 · 刚刚更新';
  $('#refreshWeather').classList.remove('spinning');
  if (window.appState.weatherMode === 'live') world.setWeather('live', data.weather);
  world.applyAtmosphere();
}

function switchScene(name) {
  const copy = $('.scene-copy'); copy.classList.add('changing');
  setTimeout(() => {
    const meta = SCENES[name];
    $('#sceneIndex').textContent = meta.index; $('#sceneTitle').textContent = meta.title; $('#sceneDescription').textContent = meta.description;
    copy.classList.remove('changing');
  }, 220);
  $$('.scene-tab').forEach((button) => button.classList.toggle('active', button.dataset.scene === name));
  world.switchScene(name);
  if (audio.ctx) audio.filter.frequency.setTargetAtTime((name === 'city' || name === 'alley') ? 650 : name === 'coast' ? 420 : 850, audio.ctx.currentTime, .8);
}

$('#sceneTabs').addEventListener('click', (event) => {
  const button = event.target.closest('[data-scene]'); if (button) switchScene(button.dataset.scene);
});

$('#weatherModes').addEventListener('click', (event) => {
  const button = event.target.closest('[data-weather]'); if (!button) return;
  window.appState.weatherMode = button.dataset.weather;
  $$('#weatherModes button').forEach((item) => item.classList.toggle('active', item === button));
  world.setWeather(button.dataset.weather);
});

$('#timeSlider').addEventListener('input', (event) => {
  const minutes = Number(event.target.value);
  window.appState.liveTime = false; $('#liveTime').classList.remove('active');
  world.setTime(minutes / 60); displayTime(Math.floor(minutes / 60), minutes % 60);
});

$('#liveTime').addEventListener('click', () => {
  window.appState.liveTime = !window.appState.liveTime;
  $('#liveTime').classList.toggle('active', window.appState.liveTime);
});

$('#ambientToggle').addEventListener('click', async () => {
  const enabled = await audio.toggle(world.activeScene);
  $('#ambientToggle').classList.toggle('active', enabled);
});

$('#collapsePanel').addEventListener('click', () => $('#controlPanel').classList.toggle('collapsed'));
$('#dismissPrivacy').addEventListener('click', () => $('#privacyNote').classList.add('hidden'));
$('#refreshWeather').addEventListener('click', syncWeather);
$('#renderQuality').addEventListener('change', (event) => world.setQuality(event.target.value));
$('#minimize').addEventListener('click', () => window.outOfWindow?.minimize());
$('#maximize').addEventListener('click', () => window.outOfWindow?.maximize());
$('#close').addEventListener('click', () => window.outOfWindow?.close());
$('#clickThrough').addEventListener('click', () => window.outOfWindow?.toggleClickThrough());
let compactUi = false;
$('#compactMode').addEventListener('click', () => {
  compactUi = !compactUi;
  document.body.classList.toggle('compact-ui', compactUi);
  window.outOfWindow?.resizeWidget(compactUi);
});
window.outOfWindow?.onDesktopState?.((state) => {
  $('#clickThrough').classList.toggle('active', state.clickThrough);
});
window.outOfWindow?.onWindowState?.(({ maximized }) => {
  const button = $('#maximize');
  button.textContent = maximized ? '❐' : '□';
  button.setAttribute('aria-label', maximized ? '还原' : '最大化');
  button.title = maximized ? '还原' : '最大化';
});

function syncClock() {
  const timezone = world.location.timezone;
  const { hour, minute } = localCalendar(new Date(), timezone);
  $('#localClock').textContent = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  if (window.appState.liveTime) {
    const total = hour * 60 + minute;
    $('#timeSlider').value = total;
    world.setTime(total / 60);
    displayTime(hour, minute);
  }
}
setInterval(syncClock, 1000);
syncClock();
syncWeather();
