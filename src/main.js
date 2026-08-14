import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
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
    this.renderer.setSize(innerWidth, innerHeight);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
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
    this.backdropMaterials = [];
    this.surfaceMaterials = [];
    this.cloudMeshes = [];
    this.activeScene = 'city';
    this.hour = 19.7;
    this.weather = 'clear';
    this.weatherData = { cloudCover: 35, windSpeed: 8, precipitation: 0 };
    this.location = { latitude: 31.23, longitude: 121.47, timezone: 'Asia/Shanghai' };
    this.pointer = { x: 0, y: 0, targetX: 0, targetY: 0, down: false, startX: 0, startY: 0 };
    this.frameSamples = [];

    this.makeLights();
    this.loadEnvironment();
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
    this.hemisphere = new THREE.HemisphereLight(0xa9c8db, 0x18231f, 1.3);
    this.scene.add(this.hemisphere);
    this.sun = new THREE.DirectionalLight(0xffe1b2, 3.2);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(1536, 1536);
    this.sun.shadow.camera.left = -70;
    this.sun.shadow.camera.right = 70;
    this.sun.shadow.camera.top = 55;
    this.sun.shadow.camera.bottom = -35;
    this.sun.shadow.camera.near = 1;
    this.sun.shadow.camera.far = 180;
    this.sun.shadow.bias = -0.0005;
    this.scene.add(this.sun, this.sun.target);
    this.sun.target.position.set(0, 0, -25);
    this.fillLight = new THREE.DirectionalLight(0x7896c8, .35);
    this.fillLight.position.set(-25, 35, 20);
    this.scene.add(this.fillLight);
  }

  loadEnvironment() {
    new RGBELoader().load('./assets/polyhaven/hdri/sunset_jhbcentral_1k.hdr', (hdr) => {
      hdr.mapping = THREE.EquirectangularReflectionMapping;
      const pmrem = new THREE.PMREMGenerator(this.renderer);
      const env = pmrem.fromEquirectangular(hdr).texture;
      this.scene.environment = env;
      this.scene.environmentIntensity = .85;
      hdr.dispose(); pmrem.dispose();
      document.documentElement.dataset.hdr = 'ready';
    }, undefined, () => { document.documentElement.dataset.hdr = 'fallback'; });
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
    loader.load('./assets/polyhaven/pine_sapling_small/pine_sapling_small_1k.gltf', (gltf) => {
      const source = gltf.scene;
      source.traverse((node) => {
        if (!node.isMesh) return;
        node.castShadow = true; node.receiveShadow = true;
        if (node.material) {
          node.material.envMapIntensity = 1.05;
          node.material.roughness = Math.max(.42, node.material.roughness ?? .7);
          node.material.needsUpdate = true;
        }
      });
      const placements = [
        [-12,-1,6,5.4,.15],[13,-1,3,4.8,-.3],[-22,-1,-10,6.2,.4],[22,-1,-16,5.8,-.6],
        [-7,-1,-22,4.2,.8],[9,-1,-28,4.6,-.9],[-29,-1,-36,6.5,.25],[30,-1,-42,6.2,-.35],
      ];
      placements.forEach(([x,y,z,s,r], index) => {
        const tree = index === 0 ? source : source.clone(true);
        tree.position.set(x,y,z); tree.scale.setScalar(s); tree.rotation.y = r;
        this.groups.forest.add(tree);
      });
      document.documentElement.dataset.heroModel = 'ready';
    }, undefined, () => { document.documentElement.dataset.heroModel = 'fallback'; });
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
      },
      vertexShader: `varying vec3 vWorld; void main(){ vec4 wp=modelMatrix*vec4(position,1.0); vWorld=normalize(wp.xyz); gl_Position=projectionMatrix*viewMatrix*wp; }`,
      fragmentShader: `
        uniform vec3 topColor; uniform vec3 horizonColor; uniform vec3 bottomColor;
        uniform vec3 sunDirection; uniform vec3 sunColor; uniform float sunStrength; uniform float cloudDim;
        varying vec3 vWorld;
        void main(){
          float h=clamp(vWorld.y*.5+.5,0.0,1.0);
          vec3 col=mix(bottomColor,horizonColor,smoothstep(.08,.48,h));
          col=mix(col,topColor,smoothstep(.48,.98,h));
          float sun=max(dot(vWorld,sunDirection),0.0);
          col += sunColor*pow(sun,420.0)*sunStrength*2.2;
          col += sunColor*pow(sun,18.0)*sunStrength*.22;
          col *= 1.0-cloudDim*.28;
          gl_FragColor=vec4(col,1.0);
        }`,
    });
    this.sky = new THREE.Mesh(geometry, this.skyMaterial);
    this.scene.add(this.sky);
  }

  makeClouds() {
    const random = seededRandom(44);
    this.cloudGroup = new THREE.Group();
    const puff = new THREE.SphereGeometry(1, 10, 7);
    for (let i = 0; i < 22; i++) {
      const mat = new THREE.MeshLambertMaterial({ color: 0xdbe1e0, transparent: true, opacity: .22, depthWrite: false });
      const cloud = new THREE.Group();
      const puffs = 3 + Math.floor(random() * 4);
      for (let j = 0; j < puffs; j++) {
        const mesh = new THREE.Mesh(puff, mat);
        mesh.position.set(j * 2.2 - puffs, random() * .7, random() * .9);
        mesh.scale.set(2.4 + random() * 2.8, .7 + random() * .8, 1.4 + random() * 2);
        cloud.add(mesh);
        this.cloudMeshes.push(mesh);
      }
      cloud.position.set((random() - .5) * 190, 24 + random() * 30, -45 - random() * 130);
      cloud.scale.setScalar(.7 + random() * 1.2);
      this.cloudGroup.add(cloud);
    }
    this.scene.add(this.cloudGroup);
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

  addGround(group, color, y = -1) {
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(220, 220), this.mat(color, .95));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, y, -45);
    ground.receiveShadow = true;
    group.add(ground);
    return ground;
  }

  addBackdrop(group, url) {
    const texture = new THREE.TextureLoader().load(url);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.minFilter = THREE.LinearFilter;
    const material = new THREE.ShaderMaterial({
      depthWrite: true,
      fog: false,
      uniforms: {
        map: { value: texture },
        daylight: { value: .45 },
        storm: { value: 0 },
        dawn: { value: .3 },
      },
      vertexShader: `varying vec2 vUv; void main(){vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
      fragmentShader: `
        uniform sampler2D map; uniform float daylight; uniform float storm; uniform float dawn; varying vec2 vUv;
        void main(){
          vec3 c=texture2D(map,vUv).rgb;
          float l=dot(c,vec3(.2126,.7152,.0722));
          vec3 night=c*vec3(.16,.25,.42)*.55 + pow(c,vec3(2.0))*vec3(.22,.16,.09);
          vec3 day=mix(vec3(l),c,.72)*vec3(.88,1.0,1.03)*1.04;
          c=mix(night,day,daylight);
          c=mix(c,c*vec3(.54,.62,.67),storm*.72);
          c+=vec3(.20,.075,.025)*dawn*.18;
          gl_FragColor=vec4(c,1.0);
        }`,
    });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(260, 146), material);
    // The detailed plate sits behind nearby real-time geometry. Distant
    // procedural meshes naturally disappear behind it, acting as low-cost LOD.
    plane.position.set(0, 38, -70);
    plane.renderOrder = -10;
    group.add(plane);
    this.backdropMaterials.push(material);
    return plane;
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
    this.addBackdrop(group, './assets/city.png');
    this.addGround(group, 0x22292d);

    const roadMat = this.mat(0x11171a, .82);
    const road1 = new THREE.Mesh(new THREE.PlaneGeometry(16, 180), roadMat);
    road1.rotation.x = -Math.PI / 2; road1.position.set(2, -.94, -45); road1.receiveShadow = true; group.add(road1);
    const road2 = new THREE.Mesh(new THREE.PlaneGeometry(130, 10), roadMat);
    road2.rotation.x = -Math.PI / 2; road2.position.set(0, -.93, -35); road2.receiveShadow = true; group.add(road2);

    const stripeMat = new THREE.MeshBasicMaterial({ color: 0xb5b09a, transparent: true, opacity: .35 });
    for (let z = 16; z > -120; z -= 8) {
      const stripe = new THREE.Mesh(new THREE.PlaneGeometry(.12, 3.8), stripeMat);
      stripe.rotation.x = -Math.PI / 2; stripe.position.set(2, -.90, z); group.add(stripe);
    }

    const windowGeo = new THREE.PlaneGeometry(.42, .28);
    for (let i = 0; i < 58; i++) {
      let x = (random() - .5) * 118;
      let z = -4 - random() * 116;
      if (Math.abs(x - 2) < 11 || Math.abs(z + 35) < 7) x += x < 2 ? -13 : 13;
      const w = 4 + random() * 7;
      const d = 4 + random() * 7;
      const h = 5 + Math.pow(random(), .55) * 30;
      const color = new THREE.Color().setHSL(.56 + random() * .05, .10 + random() * .12, .22 + random() * .14);
      const building = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), this.mat(color, .75, .1));
      building.position.set(x, h / 2 - 1, z);
      building.castShadow = true; building.receiveShadow = true;
      group.add(building);
      if (random() > .5) {
        const roof = new THREE.Mesh(new THREE.BoxGeometry(w * .45, .5 + random(), d * .45), this.mat(0x343c40, .88, .15));
        roof.position.set(x, h - .65, z); group.add(roof);
      }
      const lightMat = new THREE.MeshBasicMaterial({ color: random() > .25 ? 0xffc77d : 0x9dc9e8, transparent: true, opacity: .15 });
      this.lightMaterials.push(lightMat);
      const cols = Math.max(2, Math.floor(w / 1.15));
      const rows = Math.min(12, Math.floor(h / 1.4));
      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          if (random() < .42) continue;
          const win = new THREE.Mesh(windowGeo, lightMat);
          win.position.set(x - w * .38 + col * (w * .76 / Math.max(cols - 1, 1)), .2 + row * 1.35, z + d / 2 + .012);
          group.add(win);
        }
      }
    }
    this.addCityCars(group, random);
  }

  addCityCars(group, random) {
    const colors = [0x292e34, 0xaeb4b1, 0x783e36, 0x394d68];
    for (let i = 0; i < 16; i++) {
      const car = new THREE.Group();
      const body = new THREE.Mesh(new THREE.BoxGeometry(1, .34, 1.9), this.mat(colors[i % colors.length], .38, .4));
      body.castShadow = true; car.add(body);
      const lampMat = new THREE.MeshBasicMaterial({ color: i % 2 ? 0xff3f28 : 0xffe7ad });
      const lamp = new THREE.Mesh(new THREE.BoxGeometry(.7, .11, .06), lampMat);
      lamp.position.set(0, .05, i % 2 ? .98 : -.98); car.add(lamp);
      car.position.set(i % 2 ? -1 : 5, -.63, 14 - random() * 130);
      car.userData = { speed: 3 + random() * 4, direction: i % 2 ? -1 : 1, lane: i % 2 ? -1 : 5 };
      group.add(car); this.cars.push(car);
    }
  }

  addTree(group, x, z, scale = 1, color = 0x31523e) {
    const tree = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(.16 * scale, .25 * scale, 2.2 * scale, 6), this.mat(0x4a3b2d, 1));
    trunk.position.y = .1 * scale; trunk.castShadow = true; tree.add(trunk);
    const foliage = new THREE.Mesh(new THREE.ConeGeometry(1.45 * scale, 4.8 * scale, 8), this.mat(color, .94));
    foliage.position.y = 2.6 * scale; foliage.castShadow = true; tree.add(foliage);
    tree.position.set(x, 0, z); group.add(tree); return tree;
  }

  addHouse(group, x, z, scale = 1, wallColor = 0xc6bda6) {
    const house = new THREE.Group();
    const base = new THREE.Mesh(new THREE.BoxGeometry(4 * scale, 2.5 * scale, 3.3 * scale), this.mat(wallColor, .92));
    base.position.y = .25 * scale; base.castShadow = true; base.receiveShadow = true; house.add(base);
    const roof = new THREE.Mesh(new THREE.ConeGeometry(3.25 * scale, 1.5 * scale, 4), this.mat(0x403b36, .96));
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
    this.addBackdrop(group, './assets/village.png');
    this.addGround(group, 0x45563c);
    for (let i = 0; i < 16; i++) {
      const field = new THREE.Mesh(new THREE.PlaneGeometry(9 + random() * 15, 8 + random() * 18), this.mat(i % 3 === 0 ? 0x5d6f43 : i % 3 === 1 ? 0x6d7644 : 0x394c35, 1));
      field.rotation.x = -Math.PI / 2; field.rotation.z = (random() - .5) * .2;
      field.position.set((random() - .5) * 90, -.91, -12 - random() * 90); field.receiveShadow = true; group.add(field);
    }
    const lane = new THREE.Mesh(new THREE.PlaneGeometry(7, 145), this.mat(0x4b4941, 1));
    lane.rotation.x = -Math.PI / 2; lane.rotation.z = -.13; lane.position.set(4, -.85, -42); group.add(lane);
    for (let i = 0; i < 18; i++) {
      const x = (random() - .5) * 80;
      const z = -4 - random() * 100;
      if (Math.abs(x - (4 + z * .13)) < 7) continue;
      this.addHouse(group, x, z, .65 + random() * .55, random() > .5 ? 0xc6bda6 : 0xb8b095);
    }
    const trees = new THREE.Group();
    for (let i = 0; i < 48; i++) this.addTree(trees, (random() - .5) * 115, -random() * 125, .35 + random() * .8, random() > .4 ? 0x3c5d3b : 0x496643);
    group.add(trees); this.swayGroups.push(trees);
    this.addMountainLayer(group, 0x394a3d, -128, 16, 1.3);
  }

  addMountainLayer(group, color, z, y, scale = 1) {
    const shape = new THREE.Shape();
    shape.moveTo(-130, -15);
    const random = seededRandom(Math.abs(Math.floor(z * 10)));
    for (let x = -130; x <= 130; x += 12) shape.lineTo(x, Math.sin(x * .06) * 4 + random() * 9 + y);
    shape.lineTo(130, -15); shape.closePath();
    const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshLambertMaterial({ color, fog: true }));
    mesh.position.z = z; mesh.scale.setScalar(scale); group.add(mesh); return mesh;
  }

  buildForest() {
    const group = this.baseGroup('forest');
    const random = seededRandom(704);
    this.addBackdrop(group, './assets/forest.png');
    this.addGround(group, 0x1d2c22);
    const streamMat = new THREE.ShaderMaterial({
      transparent: true,
      uniforms: { time: { value: 0 }, night: { value: 0 } },
      vertexShader: `uniform float time; varying vec2 vUv; void main(){vUv=uv; vec3 p=position; p.z+=sin(p.y*.35+time)*.12; gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);}`,
      fragmentShader: `uniform float time; uniform float night; varying vec2 vUv; void main(){float r=sin(vUv.y*80.0-time*3.0)*.5+.5; vec3 c=mix(vec3(.06,.20,.23),vec3(.35,.58,.62),r*.22); c*=1.0-night*.55; gl_FragColor=vec4(c,.86);}`,
      side: THREE.DoubleSide,
    });
    const stream = new THREE.Mesh(new THREE.PlaneGeometry(12, 150, 8, 40), streamMat);
    stream.rotation.x = -Math.PI / 2; stream.rotation.z = -.18; stream.position.set(0, -.74, -42); group.add(stream); this.waveMaterials.push(streamMat);
    const trees = new THREE.Group();
    for (let i = 0; i < 115; i++) {
      let x = (random() - .5) * 125;
      const z = 8 - random() * 140;
      if (Math.abs(x - z * .18) < 7) x += x < 0 ? -9 : 9;
      this.addTree(trees, x, z, .65 + random() * 1.45, random() > .3 ? 0x203d2b : 0x294a34);
    }
    group.add(trees); this.swayGroups.push(trees);
    const rockMat = this.mat(0x3b4540, 1);
    for (let i = 0; i < 30; i++) {
      const rock = new THREE.Mesh(new THREE.DodecahedronGeometry(.5 + random() * 1.4, 0), rockMat);
      rock.scale.set(1.4, .65, 1); rock.position.set((random() - .5) * 24, -.2, 2 - random() * 110); rock.rotation.set(random(), random(), random()); rock.castShadow = true; group.add(rock);
    }
    this.addMountainLayer(group, 0x243e32, -145, 22, 1.5);
  }

  buildCoast() {
    const group = this.baseGroup('coast');
    const random = seededRandom(118);
    this.addBackdrop(group, './assets/coast.png');
    this.addGround(group, 0x665d4d);
    const oceanMat = new THREE.ShaderMaterial({
      uniforms: { time: { value: 0 }, night: { value: 0 }, sunColor: { value: new THREE.Color(0xffd1a0) } },
      vertexShader: `uniform float time; varying vec2 vUv; varying float vWave; void main(){vUv=uv; vec3 p=position; float w=sin(p.x*.32+time)*.22+sin(p.y*.23-time*.7)*.3+sin((p.x+p.y)*.11+time*.45)*.4; p.z+=w; vWave=w; gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);}`,
      fragmentShader: `uniform float time; uniform float night; uniform vec3 sunColor; varying vec2 vUv; varying float vWave; void main(){float glint=pow(max(0.0,sin(vUv.x*120.0+time)+sin(vUv.y*90.0-time*.7))*.5,7.0); vec3 deep=mix(vec3(.025,.16,.24),vec3(.08,.35,.46),vWave*.55+.5); deep=mix(deep,vec3(.015,.035,.075),night*.7); deep+=sunColor*glint*(1.0-night)*.16; gl_FragColor=vec4(deep,1.0);}`,
      side: THREE.DoubleSide,
    });
    const ocean = new THREE.Mesh(new THREE.PlaneGeometry(170, 180, 70, 70), oceanMat);
    ocean.rotation.x = -Math.PI / 2; ocean.position.set(32, -1.1, -48); group.add(ocean); this.waveMaterials.push(oceanMat);
    const cliffMat = this.mat(0x594d3c, 1);
    for (let i = 0; i < 24; i++) {
      const cliff = new THREE.Mesh(new THREE.DodecahedronGeometry(4 + random() * 7, 1), cliffMat);
      cliff.scale.set(1.5, .8 + random(), 1.4); cliff.position.set(-32 - random() * 38, 1 + random() * 5, 7 - i * 5); cliff.castShadow = true; group.add(cliff);
    }
    for (let i = 0; i < 26; i++) this.addHouse(group, -20 - random() * 56, 4 - random() * 104, .42 + random() * .52, random() > .4 ? 0xd6d0bd : 0xc3b59a);
    const coastTrees = new THREE.Group();
    for (let i = 0; i < 32; i++) this.addTree(coastTrees, -12 - random() * 75, 9 - random() * 112, .35 + random() * .55, 0x304b37);
    group.add(coastTrees); this.swayGroups.push(coastTrees);
    this.addMountainLayer(group, 0x445451, -148, 12, 1.2);
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
    Object.entries(this.groups).forEach(([key, group]) => { group.visible = key === name; });
    const setups = {
      city: [[0, 9, 22], [0, 4, -24], 0.0065],
      village: [[0, 8, 24], [0, 2, -30], 0.0085],
      forest: [[0, 7, 20], [0, 3, -24], 0.012],
      coast: [[0, 10, 25], [7, 2, -31], 0.0065],
    };
    const [pos, target, fog] = setups[name];
    this.baseCamera = new THREE.Vector3(...pos);
    this.baseTarget = new THREE.Vector3(...target);
    this.scene.fog.density = fog;
    this.targetFog = fog;
    if (!animate) { this.camera.position.copy(this.baseCamera); this.cameraTarget.copy(this.baseTarget); }
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

    const distance = 100;
    const sunDir = new THREE.Vector3(Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation), -Math.cos(azimuth) * Math.cos(elevation)).normalize();
    this.skyMaterial.uniforms.sunDirection.value.copy(sunDir);
    this.sun.position.copy(sunDir).multiplyScalar(distance);
    this.sun.position.y = Math.max(4, this.sun.position.y);
    this.sun.color.set(horizonGlow > .18 ? 0xffb46f : 0xfff1cf);
    this.sun.intensity = Math.max(.05, daylight * 3.5 * (1 - cloud * .68));
    this.hemisphere.intensity = .17 + daylight * 1.35 * (1 - storm * .5);
    this.hemisphere.color.set(top);
    this.fillLight.intensity = .18 + night * .3;
    this.renderer.toneMappingExposure = .58 + daylight * .55 + horizonGlow * .12;
    this.scene.fog.color.copy(horizon).lerp(new THREE.Color(0xb8c2bf), this.activeWeather === 'fog' ? .45 : 0);
    this.scene.fog.density = (this.targetFog ?? .007) * (this.activeWeather === 'fog' ? 3.2 : this.activeWeather === 'rain' ? 1.5 : 1);
    this.lightMaterials.forEach((mat, index) => { mat.opacity = clamp(.04 + night * (.45 + (index % 4) * .13), .04, .92); });
    const wetness = this.activeWeather === 'rain' ? .72 : .04;
    this.surfaceMaterials.forEach((mat) => {
      mat.clearcoat = Math.max(mat.metalness > .2 ? .25 : 0, wetness);
      mat.clearcoatRoughness = this.activeWeather === 'rain' ? .08 : .32;
      mat.envMapIntensity = this.activeWeather === 'rain' ? 1.18 : .75;
    });
    if (this.physicalGlass) {
      this.physicalGlass.material.roughness = this.activeWeather === 'rain' ? .2 : .08;
      this.physicalGlass.material.opacity = this.activeWeather === 'fog' ? .22 : .12;
    }
    this.backdropMaterials.forEach((mat) => {
      mat.uniforms.daylight.value = daylight;
      mat.uniforms.storm.value = storm;
      mat.uniforms.dawn.value = horizonGlow;
    });
    this.waveMaterials.forEach((mat) => { if (mat.uniforms.night) mat.uniforms.night.value = night; });
    this.cloudMeshes.forEach((mesh) => { mesh.material.opacity = .035 + cloud * .4; mesh.material.color.copy(new THREE.Color(0xdde3e2).lerp(new THREE.Color(0x657078), storm + night * .25)); });
  }

  bindEvents() {
    addEventListener('resize', () => {
      this.camera.aspect = innerWidth / innerHeight; this.camera.updateProjectionMatrix();
      this.renderer.setSize(innerWidth, innerHeight); this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.65));
    });
    this.canvas.addEventListener('pointerdown', (event) => { this.pointer.down = true; this.pointer.startX = event.clientX; this.pointer.startY = event.clientY; this.canvas.setPointerCapture(event.pointerId); });
    this.canvas.addEventListener('pointermove', (event) => {
      if (this.pointer.down) {
        this.pointer.targetX = clamp(this.pointer.targetX + (event.clientX - this.pointer.startX) / innerWidth * .65, -.28, .28);
        this.pointer.targetY = clamp(this.pointer.targetY + (event.clientY - this.pointer.startY) / innerHeight * .35, -.14, .14);
        this.pointer.startX = event.clientX; this.pointer.startY = event.clientY;
      } else {
        this.pointer.targetX = (event.clientX / innerWidth - .5) * .065;
        this.pointer.targetY = (event.clientY / innerHeight - .5) * .035;
      }
    });
    this.canvas.addEventListener('pointerup', () => { this.pointer.down = false; });
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
    this.pointer.x = lerp(this.pointer.x, this.pointer.targetX, .035);
    this.pointer.y = lerp(this.pointer.y, this.pointer.targetY, .035);
    const desired = this.baseCamera.clone();
    desired.x += this.pointer.x * 22; desired.y -= this.pointer.y * 12;
    this.camera.position.lerp(desired, .035);
    const target = this.baseTarget.clone(); target.x += this.pointer.x * 25; target.y -= this.pointer.y * 9;
    this.cameraTarget.lerp(target, .035); this.camera.lookAt(this.cameraTarget);

    this.cloudGroup.children.forEach((cloud, index) => {
      cloud.position.x += dt * (.18 + (this.weatherData.windSpeed ?? 8) * .018) * (index % 3 + 1);
      if (cloud.position.x > 115) cloud.position.x = -115;
    });
    this.cars.forEach((car) => {
      if (!car.parent.visible) return;
      car.position.z += dt * car.userData.speed * car.userData.direction;
      if (car.position.z > 22) car.position.z = -120;
      if (car.position.z < -125) car.position.z = 18;
    });
    this.waveMaterials.forEach((mat) => { mat.uniforms.time.value = elapsed; });
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
