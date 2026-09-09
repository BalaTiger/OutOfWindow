// Run with: node_modules/.bin/electron scripts/render-audit.cjs
// Requires npm run dev. Outputs stay under .runtime/render-audit/.
const { app, BrowserWindow, session } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const output = path.join(root, '.runtime', 'render-audit');
fs.mkdirSync(output, { recursive: true });
app.setPath('userData', path.join(output, 'electron-profile'));
app.commandLine.appendSwitch('disable-renderer-backgrounding');
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const errors = [];
let win;
setTimeout(() => { console.error('Audit exceeded five minutes'); app.exit(1); }, 300000).unref();
async function waitFor(expression, timeout = 120000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await win.webContents.executeJavaScript(expression)) return;
    await delay(250);
  }
  throw new Error(`Timed out: ${expression}`);
}
app.whenReady().then(async () => {
  // Repeatable local rendering; weather/location requests are deliberately offline.
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    callback({ cancel: /^https?:/.test(details.url) && new URL(details.url).hostname !== '127.0.0.1' });
  });
  win = new BrowserWindow({ width: 1280, height: 820, show: false, webPreferences: { offscreen: true, backgroundThrottling: false, contextIsolation: true, nodeIntegration: false } });
  win.webContents.setFrameRate(60);
  win.webContents.on('console-message', (details) => {
    if (details.level === 'error' && !details.message.includes('ERR_BLOCKED_BY_CLIENT')) { errors.push(details.message); if (errors.length <= 3) console.error(details.message); }
    if (/GL_INVALID|Feedback loop|feedback loop/.test(details.message)) errors.push(details.message);
  });
  win.webContents.on('render-process-gone', (_event, details) => errors.push(JSON.stringify(details)));
  if (process.env.AUDIT_PRODUCTION) {
    win.setContentSize(1040, 690);
    win.loadFile(path.join(root, 'dist', 'index.html')).catch(console.error);
    await delay(2000);
    await waitFor("document.documentElement.dataset.cityAssets === 'ready'");
    await waitFor("document.documentElement.dataset.preloadComplete === 'true'");
    await delay(4000);
    fs.writeFileSync(path.join(output, 'production.png'), (await win.webContents.capturePage()).toPNG());
    const sceneButtons = await win.webContents.executeJavaScript("[...document.querySelectorAll('[data-scene]')].map(el=>({scene:el.dataset.scene,label:el.textContent.trim()}))");
    if (sceneButtons.length !== 5) throw new Error('Expected five scene buttons');
    for (const {scene} of sceneButtons) {
      await win.webContents.executeJavaScript(`document.querySelector('[data-scene="${scene}"]').click()`);
      await waitFor(`document.documentElement.dataset['${scene}Assets'] === 'ready'`);
      await delay(1000);
      const active = await win.webContents.executeJavaScript('document.documentElement.dataset.activeScene');
      if (active !== scene) throw new Error('Scene button failed: ' + scene);
    }
    await win.webContents.executeJavaScript("document.querySelector('[data-scene=alley]').click()");
    await delay(1500);
    fs.writeFileSync(path.join(output, 'production-alley.png'), (await win.webContents.capturePage()).toPNG());
    if (process.env.AUDIT_PRODUCTION_WEATHER) {
      await win.webContents.executeJavaScript(`(() => {
        const slider=document.querySelector('#timeSlider');slider.value=647;slider.dispatchEvent(new Event('input'));
        document.querySelector('[data-weather=rain]').click();
      })()`);
      await delay(14000);
      const period=await win.webContents.executeJavaScript("document.querySelector('#periodLabel').textContent");
      if(period!=='上午')throw new Error('Production 10:47 label mismatch: '+period);
      fs.writeFileSync(path.join(output,'production-rain.png'),(await win.webContents.capturePage()).toPNG());
    }
    win.setContentSize(760, 510);
    await delay(1500);
    fs.writeFileSync(path.join(output, 'production-compact.png'), (await win.webContents.capturePage()).toPNG());
    const dataset = await win.webContents.executeJavaScript('({...document.documentElement.dataset})');
    fs.writeFileSync(path.join(output, 'production.json'), JSON.stringify({dataset, sceneButtons, errors}, null, 2));
    console.log(JSON.stringify({production: true, errors: errors.length, dataset}));
    app.exit(errors.length ? 1 : 0);
    return;
  }
  console.log('Loading local scene');
  win.loadURL(process.env.AUDIT_URL || 'http://127.0.0.1:5173/').catch(console.error);
  await delay(2000);
  console.log('Waiting for city assets');
  await waitFor("Boolean(window.__livingWorld && document.documentElement.dataset.cityAssets === 'ready')");
  console.log('City assets ready');
  await waitFor("document.documentElement.dataset.preloadComplete === 'true'");
  await win.webContents.executeJavaScript(`(() => {
    window.appState.liveTime = false; window.appState.weatherMode = 'clear';
    const world = window.__livingWorld;
    world.location = { latitude: 31.23, longitude: 121.47, timezone: 'Asia/Shanghai' };
    world.solarDate = new Date('2026-09-08T04:00:00Z');
    document.querySelectorAll('.status-card,.scene-copy,.control-panel,.ambient-toggle,.footer,.hint').forEach(el => el.style.display = 'none');
  })()`);
  const cases = JSON.parse(process.env.AUDIT_CASES || '[{"name":"city-noon","scene":"city","hour":12,"weather":"clear"}]');
  const startup = await win.webContents.executeJavaScript('({...document.documentElement.dataset})');
  const report = { date: new Date().toISOString(), viewport: [1280, 820], startup, cases: [], errors };
  for (const entry of cases) {
    await win.webContents.executeJavaScript(`(() => {
      const entry = ${JSON.stringify(entry)}, world = window.__livingWorld;
      if (entry.location) world.location = entry.location;
      if (entry.date) world.solarDate = new Date(entry.date);
      world.switchScene(entry.scene, false); world.setTime(entry.hour); world.setWeather(entry.weather);
      if (entry.weatherData) world.setWeather(entry.weather, entry.weatherData);
      if (entry.wetSeconds) world.rainResponse.update(entry.wetSeconds,world.clock.elapsedTime);
      if (entry.camera) { world.baseCamera.fromArray(entry.camera); world.camera.position.copy(world.baseCamera); }
      if (entry.target) { world.baseTarget.fromArray(entry.target); world.cameraTarget.copy(world.baseTarget); }
      if (entry.fov) { world.camera.fov = entry.fov; world.camera.updateProjectionMatrix(); }
      if (entry.quality) world.setQuality?.(entry.quality);
    })()`);
    await waitFor(`(() => { const state = document.documentElement.dataset[${JSON.stringify(entry.scene + 'Assets')}]; if (state === 'error') throw new Error('Scene asset failed'); return state === 'ready'; })()`);
    if (process.env.AUDIT_HOOK) {
      const result = await win.webContents.executeJavaScript(fs.readFileSync(path.resolve(process.env.AUDIT_HOOK), 'utf8'));
      if (result) console.log(JSON.stringify(result));
    }
    if (entry.expectedModels) await waitFor(`Number(document.documentElement.dataset.heroModels) >= ${Number(entry.expectedModels)}`);
    await delay(entry.settleMs || 5000);
    await waitFor('!window.__livingWorld.dynamicEnvironmentPending && !window.__livingWorld.dynamicEnvironmentDirty');
    console.log('Sampling ' + entry.name);
    const data = await win.webContents.executeJavaScript(`new Promise(resolve => {
      const samples = []; let last = performance.now();
      const sample = now => { samples.push(now - last); last = now;
        if (samples.length < 90) return requestAnimationFrame(sample);
        const world = window.__livingWorld, materials = new Set();
        world.groups[world.activeScene].traverse(node => { if (node.isMesh) (Array.isArray(node.material) ? node.material : [node.material]).forEach(m => materials.add(m)); });
        samples.shift(); samples.sort((a,b) => a-b);
        resolve({ dataset: {...document.documentElement.dataset}, camera: world.camera.position.toArray(), target: world.cameraTarget.toArray(), elevation: world.solarPosition().elevation * 180 / Math.PI,
          frameMs: {median: samples[Math.floor(samples.length*.5)], p95: samples[Math.floor(samples.length*.95)]},
          render: {...world.renderer.info.render}, memory: {...world.renderer.info.memory},
          materials: {total: materials.size, normal: [...materials].filter(m=>m.normalMap).length, roughness: [...materials].filter(m=>m.roughnessMap).length, ao: [...materials].filter(m=>m.aoMap).length},
          shaderErrors: world.renderer.info.programs.filter(p => p.diagnostics && !p.diagnostics.runnable).length });
      }; requestAnimationFrame(sample);
    })`);
    const filename = `${process.env.AUDIT_PREFIX || 'audit'}-${entry.name}`;
    fs.writeFileSync(path.join(output, `${filename}.png`), (await win.webContents.capturePage()).toPNG());
    if (process.env.AUDIT_THUMBNAILS && ['city','alley'].includes(entry.scene) && entry.hour === 12 && entry.weather === 'clear') {
      const rect = await win.webContents.executeJavaScript('(() => {const r=window.__livingWorld.canvas.getBoundingClientRect();return {x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)};})()');
      const previewDir = path.join(root, 'public', 'assets', 'previews');
      fs.mkdirSync(previewDir, {recursive:true});
      fs.writeFileSync(path.join(previewDir, entry.scene + '.jpg'), (await win.webContents.capturePage(rect)).resize({width:320}).toJPEG(88));
    }
    report.cases.push({ ...entry, ...data, image: `${filename}.png` });
    console.log(JSON.stringify({ name: entry.name, frameMs: data.frameMs, errors: data.shaderErrors }));
    if (entry.motionProbe) {
      const regions = await win.webContents.executeJavaScript(`(() => {
        const w=window.__livingWorld,T=window.__THREE,c=w.canvas.getBoundingClientRect();
        const ray=new T.Raycaster();
        const result=['awning','foliage'].map(kind=>{
          const candidates=w.rainResponse.motionMeshes.filter(m=>m.userData.rainMotion===kind).map(m=>{
            const b=new T.Box3().setFromObject(m),center=b.getCenter(new T.Vector3()),p=center.clone().project(w.camera);
            if(Math.abs(p.x)>1.1||Math.abs(p.y)>1.1||p.z>1)return null;
            const pts=[];for(const x of [b.min.x,b.max.x])for(const y of [b.min.y,b.max.y])for(const z of [b.min.z,b.max.z])pts.push(new T.Vector3(x,y,z).project(w.camera));
            const leftNdc=Math.max(-.95,Math.min(...pts.map(p=>p.x))),rightNdc=Math.min(.95,Math.max(...pts.map(p=>p.x)));
            const bottomNdc=Math.max(-.9,Math.min(...pts.map(p=>p.y))),topNdc=Math.min(.9,Math.max(...pts.map(p=>p.y)));
            let visible=false;
            for(let ix=1;ix<6&&!visible;ix++)for(let iy=1;iy<6&&!visible;iy++){
              ray.setFromCamera(new T.Vector2(T.MathUtils.lerp(leftNdc,rightNdc,ix/6),T.MathUtils.lerp(bottomNdc,topNdc,iy/6)),w.camera);
              visible=ray.intersectObject(w.groups.alley,true).find(h=>{if(!h.object.isMesh)return false;let o=h.object;while(o){if(!o.visible)return false;o=o.parent;}return true;})?.object===m;
            }
            if(!visible)return null;
            const x=Math.max(Math.ceil(c.x),Math.floor(c.x+(Math.min(...pts.map(p=>p.x))+1)*c.width/2)-12);
            const y=Math.max(Math.ceil(c.y),Math.floor(c.y+(1-Math.max(...pts.map(p=>p.y)))*c.height/2)-12);
            const right=Math.min(Math.floor(c.right),Math.ceil(c.x+(Math.max(...pts.map(p=>p.x))+1)*c.width/2)+12);
            const bottom=Math.min(Math.floor(c.bottom),Math.ceil(c.y+(1-Math.min(...pts.map(p=>p.y)))*c.height/2)+12);
            return {uuid:m.uuid,name:m.name,kind,x,y,width:right-x,height:bottom-y};
          }).filter(Boolean).sort((a,b)=>b.width*b.height-a.width*a.height);
          if(!candidates.length)throw new Error('No visible '+kind+' for motion probe');return candidates[0];
        });
        window.probeState={elapsed:w.clock.elapsedTime,water:w.rainResponse.uniforms.rwWater.value,rain:w.rainResponse.uniforms.rwRain.value,visibility:[w.rain,w.snow,w.sky,w.physicalGlass].map(m=>[m,m.visible])};
        w.clock.stop();w.clock.autoStart=false;w.rain.visible=false;w.snow.visible=false;w.sky.visible=false;w.physicalGlass.visible=false;
        w.dynamicEnvironmentDirty=false;w.rainResponse.uniforms.rwWater.value=0;w.rainResponse.uniforms.rwRain.value=0;
        window.probeVisibility=[];w.groups.alley.traverse(m=>{if(m.isMesh){window.probeVisibility.push([m,m.visible]);m.visible=false;}});
        return result;
      })()`);
      const probes=[];
      for(const region of regions){
        const bitmaps=[];
        for(const [index,time] of [3,3.8].entries()){
          await win.webContents.executeJavaScript(`(() => {const w=window.__livingWorld;window.probeVisibility.forEach(([m])=>m.visible=m.uuid===${JSON.stringify(region.uuid)});w.clock.elapsedTime=${time};})()`);
          await delay(180);
          const capture=await win.webContents.capturePage({x:region.x,y:region.y,width:region.width,height:region.height});
          bitmaps.push(capture.toBitmap());
          fs.writeFileSync(path.join(output,filename+'-'+region.kind+'-motion-'+index+'.png'),capture.toPNG());
        }
        let changed=0,foreground=0;
        for(let i=0;i<bitmaps[0].length;i+=4){
          if(Math.max(...bitmaps[0].subarray(i,i+3),...bitmaps[1].subarray(i,i+3))>24)foreground++;
          if(Math.max(...[0,1,2].map(c=>Math.abs(bitmaps[0][i+c]-bitmaps[1][i+c])))>12)changed++;
        }
        probes.push({...region,changedPixels:changed,foregroundPixels:foreground,changedFraction:changed/Math.max(foreground,1)});
        if(changed<100 || changed/Math.max(foreground,1)<.01)throw new Error('GPU motion is not visible: '+region.name);
      }
      report.motionProbes=probes;console.log(JSON.stringify({motionProbes:probes}));
      await win.webContents.executeJavaScript(`(() => {
        const w=window.__livingWorld,s=window.probeState;window.probeVisibility.forEach(([m,v])=>m.visible=v);s.visibility.forEach(([m,v])=>m.visible=v);
        w.rainResponse.uniforms.rwWater.value=s.water;w.rainResponse.uniforms.rwRain.value=s.rain;
        w.clock.start();w.clock.elapsedTime=s.elapsed;w.rainResponse.lastReflection=-Infinity;w.applyAtmosphere();
      })()`);
    }
    if (entry.clip) {
      const recording = await win.webContents.executeJavaScript(`new Promise(async (resolve,reject)=>{
        try {
          const stream=window.__livingWorld.canvas.captureStream(20);
          const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp9',videoBitsPerSecond:2500000});
          const chunks=[];recorder.ondataavailable=e=>chunks.push(e.data);
          recorder.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());resolve(Array.from(new Uint8Array(await new Blob(chunks).arrayBuffer())));};
          recorder.start();setTimeout(()=>recorder.stop(),5000);
        }catch(error){reject(error);}
      })`);
      fs.writeFileSync(path.join(output,filename+'.webm'),Buffer.from(recording));
      report.cases[report.cases.length-1].clip=filename+'.webm';
    }
  }
  if (process.env.AUDIT_VERIFY) {
    await win.webContents.executeJavaScript("window.__livingWorld.switchScene('alley', false)");
    await waitFor("document.documentElement.dataset.alleyAssets === 'ready'");
    report.checks = [startup.alleyAssets === 'ready' && startup.forestAssets === 'ready' && startup.coastAssets === 'ready' && startup.preloadComplete === 'true' ? 'All scene assets are preloaded before interaction' : (() => { throw new Error('Scene assets were still lazy-loaded at startup'); })()];
    report.checks.push(...await win.webContents.executeJavaScript(`(() => {
      const w=window.__livingWorld, T=window.__THREE;
      const check=(condition,message)=>{if(!condition) throw new Error(message); return message;};
      const checks=[];
      checks.push(check(!w.groups.city.getObjectByName('ORCA_Bistro_Exterior') && !!w.groups.alley.getObjectByName('ORCA_Bistro_Exterior'),'Bistro belongs exclusively to alley'));
      checks.push(check(!!w.groups.city.getObjectByName('PolyHaven_Urban_Block') && !w.groups.alley.getObjectByName('PolyHaven_Urban_Block'),'Apartment blocks belong exclusively to city'));
      const loads=JSON.stringify(w.assetLoadCounts), counts=Object.values(w.groups).map(g=>g.children.length).join(',');
      for(let i=0;i<4;i++) { w.switchScene('city', false); w.switchScene('alley', false); }
      checks.push(check(loads===JSON.stringify(w.assetLoadCounts) && counts===Object.values(w.groups).map(g=>g.children.length).join(','),'Repeated scene switches reuse loaded assets'));
      checks.push(check(w.baseCamera.equals(new T.Vector3(-20,23,-208)) && w.baseTarget.equals(new T.Vector3(-46,23,-246)),'Alley preserves the original camera and target'));
      checks.push(check(Object.entries(w.groups).every(([name,g])=>g.visible===(name==='alley')),'Only the selected scene is visible'));
      w.setTime(18); w.setWeather('rain'); w.setQuality('balanced');
      w.switchScene('city'); w.switchScene('alley');
      checks.push(check(w.hour===18 && w.activeWeather==='rain' && w.quality==='balanced','Time, weather and quality survive scene switching'));
      checks.push(check([...w.bistroMaterials].filter(m=>m.map).length>70,'Bistro color textures loaded'));
      w.setTime(23);
      checks.push(check(w.sun.intensity===0 && w.sun.position.y<w.sun.target.position.y,'Night sun below horizon and off'));
      w.setWeather('live',{weatherCode:75,cloudCover:100});
      checks.push(check(w.snow.visible && !w.rain.visible,'Live weather uses supplied weather code'));
      w.setWeather('clear');
      w.renderer.shadowMap.needsUpdate=true;
      w.refreshDynamicEnvironment();
      checks.push(check(w.renderer.shadowMap.needsUpdate,'Sky capture preserves pending scene shadows'));
      const textures=w.renderer.info.memory.textures;
      for(let i=0;i<6;i++) w.refreshDynamicEnvironment();
      checks.push(check(w.renderer.info.memory.textures===textures,'PMREM textures stable across six recaptures'));
      checks.push(check(!w.dynamicEnvironmentPending && w.skyMaterial.uniforms.solarDisc.value===1,'Capture restores visibility and solar disc'));
      for(const quality of ['eco','balanced','high']) {w.setQuality(quality); checks.push(check(w.pipeline.ao.enabled===(quality!=='eco'),'Quality mode '+quality));}
      checks.push(check(!w.pipeline.ao._renderGBuffer,'AO reuses beauty depth without geometry redraw'));
      w.switchScene('city', false);
      const cityOrigin = w.sun.target.position.clone();
      w.switchScene('alley', false);
      checks.push(check(w.sun.target.position.equals(w.lightTarget) && w.sun.target.position.distanceTo(cityOrigin)>100,'Manual-time scene switch updates lighting origin'));
      return checks;
    })()`));
    console.log(JSON.stringify({checks:report.checks}));
  }
  if (process.env.AUDIT_WEATHER_VERIFY) {
    const extra = await win.webContents.executeJavaScript(`(async () => {
      const w=window.__livingWorld,T=window.__THREE,checks=[];
      const check=(condition,label)=>{if(!condition)throw new Error(label);checks.push(label);};
      w.switchScene('alley',false);
      w.location={latitude:1.29,longitude:103.85,timezone:'Asia/Singapore'};
      w.solarDate=new Date('2026-09-09T02:47:00Z');
      const slider=document.querySelector('#timeSlider');slider.value=647;slider.dispatchEvent(new Event('input'));
      check(document.querySelector('#periodLabel').textContent==='上午','10:47 UI label agrees with daytime sun');
      check(w.solarPosition().elevation*180/Math.PI>55,'Singapore 10:47 sun above 55 degrees');
      const ray=new T.Raycaster();ray.setFromCamera(new T.Vector2(.35,.3),w.camera);
      const wall=ray.intersectObject(w.groups.alley,true)[0];
      check(wall.object.userData.wallNormalsRepaired && wall.face.normal.dot(wall.normal.clone().normalize())>.95,'Visible wall smooth normal agrees with its plane');
      check(w.rainResponse.motionMeshes.some(m=>m.userData.rainMotion==='awning') && w.rainResponse.motionMeshes.some(m=>m.userData.rainMotion==='foliage'),'Awnings and foliage have deformable meshes');
      check([...w.bistroMaterials].filter(m=>/^Foliage_/.test(m.name)&&m.alphaTest>0).every(m=>!m.transparent&&m.depthWrite),'Leaf cutouts write depth without blended highlight stacking');
      for(const [x,y] of [[.18,-.44],[.5,-.4],[.83,-.38]]){
        ray.setFromCamera(new T.Vector2(x,y),w.camera);
        const awning=ray.intersectObject(w.groups.alley,true).find(h=>h.object.isMesh)?.object;
        check(awning?.userData.rainMotion==='awning' && /Awnings_Hotel_Fabric/.test(awning.material.name),'Visible red hotel awning receives wind deformation at '+x);
      }
      for(const kind of ['awning','foliage']) {
        const mesh=w.rainResponse.motionMeshes.find(m=>m.userData.rainMotion===kind),a=mesh.geometry.getAttribute('rwMotion');
        let min=1,max=0;for(let i=0;i<a.count;i++){min=Math.min(min,a.getX(i));max=Math.max(max,a.getX(i));}
        check(min===0 && max>.9 && !!mesh.customDepthMaterial,'Pinned and movable '+kind+' vertices with matching shadow material');
      }
      for(const name of ['city','alley']) {
        const f=w.rainResponse.fields.get(name),data=f.texture.image.data;
        check(f.positions.length>100 && data.some((v,i)=>i%4===0&&v===0),'Ground impacts and shelter mask: '+name);
        const points=f.splashes.geometry.attributes.position;
        const spread=new T.Box3().setFromBufferAttribute(points),full=new T.Box3().setFromPoints(f.positions);
        check(spread.getSize(new T.Vector3()).z>full.getSize(new T.Vector3()).z*.9,'Splash budget covers near and far ground: '+name);
      }
      const runoff=w.rainResponse.fields.get('alley').drips;
      check(runoff?.parent===w.groups.alley && runoff.geometry.attributes.position.count>300,'Awning runoff belongs to alley and includes visible canopies');
      w.setWeather('rain');w.rainResponse.update(60,w.clock.elapsedTime);
      w.setQuality('balanced');w.renderer.shadowMap.needsUpdate=true;
      w.rainResponse.lastReflection=-Infinity;
      w.rainResponse.renderReflection(w.renderer,w.scene,w.camera,w.quality,[w.physicalGlass,w.rain,w.snow]);
      check(w.renderer.shadowMap.needsUpdate,'Puddle reflection preserves pending scene shadows');
      const textures=w.renderer.info.memory.textures;
      for(let i=0;i<5;i++){w.rainResponse.lastReflection=-Infinity;w.rainResponse.renderReflection(w.renderer,w.scene,w.camera,w.quality,[w.physicalGlass,w.rain,w.snow]);}
      check(textures===w.renderer.info.memory.textures,'Puddle reflection reuses render target across captures');
      w.setQuality('eco');w.rainResponse.renderReflection(w.renderer,w.scene,w.camera,w.quality,[]);
      check(w.rainResponse.uniforms.rwReflectionMix.value===0,'Eco quality skips scene reflection capture');
      w.setWeather('clear');w.rainResponse.update(1,w.clock.elapsedTime);
      check(w.rainResponse.uniforms.rwWet.value>.9 && w.rainResponse.uniforms.rwWater.value>.8,'Wet ground and pools persist immediately after rain');
      w.rainResponse.update(900,w.clock.elapsedTime);
      check(w.rainResponse.uniforms.rwWet.value<.001 && w.rainResponse.uniforms.rwWater.value<.001,'Ground eventually dries');
      return checks;
    })()`);
    report.weatherChecks=extra;console.log(JSON.stringify({weatherChecks:extra}));
  }
  fs.writeFileSync(path.join(output, `${process.env.AUDIT_PREFIX || 'audit'}.json`), JSON.stringify(report, null, 2));
  app.exit(errors.length || report.cases.some(entry => entry.shaderErrors) ? 1 : 0);
}).catch(error => { console.error(error); app.exit(1); });
