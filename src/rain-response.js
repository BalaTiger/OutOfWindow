import * as THREE from 'three';
import { Reflector } from 'three/addons/objects/Reflector.js';

const clamp = THREE.MathUtils.clamp;
const noiseGLSL = `
float rwHash(vec2 p) { return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
float rwNoise(vec2 p) {
 vec2 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f);
 return mix(mix(rwHash(i),rwHash(i+vec2(1,0)),f.x),mix(rwHash(i+vec2(0,1)),rwHash(i+1.0),f.x),f.y);
}
`;
const surfaceUniforms = `
uniform float rwWet, rwWater, rwRain, rwTime;
uniform sampler2D rwField;
uniform vec4 rwBounds;
uniform sampler2D rwReflection;
uniform mat4 rwReflectionMatrix;
uniform float rwReflectionMix, rwReflectionHeight;
varying vec3 rwPosition, rwNormal;
`;
const motionGLSL = `
attribute vec4 rwMotion;
uniform float rwTime, rwRain;
uniform vec2 rwWind;
vec3 rainMotion(vec3 p) {
 float phase=rwMotion.y;
 float wind=sqrt(min(length(rwWind)/4.0,2.5));
 float gust=.65+.35*sin(rwTime*.73+phase*.2);
 float sway=sin(rwTime*(1.5+wind*.3)+phase)*gust;
 float flutter=sin(rwTime*8.1+phase*2.4)*.3;
 // Fast, decaying impulses approximate drop impacts independently of wind.
 float age=fract(rwTime*2.7+phase*.17);
 float impact=exp(-age*12.0)*sin(age*35.0)*rwRain;
 float gain=rwMotion.x;
 vec2 direction=rwWind/max(length(rwWind),.01);
 bool cloth=rwMotion.w>.5;
 float amplitude=cloth?.115:clamp(rwMotion.z*.055,.045,.32);
 vec3 delta=vec3(0.0);
 delta.xz=direction*gain*(sway+flutter*.45)*wind*amplitude;
 delta.y=gain*(flutter*wind*(cloth?.045:.02)+impact*(cloth?.055:.025));
 // Displacements are in metres, independent of asset scale and orientation.
 p+=transpose(normalMatrix)*(mat3(viewMatrix)*delta);
 return p;
}
`;

export class RainResponse {
  constructor() {
    const neutral = new THREE.DataTexture(new Uint8Array([255,0,255,255]),1,1);
    neutral.needsUpdate=true;
    this.uniforms = {
      rwWet:{value:0},rwWater:{value:0},rwRain:{value:0},rwTime:{value:0},
      rwLight:{value:1},
      rwWind:{value:new THREE.Vector2()},rwField:{value:neutral},
      rwBounds:{value:new THREE.Vector4(-10000,-10000,20000,20000)},
      rwReflection:{value:neutral},rwReflectionMatrix:{value:new THREE.Matrix4()},
      rwReflectionMix:{value:0},rwReflectionHeight:{value:0},
    };
    this.neutral=neutral; this.fields=new Map(); this.surfaces=new WeakSet();
    this.motionMaterials=new WeakSet(); this.motionMeshes=[]; this.dripOrigins=[]; this.mode='clear';
    this.activeScene='city'; this.rainTarget=0; this.windTarget=new THREE.Vector2();
    this.reflector=new Reflector(new THREE.PlaneGeometry(1,1),{textureWidth:768,textureHeight:512,clipBias:.003,multisample:0});
    this.reflector.rotation.x=-Math.PI/2;this.reflector.visible=false;
    this.uniforms.rwReflection.value=this.reflector.getRenderTarget().texture;
    this.lastReflection=-Infinity;
  }

  setWeather(mode,data={}) {
    this.mode=mode;
    // Open-Meteo precipitation is an accumulation, used here as a visual intensity proxy.
    this.rainTarget=mode==='rain'?clamp(.24+Math.sqrt(Math.max(0,data.precipitation??1.5))*.27,.24,1):0;
    const speed=clamp(data.windSpeed??8,0,100)/3.6;
    const gust=clamp(data.windGustSpeed??data.windSpeed??8,0,140)/3.6;
    const direction=(data.windDirection??240)*Math.PI/180;
    this.windTarget.set(-Math.sin(direction),Math.cos(direction)).multiplyScalar(speed*.8+gust*.2);
  }

  update(dt,elapsed) {
    const u=this.uniforms;
    u.rwTime.value=elapsed;
    u.rwRain.value=THREE.MathUtils.damp(u.rwRain.value,this.rainTarget,2,dt);
    u.rwWet.value=THREE.MathUtils.damp(u.rwWet.value,this.rainTarget>0?1:0,this.rainTarget>0?.22:.012,dt);
    const waterTarget=this.rainTarget>0?clamp(this.rainTarget*1.5,0,1)*u.rwWet.value:0;
    u.rwWater.value=THREE.MathUtils.damp(u.rwWater.value,waterTarget,this.rainTarget>0?.10:.025,dt);
    u.rwWind.value.lerp(this.windTarget,1-Math.exp(-dt*1.8));
    for(const [name,field] of this.fields) {
      const raining=name===this.activeScene && u.rwRain.value>.015;
      field.splashes.visible=raining;
      if(field.drips)field.drips.visible=raining;
    }
  }

  setScene(name) {
    this.activeScene=name;
    const field=this.fields.get(name);
    this.uniforms.rwField.value=field?.texture??this.neutral;
    this.uniforms.rwBounds.value.copy(field?.bounds??new THREE.Vector4(-10000,-10000,20000,20000));
    this.uniforms.rwReflectionMix.value=0;this.lastReflection=-Infinity;
  }

  attachSurface(material) {
    if(this.surfaces.has(material) || !material.isMeshStandardMaterial) return;
    this.surfaces.add(material);
    const previous=material.onBeforeCompile;
    const kind=/fabric/i.test(material.name)?'CLOTH':/foliage/i.test(material.name)&&!/trunk|branches/i.test(material.name)?'LEAF':/^Pavement_/i.test(material.name)||['roadSurface','asphalt','concrete'].includes(material.userData.profile)?'GROUND':'WALL';
    const bistroWall=material.userData.bistroWallSurface===true;
    const bistroGround=material.userData.bistroGroundSurface===true;
    material.onBeforeCompile=shader=>{
      previous.call(material,shader);
      Object.assign(shader.uniforms,this.uniforms);
      shader.vertexShader='varying vec3 rwPosition, rwNormal;\n'+shader.vertexShader;
      shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>',`#include <begin_vertex>
        vec4 rainVertex=vec4(transformed,1.0);
        vec3 rainVertexNormal=objectNormal;
        #ifdef USE_INSTANCING
          rainVertex=instanceMatrix*rainVertex;
          rainVertexNormal=mat3(instanceMatrix)*rainVertexNormal;
        #endif
        rwPosition=(modelMatrix*rainVertex).xyz;
        rwNormal=normalize(mat3(modelMatrix)*rainVertexNormal);`);
      const brickSurface=material.userData.bistroBrickSurface===true;
      const plasterSurface=material.userData.bistroPlasterSurface===true;
      shader.fragmentShader='#define RAIN_'+kind+'\n'+(bistroWall?'#define RAIN_BISTRO_WALL\n':'')+(bistroGround?'#define RAIN_BISTRO_GROUND\n':'')+(brickSurface?'#define RAIN_BISTRO_BRICK\n':'')+(plasterSurface?'#define RAIN_BISTRO_PLASTER\n':'')+surfaceUniforms+noiseGLSL+shader.fragmentShader;
      shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>',`#include <color_fragment>
        vec2 rainUV=(rwPosition.xz-rwBounds.xy)/rwBounds.zw;
        float inField=step(0.0,rainUV.x)*step(0.0,rainUV.y)*step(rainUV.x,1.0)*step(rainUV.y,1.0);
        float exposure=texture2D(rwField,clamp(rainUV,0.0,1.0)).r*inField;
        float upwards=smoothstep(.45,.93,normalize(rwNormal).y);
        float dampness=rwWet*mix(.3,exposure,upwards);
        float wetPattern=rwNoise(rwPosition.xz*.14)*.65+rwNoise(rwPosition.xz*.43)*.25+rwNoise(rwPosition.xz*1.6)*.10;
        float wetMask=dampness*(.7+.3*wetPattern);
        float pool=0.0;
        #ifdef RAIN_GROUND
          // Rain volume grows coverage. A shallow puddle already has a smooth
          // water surface; its reflectivity must not be scaled down by depth.
          float bistroCoverage=exposure;
          #ifdef RAIN_BISTRO_GROUND
            // The imported Bistro mesh has sparse ground-hit cells in its
            // low-resolution rain field. Preserve spatial breakup, but do not
            // let that bake-time mask erase the visible foreground puddles.
            float puddleNoise=rwNoise(rwPosition.xz*.34+vec2(13.0,7.0));
            bistroCoverage=max(exposure,smoothstep(.08,.34,rwWater)*(.38+.34*puddleNoise));
          #endif
          pool=smoothstep(.02,.16,rwWater)*upwards*bistroCoverage*smoothstep(.52-rwWater*.19,.65-rwWater*.18,wetPattern);
          diffuseColor.rgb*=1.0-wetMask*.38-pool*.24;
        #endif
        #ifdef RAIN_CLOTH
          wetMask=rwWet*(.72+.28*rwNoise(rwPosition.xz*3.0));
          diffuseColor.rgb*=1.0-wetMask*.4;
        #endif
        #ifdef RAIN_LEAF
          wetMask=rwWet*(.65+.35*abs(normalize(rwNormal).y));
          diffuseColor.rgb*=1.0-wetMask*.25;
        #endif
        #ifdef RAIN_WALL
          vec3 wallAxis=abs(rwNormal.z)>.55?vec3(rwPosition.x,rwPosition.y,0.0):vec3(rwPosition.z,rwPosition.y,0.0);
          float mineral=rwNoise(wallAxis.xy*.22)+rwNoise(wallAxis.xy*1.15)*.24;
          float pockle=rwNoise(wallAxis.xy*3.8)*.18;
          float verticalStain=rwNoise(vec2(wallAxis.x*1.15,floor(wallAxis.y*.22)));
          float streak=rwNoise(vec2(wallAxis.x*.72,wallAxis.y*.12));
          float ageMask=smoothstep(.24,.72,min(1.0,mineral*.72+pockle+verticalStain*.30));
          vec3 agedStone=mix(vec3(.97,.92,.83),vec3(.54,.49,.42),ageMask*.82);
          #ifdef RAIN_BISTRO_BRICK
            // Lower courses and exposed masonry use a warmer, darker stone
            // response with stronger mortar separation.
            agedStone=mix(vec3(.68,.50,.36),vec3(.27,.19,.14),smoothstep(.18,.76,ageMask));
          #endif
          #ifdef RAIN_BISTRO_PLASTER
            // Upper render/plaster remains lighter and broader in value than
            // the brick base, matching the building's actual construction.
            agedStone=mix(vec3(.99,.94,.86),vec3(.68,.63,.57),smoothstep(.22,.78,ageMask));
          #endif
          // Separate broad facade regions before the fine grain pass. The
          // imported Bistro walls share similar albedo and receive mostly
          // ambient light, so a low-frequency mineral/stain mask is what keeps
          // plaster, repairs and sheltered stone from collapsing into one
          // blue-gray value.
          float facadePatch=rwNoise(wallAxis.xy*.16+vec2(7.0,19.0))*.72
            +rwNoise(wallAxis.xy*.44+vec2(23.0,5.0))*.20
            +verticalStain*.14;
          float facadeRegion=smoothstep(.30,.68,facadePatch);
          float facadeContrast=mix(.66,1.28,facadeRegion);
          #ifdef RAIN_BISTRO_BRICK
            facadeContrast=mix(.58,1.34,facadeRegion);
          #endif
          #ifdef RAIN_BISTRO_PLASTER
            facadeContrast=mix(.82,1.20,facadeRegion);
            // Explicit albedo lift keeps rendered plaster above the darker
            // lower brick courses even under the same overcast sky bounce.
            diffuseColor.rgb*=vec3(1.18,1.13,1.06);
          #endif
          #ifdef RAIN_BISTRO_BRICK
            diffuseColor.rgb*=vec3(.90,.87,.82);
          #endif
          float faceKey=.90+.16*max(dot(normalize(rwNormal),normalize(vec3(-.38,.72,.56))),0.0);
          float dripShade=smoothstep(.62,.94,rwNoise(vec2(floor(wallAxis.x*.72),wallAxis.y*.095)));
          float stoneGrain=rwNoise(wallAxis.xy*8.0);
          // Long, broken joints keep the large modular elevations from reading
          // as a single flat color block at the city camera distance.
          float panelX=abs(fract(wallAxis.x*.18)-.5);
          float panelY=abs(fract(wallAxis.y*.24)-.5);
          float joint=smoothstep(.018,.002,min(panelX,panelY));
          float edgeDust=smoothstep(.25,.8,rwNoise(wallAxis.xy*.42+vec2(11.0,4.0)));
          diffuseColor.rgb*=mix(vec3(1.0),agedStone,.84);
          diffuseColor.rgb*=facadeContrast*faceKey;
          diffuseColor.rgb*=.82+stoneGrain*.26;
          diffuseColor.rgb*=1.0-joint*(.12+.09*edgeDust);
          diffuseColor.rgb*=1.0-dripShade*(.035+rwWet*.095);
          wetMask=rwWet*(.08+.26*streak+.16*verticalStain);
          diffuseColor.rgb*=1.0-wetMask*.28;
          #ifdef RAIN_BISTRO_WALL
            // Add a second, high-frequency breakup layer. This is intentionally
            // independent of the 768px base color so the wall does not read as
            // a smooth gray plane when viewed close to the window.
            float fineMineral=rwNoise(wallAxis.xy*18.0+vec2(4.0,17.0));
            float pittedMortar=rwNoise(wallAxis.xy*42.0+vec2(21.0,3.0));
            float dampEdge=smoothstep(.32,.86,verticalStain+fineMineral*.24);
            diffuseColor.rgb*=.86+fineMineral*.22;
            diffuseColor.rgb*=1.0-pittedMortar*.055*(1.0-dampEdge*.42);
            // Keep the neutral-warm limestone albedo from being washed into
            // the blue-gray sky color under the alley's overcast fill.
            diffuseColor.rgb*=vec3(1.16,1.075,.89);
          #endif
        #endif`);
      shader.fragmentShader=shader.fragmentShader.replace('#include <roughnessmap_fragment>',`#include <roughnessmap_fragment>
        #ifdef RAIN_WALL
          // Do not clamp wet masonry back to a dry .68 roughness. The old
          // clamp was the reason rain never produced a readable wall sheen.
          roughnessFactor=mix(max(roughnessFactor,.68),.24,wetMask);
          #ifdef RAIN_BISTRO_WALL
            // Sheltered patches stay matte while worn/exposed patches catch a
            // controlled highlight, making the material read as stone rather
            // than a single uniformly lit card.
            roughnessFactor=clamp(roughnessFactor+(.52-facadeRegion)*.14, .08, 1.0);
          #endif
        #endif
        #ifndef RAIN_WALL
          roughnessFactor=mix(roughnessFactor,.22,wetMask);
        #endif
        #ifdef RAIN_CLOTH
          roughnessFactor=mix(roughnessFactor,.32+.12*rwNoise(rwPosition.xz*18.0),wetMask);
        #endif
        #ifdef RAIN_LEAF
          roughnessFactor=mix(roughnessFactor,.30,wetMask);
        #endif
        roughnessFactor=mix(roughnessFactor,.055,pool);`);
      shader.fragmentShader=shader.fragmentShader.replace('#include <normal_fragment_maps>',`#include <normal_fragment_maps>
        #if defined(USE_BUMPMAP) && (defined(USE_NORMALMAP_TANGENTSPACE) || defined(USE_NORMALMAP_OBJECTSPACE))
          // Keep the imported tangent normal and layer the masonry/paving
          // height channel on top; Three.js otherwise skips bumpMap whenever
          // a normalMap is present.
          normal=perturbNormalArb(-vViewPosition,normal,dHdxy_fwd(),faceDirection);
        #endif
        #ifdef RAIN_CLOTH
          // Fine fabric relief breaks up a single plastic-looking highlight.
          float grain=rwNoise(rwPosition.xz*90.0+rwPosition.y*vec2(37.0,53.0));
          vec3 dx=dFdx(-vViewPosition),dy=dFdy(-vViewPosition);
          vec3 crossX=cross(dy,normal),crossY=cross(normal,dx);
          float determinant=dot(dx,crossX);
          normal=normalize(abs(determinant)*normal-sign(determinant)*.0015*(dFdx(grain)*crossX+dFdy(grain)*crossY));
        #endif
        #if defined(RAIN_BISTRO_WALL) || defined(RAIN_BISTRO_GROUND)
          // Screen-space derivative bump keeps the added relief scale stable
          // regardless of the source mesh's UV density.
          vec3 microAxis=abs(rwNormal.z)>.55?vec3(rwPosition.x,rwPosition.y,0.0):vec3(rwPosition.z,rwPosition.y,0.0);
          float microHeight=rwNoise(microAxis.xy*21.0)*.72+rwNoise(microAxis.xy*55.0)*.28;
          vec3 microDx=dFdx(-vViewPosition),microDy=dFdy(-vViewPosition);
          vec3 microRx=cross(microDy,normal),microRy=cross(normal,microDx);
          float microDet=dot(microDx,microRx);
          normal=normalize(abs(microDet)*normal-sign(microDet)*.0105*(dFdx(microHeight)*microRx+dFdy(microHeight)*microRy));
        #endif
        vec2 cell=floor(rwPosition.xz*2.2), local=fract(rwPosition.xz*2.2)-.5;
        float age=fract(rwTime*1.35+rwHash(cell));
        float radius=length(local), ring=radius-age*.58;
        float wave=sin(ring*58.0)*exp(-abs(ring)*20.0)*(1.0-age)*rwRain;
        vec2 grad=local/max(radius,.01)*wave*.18;
        vec3 waterNormal=normalize(mat3(viewMatrix)*vec3(grad.x,1.0,grad.y));
        normal=normalize(mix(normal,waterNormal,smoothstep(.05,.8,pool)));`);
      shader.fragmentShader=shader.fragmentShader.replace('#include <lights_physical_fragment>',`#include <lights_physical_fragment>
        // The upper water film is smoother than the underlying cobble geometry.
        material.roughness=mix(material.roughness,.055,pool);`);
      shader.fragmentShader=shader.fragmentShader.replace('#include <opaque_fragment>',`
        vec4 projected=rwReflectionMatrix*vec4(rwPosition,1.0);
        vec2 reflectedUV=projected.xy/max(projected.w,.001)+grad*.014;
        float validUV=step(0.0,reflectedUV.x)*step(0.0,reflectedUV.y)*step(reflectedUV.x,1.0)*step(reflectedUV.y,1.0);
        float samePlane=1.0-smoothstep(.12,.5,abs(rwPosition.y-rwReflectionHeight));
        // Schlick Fresnel: vViewPosition points from the camera toward the
        // fragment, so the surface-to-camera vector must be negated. This
        // makes grazing puddles reflect strongly without whitening top-down
        // water with a constant blue tint.
        float cosTheta=clamp(dot(normalize(waterNormal),normalize(-vViewPosition)),0.0,1.0);
        float fresnel=.035+.965*pow(1.0-cosTheta,5.0);
        vec3 reflected=texture2D(rwReflection,clamp(reflectedUV,0.0,1.0)).rgb;
        // Only a weak cool absorption tint remains; reflection carries the
        // visible puddle color and architecture/sky detail.
        vec3 puddleTint=vec3(.23,.29,.30);
        reflected*=vec3(.94,.98,1.0);
        float waterReflect=pool*rwReflectionMix*validUV*samePlane;
        // Replace the sky-only specular lobe with the local reflection; retaining
        // both washes out the reflected doors/windows in a narrow, shaded street.
        float reflectionWeight=clamp(fresnel*3.2,.12,.94);
        float puddleGlint=smoothstep(.25,.75,wetPattern);
        reflected=mix(reflected,reflected*1.10+vec3(.01,.016,.018),puddleGlint*.10);
        float skyBreak=rwNoise(rwPosition.xz*.24+vec2(7.0,19.0));
        reflected=mix(reflected,max(reflected,vec3(.20,.26,.28)),skyBreak*puddleGlint*.10);
        vec3 waterLight=puddleTint*(1.0-reflectionWeight)*.12+reflected*reflectionWeight+reflectedLight.directSpecular*.08+totalEmissiveRadiance;
        float waterBlend=max(waterReflect,pool*.08);
        outgoingLight=mix(outgoingLight,waterLight,waterBlend);
        #include <opaque_fragment>`);
    };
    material.customProgramCacheKey=()=> 'rain-surface-v4-'+kind+'-'+(bistroWall?'bistro-wall':'')+(bistroGround?'bistro-ground':'');
    material.needsUpdate=true;
  }

  attachMotion(mesh,type='foliage') {
    if(mesh.geometry.getAttribute('rwMotion')) return;
    mesh.geometry=mesh.geometry.clone();
    mesh.geometry.computeBoundingBox();
    const box=mesh.geometry.boundingBox,height=Math.max(box.max.y-box.min.y,.05);
    const worldBox=new THREE.Box3().setFromObject(mesh),worldHeight=worldBox.max.y-worldBox.min.y;
    const position=mesh.geometry.attributes.position, weights=new Float32Array(position.count*4);
    for(let i=0;i<position.count;i++) {
      const fraction=clamp((position.getY(i)-box.min.y)/height,0,1);
      weights[i*4]=type==='awning'?Math.pow(1-fraction,1.5):Math.pow(fraction,1.25);
      weights[i*4+1]=position.getX(i)*1.31+position.getZ(i)*.87;
      weights[i*4+2]=Math.min(worldHeight,8);
      weights[i*4+3]=type==='awning'?1:0;
    }
    mesh.geometry.setAttribute('rwMotion',new THREE.BufferAttribute(weights,4));
    const patch=material=>{
      if(this.motionMaterials.has(material)) return;
      this.motionMaterials.add(material);
      const previous=material.onBeforeCompile, key=material.customProgramCacheKey();
      material.onBeforeCompile=shader=>{
        previous.call(material,shader); Object.assign(shader.uniforms,this.uniforms);
        shader.vertexShader=motionGLSL+shader.vertexShader;
        shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed=rainMotion(transformed);');
      };
      material.customProgramCacheKey=()=>key+'-rain-motion-v2';material.needsUpdate=true;
    };
    (Array.isArray(mesh.material)?mesh.material:[mesh.material]).forEach(patch);
    const material=Array.isArray(mesh.material)?mesh.material[0]:mesh.material;
    mesh.customDepthMaterial=new THREE.MeshDepthMaterial({depthPacking:THREE.RGBADepthPacking,map:material.map,alphaMap:material.alphaMap,alphaTest:material.alphaTest,side:material.side});
    patch(mesh.customDepthMaterial);
    mesh.geometry.computeBoundingSphere();mesh.geometry.boundingSphere.radius*=1.12;
    mesh.userData.rainMotion=type;this.motionMeshes.push(mesh);
    if(type==='awning') {
      const rim=[];
      for(let i=0;i<position.count;i++)if(weights[i*4]>.83)rim.push(new THREE.Vector3().fromBufferAttribute(position,i).applyMatrix4(mesh.matrixWorld));
      for(let i=0;i<14&&rim.length;i++)this.dripOrigins.push(rim[Math.floor((i+.35)*rim.length/14)]);
    }
  }

  clipRain(material) {
    material.onBeforeCompile=shader=>{
      Object.assign(shader.uniforms,this.uniforms);
      shader.vertexShader='varying vec3 rainDropWorld;\n'+shader.vertexShader;
      shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>',`#include <begin_vertex>
      rainDropWorld=(modelMatrix*vec4(transformed,1.0)).xyz;`);
      shader.fragmentShader='varying vec3 rainDropWorld; uniform sampler2D rwField; uniform vec4 rwBounds;\n'+shader.fragmentShader;
      shader.fragmentShader=shader.fragmentShader.replace('void main() {',`void main() {
      vec2 fieldUV=(rainDropWorld.xz-rwBounds.xy)/rwBounds.zw;
      if(all(greaterThanEqual(fieldUV,vec2(0.0))) && all(lessThanEqual(fieldUV,vec2(1.0)))) {
        float blocker=texture2D(rwField,fieldUV).g*100.0;
        if(rainDropWorld.y<blocker-.4) discard;
      }`);
    };
    material.customProgramCacheKey=()=> 'rain-occlusion-v1';
    material.needsUpdate=true;
  }

  registerScene(name,group,region) {
    if(this.fields.has(name)) return;
    group.updateWorldMatrix(true,true);
    const meshes=[];
    group.traverse(mesh=>{
      if(!mesh.isMesh || mesh.isInstancedMesh || mesh.parent?.userData.speed) return;
      const materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];
      const ground=materials.some(m=>/^Pavement_/i.test(m.name)||['roadSurface','asphalt','concrete'].includes(m.userData.profile));
      meshes.push({mesh,ground,box:new THREE.Box3().setFromObject(mesh)});
    });
    const [minX,minZ,width,depth]=region, nx=48,nz=64;
    const data=new Uint8Array(nx*nz*4),positions=[];
    const ray=new THREE.Raycaster(new THREE.Vector3(),new THREE.Vector3(0,-1,0),0,150);
    for(let z=0;z<nz;z++)for(let x=0;x<nx;x++) {
      const wx=minX+(x+.5)*width/nx,wz=minZ+(z+.5)*depth/nz;
      ray.ray.origin.set(wx,95,wz);
      const candidates=meshes.filter(({box})=>wx>=box.min.x&&wx<=box.max.x&&wz>=box.min.z&&wz<=box.max.z);
      const hits=ray.intersectObjects(candidates.map(c=>c.mesh),false);
      const hit=hits.find(h=>!h.object.material?.transparent);
      const floor=hit&&candidates.find(c=>c.mesh===hit.object)?.ground&&hit.face.normal.clone().transformDirection(hit.object.matrixWorld).y>.75;
      const index=(z*nx+x)*4;
      data[index]=floor?255:0;
      data[index+1]=Math.round(clamp((hit?.point.y??0)/100,0,1)*255);
      data[index+2]=floor?255:0; data[index+3]=255;
      if(floor) positions.push(hit.point.clone().add(new THREE.Vector3(0,.025,0)));
    }
    const texture=new THREE.DataTexture(data,nx,nz);
    texture.minFilter=texture.magFilter=THREE.LinearFilter;texture.needsUpdate=true;
    const heights=positions.map(p=>p.y-.025).sort((a,b)=>a-b);
    const field={texture,bounds:new THREE.Vector4(...region),positions,height:heights[Math.floor(heights.length*.5)]??7};
    field.splashes=this.makeSplashes(positions);
    if(name==='alley'&&this.dripOrigins.length) {
      field.drips=this.makeDrips(this.dripOrigins,field.height);
      group.add(field.drips);
    }
    group.add(field.splashes);this.fields.set(name,field);this.setScene(this.activeScene);
    document.documentElement.dataset[name+'RainGround']=String(positions.length);
  }

  renderReflection(renderer,scene,camera,quality,hidden=[]) {
    const field=this.fields.get(this.activeScene),u=this.uniforms;
    if(!field || quality==='eco' || u.rwWater.value<.08) {u.rwReflectionMix.value=0;return;}
    if(u.rwTime.value-this.lastReflection < (quality==='high'?.10:.18)) return;
    const target=this.reflector,visibility=hidden.map(object=>object.visible);
    const shadow=renderer.shadowMap.needsUpdate,oldTarget=renderer.getRenderTarget();
    const oldXr=renderer.xr.enabled,oldAuto=renderer.shadowMap.autoUpdate;
    try {
      hidden.forEach(object=>object.visible=false);
      // Prevent feedback into the reflection and preserve a pending scene shadow update.
      u.rwReflectionMix.value=0;u.rwReflection.value=this.neutral;renderer.shadowMap.needsUpdate=false;
      target.position.set(0,field.height+.035,0);target.updateMatrixWorld(true);camera.updateMatrixWorld(true);
      target.onBeforeRender(renderer,scene,camera);
      u.rwReflectionMatrix.value.copy(target.material.uniforms.textureMatrix.value).multiply(target.matrixWorld.clone().invert());
      u.rwReflectionHeight.value=field.height;u.rwReflectionMix.value=1;
      this.lastReflection=u.rwTime.value;
    } finally {
      target.visible=false;renderer.shadowMap.needsUpdate=shadow;
      u.rwReflection.value=target.getRenderTarget().texture;
      renderer.xr.enabled=oldXr;renderer.shadowMap.autoUpdate=oldAuto;renderer.setRenderTarget(oldTarget);
      hidden.forEach((object,i)=>object.visible=visibility[i]);
    }
  }

  makeDrips(origins,groundHeight) {
    const points=new Float32Array(origins.length*6),seeds=new Float32Array(origins.length*2),tips=new Float32Array(origins.length*2);
    origins.forEach((p,i)=>{
      p.toArray(points,i*6);p.toArray(points,i*6+3);
      seeds[i*2]=seeds[i*2+1]=(i*.61803398875)%1;tips[i*2+1]=1;
    });
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(points,3));
    geometry.setAttribute('rwSeed',new THREE.BufferAttribute(seeds,1));
    geometry.setAttribute('rwTip',new THREE.BufferAttribute(tips,1));
    const material=new THREE.ShaderMaterial({
      uniforms:{...this.uniforms,rwFloor:{value:groundHeight}},transparent:true,depthWrite:false,
      vertexShader:`attribute float rwSeed,rwTip;uniform float rwTime,rwRain,rwFloor;uniform vec2 rwWind;varying float life;
      void main(){
        float age=fract(rwTime*(.8+rwSeed*.25)+rwSeed*17.0);
        float fall=age*age*5.0;
        vec3 p=position;p.y-=fall+rwTip*(.055+age*.2);p.xz+=rwWind*age*age*.075;
        life=step(rwSeed,rwRain*.9)*smoothstep(0.0,.07,age)*(1.0-smoothstep(.85,1.0,age))*step(rwFloor+.06,p.y);
        gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);
      }`,
      fragmentShader:`varying float life;uniform float rwLight;void main(){
        if(life<.01)discard;gl_FragColor=vec4(vec3(.8,.88,.92)*rwLight,life*.62);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    });
    const drips=new THREE.LineSegments(geometry,material);drips.name='Rain_Awning_Runoff';drips.frustumCulled=false;drips.visible=false;
    return drips;
  }

  makeSplashes(positions) {
    const count=Math.min(positions.length*4,1200), points=new Float32Array(count*3), seeds=new Float32Array(count);
    // Cover the entire ground field even when the particle budget is capped.
    for(let i=0;i<count;i++) {const p=positions[Math.floor(Math.floor(i/4)*positions.length/Math.ceil(count/4))];p.toArray(points,i*3);seeds[i]=(i*.61803398875)%1;}
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(points,3));geometry.setAttribute('rwSeed',new THREE.BufferAttribute(seeds,1));
    const material=new THREE.ShaderMaterial({
      uniforms:this.uniforms,transparent:true,depthWrite:false,
      vertexShader:`attribute float rwSeed;uniform float rwTime,rwRain;varying float life;
      void main(){float age=fract(rwTime*(1.4+rwSeed*.6)+rwSeed*11.0);life=(1.0-age)*step(age,.48)*step(rwSeed,rwRain);
      float angle=rwSeed*137.5;vec3 p=position;
      p.xz+=vec2(cos(angle),sin(angle))*(age*.34);
      p.y+=max(0.0,age*1.25-age*age*3.0);
      vec4 view=modelViewMatrix*vec4(p,1.0);gl_Position=projectionMatrix*view;
      gl_PointSize=clamp(75.0/max(1.0,-view.z),1.0,3.0);}`,
      fragmentShader:`varying float life;uniform float rwLight;void main(){float d=length(gl_PointCoord-.5);float alpha=(1.0-smoothstep(.12,.5,d))*life*.55;if(alpha<.01)discard;gl_FragColor=vec4(vec3(.52,.61,.68)*rwLight,alpha);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
      }`,
    });
    const splashes=new THREE.Points(geometry,material);splashes.name='Rain_Ground_Impacts';splashes.frustumCulled=false;splashes.visible=false;
    return splashes;
  }
}
