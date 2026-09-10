"""NeuralFlow local JSON service. One inference owner, bounded live state."""
import argparse,base64,io,json,math,os,pathlib,queue,subprocess,sys,threading,time,traceback
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
import numpy as np
import cv2
from PIL import Image
from backend import Backend,import_runtime,Cancelled as BackendCancelled,APP_VERSION
from video import export_video,prepare_playback,Cancelled as VideoCancelled
import media_tools
import runtime_setup
cv2.setNumThreads(2)
WRITE=threading.Lock()
def emit(kind,data):
    with WRITE:print(json.dumps({'type':kind,'data':data}),flush=True)
def reply(id,data=None,error=None):
    with WRITE:print(json.dumps({'id':id,'ok':error is None,'data':data,'error':error}),flush=True)

class CaptureNotReady(RuntimeError):pass

class Capture:
    def __init__(self):
        executable=ROOT.parent/'capture'/'NeuralFlow.Capture.exe'
        if not executable.is_file():raise RuntimeError('GPU capture component is missing. Extract the complete app package.')
        self.process=subprocess.Popen([str(executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
        self.lock=threading.Lock();self.messages=queue.Queue();self.number=0
        def reader():
            try:
                for line in self.process.stdout:
                    try:self.messages.put(json.loads(line))
                    except ValueError:pass
            except (OSError,ValueError):pass
        threading.Thread(target=reader,daemon=True).start()
    def call(self,command,timeout=8,**values):
        if not self.lock.acquire(timeout=timeout):
            self.kill();raise TimeoutError('GPU capture was blocked; its overlay has been closed.')
        try:
            self.number+=1;number=self.number
            try:self.process.stdin.write(json.dumps(dict(command=command,id=number,**values))+'\n');self.process.stdin.flush()
            except (OSError,ValueError):self.kill();raise RuntimeError('GPU capture stopped.')
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                try:r=self.messages.get(timeout=.1)
                except queue.Empty:
                    if self.process.poll() is not None:raise RuntimeError('GPU capture stopped.')
                    continue
                if r.get('id')!=number:continue
                if not r.get('ok',False):
                    error=r.get('error','Capture command failed.')
                    if command=='grab' and (error=='No fresh captured frame' or error.startswith('GPU readback busy')):raise CaptureNotReady(error)
                    raise RuntimeError(error)
                return r
            self.kill();raise TimeoutError('GPU capture did not respond; its overlay has been closed.')
        finally:self.lock.release()
    def grab(self,size):
        try:r=self.call('grab',size=size)
        except CaptureNotReady:return None
        if not r.get('rgb'):return None
        return Image.frombytes('RGB',(size,size),base64.b64decode(r['rgb'],validate=True)),r.get('serial',0)
    def kill(self):
        try:
            if self.process.poll() is None:self.process.kill()
            self.process.wait(timeout=2)
        except (OSError,subprocess.TimeoutExpired):pass
    def close(self):
        try:self.call('close',timeout=1)
        except Exception:pass
        self.kill()
        for pipe in (self.process.stdin,self.process.stdout):
            try:pipe.close()
            except (OSError,ValueError):pass

class Temporal:
    def __init__(self,size=192):
        self.size=size;self.previous=None;self.history=np.zeros((size,size,3),np.float32)
        x,y=np.meshgrid(np.arange(size),np.arange(size));self.xy=np.stack([x,y],axis=2).astype(np.float32)
    def pixels(self,image):return np.asarray(image.resize((self.size,self.size),Image.Resampling.BILINEAR),np.float32)
    def align(self,reference,current,residual):
        if np.array_equal(reference,current):return residual.copy(),np.ones(reference.shape[:2],np.float32),False
        a=cv2.cvtColor(reference.astype(np.uint8),cv2.COLOR_RGB2GRAY);b=cv2.cvtColor(current.astype(np.uint8),cv2.COLOR_RGB2GRAY)
        back=cv2.calcOpticalFlowFarneback(b,a,None,.5,3,15,2,5,1.1,0);forward=cv2.calcOpticalFlowFarneback(a,b,None,.5,3,15,2,5,1.1,0)
        maps=self.xy+back
        def warp(v):return cv2.remap(v,maps,None,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        error=np.mean(np.abs(current-warp(reference)),axis=2);cycle=np.linalg.norm(back+warp(forward),axis=2)
        valid=(maps[:,:,0]>=0)&(maps[:,:,0]<self.size-1)&(maps[:,:,1]>=0)&(maps[:,:,1]<self.size-1)
        confidence=np.clip(1-error/24,0,1)*np.clip(1-cycle/2,0,1)*valid
        return warp(residual),confidence,bool(np.mean(error)>35 and np.mean(confidence)<.2)
    def step(self,source,correction,stability):
        current=self.pixels(source);history=np.zeros_like(self.history)
        if self.previous is not None:
            warped,confidence,cut=self.align(self.previous,current,self.history)
            if not cut:history=warped*confidence[:,:,None]
        target=np.zeros_like(history)
        if correction:
            stamp,a,b=correction;fresh=float(np.clip((1.2-(time.monotonic()-stamp))/.65,0,1))
            if fresh>0:
                reference=self.pixels(a);residual=np.clip(self.pixels(b)-reference,-48,48)
                warped,confidence,cut=self.align(reference,current,residual)
                if not cut:target=warped*confidence[:,:,None]*fresh
        self.history=history+(target-history)*(.65-.5*stability);self.previous=current
        return self.history

class Service:
    def __init__(self,data):
        self.data=pathlib.Path(data);self.data.mkdir(parents=True,exist_ok=True)
        media_tools.configure(self.data)
        self.backend=Backend(data,runtime_dir=os.environ.get('NEURALFLOW_RUNTIME'))
        self.capture=None;self.controls=[];self.active=False;self.hold=False;self.closed=False
        self.settings={};self.generation=0;self.correction=None;self.neural_ms=0;self.count=0
        self.cancel=threading.Event();self.busy=False;self.operation_lock=threading.Lock();self.start_lock=threading.RLock();self.job_thread=None
        self.threads=[threading.Thread(target=self.infer,daemon=True,name='Neural inference'),threading.Thread(target=self.live,daemon=True,name='Residual stabilization')]
        for thread in self.threads:thread.start()
    def status(self):return {'backend':self.backend.status(),'media':media_tools.status(self.data),'active':self.active,'busy':self.busy,'app':'NeuralFlow','version':APP_VERSION}
    def native(self):
        if self.capture is None:
            self.capture=Capture()
            for hwnd in self.controls:self.capture.call('exclude',hwnd=hwnd)
        return self.capture
    def parameters(self):
        s=self.settings
        return dict(strength=0 if self.hold else s.get('strength',0),clarity=0 if self.hold else s.get('clarity',0),saturation=1 if self.hold else 1+s.get('saturation',0),contrast=1 if self.hold else 1+s.get('contrast',0),brightness=0 if self.hold else s.get('brightness',0),warmth=0 if self.hold else s.get('warmth',0),tone=0 if self.hold else s.get('tone',0))
    def validated(self,values):
        limits={'strength':(0,1),'stability':(0,1),'refresh':(1,4),'clarity':(0,1),'saturation':(-.4,.6),'contrast':(-.25,.3),'brightness':(-.12,.12),'warmth':(-1,1),'tone':(0,1)}
        s={}
        for k,(lo,hi) in limits.items():
            value=float(values.get(k,.75 if k=='stability' else 3 if k=='refresh' else 0))
            if not math.isfinite(value):raise ValueError('Controls must contain finite numbers.')
            s[k]=max(lo,min(hi,value))
        s['size']=values.get('size','Auto');s['preset']=values.get('preset','Balanced')
        if s['strength']>0:
            supported=self.backend.status()['supported_sizes']
            if not supported:raise RuntimeError('Open System and run Check my hardware before enabling neural detail. Color controls work at zero neural strength.')
            n=self.backend.auto_size(s['preset']) if s['size']=='Auto' else int(s['size'])
            if n not in supported:raise RuntimeError('That neural processing size has not passed this GPU’s compatibility check.')
            s['actual_size']=n
        else:s['actual_size']=256
        return s
    def stop(self):
        with self.start_lock:
            self.active=False;self.hold=False;self.generation+=1;self.correction=None
            if self.capture:
                try:self.capture.call('stop',timeout=1)
                except Exception:
                    self.capture.kill();self.capture=None
    def fail_live(self,error,generation):
        with self.start_lock:
            if not self.active or generation!=self.generation:return
            self.stop()
        emit('error',{'message':str(error)})
    def launch(self,kind,work):
        if self.busy:raise RuntimeError('Another preparation is already running.')
        self.stop();self.busy=True;self.cancel.clear()
        def job():
            result=None;error=None;cancelled=False
            try:
                with self.operation_lock:result=work()
            except (BackendCancelled,VideoCancelled):cancelled=True
            except Exception as exc:
                if self.cancel.is_set():cancelled=True
                else:error=exc;traceback.print_exc(file=sys.stderr)
            finally:self.busy=False
            if self.closed:return
            if cancelled:emit('cancelled',{'message':'Cancelled. Original files are preserved.'})
            elif error:emit('error',{'message':str(error)})
            else:emit('complete',dict(kind=kind,**result))
        self.job_thread=threading.Thread(target=job,daemon=True,name='NeuralFlow preparation');self.job_thread.start()
    def progress(self,p):
        p=dict(p)
        if 'message' not in p:
            p['message']=p.get('phase','Preparing video')
            if 'frames' in p:p['message']+=f" · {p['frames']} frames"
        if p.get('total'):p['percent']=100*p.get('index',0)/p['total']
        emit('progress',p)
    def command(self,r):
        op=r['op']
        if op=='status':return self.status()
        if op=='exclude':
            self.controls.append(int(r['hwnd']))
            if self.capture:self.capture.call('exclude',hwnd=int(r['hwnd']))
        elif op in ('import_runtime','adapter'):
            if self.busy:raise RuntimeError('Finish or cancel the current job first.')
            self.stop()
            if op=='import_runtime':import_runtime(r['path'],self.data)
            with self.operation_lock:
                previous=self.backend
                self.backend=Backend(self.data,adapter_luid=r.get('luid'))
                previous.close()
            return self.status()
        elif op=='benchmark':self.launch('benchmark',lambda:self.backend.benchmark(self.progress,self.cancel))
        elif op=='install_media':self.launch('media',lambda:media_tools.install(self.data,self.cancel,self.progress))
        elif op=='complete_setup':
            if not self.backend.adapter:raise RuntimeError('Neural setup needs an NVIDIA GPU and its installed driver. Video tools can be installed separately.')
            if not self.backend.core:raise RuntimeError('The installed NVIDIA driver core is unavailable. Complete setup does not install or replace graphics drivers.')
            def setup():
                luid=self.backend.adapter['luid']
                runtime_setup.install(self.data,self.cancel,self.progress)
                runtime_setup.check(self.cancel)
                previous=self.backend;previous.close()
                self.backend=Backend(self.data,adapter_luid=luid)
                self.progress({'message':'Installing video tools…'})
                media_tools.install(self.data,self.cancel,self.progress)
                runtime_setup.check(self.cancel)
                if not self.backend.status()['supported_sizes']:
                    self.progress({'message':'Checking neural processing sizes on your GPU…'})
                    self.backend.benchmark(self.progress,self.cancel)
                if not self.backend.status()['supported_sizes']:
                    raise RuntimeError('Components installed, but neural evaluation did not pass on this GPU. See compatibility diagnostics.')
                return self.status()
            self.launch('setup',setup)
        elif op=='start':
            if self.busy:raise RuntimeError('Finish video preparation first.')
            if r['kind'] not in ('window','monitor'):raise ValueError('Choose an application window or a display.')
            settings=self.validated(r['settings'])
            with self.start_lock:
                self.stop();self.settings=settings;self.generation+=1
                try:self.native().call('start',target=int(r['target']),kind=r['kind']);self.capture.call('parameters',**self.parameters());self.active=True
                except Exception:self.stop();raise
        elif op=='stop':self.stop()
        elif op=='settings':
            old=self.settings;self.settings=self.validated(r['settings'])
            if old.get('actual_size')!=self.settings.get('actual_size'):self.generation+=1;self.correction=None
            if self.capture and self.active:self.capture.call('parameters',**self.parameters())
        elif op=='compare':
            self.hold=bool(r['hold'])
            if self.active:self.capture.call('parameters',**self.parameters())
        elif op=='cancel':self.cancel.set()
        elif op=='export':
            media_tools.configure(self.data)
            if not media_tools.status(self.data).get('available'):raise RuntimeError('Open System and Download video tools before rendering a video.')
            if float(r['strength'])>0 and 512 not in self.backend.status()['supported_sizes']:raise RuntimeError('Video rendering needs a successful 512-size hardware check.')
            def export():
                result=export_video(r['source'],r['destination'],r['strength'],r['stability'],self.backend,self.cancel,self.progress)
                import uuid
                cache=self.data/'playback';cache.mkdir(exist_ok=True)
                emit('progress',{'message':'Render saved. Preparing synchronized playback…'})
                original=prepare_playback(r['source'],cache/(uuid.uuid4().hex+'-original.mp4'),self.cancel,self.progress)
                if pathlib.Path(r['destination']).suffix.lower()=='.mp4':enhanced=str(pathlib.Path(r['destination']).resolve())
                else:enhanced=prepare_playback(r['destination'],cache/(uuid.uuid4().hex+'-enhanced.mp4'),self.cancel,self.progress)['path']
                return dict(result=result,original_playback=original['path'],enhanced_playback=enhanced)
            self.launch('export',export)
        elif op=='shutdown':self.closed=True;self.cancel.set();self.stop()
        else:raise ValueError('Unknown operation: '+op)
        return self.status() if op=='start' else {}
    def infer(self):
        while not self.closed:
            if not self.active or self.busy or self.settings.get('strength',0)<=0:time.sleep(.05);continue
            start=time.monotonic();generation=self.generation;s=self.settings
            try:
                sample=self.capture.grab(s['actual_size'])
                if sample:
                    source,serial=sample
                    with self.operation_lock:
                        if not self.active or self.busy or generation!=self.generation:continue
                        out,metrics=self.backend.render(source)
                    if self.active and generation==self.generation:self.correction=(start,source,out);self.neural_ms=metrics.get('gpu_ms',0);self.count+=1
            except Exception as error:
                self.fail_live('Neural processing stopped: '+str(error),generation)
            time.sleep(max(.01,1/max(1,s.get('refresh',3))-(time.monotonic()-start)))
    def live(self):
        temporal=Temporal();generation=-1;last_report=0;last_displayed=0
        while not self.closed:
            start=time.monotonic()
            if not self.active:time.sleep(.04);continue
            try:
                if generation!=self.generation:temporal=Temporal();generation=self.generation;last_displayed=0;last_report=start
                if self.settings.get('strength',0)>0:
                    sample=self.capture.grab(192)
                    if sample:
                        source,serial=sample;residual=temporal.step(source,self.correction,self.settings.get('stability',.75))
                        if self.active and generation==self.generation:self.capture.call('residual',size=192,rgb=base64.b64encode(residual.astype('<f4').tobytes()).decode(),reference=base64.b64encode(source.tobytes()).decode(),serial=serial)
                if start-last_report>1:
                    status=self.capture.call('status')
                    state=status.get('status',status)
                    shown=state.get('displayed_frames',0);fps=max(0,shown-last_displayed)/max(.001,start-last_report);last_displayed=shown;last_report=start
                    state['display_fps']=fps
                    if (state.get('emergency') or state.get('active') is False) and generation==self.generation:
                        self.active=False;self.generation+=1;self.correction=None
                    emit('stats',dict(active=self.active,message=f"{'Enhancing' if self.active else 'Effects OFF'} · {fps:.1f} displayed FPS · neural {self.neural_ms:.0f} ms · {self.settings.get('actual_size',256)} processing",capture=state))
            except Exception as error:
                self.fail_live('Live display stopped: '+str(error),generation)
            time.sleep(max(.001,1/30-(time.monotonic()-start)))
    def close(self):
        self.closed=True;self.cancel.set()
        try:self.stop()
        except Exception:pass
        self.backend.close()
        if self.capture:self.capture.close()
        if self.job_thread and self.job_thread is not threading.current_thread():self.job_thread.join(timeout=5)
        for thread in self.threads:
            if thread is not threading.current_thread():thread.join(timeout=1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',required=True);args=parser.parse_args();service=Service(args.data)
    try:
        for line in sys.stdin:
            request=None
            try:
                request=json.loads(line);result=service.command(request);reply(request.get('id'),result)
                if service.closed:break
            except Exception as error:reply(request.get('id') if isinstance(request,dict) else None,error=str(error))
    finally:service.close()
