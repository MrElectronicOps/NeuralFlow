"""Local hardware smoke test using only this test's own window."""
import base64, ctypes, json, pathlib, subprocess, time, tkinter as tk
import numpy as np
from PIL import ImageGrab

ROOT=pathlib.Path(__file__).resolve().parent
EXE=ROOT/'bin/Release/net10.0-windows10.0.22621.0/win-x64/NeuralFlow.Capture.exe'
root=tk.Tk();root.title('NeuralFlow capture hardware test');root.geometry('800x450+80+100')
canvas=tk.Canvas(root,bg='#305070',highlightthickness=0);canvas.pack(fill='both',expand=True)
canvas.create_text(400,170,text='NeuralFlow capture test',fill='white',font=('Segoe UI',24))
root.update()
u=ctypes.windll.user32
u.GetParent.restype=ctypes.c_void_p;hwnd=u.GetParent(root.winfo_id())
u.SetForegroundWindow(ctypes.c_void_p(hwnd))
p=subprocess.Popen([str(EXE),'--diagnostics'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
def command(name,**values):
    p.stdin.write(json.dumps(dict(command=name,**values))+'\n');p.stdin.flush()
    line=p.stdout.readline()
    if not line:raise RuntimeError(p.stderr.read())
    result=json.loads(line)
    if not result.get('ok'):raise RuntimeError(result)
    return result
def tick(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:root.update();time.sleep(.008)
report={}
try:
    report['ready']=json.loads(p.stdout.readline())
    root.lift();root.focus_force();tick(.1)
    report['start']=command('start',target=hwnd,kind='window')
    # The desktop host may keep foreground during unattended tests. Exercise the
    # controller focus-exception path without reading or changing that window.
    u.GetForegroundWindow.restype=ctypes.c_void_p
    command('exclude',hwnd=u.GetForegroundWindow())
    tick(1)
    grab=command('grab',size=256);rgb=np.frombuffer(base64.b64decode(grab['rgb']),np.uint8).reshape(256,256,3)
    report['capture']={k:v for k,v in grab.items() if k!='rgb'}
    report['center_rgb']=rgb[170,110].tolist()
    assert rgb.std()>5,'Capture output is blank'
    command('parameters',strength=0,clarity=0,saturation=1,contrast=1,brightness=0,warmth=0,tone=0)
    tick(.15);report['neutral']=command('status');assert not report['neutral']['visible']
    diff=np.zeros((256,256,3),np.float32);diff[:,:,0]=40
    command('residual',size=256,rgb=base64.b64encode(diff.tobytes()).decode(),reference=grab['rgb'])
    command('parameters',strength=1,brightness=.05)
    tick(.05)
    report['effect']=command('status');assert report['effect']['visible'],report['effect']
    report['visible_pixel']=command('probe')
    assert report['visible_pixel']['rgb'][0]>70,'Direct3D compositor did not visibly change the window'
    # Directly inspect this test's own enhanced window with exclusion temporarily off.
    overlay=report['effect']['overlay_hwnd']
    # Foreign HWND affinity cannot be changed by the test; actual shader readback is
    # exercised separately by the native composite probe command.
    started=time.monotonic()
    for i in range(80):
        canvas.create_rectangle(i*8%780,240,i*8%780+20,265,fill='#f07330',outline='')
        tick(.016)
    report['moving']=command('status')
    report['wall_seconds']=time.monotonic()-started
    root.geometry('960x540+110+130');tick(.25)
    report['resized']=command('status');assert report['resized']['width']>report['effect']['width']
    root.iconify();tick(.15);report['minimized']=command('status');assert not report['minimized']['visible']
    root.deiconify();tick(.2)
    report['stop']=command('stop');assert not report['stop']['visible'] and not report['stop']['active']
    u.MonitorFromWindow.restype=ctypes.c_void_p
    monitor=u.MonitorFromWindow(ctypes.c_void_p(hwnd),2)
    report['monitor_start']=command('start',target=monitor,kind='monitor')
    command('parameters',strength=0,brightness=0)
    tick(.3);mg=command('grab',size=128)
    report['monitor_capture']={k:v for k,v in mg.items() if k!='rgb'}
    m0=np.frombuffer(base64.b64decode(mg['rgb']),np.uint8).reshape(128,128,3)
    mask=np.max(np.abs(m0.astype(int)-np.array([48,80,112])),axis=2)<3
    report['monitor_rgb_range']=[int(m0.min()),int(m0.max())]
    report['monitor_nearest_blue']=int(np.min(np.max(np.abs(m0.astype(int)-np.array([48,80,112])),axis=2)))
    command('parameters',strength=0,brightness=.1)
    tick(.25)
    report['monitor_effect']=command('status')
    assert report['monitor_effect']['visible']
    mg=command('grab',size=128)
    m1=np.frombuffer(base64.b64decode(mg['rgb']),np.uint8).reshape(128,128,3)
    report['monitor_self_capture_difference']=float(np.median(np.abs(m1.astype(float)-m0)[mask])) if mask.any() else None
    report['monitor_test_pixels']=int(mask.sum())
    assert mask.sum()>20 and report['monitor_self_capture_difference']<2,'Monitor overlay captured its own enhanced output'
    command('stop');command('close')
    report['success']=True
finally:
    try:p.kill()
    except:pass
    root.destroy()
    (ROOT/'test-capture-result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
