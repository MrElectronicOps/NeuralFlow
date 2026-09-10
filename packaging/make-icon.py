"""Render the existing NeuralFlow flowing-frame mark into Windows icon sizes."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
folder = root / 'branding'
folder.mkdir(exist_ok=True)
image = Image.new('RGBA', (1024, 1024))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((16, 16, 1008, 1008), radius=230, fill='#101923')
scale, offset = 21, 92
def line(points, color):
    points = [(offset+x*scale, offset+y*scale) for x,y in points]
    width = 3*scale
    draw.line(points, fill=color, width=width, joint='curve')
    for x,y in points:
        draw.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=color)
def curve(a,b,c,d):
    return [tuple((1-t)**3*a[j]+3*(1-t)**2*t*b[j]+3*(1-t)*t*t*c[j]+t**3*d[j] for j in (0,1)) for t in [i/100 for i in range(101)]]
line(curve((3,28),(12,28),(9,8),(19,8))+[(36,8)], '#79e8ed')
line(curve((3,35),(17,35),(17,15),(27,15))+[(36,15)], '#79e8ed')
line([(3,20),(9,20)], '#a99aff')
line([(28,29),(36,29)], '#a99aff')
image.resize((256,256),Image.Resampling.LANCZOS).save(folder/'NeuralFlow.png')
image.save(folder/'NeuralFlow.ico',sizes=[(n,n) for n in (16,20,24,32,40,48,64,128,256)])
print('Rendered NeuralFlow Windows icon: 16–256 pixels')
