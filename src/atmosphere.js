import * as THREE from 'three';
import { Sky } from 'three/addons/objects/Sky.js';

// Analytic Rayleigh/Mie daylight with a low-cost moving cloud layer.
// Clouds are a 2D optical-depth approximation, not volumetric ray marching.
export function createAtmosphere() {
  const sky = new Sky();
  sky.scale.setScalar(10000);
  sky.frustumCulled = false;
  sky.renderOrder = -1000;
  Object.assign(sky.material.uniforms, {
    sunDirection: { value: new THREE.Vector3() },
    sunColor: { value: new THREE.Color() },
    daylight: { value: 1 },
    cloudCoverage: { value: .3 },
    cloudTime: { value: 0 },
    cloudWind: { value: new THREE.Vector2() },
    solarDisc: { value: 1 },
  });
  sky.material.fragmentShader = sky.material.fragmentShader.replace('void main() {', `
    uniform vec3 sunColor;
    uniform float daylight, cloudCoverage, cloudTime, solarDisc;
    uniform vec2 cloudWind;
    float hash21(vec2 p) {
      p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32);
      return fract(p.x * p.y);
    }
    float noise2(vec2 p) {
      vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
      return mix(mix(hash21(i),hash21(i+vec2(1,0)),f.x),mix(hash21(i+vec2(0,1)),hash21(i+1.0),f.x),f.y);
    }
    float fbm(vec2 p) {
      float value = 0.0, amplitude = .54;
      for(int i=0;i<5;i++) {
        value += noise2(p)*amplitude;
        p = mat2(.82,.57,-.57,.82)*p*2.03+17.1; amplitude *= .49;
      }
      return value;
    }
    void main() {
  `).replace('( vSunE * 19000.0 * Fex ) * sundisk', '( vSunE * 19000.0 * Fex ) * sundisk * solarDisc')
    .replace('gl_FragColor = vec4( retColor, 1.0 );', `
      vec3 nightSky = mix(vec3(.008,.014,.026), vec3(.045,.061,.082), pow(1.0-max(direction.y,0.0),3.0));
      vec3 skyColor = mix(nightSky, retColor, daylight);
      float overcast = smoothstep(.5,.98,cloudCoverage);
      float luminance = dot(skyColor,vec3(.2126,.7152,.0722));
      skyColor = mix(skyColor,vec3(luminance)*vec3(.93,.97,1.0)*.65,overcast*.8);
      vec2 uvCloud = direction.xz / max(direction.y+.16,.12)*.6 + cloudWind*cloudTime;
      float broad = fbm(uvCloud);
      float detail = fbm(uvCloud*3.1+9.2);
      float field = broad*.8+detail*.2;
      float threshold = mix(.82,.25,cloudCoverage);
      float density = smoothstep(threshold-.06,threshold+.15,field);
      density *= smoothstep(.005,.09,direction.y);
      float transmission = exp(-density*mix(2.2,5.0,cloudCoverage));
      float lightSample = fbm(uvCloud+vSunDirection.xz*.25);
      float edgeLight = clamp((broad-lightSample)*3.0+.55,.12,1.0);
      vec3 cloudLight = mix(sunColor*1.6,vec3(1.30,1.34,1.38),overcast);
      vec3 cloudColor = mix(vec3(.38,.44,.52),cloudLight,edgeLight);
      cloudColor *= mix(.009,1.0,daylight)*(1.0-overcast*.4);
      skyColor = mix(cloudColor,skyColor,transmission);
      // The lower hemisphere represents ground bounce, not another luminous sky.
      vec3 ground = mix(vec3(.001),vec3(.055,.063,.065),daylight);
      skyColor = mix(ground,skyColor,smoothstep(-.08,.015,direction.y));
      gl_FragColor = vec4(skyColor*.35,1.0);
    `);
  return sky;
}
