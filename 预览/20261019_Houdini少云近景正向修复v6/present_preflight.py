"""Coverage evidence only: show pre-render camera-ray opacity projections."""
import os,json
from pathlib import Path
dll=os.add_dll_directory('D:/Houdini/bin')
import numpy as np
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parent
r=json.loads((root/'offline-result.json').read_text(encoding='utf8'))
data=np.load(root/'opacity-preflight.npz')
canvas=Image.new('RGB',(1082,1375),'#eef2f6')
draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',23)
small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
for i,name in enumerate(('original','control','candidate')):
    y=20+i*432
    draw.text((16,y),name+' / unshaded opacity preflight, NOT a cloud render',font=font,fill='#152334')
    a=np.rint(np.clip(data[name],0,1)*255).astype('uint8')
    panel=Image.fromarray(a).convert('RGB').resize((1050,375),Image.NEAREST)
    canvas.paste(panel,(16,y+40))
pr=r['projection']['controlVsCandidate']
draw.text((16,1320),f"Control/candidate support IoU {pr['alpha02IoU']:.6f}; added pixels {pr['newSupportPixels']}",font=small,fill='#152334')
draw.text((16,1348),'Fixed camera rays; density integration only. No light, material, denoise, stretching or exposure fitting.',font=small,fill='#152334')
canvas.save(root/'opacity-preflight.png')
print(json.dumps(dict(gatesPassed=r['gatesPassed'],path=str(root/'opacity-preflight.png'),projection=pr)))
