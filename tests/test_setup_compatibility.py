"""Exercise setup failure handling with controlled backends, not physical GPU claims."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import service

class FakeBackend:
    def __init__(self, data, **kwargs):
        self.adapter={'luid':'test'} if mode!='no-nvidia' else None
        self.core={'path':'test'} if self.adapter else None
        self.cache={'complete':True,'supported_sizes':[]} if mode=='cached-failure' else None
    def status(self):
        return {'supported_sizes':(self.cache or {}).get('supported_sizes',[])}
    def benchmark(self,*args):
        calls.append('benchmark')
        self.cache={'complete':True,'supported_sizes':[128] if mode=='success' else []}
    def close(self): pass

for mode in ('failure','cached-failure','no-nvidia','success'):
    calls=[];events=[]
    with tempfile.TemporaryDirectory() as data, patch.object(service,'Backend',FakeBackend), \
         patch.object(service.media_tools,'configure',return_value={}), \
         patch.object(service.media_tools,'status',return_value={'available':True}), \
         patch.object(service.media_tools,'install',return_value={'available':True}), \
         patch.object(service.runtime_setup,'install',return_value={}), \
         patch.object(service,'emit',side_effect=lambda kind,state:events.append((kind,state))):
        app=service.Service(data)
        try:
            app.command({'op':'complete_setup'});app.job_thread.join(5)
            assert not app.job_thread.is_alive()
            completed=[s for k,s in events if k=='complete']
            assert len(completed)==1 and not any(k=='error' for k,s in events),events
            assert completed[0]['setup_mode']==('neural' if mode=='success' else 'non-neural')
            assert not app.active
            assert app.validated({'strength':0,'clarity':.25})['clarity']==.25
            if mode!='success':
                try: app.validated({'strength':.15})
                except RuntimeError: pass
                else: raise AssertionError('Unverified neural processing was enabled')
            if mode in ('cached-failure','no-nvidia'): assert not calls
        finally: app.close()
print('PASS: failed, cached failed, missing NVIDIA, successful setup; neural proof gate preserved')
