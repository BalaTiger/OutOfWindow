"""Produce evidence from actual EXRs only; no denoise, sharpening or fitted gain."""
import os,json,hashlib,sys
if sys.flags.optimize: raise RuntimeError('Optimized Python disables required validation')
from pathlib import Path
_houdini_dll_directory = os.add_dll_directory('D:/Houdini/bin')
import OpenImageIO as oiio,numpy as np
from PIL import Image,ImageDraw,ImageFont,PngImagePlugin
ROOT=Path(__file__).resolve().parent
SRC=Path('C:/Users/zhuzi/Documents/Codex/2026-10-07/task-5/cloud-single-reference-specimen-20261014')
result=json.loads((ROOT/'render-result.json').read_text(encoding='utf8'))
assert result['status']=='REJECTED_THREE_ROUTE_RENDER_COMPLETED'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):
    path=ROOT/(name+'.exr'); receipt=next(r for r in result['actualRenders'] if r['name']==name)
    assert digest(path)==receipt['sha256']
    inp=oiio.ImageInput.open(str(path)); assert inp
    s=inp.spec(); a=np.asarray(inp.read_image(format=oiio.FLOAT)); channels=list(s.channelnames); inp.close()
    assert (s.x,s.y,s.width,s.height,s.full_width,s.full_height)==(100,190,350,125,2560,1440)
    assert np.isfinite(a).all()
    return a[...,[channels.index(c) for c in ('R','G','B','A')]]
arrays={n:read(n) for n in ('original','control','candidate')}
bg=np.array((104,82,119))/255
bg=np.where(bg<=.04045,bg/12.92,((bg+.055)/1.055)**2.4)
def display(a):
    linear=a[...,:3]+bg*(1-a[...,3:4])
    enc=np.where(linear<=.0031308,linear*12.92,1.055*np.maximum(linear,0)**(1/2.4)-.055)
    return Image.fromarray(np.rint(np.clip(enc,0,1)*255).astype('uint8'))
mapping=json.loads((SRC/'composition.json').read_text(encoding='utf8'))['referenceToNativeMapping']
ref=Image.open(SRC/'references/reference-cloud-crop.png').convert('RGB')
origin=np.asarray(mapping['nativeOriginPixels'])+mapping['uniformScale']*(np.array([574,507])-mapping['sourceOriginPixels'])
offset=tuple(np.rint((origin-[100,190])*3).astype(int))
reference=Image.new('RGB',(1050,375),'#dce3ea')
reference.paste(ref.resize(tuple(round(v*3*mapping['uniformScale']) for v in ref.size),Image.NEAREST),offset)
panels=[('WMO reference / existing fixed mapping',reference)]
panels += [(label,display(arrays[n]).resize((1050,375),Image.NEAREST)) for n,label in
    [('original','0 Original sample06 / original 128^3 box'),('control','1 Local 128^3 resample control'),('candidate','2 REJECTED v5 / local front recession')]]
canvas=Image.new('RGB',(2148,974),'#f1f4f8'); draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22); small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
for i,(label,panel) in enumerate(panels):
    x=16+(i%2)*1066; y=16+(i//2)*425
    draw.text((x,y),label,font=font,fill='#1b2a40'); canvas.paste(panel,(x,y+36))
for y,text in [(872,'Same fixed camera, sun, material, AA and step-rate parameter values; native crop 350 x 125, enlarged 3x.'),
               (902,'Judge sculpting against route 1: only control/candidate share identical voxels and physical sampling. Original/grid comparison includes resampling.'),
               (932,'REJECTED TOPOLOGY. Exact frozen data, no cleanup. Protected B exact vs grid control. NOT integrated into runtime.')]:
    draw.text((16,y),text,font=small,fill='#1b2a40')
tag=PngImagePlugin.PngInfo(); tag.add(b'sRGB',b'\x00')
canvas.save(ROOT/'reference-original-control-candidate.png',pnginfo=tag)
display(arrays['candidate']).resize((1400,500),Image.NEAREST).save(ROOT/'candidate.png',pnginfo=tag)
def bounds(a):
    yy,xx=np.nonzero(a>.02)
    return [int(xx.min())+100,int(yy.min())+190,int(xx.max())+101,int(yy.max())+191]
def pair(before,after):
    a=before[...,3]>.02; b=after[...,3]>.02
    return dict(alphaSilhouetteIoU=float(np.count_nonzero(a&b)/np.count_nonzero(a|b)),
        boundsBefore=bounds(before[...,3]),boundsAfter=bounds(after[...,3]),
        meanAbsLinearRGBDelta=float(np.mean(abs(before[...,:3]-after[...,:3]))),
        opaquePixelsBefore=int(np.count_nonzero(before[...,3]>.8)),opaquePixelsAfter=int(np.count_nonzero(after[...,3]>.8)))
audit=dict(status='REJECTED_DIAGNOSTIC_IMAGES_SAVED',topologyAccepted=False,originalVsControl=pair(arrays['original'],arrays['control']),
    controlVsCandidate=pair(arrays['control'],arrays['candidate']),displayExposure=1,encoding='standard sRGB',
    nativeCrop=[100,190,350,125],referenceSHA256=digest(SRC/'references/reference-cloud-crop.png'),
    photographicNaturalnessAccepted=False,files={n:digest(ROOT/n) for n in ('reference-original-control-candidate.png','candidate.png')})
audit['broadSilhouetteGatePassed']=audit['controlVsCandidate']['alphaSilhouetteIoU']>=.95
(ROOT/'image-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
print(json.dumps(audit))
assert audit['broadSilhouetteGatePassed'], 'Broad silhouette changed too much; retain only as a rejected diagnostic'
