"""Service lifecycle and protocol tests with deterministic backend/capture doubles.

These exercise dispatch, cancellation and restoration, not neural image quality.
Use --native for an additional real packaged capture protocol startup/close smoke.
"""
import argparse
import base64
import json
from pathlib import Path
import queue
import threading
import time

import numpy as np
from PIL import Image
import service as module


def until(predicate, timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Timed out waiting for the expected service state.')


class Backend:
    def __init__(self,*args,**kwargs):self.closed=False;self.fail=False
    def status(self):return {'available':True,'supported_sizes':[128,256,512]}
    def auto_size(self,preset):return 256
    def render(self,image,cancel=None):
        if self.fail:raise RuntimeError('Injected worker crash')
        if self.closed:raise RuntimeError('Closed backend')
        return image.copy(),{'gpu_ms':5}
    def close(self):self.closed=True


class Capture:
    def __init__(self):self.active=False;self.calls=[];self.grabs=0;self.shown=0;self.dead=False
    def call(self,command,**kwargs):
        self.calls.append((command,kwargs))
        if self.dead:raise RuntimeError('Injected capture crash')
        if command=='start':self.active=True
        if command in ('stop','close'):self.active=False
        if command=='residual':self.shown+=1
        if command=='status':return {'ok':True,'active':self.active,'displayed_frames':self.shown,'average_fps':30}
        return {'ok':True}
    def grab(self,size):
        self.grabs+=1
        if self.grabs<4:return None
        if self.dead:raise RuntimeError('Injected capture crash')
        return Image.new('RGB',(size,size),(50,80,100)),self.grabs
    def kill(self):self.dead=True;self.active=False
    def close(self):self.kill()


class Sink:
    def write(self,text):pass
    def flush(self):pass


class Process:
    def __init__(self):self.stdin=Sink();self.dead=False
    def poll(self):return 1 if self.dead else None
    def kill(self):self.dead=True
    def wait(self,timeout=None):return 1


def test_capture_protocol():
    native=object.__new__(module.Capture)
    native.lock=threading.Lock();native.messages=queue.Queue();native.number=0;native.process=Process()
    native.messages.put({'ready':True,'protocol':1})
    native.messages.put({'id':1,'ok':False,'error':'No fresh captured frame'})
    assert native.grab(128) is None
    native.messages.put({'id':2,'ok':False,'error':'GPU readback busy; try the newest frame'})
    assert native.grab(128) is None
    image=Image.new('RGB',(128,128),'red')
    native.messages.put({'id':3,'ok':True,'rgb':base64.b64encode(image.tobytes()).decode(),'serial':9})
    read,serial=native.grab(128)
    assert read.tobytes()==image.tobytes() and serial==9
    started=time.monotonic()
    try:native.call('status',timeout=.1);raise AssertionError('Timeout was ignored')
    except TimeoutError:pass
    assert native.process.dead and time.monotonic()-started<.5


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',required=True);parser.add_argument('--native',action='store_true');args=parser.parse_args()
    output=Path(args.data);output.mkdir(parents=True,exist_ok=True)
    test_capture_protocol()
    actual_backend,actual_capture=module.Backend,module.Capture
    events=[]
    module.emit=lambda kind,data:events.append((kind,data))
    module.Backend, module.Capture=Backend,Capture
    service=module.Service(output/'service-double')
    settings={'strength':.15,'size':'Auto','stability':.75,'refresh':3}
    try:
        service.command({'op':'start','kind':'window','target':42,'settings':settings})
        until(lambda:service.count>0)
        assert service.active, 'Transient initial capture frames stopped the session.'
        until(lambda:any(kind=='stats' for kind,_ in events))
        stats=next(data for kind,data in reversed(events) if kind=='stats')
        assert stats['capture']['display_fps']>0, stats
        service.command({'op':'compare','hold':True})
        assert service.capture.calls[-1][1]['strength']==0
        service.command({'op':'compare','hold':False})
        assert service.capture.calls[-1][1]['strength']==.15
        generation=service.generation
        service.command({'op':'start','kind':'window','target':44,'settings':settings})
        service.fail_live('Old session error',generation)
        assert service.active, 'Old generation error stopped the new target.'
        service.backend.fail=True
        until(lambda:not service.active)
        assert any(kind=='error' and 'Injected worker crash' in data['message'] for kind,data in events)
        assert service.capture.calls[-1][0]=='stop'
        service.backend.fail=False
        service.command({'op':'start','kind':'window','target':44,'settings':settings})
        until(lambda:service.active)
        service.capture.dead=True
        service.command({'op':'stop'})
        assert not service.active and service.capture is None
        service.command({'op':'start','kind':'monitor','target':45,'settings':settings})
        assert service.active and service.capture is not None
        before=service.backend
        original_import=module.import_runtime
        def bad_import(*a):raise RuntimeError('Rejected import')
        module.import_runtime=bad_import
        try:service.command({'op':'import_runtime','path':'invalid'});raise AssertionError('Invalid import accepted')
        except RuntimeError:pass
        finally:module.import_runtime=original_import
        assert service.backend is before and not before.closed
        def cancelled_job():
            service.cancel.wait(timeout=2)
            raise module.BackendCancelled('cancelled')
        service.launch('test',cancelled_job)
        service.command({'op':'cancel'})
        until(lambda:not service.busy)
        until(lambda:any(kind=='cancelled' for kind,_ in events))
        try:service.validated(dict(settings,strength=float('nan')));raise AssertionError('NaN accepted')
        except ValueError:pass
        temporal=module.Temporal(32)
        source=Image.new('RGB',(32,32),'black');enhanced=Image.new('RGB',(32,32),(30,30,30))
        for _ in range(8):temporal.step(source,(time.monotonic(),source,enhanced),.75)
        assert float(np.max(temporal.history))>0
        after_cut=temporal.step(Image.new('RGB',(32,32),'white'),None,.75)
        assert not np.any(after_cut), 'Scene cut retained old enhancement.'
    finally:
        service.close();module.Backend,module.Capture=actual_backend,actual_capture
    assert all(not t.is_alive() for t in service.threads)
    checks={'transient_capture_retry':True,'capture_timeout_closes_overlay':True,'displayed_fps_protocol':True,
            'comparison_hold':True,'old_session_error_ignored':True,'worker_failure_restores_original':True,
            'capture_crash_recovery':True,'failed_import_preserves_backend':True,'job_cancellation':True,
            'reject_nonfinite_settings':True,'scene_cut_clears_history':True,'service_thread_cleanup':True}
    if args.native:
        capture=actual_capture()
        try:
            status=capture.call('status')
            assert status['ok'] and status['active'] is False and status['backend']=='Windows Graphics Capture / Direct3D 11'
            checks['actual_native_protocol']=True
        finally:capture.close()
    (output/'service-checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks),flush=True)


if __name__=='__main__':main()
