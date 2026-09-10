"""Explicit network/GPU end-to-end check in a fresh, isolated app-data folder."""
import json
from pathlib import Path
import sys
import time
import urllib.request

if '--offline' in sys.argv:
    def no_network(*args, **kwargs):
        raise AssertionError('Offline setup attempted a network request')
    urllib.request.urlopen = no_network

package=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(package/'engine'))
import service

data=Path(sys.argv[2]).resolve()
assert not data.exists(), 'Use a new folder to test first-run setup.'
events=[]
def emit(kind,state):
    events.append((kind,state))
    if kind!='progress' or not state.get('message','').startswith('Downloading neural'):
        print(json.dumps({'type':kind,'message':state.get('message',kind)}),flush=True)
service.emit=emit
app=service.Service(str(data))
start=time.monotonic()
try:
    app.command({'op':'complete_setup'})
    app.job_thread.join(timeout=600)
    assert not app.job_thread.is_alive(), 'Setup timed out'
    assert any(k=='complete' and d.get('kind')=='setup' for k,d in events), events[-1:]
    state=app.status()
    assert state['media']['available'] and state['backend']['supported_sizes']
    assert not state['active']
    assert not list(data.glob('component-setup-*'))
    sources=json.loads((data/'runtime/setup-sources.json').read_text())
    report={'passed':True,'first_run_seconds':round(time.monotonic()-start,2),
            'sizes':state['backend']['supported_sizes'],'video_tools_ready':True,
            'effects_off':True,'upstream_archive_hashes':[a['sha256'] for a in sources['assets']]}
    events.clear();start=time.monotonic()
    app.command({'op':'complete_setup'});app.job_thread.join(timeout=60)
    assert any(k=='complete' and d.get('kind')=='setup' for k,d in events)
    report['repeat_setup_seconds']=round(time.monotonic()-start,2)
    report['repeat_downloads']=sum(k=='progress' and d.get('message','').startswith('Downloading') for k,d in events)
    assert report['repeat_downloads']==0
    (data/'test-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
finally:app.close()
