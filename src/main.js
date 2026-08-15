import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { LightProbeGenerator } from 'three/addons/lights/LightProbeGenerator.js';
import { Water } from 'three/addons/objects/Water.js';
import { MATERIAL_PROFILES, SCENE_PACK } from './scene-pack.js';
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
  city: { index: '01 / 04', title: '云上城市', description: '远处的楼群逐渐亮起，车流沿着街道缓慢穿行。', accent: 0xa6c7d5 },
  village: { index: '02 / 04', title: '雾隐村庄', description: '田埂与屋瓦顺着山势铺开，晨雾在低处缓缓散去。', accent: 0xb4c990 },
  forest: { index: '03 / 04', title: '深山呼吸', description: '林冠随风轻摆，溪水穿过长满苔藓的岩石。', accent: 0x7fa38a },
  coast: { index: '04 / 04', title: '潮汐海岸', description: '海面收集天光，潮线与沿海公路一起延伸向远方。', accent: 0x79b8c7 },
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
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.useLegacyLights = false;

    this.clock = new THREE.Clock();
    this.groups = {};
    this.cars = [];
    this.swayGroups = [];
    this.lightMaterials = [];
    this.waveMaterials = [];
    this.waterSurfaces = [];
    this.animatedWaterMaterials = [];
    this.surfaceMaterials = [];
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
    this.sun.shadow.bias = -0.0005;
    this.scene.add(this.sun, this.sun.target);
    this.sun.target.position.set(0, 0, -25);
    this.fillLight = new THREE.DirectionalLight(0x7896c8, .35);
    this.fillLight.position.set(-25, 35, 20);
    this.scene.add(this.fillLight);
  }

  setupDynamicEnvironment() {
    this.environmentTarget = new THREE.WebGLCubeRenderTarget(64, {
      type: THREE.HalfFloatType,
      generateMipmaps: true,
      minFilter: THREE.LinearMipmapLinearFilter,
    });
    this.environmentCamera = new THREE.CubeCamera(.5, 300, this.environmentTarget);
    this.environmentCamera.position.set(0, 12, -18);
    this.scene.add(this.environmentCamera);
    this.pmrem = new THREE.PMREMGenerator(this.renderer);
    this.pmrem.compileCubemapShader();
    this.lightProbe = new THREE.LightProbe(undefined, .82);
    this.scene.add(this.lightProbe);
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
      this.surfaceMaterials.push(material);
    });
    document.documentElement.dataset.materialProfiles = Object.keys(this.materialLibrary).join(',');
    document.documentElement.dataset.scenePackStyle = SCENE_PACK.style;
  }

  materialFor(profileName, tint) {
    const source = this.materialLibrary[profileName];
    if (!source) return this.mat(tint ?? 0x888888);
    const material = source.clone();
    material.userData = { ...source.userData };
    if (tint !== undefined) material.color.set(tint);
    this.surfaceMaterials.push(material);
    return material;
  }

  scheduleEnvironmentUpdate(delay = .12) {
    this.dynamicEnvironmentDirty = true;
    this.nextEnvironmentUpdate = Math.max(this.clock.elapsedTime + delay, this.nextEnvironmentUpdate);
  }

  async refreshDynamicEnvironment() {
    if (this.dynamicEnvironmentPending) return;
    this.dynamicEnvironmentPending = true;
    this.dynamicEnvironmentDirty = false;
    const previousEnvironment = this.scene.environment;
    const glassVisible = this.physicalGlass?.visible;
    if (this.physicalGlass) this.physicalGlass.visible = false;
    this.scene.environment = null;
    // Environment lighting is derived from the live sky/weather. Hiding the
    // heavy city groups avoids drawing the multi-million-triangle scene six
    // extra times whenever the cube map is refreshed.
    const groupVisibility = Object.values(this.groups).map((group) => group.visible);
    Object.values(this.groups).forEach((group) => { group.visible = false; });
    const waterVisibility = this.waterSurfaces.map((water) => water.visible);
    this.waterSurfaces.forEach((water) => { water.visible = false; });
    this.environmentCamera.update(this.renderer, this.scene);
    const nextEnvironment = this.pmrem.fromCubemap(this.environmentTarget.texture).texture;
    this.scene.environment = nextEnvironment;
    if (this.runtimeEnvironment) this.runtimeEnvironment.dispose();
    this.runtimeEnvironment = nextEnvironment;
    if (previousEnvironment && previousEnvironment !== this.runtimeEnvironment) previousEnvironment.dispose?.();
    if (this.physicalGlass) this.physicalGlass.visible = glassVisible;
    Object.values(this.groups).forEach((group, index) => { group.visible = groupVisibility[index]; });
    this.waterSurfaces.forEach((water, index) => { water.visible = waterVisibility[index]; });
    try {
      const probe = await LightProbeGenerator.fromCubeRenderTarget(this.renderer, this.environmentTarget);
      this.lightProbe.sh.copy(probe.sh);
      this.lightProbe.intensity = .28 + (1 - (this.cloudAmount ?? .3)) * .34;
      document.documentElement.dataset.environment = 'runtime-captured';
      this.environmentRevision = (this.environmentRevision ?? 0) + 1;
      document.documentElement.dataset.environmentRevision = String(this.environmentRevision);
    } finally {
      this.dynamicEnvironmentPending = false;
      this.nextEnvironmentUpdate = this.clock.elapsedTime + 1.5;
    }
  }

  makePhysicalGlass() {
    this.physicalGlass = new THREE.Mesh(
      new THREE.PlaneGeometry(31, 19),
      new THREE.MeshPhysicalMaterial({
        color: 0xd8eef2, roughness: .08, transmission: .96, thickness: .08,
        ior: 1.52, clearcoat: 1, clearcoatRoughness: .04,
        transparent: true, opacity: .12, envMapIntensity: 1.35,
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
    const load = (url, ready, settled = () => {}) => loader.load(url, (gltf) => {
      try {
        this.prepareLicensedAsset(gltf.scene);
        ready(gltf.scene);
        onReady();
      } catch (error) {
        document.documentElement.dataset.modelLoadError = `${url}: ${error?.message || 'asset preparation error'}`;
        console.error('Model preparation failed', url, error);
      } finally {
        settled();
      }
    }, undefined, (error) => {
      document.documentElement.dataset.modelLoadError = `${url}: ${error?.message || 'unknown load error'}`;
      console.error('Model load failed', url, error);
      settled();
    });
    let cityLoadChain = Promise.resolve();
    const loadCity = (url, ready) => {
      cityLoadChain = cityLoadChain.then(() => new Promise((resolve) => load(url, ready, resolve)));
      return cityLoadChain;
    };
    this.pendingAssetLoads ??= { village: [], forest: [], coast: [] };
    const loadDeferred = (sceneNames, url, ready) => {
      let started = false;
      const execute = () => {
        if (started) return;
        started = true;
        load(url, ready);
      };
      sceneNames.forEach((sceneName) => this.pendingAssetLoads[sceneName].push(execute));
    };

    loadCity('./assets/orca/bistro/bistro-exterior-lod-safe-512.glb', (source) => {
      const simplifiedMetal = /antenna|railing|forge_metal|metal_pipe|chimneys_metal|streetlight_metal|grain_metal/i;
      source.traverse((node) => {
        if (!node.isMesh) return;
        node.castShadow = true;
        node.receiveShadow = true;
        const materials = Array.isArray(node.material) ? node.material : [node.material];
        const usesFlatMicroMetal = materials.filter(Boolean).every((material) => simplifiedMetal.test(material.name || ''));
        if (usesFlatMicroMetal) node.castShadow = false;
        materials.filter(Boolean).forEach((material) => {
          if (!simplifiedMetal.test(material.name || '')) return;
          material.map = null;
          material.normalMap = null;
          material.roughnessMap = null;
          material.metalnessMap = null;
          material.color.set(0x596169);
          material.metalness = .88;
          material.roughness = .34;
          material.envMapIntensity = 1.18;
          material.needsUpdate = true;
        });
      });
      const city = this.placeLicensedModel(source, this.groups.city, {
        position: [-10, -1, -205], targetSize: 190, rotationY: 0,
      });
      city.name = 'ORCA_Bistro_Exterior';
      this.buildCityRoadLayout();
      document.documentElement.dataset.cityAsset = 'ORCA_Bistro_Exterior_LOD_CC-BY-4.0';
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

    loadCity('./assets/polyhaven/models/modular_street_seating/modular_street_seating_1k.gltf', (source) => {
      [[-39,6.91,-211,.58,.72],[31,6.91,-221,.52,-2.36],[-58,6.91,-247,.48,.7]].forEach(([x,y,z,s,r]) => {
        this.placeLicensedModel(source, this.groups.city, { position: [x,y,z], targetSize: s * 5.2, rotationY: r });
      });
    });

    loadCity('./assets/polyhaven/models/modular_urban_apartments_facade/modular_urban_apartments_facade_1k.gltf', (source) => {
      const middleDistance = [
        [-105, 6.88, -148, .92, .08], [-128, 6.88, -196, 1.08, .03],
        [-126, 6.88, -254, 1.2, -.04], [105, 6.88, -166, .96, -.07],
        [126, 6.88, -226, 1.12, -.03], [112, 6.88, -282, 1.2, -.04],
      ];
      middleDistance.forEach(([x, y, z, scale, rotation]) => this.addApartmentFacade(source, [x, y, z], scale, rotation));
      for (let x = -144; x <= 144; x += 48) {
        this.addApartmentFacade(source, [x, 6.84, -326 - Math.abs(x) * .04], 1.24 + (Math.abs(x) % 5) * .025, 0);
      }
      document.documentElement.dataset.cityPeriphery = 'polyhaven-cc0-pbr-midground';
      this.scheduleEnvironmentUpdate(1.4);
    });

    loadCity('./assets/polyhaven/models/modular_factory_facade/modular_factory_facade_1k.gltf', (source) => {
      [
        [-82, 6.86, -286, .86, .18], [78, 6.86, -302, .92, -.16],
        [-154, 6.86, -292, 1.02, .12], [148, 6.86, -322, 1.08, -.12],
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
        position: [-8, 6.45, -430], targetSize: 430, rotationY: .05,
      });
      skyline.name = 'Helsinki_CC-BY_4_Periphery_LOD2';
      document.documentElement.dataset.cityFarPeriphery = 'helsinki-textured-city-mesh-cc-by-4-lod2';
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

  addApartmentFacade(source, position, scale, rotationY) {
    const facade = new THREE.Group();
    const bays = [-4, 0, 4];
    const modules = [
      ['wall_door_window_small_01', 0], ['door_window_small_01', 0],
      ['wall_window_centered_double_01', 4], ['window_centered_double_01', 4],
      ['wall_window_centered_double_02', 8], ['window_centered_double_02', 8],
      ['wall_window_centered_double_03', 12], ['window_centered_double_03', 12],
      ['cornice_standard_standard_01', 16], ['crown_standard_standard_01', 16],
    ];
    bays.forEach((x) => modules.forEach(([name,y]) => {
      const part = this.assetPart(source, name);
      if (!part) return;
      part.position.set(x, y, .42);
      facade.add(part);
    }));
    const sideColumns = [-6, 6];
    sideColumns.forEach((x) => {
      const pier = this.assetPart(source, 'wall_pier_standard_01');
      if (!pier) return;
      pier.position.set(x, 0, .42);
      facade.add(pier);
    });
    const shell = new THREE.Mesh(new THREE.BoxGeometry(12, 16, 4.4), this.materialFor('concrete', 0x879093));
    shell.position.set(0, 8, -1.9);
    shell.castShadow = true;
    shell.receiveShadow = true;
    facade.add(shell);
    facade.position.set(...position);
    facade.rotation.y = rotationY;
    facade.scale.setScalar(scale);
    this.groups.city.add(facade);
    return facade;
  }

  addFactoryFacade(source, position, scale, rotationY) {
    const facade = new THREE.Group();
    const bays = [-8, -4, 0, 4, 8];
    const addPart = (name, x, y, z = .45) => {
      const part = this.assetPart(source, name);
      if (!part) return;
      part.position.set(x, y, z);
      facade.add(part);
    };
    bays.forEach((x, index) => {
      const garage = index === 2;
      addPart(garage ? 'wall_door_garage_door_01' : 'wall_window_centered_large_01', x, 0);
      addPart(garage ? 'door_garage_door_01' : 'window_centered_large_01', x, 0);
      for (const y of [4, 8]) {
        addPart('wall_window_centered_large_02', x, y);
        addPart('window_centered_large_02', x, y);
      }
      addPart('cornice02_standard_standard_01', x, 12);
      addPart('crown_standard_standard_01', x, 12.8);
    });
    for (const x of [-10, 10]) {
      addPart('wall_pier_standard_01', x, 0);
      addPart('cornice02_pier_standard_01', x, 12);
    }
    const shell = new THREE.Mesh(new THREE.BoxGeometry(20, 13, 7.2), this.materialFor('concrete', 0x686c6b));
    shell.position.set(0, 6.5, -3.1);
    shell.castShadow = true;
    shell.receiveShadow = true;
    facade.add(shell);
    facade.position.set(...position);
    facade.rotation.y = rotationY;
    facade.scale.setScalar(scale);
    this.groups.city.add(facade);
    return facade;
  }

  makeSky() {
    const geometry = new THREE.SphereGeometry(260, 32, 18);
    this.skyMaterial = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {
        topColor: { value: new THREE.Color(0x182944) },
        horizonColor: { value: new THREE.Color(0xda8f7d) },
        bottomColor: { value: new THREE.Color(0x586474) },
        sunDirection: { value: new THREE.Vector3(.2, .25, -.8).normalize() },
        sunColor: { value: new THREE.Color(0xffd5a0) },
        sunStrength: { value: 1 },
        cloudDim: { value: .1 },
        cloudCoverage: { value: .32 },
        cloudTime: { value: 0 },
        cloudWind: { value: new THREE.Vector2(.012, .004) },
      },
      vertexShader: `varying vec3 vWorld; void main(){ vec4 wp=modelMatrix*vec4(position,1.0); vWorld=normalize(wp.xyz); gl_Position=projectionMatrix*viewMatrix*wp; }`,
      fragmentShader: `
        uniform vec3 topColor; uniform vec3 horizonColor; uniform vec3 bottomColor;
        uniform vec3 sunDirection; uniform vec3 sunColor; uniform float sunStrength; uniform float cloudDim;
        uniform float cloudCoverage; uniform float cloudTime; uniform vec2 cloudWind;
        varying vec3 vWorld;
        float hash21(vec2 p){
          p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y);
        }
        float noise2(vec2 p){
          vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
          return mix(mix(hash21(i),hash21(i+vec2(1.0,0.0)),f.x),mix(hash21(i+vec2(0.0,1.0)),hash21(i+1.0),f.x),f.y);
        }
        float fbm(vec2 p){
          float value=0.0, amplitude=.54;
          mat2 turn=mat2(.82,.57,-.57,.82);
          for(int i=0;i<5;i++){ value+=noise2(p)*amplitude; p=turn*p*2.03+17.1; amplitude*=.49; }
          return value;
        }
        void main(){
          float h=clamp(vWorld.y*.5+.5,0.0,1.0);
          vec3 col=mix(bottomColor,horizonColor,smoothstep(.08,.48,h));
          col=mix(col,topColor,smoothstep(.48,.98,h));
          float sun=max(dot(vWorld,sunDirection),0.0);
          col += sunColor*pow(sun,420.0)*sunStrength*2.2;
          col += sunColor*pow(sun,18.0)*sunStrength*.22;
          col *= 1.0-cloudDim*.28;
          float skyHeight=max(vWorld.y,.045);
          vec2 cloudUv=vWorld.xz/(skyHeight+.28)*.52+cloudWind*cloudTime;
          float broad=fbm(cloudUv*.72);
          float billow=fbm(cloudUv*1.8+vec2(9.2,-4.7))*.36;
          float densityField=broad+billow;
          float threshold=1.03-cloudCoverage*.72;
          float density=smoothstep(threshold-.11,threshold+.08,densityField);
          density*=smoothstep(.025,.24,vWorld.y)*(1.0-smoothstep(.88,1.0,vWorld.y));
          float litSample=fbm(cloudUv*.72+sunDirection.xz*.16);
          float edgeLight=clamp((broad-litSample)*3.2+.48,0.12,1.0);
          vec3 cloudShadow=mix(vec3(.34,.39,.44),horizonColor,.16);
          vec3 cloudLight=mix(vec3(.82,.86,.87),sunColor,.28+edgeLight*.24);
          vec3 cloudColor=mix(cloudShadow,cloudLight,edgeLight);
          cloudColor+=sunColor*pow(max(dot(vWorld,sunDirection),0.0),8.0)*density*.18;
          col=mix(col,cloudColor,density*(.68+cloudCoverage*.26));
          gl_FragColor=vec4(col,1.0);
        }`,
    });
    this.sky = new THREE.Mesh(geometry, this.skyMaterial);
    this.scene.add(this.sky);
  }

  makeClouds() {
    this.cloudGroup = new THREE.Group();
    this.scene.add(this.cloudGroup);
    document.documentElement.dataset.clouds = 'dynamic-layered-fbm-volume';
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
    this.buildVillage();
    this.buildForest();
    this.buildCoast();
  }

  buildCity() {
    const group = this.baseGroup('city');
    const random = seededRandom(921);
    this.addCityCars(group, random);
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
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, length / 8, 1, length / 8], 2));
    geometry.setIndex([0, 2, 1, 2, 3, 1]);
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
    underlay.position.set(-10, 6.72, -205);
    underlay.receiveShadow = true;
    group.add(underlay);

    const routeStart = [96, -142];
    const routeEnd = [-62, -278];
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

    const crossStart = [-132, -273];
    const crossEnd = [128, -273];
    this.makeRoadStrip(group, crossStart, crossEnd, 15, road, 6.865);
    this.makeRoadStrip(group, crossStart, crossEnd, 3.2, parking, 6.885, -9.4);
    this.makeRoadStrip(group, crossStart, crossEnd, 3.2, parking, 6.885, 9.4);
    this.makeRoadStrip(group, crossStart, crossEnd, 5.8, sidewalk, 6.88, -14);
    this.makeRoadStrip(group, crossStart, crossEnd, 5.8, sidewalk, 6.88, 14);

    const marking = new THREE.MeshBasicMaterial({ color: 0xe7e1ce, transparent: true, opacity: .82, depthWrite: false });
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
      const routeStart = new THREE.Vector3(57, 7.38, -176);
      const routeEnd = new THREE.Vector3(6, 7.38, -221);
      const routeDirection = routeEnd.clone().sub(routeStart).normalize();
      const laneOffset = new THREE.Vector3(-routeDirection.z, 0, routeDirection.x).multiplyScalar(direction * 1.35);
      const pathT = random();
      car.position.lerpVectors(routeStart, routeEnd, pathT).add(laneOffset);
      car.rotation.y = Math.atan2(routeDirection.x * direction, routeDirection.z * direction);
      car.userData = {
        speed: .035 + random() * .04,
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
    this.rain.visible = false; this.scene.add(this.rain);

    const snowPositions = [];
    for (let i = 0; i < 850; i++) snowPositions.push((random() - .5) * 100, random() * 55, 18 - random() * 115);
    const snowGeo = new THREE.BufferGeometry();
    snowGeo.setAttribute('position', new THREE.Float32BufferAttribute(snowPositions, 3));
    this.snow = new THREE.Points(snowGeo, new THREE.PointsMaterial({ color: 0xffffff, size: .22, transparent: true, opacity: .72, depthWrite: false }));
    this.snow.visible = false; this.scene.add(this.snow);
  }

  switchScene(name, animate = true) {
    this.activeScene = name;
    if (name !== 'city' && this.pendingAssetLoads?.[name]?.length) {
      const queued = this.pendingAssetLoads[name].splice(0);
      queued.forEach((startLoad) => startLoad());
    }
    Object.entries(this.groups).forEach(([key, group]) => { group.visible = key === name; });
    const setups = {
      city: { position: [0, 31, -35], target: [-6, 17, -205], fog: 0.0026, fov: 47, lightTarget: [-10, 12, -205], environment: [-10, 23, -205] },
      village: { position: [0, 8, 24], target: [0, 2, -30], fog: 0.0085, fov: 48, lightTarget: [0, 4, -32], environment: [0, 10, -24] },
      forest: { position: [0, 7, 20], target: [0, 3, -24], fog: 0.012, fov: 48, lightTarget: [0, 6, -42], environment: [0, 10, -28] },
      coast: { position: [0, 10, 25], target: [7, 2, -31], fog: 0.0065, fov: 48, lightTarget: [4, 3, -38], environment: [4, 12, -28] },
    };
    const setup = setups[name];
    if (import.meta.env.DEV && name === 'city') {
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
    if (!animate) { this.camera.position.copy(this.baseCamera); this.cameraTarget.copy(this.baseTarget); }
    this.scheduleEnvironmentUpdate(.18);
  }

  setWeather(mode, data = this.weatherData) {
    this.weather = mode;
    this.weatherData = { ...this.weatherData, ...data };
    const actual = mode === 'live' ? weatherModeFromCode(window.appState?.weather?.weatherCode ?? 1) : mode;
    this.activeWeather = actual;
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
  }

  solarPosition() {
    const now = new Date();
    const start = new Date(Date.UTC(now.getUTCFullYear(), 0, 0));
    const day = Math.floor((now - start) / 86400000);
    const hour = this.hour;
    const gamma = 2 * Math.PI / 365 * (day - 1 + (hour - 12) / 24);
    const decl = .006918 - .399912 * Math.cos(gamma) + .070257 * Math.sin(gamma) - .006758 * Math.cos(2 * gamma) + .000907 * Math.sin(2 * gamma) - .002697 * Math.cos(3 * gamma) + .00148 * Math.sin(3 * gamma);
    const eq = 229.18 * (.000075 + .001868 * Math.cos(gamma) - .032077 * Math.sin(gamma) - .014615 * Math.cos(2 * gamma) - .040849 * Math.sin(2 * gamma));
    const offset = this.timezoneOffset(now, this.location.timezone);
    const solarMinutes = hour * 60 + eq + 4 * this.location.longitude - 60 * offset;
    const ha = (solarMinutes / 4 - 180) * Math.PI / 180;
    const lat = this.location.latitude * Math.PI / 180;
    const elevation = Math.asin(Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(ha));
    const azimuth = Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(lat) - Math.tan(decl) * Math.cos(lat));
    return { elevation, azimuth };
  }

  timezoneOffset(date, timezone) {
    try {
      const parts = new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(date);
      const get = (type) => Number(parts.find((p) => p.type === type)?.value);
      const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'));
      return (asUtc - date.getTime()) / 3600000;
    } catch { return -new Date().getTimezoneOffset() / 60; }
  }

  applyAtmosphere() {
    if (!this.skyMaterial) return;
    const { elevation, azimuth } = this.solarPosition();
    const sunHeight = Math.sin(elevation);
    const daylight = smoothstep(-.12, .18, sunHeight);
    const night = 1 - daylight;
    const horizonGlow = Math.exp(-Math.pow(sunHeight / .22, 2));
    const storm = this.activeWeather === 'rain' ? .42 : this.activeWeather === 'fog' ? .35 : 0;
    const cloud = this.cloudAmount ?? .3;

    const topNight = new THREE.Color(0x040b18), topDay = new THREE.Color(0x4f8fbd);
    const horizonNight = new THREE.Color(0x101b31), horizonDay = new THREE.Color(0xb9d6dd);
    const horizonDawn = new THREE.Color(0xe79468);
    const bottomNight = new THREE.Color(0x0b1420), bottomDay = new THREE.Color(0x728f91);
    const top = topNight.clone().lerp(topDay, daylight).lerp(new THREE.Color(0x48545d), storm);
    const horizon = horizonNight.clone().lerp(horizonDay, daylight).lerp(horizonDawn, horizonGlow * .72).lerp(new THREE.Color(0x697278), storm);
    const bottom = bottomNight.clone().lerp(bottomDay, daylight).lerp(new THREE.Color(0x3f494b), storm);
    this.skyMaterial.uniforms.topColor.value.copy(top);
    this.skyMaterial.uniforms.horizonColor.value.copy(horizon);
    this.skyMaterial.uniforms.bottomColor.value.copy(bottom);
    this.skyMaterial.uniforms.sunColor.value.set(horizonGlow > .25 ? 0xffc178 : 0xffeed0);
    this.skyMaterial.uniforms.sunStrength.value = daylight * (1 - cloud * .72);
    this.skyMaterial.uniforms.cloudDim.value = cloud;
    this.skyMaterial.uniforms.cloudCoverage.value = clamp(.2 + cloud * .72, .18, .92);

    const distance = 100;
    const sunDir = new THREE.Vector3(Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation), -Math.cos(azimuth) * Math.cos(elevation)).normalize();
    this.skyMaterial.uniforms.sunDirection.value.copy(sunDir);
    const lightTarget = this.lightTarget ?? new THREE.Vector3(0, 4, -25);
    this.sun.target.position.copy(lightTarget);
    this.sun.position.copy(lightTarget).addScaledVector(sunDir, distance);
    this.sun.position.y = Math.max(lightTarget.y + 4, this.sun.position.y);
    this.sun.color.set(horizonGlow > .18 ? 0xffb46f : 0xfff1cf);
    this.sun.intensity = Math.max(.05, daylight * 2.35 * (1 - cloud * .62));
    this.hemisphere.intensity = .025 + daylight * .1 * (1 - storm * .5);
    this.hemisphere.color.set(top);
    this.fillLight.intensity = .035 + night * .15;
    this.lightProbe.intensity = .28 + daylight * .34 * (1 - cloud * .35);
    this.renderer.toneMappingExposure = .52 + daylight * .28 + horizonGlow * .08;
    const shadowHourDelta = this.lastShadowHour == null
      ? 24
      : Math.min(Math.abs(this.hour - this.lastShadowHour), 24 - Math.abs(this.hour - this.lastShadowHour));
    if (shadowHourDelta >= .08) {
      this.lastShadowHour = this.hour;
      this.renderer.shadowMap.needsUpdate = true;
    }
    this.scene.fog.color.copy(horizon).lerp(new THREE.Color(0xb8c2bf), this.activeWeather === 'fog' ? .45 : 0);
    this.scene.fog.density = (this.targetFog ?? .007) * (this.activeWeather === 'fog' ? 3.2 : this.activeWeather === 'rain' ? 1.5 : 1);
    this.lightMaterials.forEach((mat, index) => { mat.opacity = clamp(.04 + night * (.45 + (index % 4) * .13), .04, .92); });
    this.surfaceMaterials.forEach((mat) => {
      const profile = MATERIAL_PROFILES[mat.userData.profile];
      if (!profile) return;
      const wet = profile.wet;
      if (this.activeWeather === 'rain' && wet) {
        mat.roughness = wet.roughness;
        mat.clearcoat = wet.clearcoat;
        mat.clearcoatRoughness = .07;
        mat.envMapIntensity = wet.envMapIntensity;
      } else {
        mat.roughness = mat.userData.baseRoughness;
        mat.clearcoat = mat.userData.baseClearcoat;
        mat.clearcoatRoughness = profile.clearcoatRoughness ?? .3;
        mat.envMapIntensity = mat.userData.baseEnvMapIntensity;
      }
    });
    if (this.physicalGlass) {
      this.physicalGlass.material.roughness = this.activeWeather === 'rain' ? .2 : .08;
      this.physicalGlass.material.opacity = this.activeWeather === 'fog' ? .22 : .12;
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
      this.renderer.setSize(width, height, false);
      this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.65));
    };
    addEventListener('resize', resize);
    this.resizeObserver = new ResizeObserver(resize);
    this.resizeObserver.observe(this.canvas);
    requestAnimationFrame(resize);
  }

  updateWeatherParticles(dt, elapsed) {
    const wind = (this.weatherData.windSpeed ?? 8) * .015;
    if (this.rain.visible) {
      const pos = this.rain.geometry.attributes.position.array;
      for (let i = 0; i < pos.length; i += 6) {
        pos[i + 1] -= dt * 38; pos[i + 4] -= dt * 38; pos[i] += wind * dt; pos[i + 3] += wind * dt;
        if (pos[i + 1] < -2) { const lift = 58; pos[i + 1] += lift; pos[i + 4] += lift; }
      }
      this.rain.geometry.attributes.position.needsUpdate = true;
    }
    if (this.snow.visible) {
      const pos = this.snow.geometry.attributes.position.array;
      for (let i = 0; i < pos.length; i += 3) {
        pos[i + 1] -= dt * 3.2; pos[i] += Math.sin(elapsed * .7 + i) * dt * .35 + wind * dt;
        if (pos[i + 1] < -2) pos[i + 1] += 57;
      }
      this.snow.geometry.attributes.position.needsUpdate = true;
    }
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    const dt = Math.min(this.clock.getDelta(), .05);
    const elapsed = this.clock.elapsedTime;
    this.skyMaterial.uniforms.cloudTime.value = elapsed;
    const cloudSpeed = .006 + (this.weatherData.windSpeed ?? 8) * .00085;
    this.skyMaterial.uniforms.cloudWind.value.set(cloudSpeed, cloudSpeed * .34);
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
    this.renderer.render(this.scene, this.camera);

    this.frameSamples.push(dt);
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
    const frequency = scene === 'city' ? 650 : scene === 'coast' ? 420 : 850;
    this.filter.frequency.setTargetAtTime(frequency, this.ctx.currentTime, .8);
    this.gain.gain.setTargetAtTime(this.enabled ? .032 : 0, this.ctx.currentTime, .35);
    return this.enabled;
  }
}

const world = new LivingWorld($('#world'));
const audio = new AmbientAudio();
window.appState = { liveTime: true, weatherMode: 'live', liveContext: null, weather: null };

function localTimeParts(timezone) {
  const parts = new Intl.DateTimeFormat('zh-CN', { timeZone: timezone, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(new Date());
  const get = (type) => Number(parts.find((part) => part.type === type)?.value || 0);
  return { hour: get('hour'), minute: get('minute'), second: get('second') };
}

function periodName(hour) {
  if (hour < 5) return '深夜'; if (hour < 8) return '晨曦'; if (hour < 11) return '清晨';
  if (hour < 14) return '日中'; if (hour < 17) return '午后'; if (hour < 19) return '黄昏'; if (hour < 22) return '暮色'; return '夜晚';
}

function displayTime(hour, minute) {
  $('#timeLabel').textContent = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  $('#periodLabel').textContent = periodName(hour + minute / 60);
}

async function getLiveContext() {
  if (window.outOfWindow) return window.outOfWindow.getLiveContext();
  try {
    const geo = await fetch('https://ipwho.is/?fields=success,city,region,country,latitude,longitude,timezone').then((r) => r.json());
    const query = new URLSearchParams({ latitude: geo.latitude, longitude: geo.longitude, current: 'temperature_2m,apparent_temperature,is_day,precipitation,weather_code,cloud_cover,wind_speed_10m', timezone: 'auto' });
    const forecast = await fetch(`https://api.open-meteo.com/v1/forecast?${query}`).then((r) => r.json());
    return { location: { city: geo.city, region: geo.region, country: geo.country, latitude: geo.latitude, longitude: geo.longitude, timezone: geo.timezone?.id || forecast.timezone }, weather: { temperature: forecast.current.temperature_2m, apparentTemperature: forecast.current.apparent_temperature, weatherCode: forecast.current.weather_code, isDay: forecast.current.is_day, precipitation: forecast.current.precipitation, cloudCover: forecast.current.cloud_cover, windSpeed: forecast.current.wind_speed_10m }, fallback: false };
  } catch { return { location: { city: '上海', country: '中国', latitude: 31.23, longitude: 121.47, timezone: 'Asia/Shanghai' }, weather: { temperature: 22, weatherCode: 1, cloudCover: 35, windSpeed: 8 }, fallback: true }; }
}

async function syncWeather() {
  $('#syncState').textContent = '正在同步本地天空';
  $('#refreshWeather').classList.add('spinning');
  const data = await getLiveContext();
  window.appState.liveContext = data;
  window.appState.weather = data.weather;
  world.location = data.location;
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
  if (audio.ctx) audio.filter.frequency.setTargetAtTime(name === 'city' ? 650 : name === 'coast' ? 420 : 850, audio.ctx.currentTime, .8);
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

setInterval(() => {
  const timezone = window.appState.liveContext?.location?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  const { hour, minute } = localTimeParts(timezone);
  $('#localClock').textContent = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  if (window.appState.liveTime) {
    const total = hour * 60 + minute;
    $('#timeSlider').value = total;
    displayTime(hour, minute);
    world.setTime(total / 60);
  }
}, 1000);

syncWeather();
