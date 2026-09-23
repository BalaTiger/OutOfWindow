// Export the actual assembled scenes, including procedural geometry and instances.
const { app, BrowserWindow, ipcMain, session } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'unreal/Migration/Exported');
fs.mkdirSync(output, { recursive: true });
app.setPath('userData', path.join(root, '.runtime/ue-export'));
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('js-flags', '--max-old-space-size=8192');
ipcMain.handle('migration:write', (_event, name, bytes, append) => {
  if (!/^(city|alley|village|forest|coast)\.(glb|json)$/.test(name)) throw Error('Invalid export name');
  fs[append ? 'appendFileSync' : 'writeFileSync'](path.join(output, name), Buffer.from(bytes));
});
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
app.whenReady().then(async () => {
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => callback({
    cancel: /^https?:/.test(details.url) && new URL(details.url).hostname !== '127.0.0.1',
  }));
  const win = new BrowserWindow({ show: false, width: 1280, height: 820,
    webPreferences: { offscreen: true, backgroundThrottling: false, preload: path.join(__dirname, 'export-preload.cjs') } });
  win.webContents.on('console-message', (_event, details) => {
    if (/MIGRATION|Error/i.test(details.message)) console.log(details.message.slice(0, 500));
  });
  await win.loadURL('http://127.0.0.1:5173/');
  const deadline = Date.now() + 300000;
  while (!(await win.webContents.executeJavaScript("document.documentElement.dataset.preloadComplete === 'true'"))) {
    if (Date.now() > deadline) throw Error('Scene preload timed out');
    await wait(500);
  }
  for (const id of ['alley', 'city', 'village', 'forest', 'coast']) {
    const result = await win.webContents.executeJavaScript(`(async () => {
      const { GLTFExporter } = await import('/node_modules/three/examples/jsm/exporters/GLTFExporter.js');
      const T = window.__THREE, w = window.__livingWorld, id = ${JSON.stringify(id)};
      w.switchScene(id, false); w.setWeather('clear'); w.setTime(12);
      w.groups[id].updateWorldMatrix(true, true);
      const out = new T.Group(); out.name = id;
      const metadata = { id, nodes: [], lights: [], camera: {position:w.baseCamera.toArray(), target:w.baseTarget.toArray(), verticalFov:w.camera.fov} };
      const mats = new Map(); let count = 0;
      const material = original => {
        if (mats.has(original.uuid)) return mats.get(original.uuid);
        const m = original.isShaderMaterial ? new T.MeshStandardMaterial({color:0x235d68,roughness:.15,metalness:.15}) : original.clone();
        m.name = original.name || ('Material_' + mats.size);
        m.userData = {}; m.envMap = null;
        mats.set(original.uuid,m); return m;
      };
      w.groups[id].traverse(node => {
        let ancestors = [], owner = node;
        while(owner && owner !== w.groups[id]) { ancestors.push(owner.name || ''); owner=owner.parent; }
        if (id === 'alley' && ancestors.some(n=>/LOD_Far/i.test(n))) return;
        if (node.isLight) { metadata.lights.push({position:node.getWorldPosition(new T.Vector3()).toArray(),color:node.color.toArray(),name:node.name}); return; }
        if (!node.isMesh || node.isSkinnedMesh) return;
        if (id === 'alley' && ancestors.some(n=>/streetlight|light_bulb/i.test(n))) return;
        const originals = Array.isArray(node.material) ? node.material : [node.material];
        if (originals.some(m=>/light_bulb|streetlight_glass/i.test(m.name))) return;
        const ms = originals.map(material);
        const car = w.cars.findIndex(c=>{let p=node;while(p){if(p===c)return true;p=p.parent;}return false;});
        const water = w.waterSurfaces.includes(node) || w.animatedWaterMaterials.some(m=>originals.includes(m)) || originals.some(m=>/water|ocean|stream/i.test(m.name));
        const instanceCount = node.isInstancedMesh ? node.count : 1;
        for (let i=0;i<instanceCount;i++) {
          const mesh = new T.Mesh(node.geometry, ms.length===1?ms[0]:ms);
          mesh.name = 'OOW_' + String(count++).padStart(5,'0') + '_' + (node.name || (water?'Water':'Mesh')).replace(/[^a-zA-Z0-9_]/g,'_').slice(0,75);
          mesh.matrixAutoUpdate=false;mesh.matrix.copy(node.matrixWorld);
          if(node.isInstancedMesh){const local=new T.Matrix4();node.getMatrixAt(i,local);mesh.matrix.multiply(local);}
          mesh.matrix.decompose(mesh.position,mesh.quaternion,mesh.scale);
          out.add(mesh);
          metadata.nodes.push({name:mesh.name,source:node.name,materials:ms.map(m=>m.name),car,water,motion:node.userData.rainMotion || null,ancestors});
        }
      });
      console.log('MIGRATION export ' + id + ' meshes=' + count);
      const buffer=await new GLTFExporter().parseAsync(out,{binary:true,onlyVisible:true,maxTextureSize:2048});
      const bytes=new Uint8Array(buffer), chunk=4*1024*1024;
      for(let start=0;start<bytes.length;start+=chunk) await window.migrationExport.write(id+'.glb',bytes.slice(start,start+chunk),start>0);
      await window.migrationExport.write(id+'.json',new TextEncoder().encode(JSON.stringify(metadata,null,2)));
      return {id,meshes:count,materials:mats.size,bytes:bytes.length};
    })()`);
    console.log(JSON.stringify(result));
  }
  app.quit();
}).catch(error => { console.error(error); app.exit(1); });
